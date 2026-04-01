from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from jinja2 import Environment, FileSystemLoader, select_autoescape
import threading
import os
import uuid
import json
import glob
from datetime import datetime
from services.gmail_service import load_secrets, fetch_recent_plaud_emails, get_email_by_id
from services.gemini_service import process_emails, GeminiAnalysis

# Router para los endpoints
router = APIRouter()


def _ensure_storage_path():
    path = os.path.join(os.path.dirname(__file__), "..", "processed_data")
    path = os.path.abspath(path)
    os.makedirs(path, exist_ok=True)
    return path


def _load_processed_reports_from_disk():
    storage_path = _ensure_storage_path()

    with processed_reports["lock"]:
        processed_reports["data"].clear()

        for json_file in glob.glob(os.path.join(storage_path, "*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    report = json.load(f)
                    processed_reports["data"].append(report)
            except Exception:
                continue


class ProcessEmailRequest(BaseModel):
    email_ids: list[str]


# Cache para los correos (se actualiza en background)
emails_cache = {"data": [], "lock": threading.Lock()}

# Cache de procesamientos
processed_reports = {"data": [], "lock": threading.Lock()}


_load_processed_reports_from_disk()


def setup_jinja2(views_path: str) -> Environment:
    """Configura Jinja2 con el directorio de vistas"""
    return Environment(
        loader=FileSystemLoader(views_path),
        autoescape=select_autoescape(['html', 'xml'])
    )


def background_fetch_emails():
    """Función para actualizar correos en background"""
    try:
        user_email, app_password = load_secrets()
        emails = fetch_recent_plaud_emails(user_email, app_password, limit=10)
        
        with emails_cache["lock"]:
            emails_cache["data"] = emails
            
        print(f"✓ Correos actualizados: {len(emails)} nuevos")
    except Exception as e:
        print(f"Error al actualizar correos: {e}")


def start_email_background_thread():
    """Inicia el hilo de actualización de correos"""
    thread = threading.Thread(target=background_fetch_emails, daemon=True)
    thread.start()


@router.get("/", response_class=HTMLResponse)
async def get_main_view(request: Request):
    """Renderiza la vista principal con la lista de correos"""
    try:
        jinja_env = request.app.jinja_env
        template = jinja_env.get_template("main_view.html")
        
        with emails_cache["lock"]:
            emails = emails_cache["data"]
        
        html = template.render(emails=emails)
        return html
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/emails")
async def get_emails():
    """Endpoint API para obtener todos los correos"""
    try:
        user_email, app_password = load_secrets()
        emails = fetch_recent_plaud_emails(user_email, app_password, limit=10)
        
        with emails_cache["lock"]:
            emails_cache["data"] = emails
        
        return {"status": "success", "count": len(emails), "emails": emails}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/emails/{email_id}")
async def get_email_detail(email_id: str):
    """Endpoint API para obtener detalles de un correo específico"""
    try:
        user_email, app_password = load_secrets()
        email = get_email_by_id(user_email, app_password, email_id)
        return {"status": "success", "email": email}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/emails/{email_id}/attachments")
async def get_attachments(email_id: str):
    """Endpoint API para obtener archivos adjuntos de un correo"""
    try:
        user_email, app_password = load_secrets()
        email = get_email_by_id(user_email, app_password, email_id)
        
        return {
            "status": "success",
            "email_id": email_id,
            "subject": email.get("subject"),
            "attachments": email.get("attachments", [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/emails/process")
async def process_selected_emails(body: ProcessEmailRequest):
    """Endpoint para procesar uno o varios emails con Gemini"""
    if not body.email_ids:
        raise HTTPException(status_code=400, detail="email_ids es obligatorio")

    try:
        user_email, app_password = load_secrets()
        selected_contents = []

        for eid in body.email_ids:
            email_data = get_email_by_id(user_email, app_password, eid)
            if not email_data.get("body"):
                continue
            selected_contents.append(email_data["body"])

        if not selected_contents:
            raise HTTPException(status_code=400, detail="No hay cuerpo de email disponible para procesar")

        analysis: GeminiAnalysis = process_emails(selected_contents)

        report_id = uuid.uuid4().hex
        timestamp = datetime.utcnow().isoformat() + "Z"

        # Añadir IDs de tarea para seguimiento fácil
        tasks_with_ids = []
        for i, t in enumerate(analysis.dict().get("tasks", []), start=1):
            task_entry = {
                "task_id": str(i),
                "task": t.get("task"),
                "assignee": t.get("assignee"),
                "done": t.get("done", False),
            }
            tasks_with_ids.append(task_entry)

        analysis_data = analysis.dict()
        analysis_data["tasks"] = tasks_with_ids

        report = {
            "id": report_id,
            "name": f"Reporte {timestamp.split('T')[0]}",
            "created_at": timestamp,
            "updated_at": timestamp,
            "status": "pending",
            "selected_email_ids": body.email_ids,
            "analysis": analysis_data,
        }

        storage_path = _ensure_storage_path()
        file_path = os.path.join(storage_path, f"{report_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        with processed_reports["lock"]:
            processed_reports["data"].append(report)

        return {
            "status": "success",
            "processed": analysis.dict(),
            "report": report,
            "selected_email_ids": body.email_ids,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class TaskStatusUpdate(BaseModel):
    done: bool


class RenameReportRequest(BaseModel):
    name: str


@router.get("/api/processed")
async def list_processed_reports():
    with processed_reports["lock"]:
        return {"status": "success", "reports": processed_reports["data"]}


@router.get("/api/processed/{report_id}")
async def get_processed_report(report_id: str):
    with processed_reports["lock"]:
        report = next((r for r in processed_reports["data"] if r["id"] == report_id), None)

    if not report:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")

    return {"status": "success", "report": report}


@router.patch("/api/processed/{processed_id}/tasks/{task_id}")
async def update_task_status(processed_id: str, task_id: str, body: TaskStatusUpdate):
    with processed_reports["lock"]:
        report = next((r for r in processed_reports["data"] if r["id"] == processed_id), None)
        if not report:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")

        tasks = report.get("analysis", {}).get("tasks", [])
        task = next((t for t in tasks if t.get("task_id") == task_id), None)
        if not task:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")

        task["done"] = body.done
        report["updated_at"] = datetime.utcnow().isoformat() + "Z"

        storage_path = _ensure_storage_path()
        file_path = os.path.join(storage_path, f"{processed_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    return {"status": "success", "report": report}


@router.get("/processed/{report_id}", response_class=HTMLResponse)
async def get_processed_dashboard(request: Request, report_id: str):
    with processed_reports["lock"]:
        report = next((r for r in processed_reports["data"] if r["id"] == report_id), None)

    if not report:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")

    # fallback for missing people
    people = report.get("analysis", {}).get("people") or []

    metrics = {
        "total_tasks": len(report.get("analysis", {}).get("tasks", [])),
        "completed_tasks": sum(1 for t in report.get("analysis", {}).get("tasks", []) if t.get("done")),
        "pending_tasks": sum(1 for t in report.get("analysis", {}).get("tasks", []) if not t.get("done")),
        "total_people": len(people),
    }

    jinja_env = request.app.jinja_env
    template = jinja_env.get_template("processed_dashboard.html")

    return template.render(report=report, metrics=metrics, people=people)


@router.post("/api/processed/{report_id}/complete")
async def mark_processed_complete(report_id: str):
    with processed_reports["lock"]:
        report = next((r for r in processed_reports["data"] if r["id"] == report_id), None)

        if not report:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")

        report["status"] = "completed"
        report["updated_at"] = datetime.utcnow().isoformat() + "Z"

        storage_path = _ensure_storage_path()
        file_path = os.path.join(storage_path, f"{report_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    return {"status": "success", "report": report}


@router.delete("/api/processed/{report_id}")
async def delete_processed_report(report_id: str):
    """Elimina un reporte procesado del sistema"""
    storage_path = _ensure_storage_path()
    file_path = os.path.join(storage_path, f"{report_id}.json")
    
    with processed_reports["lock"]:
        # Verificar que el reporte existe
        report = next((r for r in processed_reports["data"] if r["id"] == report_id), None)
        if not report:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        
        # Eliminar del cache en memoria
        processed_reports["data"] = [r for r in processed_reports["data"] if r["id"] != report_id]
        
        # Eliminar del disco
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al eliminar archivo: {str(e)}")
    
    return {"status": "success", "message": "Reporte eliminado correctamente"}


@router.patch("/api/processed/{report_id}/rename")
async def rename_processed_report(report_id: str, body: RenameReportRequest):
    """Renombra un reporte procesado (edita el nombre del archivo)"""
    storage_path = _ensure_storage_path()
    old_file_path = os.path.join(storage_path, f"{report_id}.json")
    
    # Validar que el nuevo nombre no sea vacío y no contenga caracteres inválidos
    new_name = body.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    
    # Crear nuevo ID basado en el nombre (slugify)
    new_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in new_name.lower()).replace(" ", "_")
    new_file_path = os.path.join(storage_path, f"{new_id}.json")
    
    # Verificar que el nuevo archivo no exista ya
    if new_id != report_id and os.path.exists(new_file_path):
        raise HTTPException(status_code=409, detail="Ya existe un reporte con ese nombre")
    
    with processed_reports["lock"]:
        # Buscar el reporte
        report = next((r for r in processed_reports["data"] if r["id"] == report_id), None)
        if not report:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        
        # Actualizar el ID y el nombre en el JSON
        report["id"] = new_id
        report["name"] = new_name
        report["updated_at"] = datetime.utcnow().isoformat() + "Z"
        
        # Si el ID cambió, renombrar el archivo
        try:
            if new_id != report_id:
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)
                new_file_path = os.path.join(storage_path, f"{new_id}.json")
            else:
                new_file_path = old_file_path
            
            # Guardar con el nuevo nombre/ID
            with open(new_file_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al guardar: {str(e)}")
    
    return {"status": "success", "report": report, "new_id": new_id}

