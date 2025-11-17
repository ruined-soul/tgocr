# src/users.py
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DATA_FILE = Path("/app/data/user_apikeys_v2.json")
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

_user_data: Dict[int, Dict] = {}


def _load() -> None:
    global _user_data
    if DATA_FILE.is_file():
        try:
            raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            _user_data = {int(cid): val for cid, val in raw.items()}
            logging.info(f"Loaded multi-key data for {len(_user_data)} users.")
        except Exception as e:
            logging.error(f"Failed to load user_apikeys_v2.json: {e}")


def _save() -> None:
    try:
        DATA_FILE.write_text(json.dumps(_user_data, indent=2), encoding="utf-8")
    except Exception as e:
        logging.error(f"Failed to save user_apikeys_v2.json: {e}")


def _ensure_user(chat_id: int) -> Dict:
    return _user_data.setdefault(chat_id, {"keys": {}, "active": None})


def get_user_keys(chat_id: int) -> Dict[str, str]:
    return _ensure_user(chat_id)["keys"].copy()


def get_active_key(chat_id: int) -> Optional[str]:
    ud = _ensure_user(chat_id)
    name = ud.get("active")
    return ud["keys"].get(name) if name else None


def set_active_key(chat_id: int, name: str) -> bool:
    ud = _ensure_user(chat_id)
    if name in ud["keys"]:
        ud["active"] = name
        _save()
        return True
    return False


def add_user_key(chat_id: int, name: str, api_key: str) -> None:
    api_key = api_key.strip()
    if not api_key:
        raise ValueError("API key cannot be empty.")
    ud = _ensure_user(chat_id)
    ud["keys"][name] = api_key
    if ud["active"] is None:
        ud["active"] = name  # ← THIS WAS MISSING =
    _save()


def delete_user_key(chat_id: int, name: str) -> bool:
    ud = _ensure_user(chat_id)
    existed = name in ud["keys"]
    if existed:
        ud["keys"].pop(name, None)
        if ud["active"] == name:
            ud["active"] = next(iter(ud["keys"]), None)
        _save()
    return existed


def list_user_keys(chat_id: int) -> List[Tuple[str, bool]]:
    ud = _ensure_user(chat_id)
    active = ud.get("active")
    return [(n, n == active) for n in ud["keys"]]


# Expose for compatibility
user_settings = _user_data

_load()
