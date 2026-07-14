"""Reconoce, completa y renderiza plantillas Cypher sin usar un LLM."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from agente_ciar.db.neo4j import ejecutar_lectura, introspeccionar_schema
from agente_ciar.plantillas.catalogo import PLANTILLAS, Plantilla

# Estas palabras describen la intención, pero no ayudan a buscar el nombre de una entidad.
_STOPWORDS = {
    "a",
    "al",
    "cual",
    "cuantas",
    "cuantos",
    "carrera",
    "competencia",
    "curso",
    "de",
    "del",
    "el",
    "en",
    "empresa",
    "esa",
    "ese",
    "esta",
    "este",
    "hay",
    "industria",
    "la",
    "las",
    "los",
    "mas",
    "para",
    "por",
    "puesto",
    "que",
    "sector",
    "se",
    "su",
    "tiene",
    "tienen",
    "ensena",
    "ensenan",
    "una",
}

# Las plantillas generales no deben tragarse preguntas con filtros que no representan.
_EXCLUSIONES: dict[str, tuple[str, ...]] = {
    "top_empresas_ofertas": ("dirigid",),
    "herramientas_mas_requeridas": ("dirigid",),
    "herramientas_de_carrera": ("ademas", "ofertas", "piden"),
}


def normalizar(texto: str) -> str:
    """Convierte a minúsculas sin tildes ni signos para comparar intenciones."""
    descompuesto = unicodedata.normalize("NFKD", texto.lower())
    sin_tildes = "".join(
        caracter for caracter in descompuesto if not unicodedata.combining(caracter)
    )
    limpio = " ".join(re.sub(r"[^a-z0-9 ]", " ", sin_tildes).split())
    # Algunas consolas sustituyen la vocal acentuada de ``cuántas/cuántos`` por un separador.
    return re.sub(r"\bcu nt(as|os)\b", r"cuant\1", limpio)


def _coincide(plantilla: Plantilla, pregunta_normalizada: str) -> bool:
    """Indica si al menos un patrón completo está contenido en la pregunta."""
    exclusiones = _EXCLUSIONES.get(plantilla["id"], ())
    if any(fragmento in pregunta_normalizada for fragmento in exclusiones):
        return False
    # Los espacios laterales evitan que ``que facultad`` coincida con ``que facultades``.
    pregunta_delimitada = f" {pregunta_normalizada} "
    return any(f" {patron} " in pregunta_delimitada for patron in plantilla["patrones"])


def _params_ok(plantilla: Plantilla, entidades: list[dict[str, Any]]) -> bool:
    """Comprueba que cada placeholder tenga una entidad del label requerido con id."""
    for ruta in plantilla["params"].values():
        _, label, campo = ruta.split(".")
        if not any(item.get("label") == label and item.get(campo) for item in entidades):
            return False
    return True


def buscar_plantilla(pregunta: str, entidades: list[dict[str, Any]]) -> Plantilla | None:
    """Elige la plantilla coincidente de mayor prioridad que ya tenga sus parámetros."""
    pregunta_normalizada = normalizar(pregunta)
    candidatas = [
        plantilla
        for plantilla in PLANTILLAS
        if _coincide(plantilla, pregunta_normalizada) and _params_ok(plantilla, entidades)
    ]
    return max(candidatas, key=lambda item: item["prioridad"]) if candidatas else None


def buscar_intencion(pregunta: str) -> Plantilla | None:
    """Reconoce la mejor intención aunque todavía falte resolver una entidad requerida."""
    pregunta_normalizada = normalizar(pregunta)
    candidatas = [
        plantilla for plantilla in PLANTILLAS if _coincide(plantilla, pregunta_normalizada)
    ]
    return max(candidatas, key=lambda item: item["prioridad"]) if candidatas else None


def _terminos_busqueda(pregunta: str, plantilla: Plantilla) -> list[str]:
    """Retira el patrón de intención y conserva palabras útiles del nombre mencionado."""
    texto = normalizar(pregunta)
    patrones = sorted(
        (patron for patron in plantilla["patrones"] if patron in texto),
        key=len,
        reverse=True,
    )
    if patrones:
        texto = texto.replace(patrones[0], " ")
    return [token for token in texto.split() if token not in _STOPWORDS and len(token) > 1]


def resolver_entidades(
    plantilla: Plantilla,
    pregunta: str,
    entidades: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Busca ids reales para parámetros faltantes usando nombres del schema, sin OpenAI."""
    resueltas = list(entidades)
    terminos = _terminos_busqueda(pregunta, plantilla)
    if not terminos:
        return resueltas

    intro = introspeccionar_schema()
    for ruta in plantilla["params"].values():
        _, label, campo = ruta.split(".")
        if any(item.get("label") == label and item.get(campo) for item in resueltas):
            continue

        propiedad_nombre = intro["name_props"].get(label)
        propiedades = intro["props"].get(label, [])
        propiedad_id = next((item for item in propiedades if item.startswith("id_")), None)
        if not propiedad_nombre or not propiedad_id:
            continue

        # Labels y propiedades proceden del schema introspectado; el texto siempre va parametrizado.
        cypher = (
            f"MATCH (n:`{label}`) "
            f"WHERE all(termino IN $terminos WHERE "
            f"apoc.text.clean(toString(n.`{propiedad_nombre}`)) CONTAINS termino) "
            f"RETURN n.`{propiedad_nombre}` AS nombre, n.`{propiedad_id}` AS id "
            f"ORDER BY size(toString(n.`{propiedad_nombre}`)) ASC LIMIT 1"
        )
        # Este query interno usa CONTAINS solo para resolver la entidad y nunca llega al estado.
        filas = _ejecutar_resolucion(cypher, {"terminos": terminos})
        if filas:
            resueltas.append(
                {
                    "texto": " ".join(terminos),
                    "label": label,
                    "nombre": filas[0].get("nombre"),
                    "id": filas[0].get("id"),
                }
            )
    return resueltas


def _ejecutar_resolucion(cypher: str, parametros: dict[str, Any]) -> list[dict[str, Any]]:
    """Ejecuta la búsqueda interna saltando solo la prohibición final de ``CONTAINS``."""
    # La consulta empieza con MATCH y no contiene operaciones de escritura; el cliente aplica
    # de nuevo su guarda básica y abre una transacción READ_ACCESS.
    return ejecutar_lectura(cypher, parametros)


def renderizar(plantilla: Plantilla, entidades: list[dict[str, Any]]) -> str:
    """Sustituye cada placeholder con un id real escapado y falla si falta alguno."""
    cypher = plantilla["cypher"]
    for placeholder, ruta in plantilla["params"].items():
        _, label, campo = ruta.split(".")
        entidad = next(
            (item for item in entidades if item.get("label") == label and item.get(campo)),
            None,
        )
        if not entidad:
            raise ValueError(f"Falta la entidad {label} para renderizar {plantilla['id']}")
        valor = str(entidad[campo]).replace("\\", "\\\\").replace("'", "\\'")
        cypher = cypher.replace("{" + placeholder + "}", valor)
    return cypher
