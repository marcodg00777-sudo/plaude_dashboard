import os
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    raise RuntimeError("Este script requiere Python 3.11+ para usar tomllib.")


def _load_secrets(path: str = "secrets.toml") -> dict:
    secrets_path = Path(path)
    if not secrets_path.exists():
        return {}

    with open(secrets_path, "rb") as f:
        return tomllib.load(f)


def get_gemini_api_key() -> str:
    """Obtiene la API key de Gemini desde env o secrets.toml"""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        return api_key

    data = _load_secrets()
    api_key = data.get("gemini", {}).get("api_key", "").strip()

    if not api_key:
        raise ValueError("No se encontró GEMINI_API_KEY en env ni [gemini].api_key en secrets.toml")

    return api_key
