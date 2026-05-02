import json
import re
from typing import Any

try:
    from google import genai
    from google.genai import types
except ModuleNotFoundError:
    genai = None
    types = None

from services.config import get_gemini_api_key

MODEL_NAME = "gemini-3.1-flash-lite-preview"


def _client():
    return genai.Client(api_key=get_gemini_api_key())


def _generate(prompt: str, max_tokens: int = 1024) -> str:
    response = _client().models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=max_tokens,
            top_p=0.95,
            response_mime_type="application/json",
        ),
    )
    raw = response.text.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start: end + 1]
    start, end = raw.find("["), raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        return raw[start: end + 1]
    return raw


def run_resumen(content: str) -> dict:
    prompt = f"""
Eres un asistente ejecutivo. Resume el siguiente contenido de reunión en español.
Responde SOLO JSON:
{{
  "titulo": "string (título corto de la reunión)",
  "resumen": "string (2-3 oraciones ejecutivas)",
  "puntos_clave": ["punto 1", "punto 2", "punto 3"],
  "decisiones": ["decisión 1"],
  "proximos_pasos": ["paso 1"]
}}

Contenido:
{content}
"""
    return json.loads(_generate(prompt))


def run_tareas(content: str) -> dict:
    prompt = f"""
Extrae todas las tareas y compromisos del siguiente texto de reunión.
Responde SOLO JSON:
{{
  "tareas_pendientes": [
    {{"tarea": "string", "responsable": "nombre o null", "fecha_limite": "fecha o null", "prioridad": "alta|media|baja"}}
  ],
  "tareas_completadas": [
    {{"tarea": "string", "responsable": "nombre o null"}}
  ],
  "total_pendientes": 0,
  "total_completadas": 0
}}

Texto:
{content}
"""
    return json.loads(_generate(prompt))


def run_traducir(content: str, target_language: str) -> dict:
    prompt = f"""
Traduce el siguiente texto al idioma: {target_language}.
Mantén el formato y los nombres propios.
Responde SOLO JSON:
{{
  "texto_original": "string",
  "texto_traducido": "string",
  "idioma_destino": "{target_language}"
}}

Texto a traducir:
{content}
"""
    return json.loads(_generate(prompt, max_tokens=2048))


def run_email_seguimiento(content: str, destinatarios: list[str] | None = None) -> dict:
    dest = ", ".join(destinatarios) if destinatarios else "los participantes"
    prompt = f"""
Redacta un email profesional de seguimiento post-reunión en español para enviar a: {dest}.
Basa el email en el siguiente resumen de reunión.
Responde SOLO JSON:
{{
  "asunto": "string",
  "saludo": "string",
  "intro": "string (1 párrafo)",
  "acuerdos": ["acuerdo 1", "acuerdo 2"],
  "tareas": [{{"responsable": "nombre", "tarea": "string", "fecha": "fecha o pronto"}}],
  "cierre": "string (1 párrafo de cierre)",
  "firma": "El equipo PLAUD"
}}

Resumen de la reunión:
{content}
"""
    return json.loads(_generate(prompt))


def run_calendario(content: str) -> dict:
    prompt = f"""
Extrae todos los eventos, fechas y compromisos mencionados en el siguiente texto de reunión.
Responde SOLO JSON:
{{
  "eventos": [
    {{
      "titulo": "string",
      "fecha": "string (fecha mencionada o deducida)",
      "hora": "string o null",
      "participantes": ["nombre1"],
      "descripcion": "string",
      "tipo": "reunion|deadline|entrega|otro"
    }}
  ],
  "total_eventos": 0
}}

Texto:
{content}
"""
    return json.loads(_generate(prompt))


def run_tendencias(reports_text: str) -> dict:
    prompt = f"""
Analiza el historial de reuniones y detecta patrones, tendencias y bloqueos recurrentes.
Responde SOLO JSON:
{{
  "temas_recurrentes": ["tema 1", "tema 2"],
  "bloqueos_frecuentes": ["bloqueo 1"],
  "personas_mas_activas": ["nombre 1"],
  "proyectos_con_mas_actividad": ["proyecto 1"],
  "insights": "string (análisis ejecutivo de 2-3 oraciones)",
  "recomendaciones": ["recomendación 1", "recomendación 2"]
}}

Historial de reuniones:
{reports_text}
"""
    return json.loads(_generate(prompt, max_tokens=1500))


def run_reporte(reports_text: str, periodo: str) -> dict:
    prompt = f"""
Genera un reporte consolidado de {periodo} basado en el historial de reuniones.
Responde SOLO JSON:
{{
  "periodo": "{periodo}",
  "titulo": "string",
  "resumen_ejecutivo": "string (3-4 oraciones)",
  "logros": ["logro 1", "logro 2"],
  "tareas_completadas": 0,
  "tareas_pendientes": 0,
  "temas_tratados": ["tema 1"],
  "puntos_de_atencion": ["punto crítico 1"],
  "recomendaciones": ["recomendación 1"]
}}

Historial:
{reports_text}
"""
    return json.loads(_generate(prompt, max_tokens=1500))


def run_crm(content: str) -> dict:
    prompt = f"""
Extrae información relevante para CRM del texto de reunión: clientes, oportunidades, proyectos, contactos.
Responde SOLO JSON:
{{
  "clientes_mencionados": [
    {{"nombre": "string", "empresa": "string o null", "contexto": "string"}}
  ],
  "oportunidades": [
    {{"titulo": "string", "cliente": "string o null", "estado": "string", "valor_estimado": "string o null"}}
  ],
  "contactos_nuevos": [
    {{"nombre": "string", "rol": "string o null", "email": "string o null"}}
  ],
  "notas_seguimiento": "string"
}}

Texto:
{content}
"""
    return json.loads(_generate(prompt))


def run_alertas(reports_text: str) -> dict:
    prompt = f"""
Revisa el historial de reuniones y genera alertas sobre tareas vencidas o próximas a vencer sin responsable confirmado.
Responde SOLO JSON:
{{
  "alertas_criticas": [
    {{"tarea": "string", "responsable": "string o null", "dias_vencida": "int o null", "accion_sugerida": "string"}}
  ],
  "alertas_proximas": [
    {{"tarea": "string", "responsable": "string o null", "dias_restantes": "int o null"}}
  ],
  "digest_resumen": "string (resumen de situación en 1-2 oraciones)"
}}

Historial:
{reports_text}
"""
    return json.loads(_generate(prompt))


def run_investigar(topic: str, context: str | None = None) -> dict:
    ctx = f"\nContexto adicional: {context}" if context else ""
    prompt = f"""
Eres un investigador experto. Proporciona un análisis profundo sobre el siguiente tema
para preparar una reunión o tomar una decisión informada.{ctx}

Tema a investigar: {topic}

Responde SOLO JSON:
{{
  "tema": "{topic}",
  "resumen": "string (explicación clara en 2-3 oraciones)",
  "puntos_clave": ["punto 1", "punto 2", "punto 3"],
  "preguntas_para_reunion": ["pregunta 1", "pregunta 2"],
  "riesgos_a_considerar": ["riesgo 1"],
  "recomendacion": "string (recomendación concreta)"
}}
"""
    return json.loads(_generate(prompt, max_tokens=1500))
