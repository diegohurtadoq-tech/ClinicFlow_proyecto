"""
Jerarquia de usuarios: Admin, Recepcionista, Medico y Paciente heredan de
una base comun `User`. Se usa herencia de tabla unica (single-table) de
SQLAlchemy: una sola tabla `users` con una columna discriminadora `role`,
y cada subclase agrega sus propios campos especificos (nulos para las
demas).

Esto demuestra herencia + polimorfismo: cualquier consulta sobre `User`
devuelve instancias del subtipo correcto (`Patient`, `Doctor`, etc.) segun
el valor de `role`.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class User(Base):
    """Clase base de todo usuario del sistema. No se instancia directamente."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(120), unique=True)
    role: Mapped[str] = mapped_column(String(20))
    # Nulo para usuarios creados administrativamente sin acceso de login propio
    # (p.ej. un paciente ingresado por recepcion via POST /api/patients).
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Solo relevante para Doctor: "eliminar" a un doctor lo desactiva en vez de
    # borrarlo (conserva citas, derivaciones y bloqueos historicos intactos;
    # ver Doctor.deactivate()). Otros roles simplemente no usan este campo.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    # Campos especificos de subclases (nulos cuando no aplican)
    specialty: Mapped[str | None] = mapped_column(String(80), nullable=True)  # Doctor
    rut: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Patient
    telegram_id: Mapped[str | None] = mapped_column(String(40), nullable=True)  # Patient

    __mapper_args__ = {
        "polymorphic_identity": "user",
        "polymorphic_on": "role",
    }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id}, name={self.name!r})"


class Patient(User):
    """Paciente: puede solicitar citas, cancelar, reagendar e ingresar a listas de espera."""

    __mapper_args__ = {"polymorphic_identity": "patient"}

    appointments: Mapped[list["Appointment"]] = relationship(  # noqa: F821
        back_populates="patient",
        foreign_keys="Appointment.patient_id",
    )


class Doctor(User):
    """Medico: posee una Agenda (Schedule) compuesta de Citas y Bloqueos."""

    __mapper_args__ = {"polymorphic_identity": "doctor"}

    schedules: Mapped[list["Schedule"]] = relationship(  # noqa: F821
        back_populates="doctor",
        cascade="all, delete-orphan",
    )

    def deactivate(self) -> None:
        """"Elimina" al doctor sin borrar su registro: deja de ofrecerse para
        nuevas citas (ScheduleService.is_available lo excluye), pero su
        historial de citas, derivaciones y bloqueos permanece intacto."""
        self.is_active = False


class Receptionist(User):
    """Recepcionista: gestiona citas, listas de espera y agendas clinicas."""

    __mapper_args__ = {"polymorphic_identity": "receptionist"}


class Admin(User):
    """Administrador: acceso completo al sistema."""

    __mapper_args__ = {"polymorphic_identity": "admin"}
