"""
Nodo 8: devuelve_resultado  (no usa LLM)

Es el ultimo nodo. Decide que texto final mostrar:
  - Si hubo un error en el camino, prepara un mensaje de error amable.
  - Si todo salio bien, deja la respuesta que redacto analiza_resultado.

No imprime nada por si mismo: deja la respuesta lista en el estado para que el
loop de consola (main.py) la muestre.
"""
from __future__ import annotations

from estado import EstadoAgente
from nodos.nodo import Nodo
from utils.memoria import actualizar_memoria, formatear_memoria


def _limpieza_turno() -> dict:
    """Quita campos pesados que no deben quedar en el checkpoint de LangGraph."""
    return {
        "schema_texto": None,
        "filas": [],
        "entidades": [],
        "cypher": None,
        "error": None,
        "historial": [],
    }


class DevuelveResultado(Nodo):
    """Prepara la respuesta final (o el mensaje de error) en el estado."""

    nombre = "devuelve_resultado"

    def __call__(self, estado: EstadoAgente) -> dict:
        # Si en algun nodo se guardo un error, ese es el mensaje que mostramos.
        error = estado.get("error")
        if error:
            return {
                "respuesta": f"Hubo un problema procesando tu solicitud: {error}",
                **_limpieza_turno(),
            }

        # Si no hubo error, usamos la respuesta ya redactada (o un texto por defecto).
        respuesta = estado.get("respuesta", "")
        if not respuesta:
            respuesta = "No encontre una respuesta para tu pregunta."
        cambios: dict = {"respuesta": respuesta, **_limpieza_turno()}

        # Si hubo una consulta real al grafo (no saludo, no error), guardamos el turno
        # en la memoria de sesion para resolver referencias implicitas despues.
        if estado.get("cypher"):
            memoria = actualizar_memoria(
                estado.get("id_sesion"),
                {
                    "pregunta": estado.get("pregunta", ""),
                    "respuesta": respuesta,
                    "entidades": estado.get("entidades", []),
                    "cypher": estado.get("cypher", ""),
                },
            )
            cambios["memoria_texto"] = formatear_memoria(memoria)
            cambios["historial"] = []

        return cambios
