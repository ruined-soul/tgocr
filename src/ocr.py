import os
import zipfile
import py7zr
import html
from PIL import Image, ImageOps, ImageEnhance, UnidentifiedImageError
import pytesseract


async def process_archive(update, context, archive_path, temp_dir):
    extract_dir = os.path.join(temp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)

    print(f"📂 Extracting archive: {archive_path}")

    # --- Extract the archive ---
    try:
        if archive_path.endswith((".zip", ".cbz")):
            with zipfile.ZipFile(archive_path, "r") as z:
                z.extractall(extract_dir)
        elif archive_path.endswith(".7z"):
            with py7zr.SevenZipFile(archive_path, "r") as z:
                z.extractall(path=extract_dir)
        else:
            await update.message.reply_text("⚠️ Unsupported file format.")
            return
    except Exception as e:
        await update.message.reply_text(f"❌ Extraction error: {e}")
        print(f"❌ Extraction error: {e}")
        return

    # --- Collect all images recursively ---
    all_files = []
    for root, _, files in os.walk(extract_dir):
        for f in files:
            all_files.append(os.path.join(root, f))

    image_files = [
        f for f in all_files
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"))
    ]

    if not image_files:
        await update.message.reply_text("⚠️ No images found inside the archive.")
        print("⚠️ No images found.")
        return

    await update.message.reply_text(f"🔍 Found {len(image_files)} image(s) — starting OCR...")

    all_text = ""

    for idx, img_path in enumerate(sorted(image_files), start=1):
        filename = os.path.basename(img_path)
        try:
            img = Image.open(img_path).convert("L")
            img = ImageOps.autocontrast(img)
            img = ImageOps.invert(img)
            img = ImageEnhance.Contrast(img).enhance(3.0)
            img = img.point(lambda x: 0 if x < 140 else 255, '1')

            text = pytesseract.image_to_string(
                img,
                lang="eng",
                config="--psm 6 --oem 3"
            )

            text = text.strip()
            text_safe = html.escape(text) if text else "(No text detected)"
            all_text += f"\n\n--- {filename} ---\n{text_safe}"

            await update.message.reply_text(
                f"📄 {filename} ({idx}/{len(image_files)}):\n\n{text_safe[:3900]}",
                parse_mode=None
            )

        except UnidentifiedImageError:
            print(f"⚠️ Skipping invalid image: {img_path}")
        except Exception as e:
            print(f"⚠️ OCR error for {img_path}: {e}")
            await update.message.reply_text(f"⚠️ Error reading {filename}: {e}")

    # --- Send combined text file ---
    if all_text.strip():
        out_path = os.path.join(temp_dir, "OCR_Result.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(all_text)
        await update.message.reply_document(
            document=open(out_path, "rb"),
            filename="OCR_Result.txt",
            caption="✅ OCR complete — full text extracted."
        )
    else:
        await update.message.reply_text("⚠️ OCR complete, but no readable text was detected.")
