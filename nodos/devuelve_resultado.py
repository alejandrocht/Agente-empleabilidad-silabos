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


class DevuelveResultado(Nodo):
    """Prepara la respuesta final (o el mensaje de error) en el estado."""

    nombre = "devuelve_resultado"

    def __call__(self, estado: EstadoAgente) -> dict:
        # Si en algun nodo se guardo un error, ese es el mensaje que mostramos.
        error = estado.get("error")
        if error:
            return {"respuesta": f"Hubo un problema procesando tu solicitud: {error}"}

        # Si no hubo error, usamos la respuesta ya redactada (o un texto por defecto).
        respuesta = estado.get("respuesta", "")
        if not respuesta:
            respuesta = "No encontre una respuesta para tu pregunta."
        return {"respuesta": respuesta}
