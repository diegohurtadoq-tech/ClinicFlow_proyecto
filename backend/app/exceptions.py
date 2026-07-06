"""
Excepciones personalizadas del dominio ClinicFlow.

Cada excepcion lleva un status_code HTTP asociado, para que los routers
(o un manejador global en main.py) puedan traducirlas directamente a
respuestas HTTP sin tener que conocer los detalles de cada regla de negocio.
"""


class ClinicFlowError(Exception):
    """Excepcion base del sistema ClinicFlow."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code

    def __str__(self) -> str:
        return f"[{self.__class__.__name__}] {self.message}"


class NotFoundError(ClinicFlowError):
    """Una entidad solicitada (paciente, cita, agenda, etc.) no existe."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=404)


class ScheduleConflictError(ClinicFlowError):
    """El horario solicitado no esta disponible (choque de agenda o bloqueo)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=409)


class InvalidStateTransitionError(ClinicFlowError):
    """Se intento una transicion de estado invalida sobre una Cita."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=409)


class AuthenticationError(ClinicFlowError):
    """No hay sesion valida: falta el token, esta mal formado, o expiro/es invalido."""

    def __init__(self, message: str = "No autenticado.") -> None:
        super().__init__(message, status_code=401)


class SecurityViolationError(ClinicFlowError):
    """
    El ActionGuard rechazo una accion propuesta por la IA antes de que
    llegara a tocar la base de datos (suplantacion de paciente, patron de
    inyeccion, accion fuera de la lista permitida, etc.).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=403)


class LLMServiceError(ClinicFlowError):
    """Error al comunicarse con el proveedor de LLM (OpenRouter)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=503)


class InvalidModelError(LLMServiceError):
    """Modelo de LLM no reconocido o no disponible."""

    def __init__(self, model: str) -> None:
        super().__init__(f"El modelo '{model}' no es valido o no esta disponible.")
        self.model = model
