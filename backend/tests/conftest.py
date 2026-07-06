"""Fixtures comunes de pytest: sesion de base de datos en memoria y helpers de fecha."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  registra todos los modelos en Base.metadata
from app.database import Base
from app.models.schedule import Schedule
from app.models.user import Doctor, Patient


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def next_monday_10am() -> dt.datetime:
    """Retorna el proximo lunes a las 10:00 (siempre futuro, weekday()==0)."""
    today = dt.date.today()
    days_ahead = (0 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    monday = today + dt.timedelta(days=days_ahead)
    return dt.datetime.combine(monday, dt.time(10, 0))


@pytest.fixture
def doctor(db_session) -> Doctor:
    """Un Doctor con agenda lunes a viernes 09:00-17:00, capacidad 1."""
    doc = Doctor(name="Dra. Carmen Vega", email="cvega@clinicflow.cl", specialty="Cardiología")
    db_session.add(doc)
    db_session.flush()
    for day in range(5):
        db_session.add(
            Schedule(
                doctor_id=doc.id,
                day_of_week=day,
                start_time=dt.time(9, 0),
                end_time=dt.time(17, 0),
                slot_minutes=30,
                capacity=1,
            )
        )
    db_session.commit()
    db_session.refresh(doc)
    return doc


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(name="Ana Torres", email="ana.torres@example.com")
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def other_patient(db_session) -> Patient:
    p = Patient(name="Carlos Ríos", email="carlos.rios@example.com")
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p
