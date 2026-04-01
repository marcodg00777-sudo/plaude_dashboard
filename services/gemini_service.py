import json
import re
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
Eres un extractor de inteligencia de reuniones en español.
Recibes texto de 1 o más emails de PLAUD.AI (transcripciones, resúmenes, metadatos).
Genera SOLO JSON válido con la forma:
{{
  "summary": "string corto - ejecutivo",
  "points": ["punto principal 1", "punto principal 2"],
  "tasks": [
    {{"task":"acción", "assignee":"nombre o null", "done":true|false|null}}
  ]
}}

Reglas:
- No inventes información.
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


def process_emails(email_texts: List[str]) -> GeminiAnalysis:
    if not email_texts:
        raise ValueError("Debe proporcionar al menos un email para procesar")

    if genai is None:
        raise RuntimeError(
            "google-genai no está instalado. Ejecuta: pip install google-genai"
        )

    api_key = get_gemini_api_key()
    client = genai.Client(api_key=api_key)

    prompt = _build_prompt(email_texts)

    if types is None:
        raise RuntimeError(
            "google-genai no está instalado correctamente; faltan tipos. Ejecuta: pip install google-genai"
        )

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
