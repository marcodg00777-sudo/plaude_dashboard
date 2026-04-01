from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
import uvicorn

from controller.email_controller import router, start_email_background_thread, setup_jinja2

# Inicializar FastAPI
app = FastAPI(
    title="PLAUD Email Manager",
    description="Gestor de correos de PLAUD",
    version="1.0.0"
)

# Configurar Jinja2
views_path = str(Path(__file__).parent / "views")
jinja_env = setup_jinja2(views_path)

# Inyectar jinja_env en el contexto de la aplicación
app.jinja_env = jinja_env


# Middleware para pasar jinja_env a las rutas
@app.middleware("http")
async def add_jinja_env(request, call_next):
    request.state.jinja_env = jinja_env
    response = await call_next(request)
    return response


# Registrar el router
app.include_router(router)


@app.on_event("startup")
async def startup_event():
    """Inicia el hilo de actualización de correos al iniciar la app"""
    print("✓ Iniciando aplicación PLAUD Email Manager")
    start_email_background_thread()
    print("✓ Hilo de actualización de correos iniciado")


@app.on_event("shutdown")
async def shutdown_event():
    """Limpieza al cerrar la app"""
    print("✓ Cerrando aplicación PLAUD Email Manager")


if __name__ == "__main__":
    print("🚀 Iniciando servidor PLAUD Email Manager")
    print("📍 URL: http://localhost:8000")
    print("📚 Docs: http://localhost:8000/docs")
    uvicorn.run(app, host="127.0.0.1", port=8000)