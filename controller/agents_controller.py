from fastapi import APIRouter, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import Optional
import os
import json
import glob

from services.agents_service import (
    run_resumen, run_tareas, run_traducir, run_email_seguimiento,
    run_calendario, run_tendencias, run_reporte, run_crm,
    run_alertas, run_investigar,
)

router = APIRouter(prefix="/api/agents", tags=["OpenClaw Agents"])

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _require_api_key(api_key: str = Security(_api_key_header)):
    expected = os.environ.get("OPENCLAW_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="OPENCLAW_API_KEY no configurada en el servidor")
    if api_key != expected:
        raise HTTPException(status_code=401, detail="API key inválida")
    return api_key


def _load_reports() -> list[dict]:
    storage = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "processed_data")
    )
    reports = []
    for f in glob.glob(os.path.join(storage, "*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                reports.append(json.load(fh))
        except Exception:
            continue
    reports.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return reports


def _report_to_text(report: dict) -> str:
    analysis = report.get("analysis", {})
    parts = [
        f"Reunión: {report.get('name', 'Sin nombre')}",
        f"Fecha: {report.get('created_at', '')}",
        f"Resumen: {analysis.get('summary', '')}",
        "Puntos: " + "; ".join(analysis.get("points", [])),
        "Tareas: " + "; ".join(
            f"{t.get('task')} ({t.get('assignee') or 'sin asignar'})"
            for t in analysis.get("tasks", [])
        ),
    ]
    return "\n".join(parts)


def _reports_to_text(reports: list[dict], limit: int = 5) -> str:
    return "\n\n---\n\n".join(_report_to_text(r) for r in reports[:limit])


def _get_report_or_latest(report_id: str | None) -> dict:
    reports = _load_reports()
    if not reports:
        raise HTTPException(status_code=404, detail="No hay reportes procesados. Procesa primero algunos correos de PLAUD.")
    if report_id:
        match = next((r for r in reports if r["id"] == report_id), None)
        if not match:
            raise HTTPException(status_code=404, detail=f"Reporte '{report_id}' no encontrado")
        return match
    return reports[0]


# ---------- Schemas ----------

class ReportIdRequest(BaseModel):
    report_id: Optional[str] = None


class TraducirRequest(BaseModel):
    report_id: Optional[str] = None
    texto: Optional[str] = None
    idioma: str = "inglés"


class EmailRequest(BaseModel):
    report_id: Optional[str] = None
    destinatarios: Optional[list[str]] = None


class ReporteRequest(BaseModel):
    periodo: str = "semana"


class InvestigarRequest(BaseModel):
    tema: str
    contexto: Optional[str] = None


# ---------- Endpoints ----------

@router.get("/status")
def agents_status():
    """Lista todos los agentes disponibles y su estado de conexión."""
    reports = _load_reports()
    return {
        "connected": True,
        "reports_disponibles": len(reports),
        "ultimo_reporte": reports[0].get("name") if reports else None,
        "agentes": [
            {"id": "resumen",           "nombre": "Resumen Ejecutivo",        "endpoint": "POST /api/agents/resumen"},
            {"id": "tareas",            "nombre": "Gestor de Tareas",          "endpoint": "POST /api/agents/tareas"},
            {"id": "traducir",          "nombre": "Traductor Multilingüe",     "endpoint": "POST /api/agents/traducir"},
            {"id": "email-seguimiento", "nombre": "Redactor de Seguimiento",   "endpoint": "POST /api/agents/email-seguimiento"},
            {"id": "calendario",        "nombre": "Agente de Calendario",      "endpoint": "POST /api/agents/calendario"},
            {"id": "tendencias",        "nombre": "Analizador de Tendencias",  "endpoint": "POST /api/agents/tendencias"},
            {"id": "reporte",           "nombre": "Generador de Reportes",     "endpoint": "POST /api/agents/reporte"},
            {"id": "crm",               "nombre": "Actualizador de CRM",       "endpoint": "POST /api/agents/crm"},
            {"id": "alertas",           "nombre": "Monitor de Compromisos",    "endpoint": "POST /api/agents/alertas"},
            {"id": "investigar",        "nombre": "Investigador de Contexto",  "endpoint": "POST /api/agents/investigar"},
        ],
    }


@router.post("/resumen")
def agente_resumen(body: ReportIdRequest, _key: str = Security(_require_api_key)):
    """Genera un resumen ejecutivo del último reporte o del indicado."""
    report = _get_report_or_latest(body.report_id)
    result = run_resumen(_report_to_text(report))
    return {"agent": "resumen", "report_id": report["id"], "resultado": result}


@router.post("/tareas")
def agente_tareas(body: ReportIdRequest, _key: str = Security(_require_api_key)):
    """Extrae y lista todas las tareas del último reporte o del indicado."""
    report = _get_report_or_latest(body.report_id)
    result = run_tareas(_report_to_text(report))
    return {"agent": "tareas", "report_id": report["id"], "resultado": result}


@router.post("/traducir")
def agente_traducir(body: TraducirRequest, _key: str = Security(_require_api_key)):
    """Traduce el contenido de un reporte o un texto libre al idioma indicado."""
    if body.texto:
        content = body.texto
        report_id = None
    else:
        report = _get_report_or_latest(body.report_id)
        content = _report_to_text(report)
        report_id = report["id"]
    result = run_traducir(content, body.idioma)
    return {"agent": "traducir", "report_id": report_id, "resultado": result}


@router.post("/email-seguimiento")
def agente_email(body: EmailRequest, _key: str = Security(_require_api_key)):
    """Redacta el email de seguimiento post-reunión."""
    report = _get_report_or_latest(body.report_id)
    result = run_email_seguimiento(_report_to_text(report), body.destinatarios)
    return {"agent": "email-seguimiento", "report_id": report["id"], "resultado": result}


@router.post("/calendario")
def agente_calendario(body: ReportIdRequest, _key: str = Security(_require_api_key)):
    """Extrae eventos y fechas del reporte para añadirlos al calendario."""
    report = _get_report_or_latest(body.report_id)
    result = run_calendario(_report_to_text(report))
    return {"agent": "calendario", "report_id": report["id"], "resultado": result}


@router.post("/tendencias")
def agente_tendencias(_key: str = Security(_require_api_key)):
    """Analiza todos los reportes e identifica tendencias y bloqueos recurrentes."""
    reports = _load_reports()
    if not reports:
        raise HTTPException(status_code=404, detail="No hay reportes procesados aún.")
    result = run_tendencias(_reports_to_text(reports, limit=10))
    return {"agent": "tendencias", "reportes_analizados": min(len(reports), 10), "resultado": result}


@router.post("/reporte")
def agente_reporte(body: ReporteRequest, _key: str = Security(_require_api_key)):
    """Genera un reporte consolidado del período indicado (semana/mes)."""
    reports = _load_reports()
    if not reports:
        raise HTTPException(status_code=404, detail="No hay reportes procesados aún.")
    result = run_reporte(_reports_to_text(reports, limit=20), body.periodo)
    return {"agent": "reporte", "periodo": body.periodo, "resultado": result}


@router.post("/crm")
def agente_crm(body: ReportIdRequest, _key: str = Security(_require_api_key)):
    """Extrae clientes, oportunidades y contactos del reporte para actualizar el CRM."""
    report = _get_report_or_latest(body.report_id)
    result = run_crm(_report_to_text(report))
    return {"agent": "crm", "report_id": report["id"], "resultado": result}


@router.post("/alertas")
def agente_alertas(_key: str = Security(_require_api_key)):
    """Genera alertas sobre tareas vencidas o próximas a vencer."""
    reports = _load_reports()
    if not reports:
        raise HTTPException(status_code=404, detail="No hay reportes procesados aún.")
    result = run_alertas(_reports_to_text(reports, limit=10))
    return {"agent": "alertas", "resultado": result}


@router.post("/investigar")
def agente_investigar(body: InvestigarRequest, _key: str = Security(_require_api_key)):
    """Investiga un tema y devuelve contexto, puntos clave y preguntas para la reunión."""
    result = run_investigar(body.tema, body.contexto)
    return {"agent": "investigar", "tema": body.tema, "resultado": result}
