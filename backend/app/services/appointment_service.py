"""
Servicio de Citas: punto unico de creacion/confirmacion/cancelacion/
reagendamiento. Es la autoridad final de las reglas de negocio — se
ejecuta independientemente de si la solicitud viene del dashboard, la API
REST directa, o de las IAs conversacionales, y vuelve a validar todo
(disponibilidad, transiciones de estado) sin confiar en el llamador.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy.orm import Session

from ..exceptions import ClinicFlowError, NotFoundError, ScheduleConflictError, SecurityViolationError
from ..models.appointment import Appointment, AppointmentStatus
from ..models.user import Doctor, Patient
from .notification_service import NotificationService
from .schedule_service import ScheduleService
from .waitlist_service import WaitlistService

logger = logging.getLogger(__name__)


class AppointmentService:
    """Logica de negocio sobre Citas."""

    def __init__(
        self,
        schedule_service: ScheduleService | None = None,
        waitlist_service: WaitlistService | None = None,
        notification_service: NotificationService | None = None,
    ) -> None:
        self._schedules = schedule_service or ScheduleService()
        self._waitlist = waitlist_service or WaitlistService()
        self._notifications = notification_service or NotificationService()

    def _get_appointment(
        self, db: Session, appointment_id: int, requesting_patient_id: int | None = None
    ) -> Appointment:
        appointment = db.get(Appointment, appointment_id)
        if appointment is None:
            raise NotFoundError(f"No existe la cita {appointment_id}.")
        if requesting_patient_id is not None and appointment.patient_id != requesting_patient_id:
            # Verificacion final de pertenencia: incluso si el ActionGuard ya
            # confirmo que la accion viene del dueño de la conversacion, el
            # Service vuelve a confirmar que la CITA referenciada le pertenece.
            raise SecurityViolationError(
                f"La cita {appointment_id} no pertenece al paciente {requesting_patient_id}."
            )
        return appointment

    def _validate_participants(self, db: Session, patient_id: int, doctor_id: int) -> None:
        if db.get(Patient, patient_id) is None:
            raise NotFoundError(f"No existe el paciente {patient_id}.")
        if db.get(Doctor, doctor_id) is None:
            raise NotFoundError(f"No existe el doctor {doctor_id}.")

    def _validate_not_in_past(self, moment: dt.datetime) -> None:
        now = dt.datetime.now()
        if moment < now:
            raise ClinicFlowError(
                "No es posible agendar o modificar citas en una fecha u hora pasada"
            )

    def _notify_appointment_change(
        self,
        db: Session,
        appointment: Appointment,
        action: str,
        new_moment: dt.datetime | None = None,
    ) -> None:
        patient = db.get(Patient, appointment.patient_id)
        if patient is None or not getattr(patient, "telegram_id", None):
            return

        doctor = db.get(Doctor, appointment.doctor_id)
        doctor_name = doctor.name if doctor and doctor.name else "nuestro equipo"
        last_name = doctor_name.split()[-1] if doctor_name else "equipo"
        moment = new_moment or appointment.datetime_
        date_label = moment.strftime("%d/%m/%Y")
        time_label = moment.strftime("%H:%M")

        if action == "cancelada":
            message = (
                f"Hola {patient.name}, te informamos que tu cita con el Dr. {last_name} "
                f"para el día {date_label} a las {time_label} ha sido cancelada. "
                "Si necesitas, puedes solicitar una nueva cita con nosotros."
            )
        else:
            message = (
                f"Hola {patient.name}, te informamos que tu cita con el Dr. {last_name} "
                f"para el día {date_label} a las {time_label} ha sido reprogramada. "
                "Te contactaremos si necesitas más información."
            )

        try:
            self._notifications.notify(patient.id, message, db=db)
        except TypeError:
            self._notifications.notify(patient.id, message)
        except Exception as exc:  # pragma: no cover - defensive path
            logger.warning("No se pudo enviar la notificacion por Telegram: %s", exc)

    def create(
        self,
        db: Session,
        patient_id: int,
        doctor_id: int,
        moment: dt.datetime,
        notes: str | None = None,
    ) -> Appointment:
        """Crea una cita en estado PENDIENTE, validando disponibilidad real contra la agenda."""
        self._validate_participants(db, patient_id, doctor_id)
        self._validate_not_in_past(moment)
        if not self._schedules.is_available(db, doctor_id, moment):
            raise ScheduleConflictError(
                f"El doctor {doctor_id} no tiene disponibilidad el {moment.isoformat()}."
            )
        appointment = Appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            datetime_=moment,
            status=AppointmentStatus.PENDIENTE,
            notes=notes,
        )
        db.add(appointment)
        db.commit()
        db.refresh(appointment)
        return appointment

    def confirm(self, db: Session, appointment_id: int) -> Appointment:
        appointment = self._get_appointment(db, appointment_id)
        appointment.transition_to(AppointmentStatus.CONFIRMADA)
        db.commit()
        db.refresh(appointment)
        return appointment

    def cancel(
        self, db: Session, appointment_id: int, requesting_patient_id: int | None = None
    ) -> Appointment:
        """Cancela una cita y libera el cupo a la lista de espera, si corresponde."""
        appointment = self._get_appointment(db, appointment_id, requesting_patient_id)
        freed_doctor_id = appointment.doctor_id
        freed_moment = appointment.datetime_
        appointment.transition_to(AppointmentStatus.CANCELADA)
        appointment.cancelled_at = dt.datetime.now()
        db.commit()
        db.refresh(appointment)
        self._notify_appointment_change(db, appointment, "cancelada")
        self._waitlist.try_fill_slot(db, self, doctor_id=freed_doctor_id, moment=freed_moment)
        return appointment

    def mark_completed(self, db: Session, appointment_id: int) -> Appointment:
        appointment = self._get_appointment(db, appointment_id)
        appointment.transition_to(AppointmentStatus.COMPLETADA)
        db.commit()
        db.refresh(appointment)
        return appointment

    def mark_no_show(self, db: Session, appointment_id: int) -> Appointment:
        appointment = self._get_appointment(db, appointment_id)
        appointment.transition_to(AppointmentStatus.NO_ASISTIO)
        db.commit()
        db.refresh(appointment)
        return appointment

    def reschedule(
        self,
        db: Session,
        appointment_id: int,
        new_moment: dt.datetime,
        requesting_patient_id: int | None = None,
    ) -> Appointment:
        """Marca la cita actual como REAGENDADA y crea una nueva cita PENDIENTE en el nuevo horario."""
        old = self._get_appointment(db, appointment_id, requesting_patient_id)
        self._validate_not_in_past(new_moment)
        if not self._schedules.is_available(db, old.doctor_id, new_moment):
            raise ScheduleConflictError(
                f"El doctor {old.doctor_id} no tiene disponibilidad el {new_moment.isoformat()}."
            )
        new_appointment = Appointment(
            patient_id=old.patient_id,
            doctor_id=old.doctor_id,
            datetime_=new_moment,
            status=AppointmentStatus.PENDIENTE,
            notes=old.notes,
        )
        db.add(new_appointment)
        old.transition_to(AppointmentStatus.REAGENDADA)
        db.flush()
        old.rescheduled_to_id = new_appointment.id
        db.commit()
        db.refresh(new_appointment)
        self._notify_appointment_change(db, old, "reprogramada", new_moment=new_appointment.datetime_)
        return new_appointment
