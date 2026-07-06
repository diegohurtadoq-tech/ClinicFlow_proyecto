"""
Servicio de notificaciones. Por ahora es un stub que registra los mensajes
en memoria (y por stdout); el punto de extension para Telegram/Email vive
aqui, sin que el resto del sistema deba cambiar.
"""

from __future__ import annotations


class NotificationService:
    """Envia notificaciones a pacientes. Implementacion actual: registro en memoria."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    def notify(self, patient_id: int, message: str) -> None:
        """Notifica a un paciente. Hoy: log; mañana: Telegram/Email/SMS."""
        self.sent.append((patient_id, message))
        print(f"[notificacion] paciente={patient_id}: {message}")
