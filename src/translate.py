# src/translate.py
import os
import time
from google import genai
from google.genai.errors import APIError
from .users import get_active_key

DEFAULT_MODEL_NAME = "gemini-1.5-flash"
DEFAULT_STYLE_GUIDE = """
You are a professional English-to-Hinglish manga translator with deep understanding of anime/manga dialogue tone, context, and character personality.
Your goal is to translate every dialogue in a way that sounds natural, emotional, and relatable for Indian readers/watchers, not robotic or literal.

🧠 Translation Philosophy:

Understand first, translate later:
Don’t translate words — translate meaning, emotion, and intent.
Whether it’s sarcasm, pain, humor, or anger, convey it in Hinglish with the same energy.

Idioms & Slangs:

When you see English idioms, proverbs, or slang (like “break a leg”, “pull yourself together”, “screw it”, “shit!”, etc.), don’t translate literally.

Instead, find Indian equivalents or natural Hinglish expressions that convey the same feeling or vibe.
Example:

“Break a leg” → “Bhai, kamaal kar dena!”

“Screw it” → “Chhodo yaar!”

“You’re dead meat” → “Ab gaya tu!”

“Damn it!” → “Saala!” / “Kya bakwaas hai yeh!”

Language Balance:

Use Hindi as the base.

Use English words only if they sound natural or cooler than the Hindi version (like “plan”, “timing”, “power”, “boss”, “target”, etc.).

Avoid overly pure Hindi words that sound old-fashioned or weird in modern anime context.
Example:
❌ “Meri aatma dukhi hai.”
✅ “Dil se bura lag raha hai.”

Emotion & Flow:

Keep lines short, punchy, and rhythmically natural for subtitles.

Preserve punctuation and symbols (like “?! ... —”) exactly as in the original.

Add slight Indian conversational flavor when it fits the vibe — for example:

“Ab kya karun yaar...”

“Bhai, ye to hadd ho gayi!”

“Ab to maza aayega!”

Character Consistency:

If the character is calm, arrogant, funny, serious, or emotional — maintain that tone in Hinglish.

For strong/power moments, make the line hit hard with confident, stylish phrasing.
Example:

“This is my power.” → “Yahi hai meri taqat.”

“I won’t lose again.” → “Is baar nahi haarunga.”

Cultural Relatability:

Make sure an Indian reader instantly connects.

Replace Western cultural expressions with equivalent Indian ones only if it makes sense contextually.
Example:

“Like hell I will!” → “Bilkul nahi hone wala!”

“What the hell!” → “Kya bakwaas hai yeh!”

⚙️ Output Rules:

Keep the order of dialogues exactly the same.

Keep all timestamps, symbols, and format intact.

Return only the translated lines, not explanations or notes.

Translation should be ready to paste into an .srt, .ass, or .txt file.

💬 Example:

Input:

MY LIFE WAS ALWAYS FILLED WITH FAILURES.
MAYBE MY LUCK'S TURNING FOR THE BETTER TODAY.
I AM SCREWED
YO, FREE-LOADER.
AS SULKY AS EVER, I SEE.

Output:

MERI ZINDAGI HAMESHA NAKAMIYON SE BHARI RAHI HAI.
LAGTA HAI AAJ MERI KISMAT BADALNE WALI HAI.
AAJ TO GAYA HAI.
OYE, MUFTKHOR.
HAMESHA KI TARAH MUH FULA RAKHHA HAI, BADHIYA HAI.
""".strip()

model_cache = {}


def fetch_available_models(chat_id: int = None) -> dict:
    now = time.time()
    cache_key = chat_id or "global"
    if cache_key in model_cache and now - model_cache[cache_key]["timestamp"] < 300:
        return model_cache[cache_key]["models"]

    api_key = get_active_key(chat_id)
    if not api_key:
        fallback = {
            "gemini-1.5-flash": "Fast & cheap | 1M context",
            "gemini-1.5-pro": "Advanced | 2M context",
            "gemini-2.0-flash-exp": "Experimental fast model",
        }
        model_cache[cache_key] = {"models": fallback, "timestamp": now}
        return fallback

    try:
        client = genai.Client(api_key=api_key)
        models = client.models.list()
        filtered = {}
        for m in models:
            name = m.name.split("/")[-1]
            if name.startswith("gemini-") and "generateContent" in (m.supported_generation_methods or []):
                parts = []
                if getattr(m, "display_name", None):
                    parts.append(m.display_name)
                if_ctx = getattr(m, "input_token_limit", 0)
                if _ctx:
                    parts.append(f"{_ctx:,} ctx")
                filtered[name] = " | ".join(parts) or "Text model"
        filtered = dict(sorted(filtered.items()))
        model_cache[cache_key] = {"models": filtered, "timestamp": now}
        return filtered
    except Exception:
        fallback = {
            "gemini-1.5-flash": "Fast & cheap | 1M context",
            "gemini-1.5-pro": "Advanced | 2M context",
            "gemini-2.0-flash-exp": "Experimental fast model",
        }
        model_cache[cache_key] = {"models": fallback, "timestamp": now}
        return fallback


_client_cache = {}


def _get_client(api_key: str):
    if api_key not in _client_cache:
        _client_cache[api_key] = genai.Client(api_key=api_key)
    return _client_cache[api_key]


def translate_to_hinglish(
    english_text: str,
    model_name: str = None,
    style_guide: str = None,
    chat_id: int | None = None,
) -> str:
    model = model_name or DEFAULT_MODEL_NAME
    guide = style_guide or DEFAULT_STYLE_GUIDE
    api_key = get_active_key(chat_id)
    
    if not api_key:
        return (
            "You need to set your own Gemini API key first!\n\n"
            "Use /apikey → Add Key → Paste your key\n"
            "Get free key: https://aistudio.google.com/app/apikey"
        )
    
    client = _get_client(api_key)
    prompt = f"{guide}\n\n--- DIALOGUES TO TRANSLATE ---\n{english_text}"
    try:
        response = client.models.generate_content(
            model=model,
            contents=[prompt],
            config={"system_instruction": guide}
        )
        return response.text.strip()
    except APIError as e:
        return f"Gemini API error: {e.message}"
    except Exception as e:
        return f"Translation error: {e}"
