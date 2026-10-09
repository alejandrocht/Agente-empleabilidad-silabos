"""Respuestas deterministas para probar el chat sin una clave de OpenAI.

El modo demo conserva el contrato público del agente: recibe lenguaje natural,
ejecuta únicamente consultas Cypher de lectura y devuelve una respuesta con la
consulta validada. No intenta interpretar preguntas nuevas con un modelo.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from agente.dashboard.catalogo_oficial import cargar_catalogo_oficial
from agente.nodos.devuelve_respuesta import ReadQueryGateway
from agente.utils.cypher_guard import guard_cypher
from agente.utils.db import normalize_neo4j_value, open_query_gateway


@dataclass(frozen=True, slots=True)
class PreguntaDemo:
    pregunta: str
    cypher: str
    encabezado: str
    columnas: tuple[str, ...]


PREGUNTAS_DEMO: tuple[PreguntaDemo, ...] = (
    PreguntaDemo(
        "¿Qué habilidades enseñadas en Ingeniería Industrial también solicitan "
        "las ofertas dirigidas a esa carrera?",
        """
        MATCH (ca:Carrera)-[:ENSENIA]-(cu:Curso)-[:TIENE]-(cc:Cobertura_Curricular)
              -[:CUBRE]-(h:Habilidad)
        MATCH (ca)-[:DIRIGE_A]-(o:Oferta_Laboral)-[:TIENE]-(r:Requerimiento_Laboral)
              -[:REQUIERE]-(h)
        WHERE toLower(ca.nombre_carrera) = toLower('Ingeniería Industrial')
          AND h.nombre_habilidad IN $habilidades_oficiales
        RETURN h.nombre_habilidad AS habilidad,
               count(DISTINCT cu) AS cursos,
               count(DISTINCT o) AS ofertas
        ORDER BY ofertas DESC, habilidad
        """,
        "Habilidades compartidas por currícula y mercado",
        ("habilidad", "cursos", "ofertas"),
    ),
    PreguntaDemo(
        "¿Qué habilidades solicitan las ofertas de Ingeniería Industrial que no se "
        "enseñan en su currícula?",
        """
        MATCH (ca:Carrera)-[:DIRIGE_A]-(o:Oferta_Laboral)-[:TIENE]-(r:Requerimiento_Laboral)
              -[:REQUIERE]-(h:Habilidad)
        WHERE toLower(ca.nombre_carrera) = toLower('Ingeniería Industrial')
          AND h.nombre_habilidad IN $habilidades_oficiales
        OPTIONAL MATCH (ca)-[:ENSENIA]-(cu:Curso)-[:TIENE]-(cc:Cobertura_Curricular)
                       -[:CUBRE]-(h)
        WITH h, count(DISTINCT o) AS ofertas, count(DISTINCT cc) AS coberturas
        WHERE coberturas = 0
        RETURN h.nombre_habilidad AS habilidad, ofertas
        ORDER BY ofertas DESC, habilidad
        """,
        "Habilidades demandadas sin cobertura curricular",
        ("habilidad", "ofertas"),
    ),
    PreguntaDemo(
        "¿Qué cursos de Ingeniería Industrial cubren habilidades que también solicita el mercado?",
        """
        MATCH (ca:Carrera)-[:ENSENIA]-(cu:Curso)-[:TIENE]-(cc:Cobertura_Curricular)
              -[:CUBRE]-(h:Habilidad)
        MATCH (ca)-[:DIRIGE_A]-(o:Oferta_Laboral)-[:TIENE]-(r:Requerimiento_Laboral)
              -[:REQUIERE]-(h)
        WHERE toLower(ca.nombre_carrera) = toLower('Ingeniería Industrial')
          AND h.nombre_habilidad IN $habilidades_oficiales
        RETURN cu.nombre_curso AS curso,
               count(DISTINCT h) AS habilidades_compartidas,
               count(DISTINCT o) AS ofertas_relacionadas
        ORDER BY habilidades_compartidas DESC, ofertas_relacionadas DESC, curso
        """,
        "Cursos alineados con el mercado",
        ("curso", "habilidades_compartidas", "ofertas_relacionadas"),
    ),
    PreguntaDemo(
        "¿Qué habilidades enseña Ingeniería Industrial que no aparecen en sus ofertas laborales?",
        """
        MATCH (ca:Carrera)-[:ENSENIA]-(cu:Curso)-[:TIENE]-(cc:Cobertura_Curricular)
              -[:CUBRE]-(h:Habilidad)
        WHERE toLower(ca.nombre_carrera) = toLower('Ingeniería Industrial')
          AND h.nombre_habilidad IN $habilidades_oficiales
        OPTIONAL MATCH (ca)-[:DIRIGE_A]-(o:Oferta_Laboral)-[:TIENE]-(r:Requerimiento_Laboral)
                       -[:REQUIERE]-(h)
        WITH h, count(DISTINCT cu) AS cursos, count(DISTINCT o) AS ofertas
        WHERE ofertas = 0
        RETURN h.nombre_habilidad AS habilidad, cursos
        ORDER BY cursos DESC, habilidad
        """,
        "Habilidades curriculares sin demanda observada",
        ("habilidad", "cursos"),
    ),
    PreguntaDemo(
        "¿Qué carreras tienen más habilidades compartidas entre su currícula y el mercado laboral?",
        """
        UNWIND $catalogo_oficial AS oficial
        MATCH (ca:Carrera)-[:ENSENIA]-(cu:Curso)-[:TIENE]-(cc:Cobertura_Curricular)
              -[:CUBRE]-(h:Habilidad)
        MATCH (ca)-[:DIRIGE_A]-(o:Oferta_Laboral)-[:TIENE]-(r:Requerimiento_Laboral)
              -[:REQUIERE]-(h)
        WHERE toLower(ca.nombre_carrera) = toLower(oficial.carrera)
          AND toLower(h.nombre_habilidad) = toLower(oficial.habilidad)
        RETURN ca.nombre_carrera AS carrera,
               count(DISTINCT h) AS habilidades_compartidas,
               count(DISTINCT o) AS ofertas_relacionadas
        ORDER BY habilidades_compartidas DESC, carrera
        """,
        "Carreras con mayor intersección curricular-laboral",
        ("carrera", "habilidades_compartidas", "ofertas_relacionadas"),
    ),
)


def _clave(texto: str) -> str:
    sin_tildes = "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", " ", sin_tildes.lower()).strip()


def encontrar_pregunta_demo(pregunta: str) -> PreguntaDemo | None:
    """Resolve solamente una de las cinco preguntas explícitas del catálogo."""
    clave = _clave(pregunta)
    return next((item for item in PREGUNTAS_DEMO if _clave(item.pregunta) == clave), None)


def _parametros_demo(item: PreguntaDemo) -> dict[str, Any]:
    """Build trusted parameters for demo queries that use the official catalog."""
    catalogo = cargar_catalogo_oficial()
    if "$habilidades_oficiales" in item.cypher:
        return {
            "habilidades_oficiales": [
                concepto["nombre"]
                for concepto in catalogo
                if "Ingeniería Industrial" in concepto["carreras"]
            ]
        }
    if "$catalogo_oficial" in item.cypher:
        return {
            "catalogo_oficial": [
                {"carrera": carrera, "habilidad": concepto["nombre"]}
                for concepto in catalogo
                for carrera in concepto["carreras"]
            ]
        }
    return {}


def _texto(valor: Any, fallback: str = "—") -> str:
    value = normalize_neo4j_value(valor)
    if value is not None and value != "":
        return str(value)
    return fallback


def _respuesta(item: PreguntaDemo, filas: list[dict[str, Any]]) -> str:
    if not filas:
        return f"### {item.encabezado}\n\nNo encontré datos en el grafo para esta consulta."

    lineas = [f"### {item.encabezado}", "", "Resultados encontrados:"]
    primera, *restantes = item.columnas
    etiquetas = {
        "cursos": "cursos",
        "ofertas": "ofertas",
        "habilidades_compartidas": "habilidades compartidas",
        "ofertas_relacionadas": "ofertas relacionadas",
    }
    for indice, fila in enumerate(filas, start=1):
        nombre = _texto(fila.get(primera))
        detalles = " · ".join(
            f"{etiquetas.get(columna, columna)}: {_texto(fila.get(columna), '0')}"
            for columna in restantes
        )
        lineas.append(f"- **{indice}. {nombre}**" + (f": {detalles}" if detalles else ""))
    return "\n".join(lineas)


async def responder_demo(
    pregunta: str,
    *,
    query_gateway: ReadQueryGateway | None = None,
) -> dict[str, Any]:
    """Run one allow-listed demo query using the same read-only gateway."""
    item = encontrar_pregunta_demo(pregunta)
    if item is None:
        disponibles = "\n".join(f"- {item.pregunta}" for item in PREGUNTAS_DEMO)
        raise ValueError("La demo solo acepta estas preguntas:\n" + disponibles)

    parameters = _parametros_demo(item)
    guarded = guard_cypher(item.cypher, parameters, allow_unbounded=True)

    async def ejecutar(gateway: ReadQueryGateway) -> list[dict[str, Any]]:
        resultado = await gateway.run(
            guarded.text,
            guarded.parameters,
            allow_unbounded=True,
        )
        normalizado = normalize_neo4j_value(resultado)
        if not isinstance(normalizado, list) or not all(
            isinstance(fila, Mapping) for fila in normalizado
        ):
            raise TypeError("La consulta demo devolvió filas inválidas")
        return [dict(fila) for fila in normalizado]

    if query_gateway is not None:
        filas = await ejecutar(query_gateway)
    else:
        async with open_query_gateway() as gateway:
            filas = await ejecutar(gateway)

    return {
        "respuesta": _respuesta(item, filas),
        "cypher": guarded.text,
        "filas": filas,
        "fase": "completado",
        "modo": "demo",
    }
