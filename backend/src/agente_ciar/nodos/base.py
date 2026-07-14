"""Clases base pequeñas para los nodos deterministas y los nodos que usan OpenAI."""

from __future__ import annotations

from typing import Any

from agente_ciar.grafo.estado import EstadoAgente
from agente_ciar.llm.fabrica import obtener_llm
from agente_ciar.prompts.cargador import cargar_prompt


class Nodo:
    """Contrato invocable que comparten todos los pasos del grafo."""

    nombre = "nodo"

    def __call__(self, estado: EstadoAgente) -> dict[str, Any]:
        """Ejecuta el paso y devuelve únicamente los campos modificados del estado."""
        raise NotImplementedError("Cada nodo debe implementar su propio __call__")


class NodoLLM(Nodo):
    """Carga el prompt al construir el nodo y el cliente OpenAI en el primer uso real."""

    def __init__(self) -> None:
        # La creación perezosa permite que saludos y plantillas sin LLM funcionen sin gastar API.
        self._llm: Any | None = None
        self.prompt = cargar_prompt(self.nombre)

    @property
    def llm(self) -> Any:
        """Crea una única instancia del modelo configurado para el nombre de este nodo."""
        if self._llm is None:
            self._llm = obtener_llm(self.nombre)
        return self._llm
