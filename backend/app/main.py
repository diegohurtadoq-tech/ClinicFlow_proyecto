"""
main.py — Aplicacion FastAPI de ClinicFlow.

Este archivo SOLO registra la app, middleware, manejadores de error y
routers. Toda la logica de negocio vive en services/, ai/ y models/.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (registra todos los modelos en Base.metadata)
from .database import Base, engine
from .exceptions import ClinicFlowError, LLMServiceError
from .routers import appointments, auth, conversation, dashboard, doctors, me, patients, schedules, telegram, waitlist

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="ClinicFlow API",
    description=(
        "Backend de gestion clinica conversacional. Incluye el flujo de dos "
        "IAs: FrontDeskAI (atiende al paciente) y ActionAI (extrae y ejecuta "
        "acciones, validadas por ActionGuard antes de tocar la base de datos)."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    """Crea las tablas si no existen. Suficiente para SQLite/desarrollo;
    en produccion con Postgres se recomendaria una migracion (Alembic)."""
    Base.metadata.create_all(bind=engine)


@app.exception_handler(ClinicFlowError)
def clinicflow_error_handler(request, exc: ClinicFlowError):
    if isinstance(exc, LLMServiceError):
        # El detalle real (rate limit, timeout, JSON de OpenRouter) queda solo
        # en el log del servidor; el cliente nunca ve detalles tecnicos del
        # proveedor de IA.
        logger.warning("LLMServiceError no manejado a nivel de ruta: %s", exc)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": "Se ha producido un problema, conéctese más tarde."},
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


app.include_router(auth.router)
app.include_router(me.router)
app.include_router(patients.router)
app.include_router(doctors.router)
app.include_router(appointments.router)
app.include_router(schedules.router)
app.include_router(waitlist.router)
app.include_router(conversation.router)
app.include_router(conversation.list_router)
app.include_router(dashboard.router)
app.include_router(telegram.router)


@app.get("/api/health", tags=["Sistema"])
def health_check():
    return {"status": "ok", "version": "0.1.0"}


# El dashboard estatico se sirve al final, para que las rutas /api/* de
# arriba se evaluen primero (un Mount en "/" actua como catch-all).
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
