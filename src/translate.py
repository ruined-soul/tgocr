# /src/translate.py
import os
from google import genai
from google.genai.errors import APIError

# --- Configuration ---
MODEL_NAME = "gemini-2.5-flash"
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("❌ GEMINI_API_KEY environment variable is missing.")

# Initialize Gemini client
client = genai.Client(api_key=API_KEY)

# --- Style guide for translation ---
STYLE_GUIDE = """
YOU ARE MY MANGA/MANHWA DIALOGUE TRANSLATION ASSISTANT.
YOUR JOB IS TO TRANSLATE ENGLISH DIALOGUES INTO CASUAL HINGLISH (MIX OF HINDI + ENGLISH).

RULES:
1. Translate all lines accurately, naturally, and emotionally.
2. Output ONLY the translated Hinglish dialogues (no explanations).
3. Maintain tone and casing from the original.
4. Avoid unnatural commas or punctuation.
5. Don't translate names, powers, or places.
6. Keep translations concise and natural.

EXAMPLES:
"YO, FREE-LOADER." → "OYE, MUFTKHOR."
"AS SULKY AS EVER, I SEE." → "HAMESHA KI TARAH MUH FULA RAKHHA HAI, BADHIYA HAI."
"""

# --- Translation function ---
def translate_to_hinglish(english_text: str) -> str:
    """Translate English text to Hinglish using Gemini."""
    prompt = f"{STYLE_GUIDE}\n\n--- DIALOGUES TO TRANSLATE ---\n{english_text}"

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[prompt],
            config={"system_instruction": STYLE_GUIDE}
        )
        return response.text.strip()
    except APIError as e:
        return f"⚠️ API Error: {e}"
    except Exception as e:
        return f"⚠️ Unexpected Error: {e}"
