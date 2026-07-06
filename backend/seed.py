"""
Script de siembra: crea doctores, pacientes y agendas de ejemplo,
reutilizando los mismos nombres del mockup ClinicFlow.html para que el
dashboard estatico y el backend cuenten una historia coherente.

Uso:
    python seed.py
"""

from __future__ import annotations

import datetime as dt

from app.auth.security import hash_password
from app.database import Base, SessionLocal, engine
from app.models.schedule import Schedule
from app.models.user import Admin, Doctor, Patient

ADMIN_PASSWORD = "admin123"
PATIENT_PASSWORD = "paciente123"

DOCTORS = [
    ("Dr. Roberto Muñoz", "rmunoz@clinicflow.cl", "Medicina General"),
    ("Dra. Carmen Vega", "cvega@clinicflow.cl", "Cardiología"),
    ("Dr. Andrés Pinto", "apinto@clinicflow.cl", "Neurología"),
    ("Dra. Isabel Lagos", "ilagos@clinicflow.cl", "Traumatología"),
]

PATIENTS = [
    ("Ana Torres", "ana.torres@example.com"),
    ("Carlos Ríos", "carlos.rios@example.com"),
    ("María Soto", "maria.soto@example.com"),
    ("Luis Herrera", "luis.herrera@example.com"),
    ("Paula Fuentes", "paula.fuentes@example.com"),
    ("Jorge Ibáñez", "jorge.ibanez@example.com"),
    ("Pedro Mora", "pedro.mora@example.com"),
    ("Roberto Díaz", "roberto.diaz@example.com"),
    ("Camila Rojas", "camila.rojas@example.com"),
]


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Doctor).first() is not None:
            print("La base de datos ya tiene datos; no se vuelve a sembrar.")
            return

        db.add(
            Admin(
                name="Jorge Zambrano",
                email="admin@clinicflow.cl",
                password_hash=hash_password(ADMIN_PASSWORD),
            )
        )

        doctors = []
        for name, email, specialty in DOCTORS:
            doctor = Doctor(name=name, email=email, specialty=specialty)
            db.add(doctor)
            doctors.append(doctor)
        db.flush()

        for doctor in doctors:
            for day in range(0, 5):  # lunes a viernes
                db.add(
                    Schedule(
                        doctor_id=doctor.id,
                        day_of_week=day,
                        start_time=dt.time(9, 0),
                        end_time=dt.time(17, 0),
                        slot_minutes=30,
                        capacity=1,
                    )
                )

        for name, email in PATIENTS:
            db.add(Patient(name=name, email=email, password_hash=hash_password(PATIENT_PASSWORD)))

        db.commit()
        print(f"Sembrados {len(doctors)} doctores y {len(PATIENTS)} pacientes con agenda lunes-viernes 09:00-17:00.")
        print(f"Login admin: admin@clinicflow.cl / {ADMIN_PASSWORD}")
        print(f"Login paciente (cualquiera de los de arriba): <su email> / {PATIENT_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
