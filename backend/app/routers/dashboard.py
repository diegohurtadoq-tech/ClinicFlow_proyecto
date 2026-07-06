"""Ruta REST para el resumen del dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth.dependencies import require_role
from ..database import get_db
from ..schemas.dashboard import DashboardStats
from ..services.dashboard_service import DashboardService

router = APIRouter(
    prefix="/api/dashboard", tags=["Dashboard"], dependencies=[Depends(require_role("admin"))]
)
_service = DashboardService()


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    return _service.get_stats(db)
