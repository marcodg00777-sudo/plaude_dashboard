from pathlib import Path
import sys

try:
    import tomllib
except ModuleNotFoundError:
    print("Este script requiere Python 3.11+ para usar tomllib.")
    sys.exit(1)

try:
    from google import genai
except ModuleNotFoundError:
    print("El módulo google.genai no está instalado. Ejecuta: pip install google-genai")
    sys.exit(1)

SECRETS_FILE = "secrets.toml"
MODEL_NAME = "gemini-3.1-flash-lite-preview"


def load_gemini_api_key(path: str = SECRETS_FILE) -> str:
    secrets_path = Path(path)
    if not secrets_path.exists():
        raise FileNotFoundError(f"No existe {path}")

    with open(secrets_path, "rb") as f:
        data = tomllib.load(f)

    api_key = data.get("gemini", {}).get("api_key", "").strip()
    if not api_key:
        raise ValueError("Falta [gemini].api_key en secrets.toml")

    return api_key


def main():
    try:
        api_key = load_gemini_api_key()
        client = genai.Client(api_key=api_key)

        prompt = """
Responde SOLO con una frase corta.
Confirma que la conexion a Gemini funciona correctamente.
"""

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )

        print("=" * 80)
        print("MODELO:", MODEL_NAME)
        print("=" * 80)
        print(response.text)

    except Exception as e:
        print(f"Error probando Gemini: {e}")


if __name__ == "__main__":
    main()