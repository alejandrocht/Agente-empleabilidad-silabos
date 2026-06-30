"""
Clases base para todos los nodos del grafo.

Tenemos dos clases base:
  - Nodo: la base de cualquier nodo. Define el "contrato" que todos deben cumplir.
  - NodoLLM: para los nodos que usan el modelo de IA. Les prepara el LLM y su prompt
    automaticamente, asi no repiten ese codigo.

En LangGraph, un nodo es "algo que se puede llamar como funcion" y recibe el estado.
Por eso definimos el metodo especial __call__, que hace que una instancia de la clase
se pueda usar como si fuera una funcion: nodo(estado).
"""
from __future__ import annotations

# Importamos el tipo del estado para anotar los metodos (ayuda a entender el codigo).
from estado import EstadoAgente
# Funciones de utils para preparar el LLM y cargar el prompt del nodo.
from utils.llm import obtener_llm
from utils.prompts import cargar_prompt


class Nodo:
    """Clase base de la que heredan todos los nodos."""

    # Nombre del nodo. Cada nodo hijo lo sobreescribe (ej: "genera_cypher").
    nombre: str = "nodo"

    def __call__(self, estado: EstadoAgente) -> dict:
        """Ejecuta el nodo. Debe devolver un dict con las claves del estado que cambia."""
        # Esta clase base no hace nada: obliga a cada nodo hijo a implementar su logica.
        raise NotImplementedError("Cada nodo debe implementar su propio __call__")


class NodoLLM(Nodo):
    """Base para nodos que usan el modelo de IA (LLM)."""

    def __init__(self) -> None:
        # Creamos el modelo de IA (configurable por .env). Queda guardado en self.llm.
        self.llm = obtener_llm()
        # Cargamos el prompt de este nodo desde prompts/<nombre>.md y lo guardamos.
        self.prompt = cargar_prompt(self.nombre)
