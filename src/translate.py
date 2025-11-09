# /src/translate.py
import os
from google import genai
from google.genai.errors import APIError

# --- Configuration ---
MODEL_NAME = "gemini-2.5-flash"

# You can set this key in Koyeb’s environment variables for security
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("❌ GEMINI_API_KEY environment variable is missing.")

# --- Initialize client ---
client = genai.Client(api_key=API_KEY)

# --- Translation Style Guide ---
STYLE_GUIDE = """
YOU ARE MY MANGA/MANHWA DIALOGUE TRANSLATION ASSISTANT.
YOUR JOB IS TO TRANSLATE ENGLISH DIALOGUES INTO CASUAL HINGLISH (MIX OF HINDI + ENGLISH) IN THE STYLE BELOW.

RULES:
1. Translate all lines accurately, in order, and with full emotion.
2. Output only the translated Hinglish dialogues — no explanations.
3. Keep emotion and tone same as original (funny, angry, sad, etc.).
4. Maintain casing (UPPERCASE → uppercase).
5. Avoid unnatural commas or punctuation.
6. Don’t translate names, powers, or unique terms.
7. Keep translations short, emotional, natural, and flowy.

EXAMPLES:
"YO, FREE-LOADER." → "OYE, MUFTKHOR."
"AS SULKY AS EVER, I SEE." → "HAMESHA KI TARAH MUH FULA RAKHHA HAI, BADHIYA HAI."
"""

# --- Translation Function ---
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
