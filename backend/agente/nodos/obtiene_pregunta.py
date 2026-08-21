from agente.grafo.estado import Estado
from agente.utils.logger import log_event
from agente.utils.verbose import verbose_step

MAX_PREGUNTA_LOG_CHARS = 120


def obtiene_pregunta(estado: Estado) -> Estado:
    pregunta = estado["pregunta"]
    verbose_step("obtiene_pregunta", "Pregunta recibida", f"length={len(pregunta)}")
    log_event(
        "question",
        "received",
        input_keys=["pregunta"],
        input_size=len(pregunta),
        length=len(pregunta),
    )
    verbose_step("obtiene_pregunta", "Pregunta preparada para validación")
    return {"pregunta": pregunta, "error": None}
