import os

def safe_listdir(path):
    try:
        return os.listdir(path)
    except Exception:
        return []
