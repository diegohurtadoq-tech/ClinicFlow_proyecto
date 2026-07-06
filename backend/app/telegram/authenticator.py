"""
PatientAuthenticator — gestiona la vinculacion de cuentas de Telegram con
cuentas de pacientes de ClinicFlow mediante codigos de un solo uso.

Los codigos se persisten en la tabla `telegram_link_codes` de la base de
datos, lo que permite que el servidor Uvicorn (que los genera via la web)
y el proceso del bot de Telegram (que los valida) compartan el mismo
almacenamiento sin importar que corran como procesos separados.
"""

from __future__ import annotations

import datetime as dt
import logging
import secrets
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..exceptions import ClinicFlowError
from ..models.telegram_link import TelegramLinkCode
from ..models.user import Patient

logger = logging.getLogger(__name__)

_CODE_EXPIRATION_MINUTES = 10
_MAX_ATTEMPTS_PER_WINDOW = 5
_ATTEMPT_WINDOW_MINUTES = 10

# Rate limiting en memoria (por proceso): solo registra intentos fallidos,
# no codigos, asi que no importa que sea por proceso.
_link_attempts: dict[str, list[dt.datetime]] = {}


class PatientAuthenticator:
    """Maneja la autenticacion de pacientes via Telegram usando codigos de vinculacion."""

    # ─────────────────────────────────────────────
    # API publica
    # ─────────────────────────────────────────────

    def generate_link_code(self, db: Session, patient_id: int) -> str:
        """Genera un codigo de vinculacion unico para un paciente.

        Persiste el codigo en la BD para que sea accesible desde cualquier
        proceso (Uvicorn y bot de Telegram comparten la misma base de datos).
        El codigo expira en 10 minutos y puede usarse una sola vez.
        Un paciente solo puede tener un codigo activo a la vez.
        """
        patient = db.get(Patient, patient_id)
        if patient is None:
            raise ClinicFlowError(f"Paciente {patient_id} no encontrado.")

        # Borrar codigos anteriores del mismo paciente (usados o no)
        db.execute(
            delete(TelegramLinkCode).where(TelegramLinkCode.patient_id == patient_id)
        )
        db.commit()

        # Generar codigo unico de 8 caracteres (mayusculas, sin ambiguos O/0/I/1)
        code = self._generate_unique_code(db)
        expires_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(minutes=_CODE_EXPIRATION_MINUTES)

        db.add(TelegramLinkCode(code=code, patient_id=patient_id, expires_at=expires_at))
        db.commit()

        logger.info(f"Codigo de vinculacion generado para paciente {patient_id}: {code}")
        return code

    def link_telegram_account(
        self, db: Session, telegram_id: str, link_code: str
    ) -> tuple[bool, str, Optional[int]]:
        """Vincula una cuenta de Telegram con una cuenta de paciente usando un codigo.

        Retorna:
            tuple[bool, str, Optional[int]]: (exito, mensaje, patient_id)
        """
        # Normalizar: strip + upper para tolerar espacios y minusculas
        link_code = link_code.strip().upper()

        # Rate limiting
        if not self._check_rate_limit(telegram_id):
            self._record_attempt(telegram_id)
            logger.warning(f"Limite de intentos excedido para telegram_id={telegram_id}")
            return (
                False,
                "Demasiados intentos de vinculacion. Por favor espera 10 minutos e intenta de nuevo.",
                None,
            )

        # Limpiar codigos expirados
        self._cleanup_expired_codes(db)

        # Buscar el codigo en BD
        record = db.scalars(
            select(TelegramLinkCode).where(
                TelegramLinkCode.code == link_code,
                TelegramLinkCode.used == False,  # noqa: E712
            )
        ).first()

        if record is None:
            self._record_attempt(telegram_id)
            logger.warning(f"Codigo invalido o ya usado: {link_code!r}")
            return False, "Codigo de vinculacion invalido o expirado.", None

        # Verificar expiracion usando UTC para consistencia entre procesos
        if dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) > record.expires_at:
            db.delete(record)
            db.commit()
            self._record_attempt(telegram_id)
            logger.warning(f"Codigo expirado: {link_code!r}")
            return False, "Codigo de vinculacion expirado. Genera uno nuevo desde la web.", None

        patient_id = record.patient_id

        # Verificar que el telegram_id no este vinculado a otra cuenta
        existing = db.scalars(
            select(Patient).where(Patient.telegram_id == telegram_id)
        ).first()

        if existing is not None:
            self._record_attempt(telegram_id)
            logger.warning(
                f"telegram_id={telegram_id} ya vinculado a paciente {existing.id}"
            )
            return (
                False,
                f"Tu cuenta de Telegram ya esta vinculada a {existing.name}. "
                "Si necesitas cambiarla, contacta al administrador.",
                None,
            )

        # Obtener el paciente y vincular
        patient = db.get(Patient, patient_id)
        if patient is None:
            db.delete(record)
            db.commit()
            self._record_attempt(telegram_id)
            logger.error(f"Paciente {patient_id} no encontrado al usar codigo {link_code!r}")
            return False, "Error al vincular cuenta. Genera un nuevo codigo.", None

        patient.telegram_id = telegram_id
        record.used = True          # marcar como consumido (auditoria)
        db.delete(record)           # eliminar para no ocupar espacio
        db.commit()

        logger.info(
            f"Vinculacion exitosa: telegram_id={telegram_id} -> paciente {patient_id} ({patient.name})"
        )
        return True, f"Cuenta vinculada exitosamente. ¡Bienvenido/a, {patient.name}!", patient_id

    def get_patient_id(self, db: Session, telegram_id: str) -> Optional[int]:
        """Retorna el patient_id del telegram_id dado, o None si no está vinculado."""
        patient = db.scalars(
            select(Patient).where(Patient.telegram_id == telegram_id)
        ).first()
        return patient.id if patient else None

    def is_linked(self, db: Session, telegram_id: str) -> bool:
        """Retorna True si el telegram_id ya está vinculado a algún paciente."""
        return self.get_patient_id(db, telegram_id) is not None

    # ─────────────────────────────────────────────
    # Helpers privados
    # ─────────────────────────────────────────────

    def _generate_unique_code(self, db: Session) -> str:
        """Genera un codigo de 8 chars que no exista actualmente en la BD."""
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin O, 0, I, 1
        for _ in range(20):  # max 20 intentos (colision practica imposible)
            code = "".join(secrets.choice(alphabet) for _ in range(8))
            exists = db.scalars(
                select(TelegramLinkCode).where(TelegramLinkCode.code == code)
            ).first()
            if exists is None:
                return code
        raise ClinicFlowError("No se pudo generar un codigo unico. Intenta de nuevo.")

    def _cleanup_expired_codes(self, db: Session) -> None:
        """Elimina codigos vencidos de la BD."""
        db.execute(
            delete(TelegramLinkCode).where(
                TelegramLinkCode.expires_at < dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
            )
        )
        db.commit()

    def _check_rate_limit(self, telegram_id: str) -> bool:
        """Devuelve False si el telegram_id superó el limite de intentos fallidos."""
        if telegram_id not in _link_attempts:
            return True
        cutoff = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(minutes=_ATTEMPT_WINDOW_MINUTES)
        recent = [ts for ts in _link_attempts[telegram_id] if ts > cutoff]
        _link_attempts[telegram_id] = recent
        return len(recent) < _MAX_ATTEMPTS_PER_WINDOW

    def _record_attempt(self, telegram_id: str) -> None:
        """Registra un intento fallido para rate limiting."""
        _link_attempts.setdefault(telegram_id, []).append(dt.datetime.now(dt.timezone.utc).replace(tzinfo=None))
