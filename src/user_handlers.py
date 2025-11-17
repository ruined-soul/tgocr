# src/user_handlers.py
import logging
from uuid import uuid4
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from .users import user_settings, get_active_key, add_user_key, set_active_key, delete_user_key, _save

logger = logging.getLogger(__name__)


async def api_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main /api menu with keys as buttons"""
    chat_id = update.effective_chat.id
    keys = user_settings.get(chat_id, {}).get("keys", {})
    active_name = user_settings.get(chat_id, {}).get("active")

    # Build key buttons
    key_buttons = []
    for name, key in keys.items():
        status = " (active)" if name == active_name else ""
        key_buttons.append([
            InlineKeyboardButton(f"{name}{status}", callback_data=f"keyinfo|{name}")
        ])

    # Bottom buttons
    bottom_buttons = [
        [InlineKeyboardButton("Add Key", callback_data="add_key")],
        [InlineKeyboardButton("Refresh", callback_data="refresh")]
    ]

    keyboard = key_buttons + bottom_buttons

    text = (
        "*Gemini API Keys*\n\n"
        "You need a key to translate!\n"
        "Get free: https://aistudio.google.com/app/apikey\n\n"
        "_Only one key can be active at a time_\n"
        "_Tap a key to manage_"
    )

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button presses except keyinfo"""
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id

    if data == "add_key":
        key_id = f"key_{str(uuid4())[:8]}"
        context.user_data["pending_key_id"] = key_id
        await query.edit_message_text(
            f"*Add New Key*\n\n"
            f"Send your Gemini API key.\n"
            f"It will be saved as: `{key_id}`\n\n"
            "_Tip: Paste directly_",
            parse_mode="Markdown"
        )
        return

    elif data == "refresh":
        fake_update = Update(update_id=update.update_id, message=query.message)
        return await api_menu(fake_update, context)

    elif data.startswith("set|"):
        name = data.split("|", 1)[1]
        if set_active_key(chat_id, name):
            # Auto-refresh to show new active key
            fake_update = Update(update_id=update.update_id, message=query.message)
            return await api_menu(fake_update, context)
        else:
            await query.edit_message_text("Key not found.")
        return

    elif data.startswith("del|"):
        name = data.split("|", 1)[1]
        if delete_user_key(chat_id, name):
            fake_update = Update(update_id=update.update_id, message=query.message)
            return await api_menu(fake_update, context)
        else:
            await query.edit_message_text("Key not found.")
        return

    elif data.startswith("rename|"):
        old_name = data.split("|", 1)[1]
        context.user_data["rename_key"] = old_name
        await query.edit_message_text(
            f"*Rename Key*\n\n"
            f"Current: `{old_name}`\n\n"
            f"Send new name:",
            parse_mode="Markdown"
        )
        return

    elif data == "back":
        fake_update = Update(update_id=update.update_id, message=query.message)
        return await api_menu(fake_update, context)


async def receive_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save new key after Add Key"""
    key = update.message.text.strip()
    key_id = context.user_data.get("pending_key_id")

    if not key_id or not key:
        await update.message.reply_text("Invalid key or expired. Use /api → Add Key.")
        context.user_data.pop("pending_key_id", None)
        return

    add_user_key(update.effective_chat.id, key_id, key)
    context.user_data.pop("pending_key_id", None)
    await update.message.reply_text(f"Key saved as `{key_id}`\nUse /api to manage.")

    keyboard = [[InlineKeyboardButton("Open /api", callback_data="refresh")]]
    await update.message.reply_text("Done!", reply_markup=InlineKeyboardMarkup(keyboard))


async def receive_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle rename input"""
    new_name = update.message.text.strip()
    old_name = context.user_data.get("rename_key")

    if not old_name or not new_name:
        await update.message.reply_text("Invalid name. Try again.")
        context.user_data.pop("rename_key", None)
        return

    chat_id = update.effective_chat.id
    keys = user_settings.get(chat_id, {}).get("keys", {})

    if new_name in keys:
        await update.message.reply_text("Name already exists. Choose another.")
        return

    if old_name not in keys:
        await update.message.reply_text("Key not found.")
        context.user_data.pop("rename_key", None)
        return

    # Rename
    keys[new_name] = keys.pop(old_name)
    if user_settings[chat_id]["active"] == old_name:
        user_settings[chat_id]["active"] = new_name
    _save()

    context.user_data.pop("rename_key", None)
    await update.message.reply_text(f"Renamed `{old_name}` → `{new_name}`")

    keyboard = [[InlineKeyboardButton("Open /api", callback_data="refresh")]]
    await update.message.reply_text("Done!", reply_markup=InlineKeyboardMarkup(keyboard))


async def show_key_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show actions for a specific key"""
    query = update.callback_query
    await query.answer()
    name = query.data.split("|", 1)[1]
    key = user_settings.get(update.effective_chat.id, {}).get("keys", {}).get(name)
    active_name = user_settings.get(update.effective_chat.id, {}).get("active")

    if not key:
        await query.edit_message_text("Key not found.")
        return

    keyboard = [
        [InlineKeyboardButton("Set Active", callback_data=f"set|{name}")],
        [InlineKeyboardButton("Rename", callback_data=f"rename|{name}")],
        [InlineKeyboardButton("Delete", callback_data=f"del|{name}")],
        [InlineKeyboardButton("Back", callback_data="back")]
    ]

    status = "Active" if name == active_name else "Inactive"

    await query.edit_message_text(
        f"*Key: `{name}`*\n\n"
        f"Status: *{status}*\n\n"
        f"Choose action:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


def get_api_handlers():
    """Return all /api handlers"""
    return [
        CommandHandler("api", api_menu),
        CallbackQueryHandler(button_handler, pattern=r"^(add_key|refresh|back)$"),
        CallbackQueryHandler(show_key_actions, pattern=r"^keyinfo\|"),
        CallbackQueryHandler(button_handler, pattern=r"^(set\|.*|del\|.*|rename\|.*)$"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, receive_key),
        MessageHandler(filters.TEXT & ~filters.COMMAND, receive_rename),
    ]
