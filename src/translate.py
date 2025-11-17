# src/translate.py
import os
import time
from google import genai
from google.genai.errors import APIError
from .users import get_active_key

DEFAULT_MODEL_NAME = "gemini-1.5-flash"
DEFAULT_STYLE_GUIDE = """
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
