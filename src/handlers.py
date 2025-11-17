# src/handlers.py
import os
import tempfile
import asyncio
import shutil
import sys
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from .ocr import process_archive, process_single_image
from .translate import translate_to_hinglish, fetch_available_models, DEFAULT_STYLE_GUIDE
from .users import get_active_key

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[handler])

active_jobs = {}
user_settings = {}
DEFAULT_MODEL = "gemini-2.5-flash"
WAITING_FOR_STYLE = 0


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /model – Show rich inline keyboard with all Gemini models + descriptions
    """
    chat_id = update.effective_chat.id
    current = user_settings.get(chat_id, {}).get("gemini_model", DEFAULT_MODEL)

    # Step 1: Show loading
    loading_msg = await update.message.reply_text(
        "Fetching latest Gemini models from Google...\n\n"
        f"Your current model: *{current}*",
        parse_mode="Markdown"
    )
    context.user_data["model_menu_msg_id"] = loading_msg.message_id

    # Step 2: Get models (cached for 5 min)
    models = fetch_available_models(chat_id)
    if not models:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=loading_msg.message_id,
            text="Could not fetch models right now. Please try again in a minute.",
            parse_mode="Markdown"
        )
        return

    # Step 3: Build beautiful buttons
    keyboard = []
    for model, desc in models.items():
        is_current = model == current
        prefix = "Current" if is_current else "Select"
        model_short = model.split("-")[-1].upper().replace("GEMINI", "")

        # Extract short hint
        hint = desc.split("|")[0].strip()
        if len(hint) > 25:
            hint = hint[:22] + "..."

        button_text = f"{prefix}: {model_short}"
        if hint and not is_current:
            button_text += f" | {hint}"

        # Enforce 64-char limit
        if len(button_text) > 64:
            button_text = f"{prefix}: {model_short}"

        btn = InlineKeyboardButton(button_text, callback_data=f"model|{model}")
        keyboard.append([btn])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Step 4: Final menu
    menu_text = (
        "*Gemini Model Selector*\n\n"
        f"Current model: **{current}**\n\n"
        "Tap any button to **switch instantly**:\n"
        "• *Flash* – Fast & lightweight\n"
        "• *Pro* – More accurate, handles complex text\n\n"
        "_You can change anytime with /model_"
    )

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=loading_msg.message_id,
        text=menu_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle model selection button press
    """
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("model|"):
        return

    _, new_model = query.data.split("|", 1)
    chat_id = query.message.chat_id

    # Save selection
    user_settings.setdefault(chat_id, {})["gemini_model"] = new_model

    # Refresh model list
    models = fetch_available_models(chat_id)
    full_desc = models.get(new_model, "Text model")

    # Rebuild keyboard with new current
    keyboard = []
    for m, m_desc in models.items():
        is_current = m == new_model
        prefix = "Current" if is_current else "Select"
        model_short = m.split("-")[-1].upper().replace("GEMINI", "")

        hint = m_desc.split("|")[0].strip()
        if len(hint) > 25:
            hint = hint[:22] + "..."

        button_text = f"{prefix}: {model_short}"
        if hint and not is_current:
            button_text += f" | {hint}"

        if len(button_text) > 64:
            button_text = f"{prefix}: {model_short}"

        btn = InlineKeyboardButton(button_text, callback_data=f"model|{m}")
        keyboard.append([btn])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Confirmation message
    confirm_text = (
        "*Model Updated!*\n\n"
        f"Now using: **{new_model}**\n"
        f"_{full_desc}_\n\n"
        "All OCR → Hinglish translations will use this model.\n"
        "Change anytime with **/model**"
    )

    await query.edit_message_text(
        confirm_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def style_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current = user_settings.get(chat_id, {}).get("style_guide", DEFAULT_STYLE_GUIDE)
    preview = (current[:250] + "\n...") if len(current) > 250 else current
    await update.message.reply_text(
        "*Your Current Style Guide:*\n\n"
        f"```{preview}```\n\n"
        "Send a *new prompt* to customize Hinglish style.\n"
        "Or type `/style default` to reset.\n\n"
        "_Example:_ `Make it fun and Gen-Z style`",
        parse_mode="Markdown"
    )
    return WAITING_FOR_STYLE


async def receive_style_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    new_guide = update.message.text.strip()

    if new_guide.lower() == "/style default":
        user_settings.setdefault(chat_id, {}).pop("style_guide", None)
        await update.message.reply_text(
            "Style guide reset to *default manga/manhwa tone*.\n"
            "Your translations are now natural and emotional.",
            parse_mode="Markdown"
        )
    else:
        user_settings.setdefault(chat_id, {})["style_guide"] = new_guide
        example = "I'm so done with this."
        translated = translate_to_hinglish(example, chat_id=chat_id)
        await update.message.reply_text(
            "*Style Saved!*\n\n"
            f"EN: `{example}`\n"
            f"HI: `{translated}`\n\n"
            "All future translations will follow this vibe!",
            parse_mode="Markdown"
        )
    return ConversationHandler.END


async def cancel_style(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Style change cancelled.")
    return ConversationHandler.END


async def set_ocr_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        current = user_settings.get(chat_id, {}).get("ocr_mode", "local")
        await update.message.reply_text(
            f"Current OCR mode: *{current.upper()}*\n\n"
            "• `local` – Uses Tesseract (free, fast, offline)\n"
            "• `online` – Uses OCRWebService (more accurate)\n\n"
            "Change with: `/ocrmode local` or `/ocrmode online`",
            parse_mode="Markdown"
        )
        return

    mode = context.args[0].lower()
    if mode not in ("local", "online"):
        await update.message.reply_text("Please use `local` or `online`.", parse_mode="Markdown")
        return

    user_settings.setdefault(chat_id, {})["ocr_mode"] = mode
    await update.message.reply_text(
        f"OCR mode set to *{mode.upper()}*\n\n"
        f"{'Tesseract (local)' if mode == 'local' else 'OCRWebService (online)'} "
        f"will now extract text from images.",
        parse_mode="Markdown"
    )


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return await update.message.reply_text("Please send a file (zip, image, or .txt).")

    name = doc.file_name.lower()
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, name)
    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(file_path)
    chat_id = update.effective_chat.id
    ocr_mode = user_settings.get(chat_id, {}).get("ocr_mode", "local")

    if name.endswith((".zip", ".7z", ".cbz")):
        active_jobs[chat_id] = {"cancel": False}
        await update.message.reply_text(
            f"Received *{doc.file_name}*\n"
            f"Extracting images and running *{ocr_mode.upper()} OCR*...\n\n"
            "You’ll get results page by page.",
            parse_mode="Markdown"
        )
        asyncio.create_task(worker(update, context, file_path, temp_dir, chat_id))
        return

    if name.endswith(".txt"):
        await update.message.reply_text("Reading your .txt file...")
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if len(content) > 15000:
                await update.message.reply_text("File too large (>15 KB). Max 15,000 chars.")
            elif not content.strip():
                await update.message.reply_text("File is empty or contains no readable text.")
            else:
                await translate_txt_content(update, context, content, name)
        except Exception as e:
            await update.message.reply_text(f"Error reading file: {e}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return

    await update.message.reply_text(
        "Unsupported file.\n\n"
        "Send:\n"
        "• `.zip`, `.cbz`, `.7z` (image archives)\n"
        "• Images (JPG, PNG, etc.)\n"
        "• `.txt` files for direct translation",
        parse_mode="Markdown"
    )
    shutil.rmtree(temp_dir, ignore_errors=True)


async def translate_txt_content(update: Update, context: ContextTypes.DEFAULT_TYPE, content: str, file_name: str):
    chat_id = update.effective_chat.id
    model = user_settings.get(chat_id, {}).get("gemini_model", DEFAULT_MODEL)
    style = user_settings.get(chat_id, {}).get("style_guide", DEFAULT_STYLE_GUIDE)

    await update.message.reply_text("Translating your text to Hinglish...")
    try:
        translated = translate_to_hinglish(content, model_name=model, style_guide=style, chat_id=chat_id)
        result_name = os.path.splitext(file_name)[0] + "_hinglish.txt"
        result_path = os.path.join(tempfile.gettempdir(), result_name)
        with open(result_path, "w", encoding="utf-8") as f:
            f.write(translated)
        await update.message.reply_document(
            document=open(result_path, "rb"),
            filename=result_name,
            caption=f"Hinglish Translation (`{model}`)\nStyle: {'Custom' if style != DEFAULT_STYLE_GUIDE else 'Default'}"
        )
        os.remove(result_path)
    except Exception as e:
        await update.message.reply_text(f"Translation failed: {e}")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in active_jobs:
        active_jobs[chat_id]["cancel"] = True
        await update.message.reply_text("OCR task cancelled. You can send a new file.")
    else:
        await update.message.reply_text("No active OCR task to cancel.")


async def worker(update, context, file_path, temp_dir, chat_id):
    try:
        await process_archive(update, context, file_path, temp_dir, active_jobs, user_settings)
    except Exception as e:
        await update.message.reply_text(f"OCR failed: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        active_jobs.pop(chat_id, None)


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        return await update.message.reply_text("Please send an image.")

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    temp_dir = tempfile.mkdtemp()
    image_path = os.path.join(temp_dir, "image.jpg")
    await file.download_to_drive(image_path)
    chat_id = update.effective_chat.id
    active_jobs[chat_id] = {"cancel": False}

    ocr_mode = user_settings.get(chat_id, {}).get("ocr_mode", "local")
    await update.message.reply_text(
        f"Running *{ocr_mode.upper()} OCR* on your image...\n"
        "Please wait...",
        parse_mode="Markdown"
    )
    asyncio.create_task(image_worker(update, context, image_path, temp_dir, chat_id))


async def image_worker(update, context, image_path, temp_dir, chat_id):
    try:
        await process_single_image(update, context, image_path, active_jobs, user_settings)
    except Exception as e:
        await update.message.reply_text(f"OCR error: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        active_jobs.pop(chat_id, None)


async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args) if context.args else None
    if not text and update.message.reply_to_message:
        text = update.message.reply_to_message.text or update.message.reply_to_message.caption

    if not text:
        await update.message.reply_text(
            "How to use `/translate`:\n\n"
            "1. Reply to a message + type `/translate`\n"
            "2. Or: `/translate your text here`\n\n"
            "_Translates English → Casual Hinglish_",
            parse_mode="Markdown"
        )
        return

    chat_id = update.effective_chat.id
    model = user_settings.get(chat_id, {}).get("gemini_model", DEFAULT_MODEL)
    style = user_settings.get(chat_id, {}).get("style_guide", DEFAULT_STYLE_GUIDE)

    await update.message.reply_text("Translating to Hinglish...")
    try:
        translated = translate_to_hinglish(text, model_name=model, style_guide=style, chat_id=chat_id)
        await update.message.reply_text(
            f"*Hinglish* (`{model}`):\n\n"
            f"{translated}\n\n"
            "_Powered by Google Gemini_",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"Translation error: {e}")
