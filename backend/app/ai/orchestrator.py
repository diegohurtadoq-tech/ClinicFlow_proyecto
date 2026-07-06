"""
ConversationOrchestrator — el componente "ConversationAI" del diagrama de
arquitectura. Coordina el turno completo descrito por el usuario:

  1. Recibe el mensaje del paciente y lo persiste.
  2. ActionAI lee la conversacion y extrae una ProposedAction (JSON validado).
  3. ActionGuard revisa la accion ANTES de tocar la base de datos
     (pertenencia del paciente, patrones de inyeccion).
  4. Si pasa el guard, se ejecuta contra el Service de dominio
     correspondiente (autoridad final de las reglas de negocio).
  5. El resultado (ActionResult) se entrega a FrontDeskAI, que redacta la
     respuesta final para el paciente.
  6. Se persiste el turno completo (intent extraido + accion tomada) para
     alimentar el dashboard de "Conversaciones IA".

Ninguna de las dos IAs ejecuta SQL ni decide el resultado final por su
cuenta: la unica pieza de codigo que decide si algo se ejecuta es
ActionGuard + los Services.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..exceptions import ClinicFlowError, LLMServiceError, SecurityViolationError
from ..models.conversation import Conversation, ConversationMessage
from ..models.user import Doctor
from ..schemas.ai import ActionResult, Intent, ProposedAction

logger = logging.getLogger(__name__)

_GENERIC_LLM_FAILURE_REPLY = "Se ha producido un problema, conéctese más tarde."
from ..schemas.conversation import MessageResponse
from ..services.appointment_service import AppointmentService
from ..services.referral_service import ReferralService
from ..services.schedule_service import ScheduleService
from ..services.waitlist_service import WaitlistService
from .action_ai import ActionAI
from .action_guard import ActionGuard
from .front_desk_ai import FrontDeskAI


class ConversationOrchestrator:
    """Glue del flujo conversacional de dos IAs."""

    def __init__(
        self,
        front_desk_ai: FrontDeskAI,
        action_ai: ActionAI,
        action_guard: ActionGuard | None = None,
        appointment_service: AppointmentService | None = None,
        schedule_service: ScheduleService | None = None,
        waitlist_service: WaitlistService | None = None,
        referral_service: ReferralService | None = None,
    ) -> None:
        self._front_desk = front_desk_ai
        self._action_ai = action_ai
        self._guard = action_guard or ActionGuard()
        self._appointments = appointment_service or AppointmentService()
        self._schedules = schedule_service or ScheduleService()
        self._waitlist = waitlist_service or WaitlistService()
        self._referrals = referral_service or ReferralService(self._appointments)

    def _get_or_create_conversation(
        self, db: Session, patient_id: int, channel: str
    ) -> Conversation:
        conversation = db.scalars(
            select(Conversation).where(
                Conversation.patient_id == patient_id, Conversation.channel == channel
            )
        ).first()
        if conversation is None:
            conversation = Conversation(patient_id=patient_id, channel=channel)
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
        return conversation

    def _history_as_messages(self, conversation: Conversation) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in conversation.messages]

    def _doctors_roster(self, db: Session) -> list[dict]:
        """Listado plano {id, name, specialty} para que ActionAI pueda resolver
        nombres/especialidades a doctor_id sin tocar la base de datos ella misma.
        Excluye doctores desactivados: no deben ofrecerse para nuevas citas."""
        return [
            {"id": d.id, "name": d.name, "specialty": d.specialty}
            for d in db.scalars(select(Doctor).where(Doctor.is_active)).all()
        ]

    def _resolve_doctor_for_specialty(
        self, db: Session, specialty: str, moment: dt.datetime
    ) -> Doctor | None:
        candidates = self._schedules.available_doctors_for_specialty(db, specialty, moment)
        return candidates[0] if candidates else None

    def _execute(self, db: Session, action: ProposedAction) -> ActionResult:
        """Despacha la accion ya aprobada por el ActionGuard hacia el Service correspondiente."""
        try:
            if action.intent == Intent.CREATE_APPOINTMENT:
                if action.requested_datetime is None:
                    return ActionResult(
                        success=False, message="Falta el horario solicitado para agendar."
                    )
                doctor_id = action.doctor_id
                if doctor_id is None and action.specialty:
                    doctor = self._resolve_doctor_for_specialty(
                        db, action.specialty, action.requested_datetime
                    )
                    if doctor is None:
                        return ActionResult(
                            success=False,
                            message=(
                                f"No hay medicos de {action.specialty} disponibles el "
                                f"{action.requested_datetime.isoformat()}."
                            ),
                        )
                    doctor_id = doctor.id
                if doctor_id is None:
                    return ActionResult(
                        success=False,
                        message="Falta el doctor o la especialidad para agendar.",
                    )
                appt = self._appointments.create(
                    db,
                    patient_id=action.patient_id,
                    doctor_id=doctor_id,
                    moment=action.requested_datetime,
                    notes=action.notes,
                )
                doctor = db.get(Doctor, doctor_id)
                doctor_label = doctor.name if doctor else f"doctor {doctor_id}"
                return ActionResult(
                    success=True,
                    message=f"Cita {appt.id} creada con {doctor_label} para el {appt.datetime_.isoformat()}.",
                    data={"appointment_id": appt.id},
                )

            if action.intent == Intent.CANCEL_APPOINTMENT:
                if action.appointment_id is None:
                    return ActionResult(success=False, message="Falta indicar que cita cancelar.")
                appt = self._appointments.cancel(
                    db, action.appointment_id, requesting_patient_id=action.patient_id
                )
                return ActionResult(
                    success=True, message=f"Cita {appt.id} cancelada.", data={"appointment_id": appt.id}
                )

            if action.intent == Intent.RESCHEDULE_APPOINTMENT:
                if action.appointment_id is None or action.requested_datetime is None:
                    return ActionResult(
                        success=False,
                        message="Falta la cita o el nuevo horario para reagendar.",
                    )
                appt = self._appointments.reschedule(
                    db,
                    action.appointment_id,
                    action.requested_datetime,
                    requesting_patient_id=action.patient_id,
                )
                return ActionResult(
                    success=True,
                    message=f"Cita reagendada para el {appt.datetime_.isoformat()} (nueva cita {appt.id}).",
                    data={"appointment_id": appt.id},
                )

            if action.intent == Intent.CHECK_AVAILABILITY:
                if action.requested_datetime is None:
                    return ActionResult(
                        success=False, message="Falta la fecha u hora a consultar."
                    )
                when = action.requested_datetime.isoformat()

                if action.doctor_id is not None:
                    available = self._schedules.is_available(db, action.doctor_id, action.requested_datetime)
                    doctor = db.get(Doctor, action.doctor_id)
                    doctor_label = doctor.name if doctor else f"el doctor {action.doctor_id}"
                    return ActionResult(
                        success=True,
                        message=(
                            f"{doctor_label} SI tiene disponibilidad el {when}."
                            if available
                            else f"{doctor_label} NO tiene disponibilidad el {when}."
                        ),
                        data={"available": available},
                    )

                if action.specialty:
                    free_doctors = self._schedules.available_doctors_for_specialty(
                        db, action.specialty, action.requested_datetime
                    )
                    if free_doctors:
                        names = ", ".join(d.name for d in free_doctors)
                        message = f"Medicos de {action.specialty} disponibles el {when}: {names}."
                    else:
                        message = f"No hay medicos de {action.specialty} disponibles el {when}."
                    return ActionResult(
                        success=True,
                        message=message,
                        data={"available_doctor_ids": [d.id for d in free_doctors]},
                    )

                return ActionResult(
                    success=False, message="Falta el doctor o la especialidad a consultar."
                )

            if action.intent == Intent.JOIN_WAITLIST:
                if not action.specialty:
                    return ActionResult(
                        success=False, message="Falta la especialidad para la lista de espera."
                    )
                entry = self._waitlist.join(
                    db,
                    patient_id=action.patient_id,
                    specialty=action.specialty,
                    doctor_id=action.doctor_id,
                )
                return ActionResult(
                    success=True,
                    message=f"Paciente inscrito en lista de espera de {action.specialty} (id {entry.id}).",
                    data={"waitlist_entry_id": entry.id},
                )

            if action.intent == Intent.ACCEPT_REFERRAL:
                if action.referral_id is None or action.doctor_id is None or action.requested_datetime is None:
                    return ActionResult(
                        success=False,
                        message="Falta informacion para aceptar la derivacion (doctor u horario).",
                    )
                appt = self._referrals.accept(
                    db, action.referral_id, action.doctor_id, action.requested_datetime
                )
                return ActionResult(
                    success=True,
                    message=f"Derivacion {action.referral_id} aceptada; cita {appt.id} creada.",
                    data={"appointment_id": appt.id},
                )

            return ActionResult(success=True, message="No se detecto ninguna accion sobre el sistema.")

        except ClinicFlowError as exc:
            return ActionResult(success=False, message=exc.message)

    def handle_message(
        self, db: Session, patient_id: int, message: str, channel: str = "web"
    ) -> MessageResponse:
        """Procesa un turno completo de conversacion y retorna la respuesta para el paciente."""
        conversation = self._get_or_create_conversation(db, patient_id, channel)

        user_msg = ConversationMessage(
            conversation_id=conversation.id, role="user", content=message
        )
        db.add(user_msg)
        db.commit()
        db.refresh(conversation)

        history = self._history_as_messages(conversation)
        try:
            action = self._action_ai.extract(
                history, patient_id=patient_id, doctors=self._doctors_roster(db)
            )
        except LLMServiceError as exc:
            logger.warning("ActionAI no disponible, se degrada a NONE: %s", exc)
            action = ProposedAction(intent=Intent.NONE, patient_id=patient_id)

        action_result: ActionResult | None = None
        if action.intent != Intent.NONE:
            try:
                self._guard.validate(action, conversation_patient_id=patient_id)
                action_result = self._execute(db, action)
            except SecurityViolationError as exc:
                action_result = ActionResult(success=False, message=str(exc))

        try:
            reply_text = self._front_desk.reply(history, action_result)
        except LLMServiceError as exc:
            # El detalle tecnico (rate limit, timeout, etc.) nunca se muestra
            # al paciente; queda en el log del servidor y, si una accion SI se
            # alcanzo a ejecutar, en action_taken para el panel de admin.
            logger.warning("FrontDeskAI no disponible: %s", exc)
            reply_text = _GENERIC_LLM_FAILURE_REPLY

        assistant_msg = ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=reply_text,
            intent=action.intent.value,
            action_taken=action_result.message if action_result else None,
        )
        db.add(assistant_msg)
        db.commit()

        return MessageResponse(
            conversation_id=conversation.id,
            reply=reply_text,
            intent=action.intent.value,
            action_taken=action_result.message if action_result else None,
        )
