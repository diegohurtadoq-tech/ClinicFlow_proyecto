"""
Servicio de Derivaciones: un Doctor deriva a un Paciente hacia otra
especialidad; el paciente puede luego aceptarla, lo que crea una Cita
ligada a la derivacion (mismo camino que tomar una hora normal).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from ..exceptions import NotFoundError
from ..models.appointment import Appointment
from ..models.referral import Referral, ReferralStatus
from .appointment_service import AppointmentService


class ReferralService:
    """Logica de negocio sobre Derivaciones."""

    def __init__(self, appointment_service: AppointmentService | None = None) -> None:
        self._appointments = appointment_service or AppointmentService()

    def create(
        self,
        db: Session,
        from_doctor_id: int,
        patient_id: int,
        to_specialty: str,
        message: str,
    ) -> Referral:
        referral = Referral(
            from_doctor_id=from_doctor_id,
            patient_id=patient_id,
            to_specialty=to_specialty,
            message=message,
            status=ReferralStatus.PENDIENTE,
        )
        db.add(referral)
        db.commit()
        db.refresh(referral)
        return referral

    def _get_referral(self, db: Session, referral_id: int) -> Referral:
        referral = db.get(Referral, referral_id)
        if referral is None:
            raise NotFoundError(f"No existe la derivacion {referral_id}.")
        return referral

    def accept(
        self, db: Session, referral_id: int, doctor_id: int, moment: dt.datetime
    ) -> Appointment:
        """Acepta la derivacion: crea la cita con el doctor/especialidad de destino."""
        referral = self._get_referral(db, referral_id)
        appointment = self._appointments.create(
            db,
            patient_id=referral.patient_id,
            doctor_id=doctor_id,
            moment=moment,
            notes=f"Derivacion #{referral.id}: {referral.message}",
        )
        appointment.referral_id = referral.id
        referral.status = ReferralStatus.ACEPTADA
        db.commit()
        db.refresh(appointment)
        return appointment

    def reject(self, db: Session, referral_id: int) -> Referral:
        referral = self._get_referral(db, referral_id)
        referral.status = ReferralStatus.RECHAZADA
        db.commit()
        db.refresh(referral)
        return referral
