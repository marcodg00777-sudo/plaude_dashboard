import json
import re
import time
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError

try:
    from google import genai
    from google.genai import types
except ModuleNotFoundError:
    genai = None
    types = None

from services.config import get_gemini_api_key

MODEL_NAME = "gemini-3.1-flash-lite-preview"

_MAX_RETRIES = 3
_RETRY_DELAYS = [5, 10, 20]  # segundos entre reintentos


class GeminiQuotaError(RuntimeError):
    """Se lanza cuando Gemini agota el cupo despues de todos los reintentos."""


class TaskItem(BaseModel):
    task: str
    assignee: Optional[str] = None
    done: Optional[bool] = None


class GeminiAnalysis(BaseModel):
    summary: str
    points: List[str] = Field(default_factory=list)
    people: List[str] = Field(default_factory=list)
    tasks: List[TaskItem] = Field(default_factory=list)


def _build_prompt(email_texts: List[str]) -> str:
    joined = "\n\n---\n\n".join(email_texts)

    prompt = f"""
Eres un extractor de inteligencia de reuniones en espanol.
Recibes texto de 1 o mas emails de PLAUD.AI (transcripciones, resumenes, metadatos).
Genera SOLO JSON valido con la forma:
{{
  "summary": "string corto - ejecutivo",
  "points": ["punto principal 1", "punto principal 2"],
  "tasks": [
    {{"task":"accion", "assignee":"nombre o null", "done":true|false|null}}
  ]
}}

Reglas:
- No inventes informacion.
- Si el responsable no es claro, usa null.
- Si el estado de done no se puede inferir, usa null.
- Consolida y deduplica contenido repetido.
- Mantén summary breve.
- output SOLO JSON.

Texto a procesar:
{joined}
"""

    return prompt


def _extract_json(raw_text: str) -> str:
    raw_text = raw_text.strip()
    raw_text = re.sub(r"(?i)warning:.*", "", raw_text)
    raw_text = raw_text.strip()

    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = raw_text[start : end + 1]
        return candidate

    return raw_text


def _is_quota_error(exc: Exception) -> bool:
    """Detecta errores 429 / RESOURCE_EXHAUSTED del SDK de Google."""
    msg = str(exc)
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower()


def process_emails(email_texts: List[str]) -> GeminiAnalysis:
    if not email_texts:
        raise ValueError("Debe proporcionar al menos un email para procesar")

    if genai is None:
        raise RuntimeError(
            "google-genai no esta instalado. Ejecuta: pip install google-genai"
        )

    api_key = get_gemini_api_key()
    client = genai.Client(api_key=api_key)

    prompt = _build_prompt(email_texts)

    if types is None:
        raise RuntimeError(
            "google-genai no esta instalado correctamente; faltan tipos. Ejecuta: pip install google-genai"
        )

    last_exc: Exception = RuntimeError("No se pudo contactar a Gemini")

    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=1024,
                    top_p=0.95,
                    response_mime_type="application/json",
                ),
            )
            break  # exito — salir del loop de reintentos
        except Exception as exc:
            last_exc = exc
            if _is_quota_error(exc) and attempt < _MAX_RETRIES - 1:
                wait = _RETRY_DELAYS[attempt]
                print(
                    f"[Gemini] Cupo agotado (intento {attempt + 1}/{_MAX_RETRIES}). "
                    f"Reintentando en {wait}s..."
                )
                time.sleep(wait)
                continue
            # Error no recuperable o ultimo intento
            if _is_quota_error(exc):
                raise GeminiQuotaError(
                    f"Gemini: cupo de API agotado despues de {_MAX_RETRIES} intentos. "
                    "Revisa tu plan en https://ai.google.dev/gemini-api/docs/rate-limits"
                ) from exc
            raise
    else:
        # El loop termino sin break (todos los reintentos fallaron con quota)
        if _is_quota_error(last_exc):
            raise GeminiQuotaError(
                f"Gemini: cupo de API agotado despues de {_MAX_RETRIES} intentos. "
                "Revisa tu plan en https://ai.google.dev/gemini-api/docs/rate-limits"
            ) from last_exc
        raise last_exc

    raw_text = response.text.strip()
    cleaned_text = _extract_json(raw_text)

    try:
        data = json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Error parseando respuesta de Gemini (salida no JSON): {e} - RESULTADO: {raw_text}"
        )

    # Compatibilidad con viejos JSON sin campo people
    if isinstance(data, dict):
        data.setdefault("people", [])

    try:
        analysis = GeminiAnalysis.parse_obj(data)
    except ValidationError as e:
        raise ValueError(f"Respuesta de Gemini no cumple esquema: {e}")

    return analysis
