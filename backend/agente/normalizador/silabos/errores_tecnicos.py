"""Technical normalizer exceptions shared by approvals and API layers."""


class AprobacionNoPermitida(RuntimeError):
    """La ejecución técnica no está en un estado seguro para recibir decisiones."""


class DecisionCurricularInvalida(ValueError):
    """La solicitud técnica no cumple el contrato de decisiones."""


class RevisionCurricularInvalida(DecisionCurricularInvalida):
    """La UI está intentando decidir sobre una cola técnica que ya cambió."""
