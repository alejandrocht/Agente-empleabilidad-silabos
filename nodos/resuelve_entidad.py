"""
Nodo 3: resuelve_entidad  (USA LLM + Neo4j)

Este es el paso ANTI-ALUCINACION. Tiene dos partes:
  1. El LLM lee la pregunta y detecta que entidades menciono el usuario por nombre
     (ej: "sistemas" -> Carrera, "bcp" -> Empresa).
  2. Para cada entidad, buscamos en Neo4j su id_* REAL.

Para comparar nombres SIN depender de un campo precalculado (nombre_norm), usamos la
funcion apoc.text.clean() de APOC: normaliza el texto (minusculas, sin tildes ni signos)
tanto del lado de la base como del termino buscado. Asi "sistemas" encuentra
"INGENIERIA DE SISTEMAS" aunque no exista la propiedad nombre_norm.
"""
from __future__ import annotations

import json
import unicodedata

from estado import EstadoAgente
from nodos.nodo import NodoLLM
from utils.neo4j import introspeccionar_schema, obtener_driver


def _normalizar(texto: str) -> str:
    """Convierte un texto a minusculas y sin tildes (limpieza basica del lado Python)."""
    # NFKD separa cada letra de su tilde; luego quitamos los signos de tilde (combining).
    descompuesto = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).strip()


def _extraer_json(texto: str) -> dict:
    """Saca el primer bloque JSON del texto que devolvio el LLM (a veces trae adornos)."""
    # Buscamos desde la primera "{" hasta la ultima "}".
    inicio = texto.find("{")
    fin = texto.rfind("}")
    if inicio == -1 or fin == -1 or fin <= inicio:
        # Si no hay JSON, devolvemos estructura vacia.
        return {"entidades": []}
    try:
        return json.loads(texto[inicio:fin + 1])
    except json.JSONDecodeError:
        return {"entidades": []}


def _prop_nombre(props: list[str]) -> str | None:
    """Devuelve cual propiedad hace de 'nombre' en un label (nombre o nombre_*)."""
    # Preferimos la propiedad exacta "nombre" si existe.
    for p in props:
        if p == "nombre":
            return p
    # Si no, la primera tipo "nombre_xxx" (pero nunca nombre_norm).
    for p in props:
        if p.startswith("nombre_") and p != "nombre_norm":
            return p
    # Si el label no tiene ninguna propiedad de nombre, devolvemos None.
    return None


def _prop_id(props: list[str]) -> str | None:
    """Devuelve la primera propiedad tipo id_* del label (su identificador)."""
    for p in props:
        if p.startswith("id_"):
            return p
    return None


class ResuelveEntidad(NodoLLM):
    """Detecta entidades en la pregunta y las resuelve a su id_* real en Neo4j."""

    nombre = "resuelve_entidad"

    def __call__(self, estado: EstadoAgente) -> dict:
        # --- Parte 1: el LLM extrae que entidades menciono el usuario ---
        # Armamos el prompt reemplazando el hueco {pregunta} por la pregunta real.
        # Usamos replace (no format) porque el prompt tiene llaves { } literales de JSON.
        prompt = (
            self.prompt
            .replace("{memoria}", estado.get("memoria_texto", "(sin memoria previa de esta sesion)"))
            .replace("{pregunta}", estado.get("pregunta", ""))
        )
        # Le pedimos al LLM que conteste.
        respuesta = self.llm.invoke(prompt)
        # Sacamos el JSON con la lista de entidades detectadas.
        datos = _extraer_json(str(respuesta.content))
        candidatos = datos.get("entidades", [])

        # Si el LLM no detecto entidades, devolvemos lista vacia y seguimos.
        if not candidatos:
            return {"entidades": []}

        # --- Parte 2: buscamos el id real de cada entidad en Neo4j ---
        intro = introspeccionar_schema()
        entidades_resueltas: list[dict] = []

        with obtener_driver().session() as sesion:
            for candidato in candidatos:
                # Texto a buscar (normalizado) y label opcional sugerido por el LLM.
                texto = _normalizar(candidato.get("texto", ""))
                label = candidato.get("label", "")
                if not texto:
                    continue

                # Decidimos en que labels buscar: el sugerido (si es valido) o todos los
                # que tengan alguna propiedad de nombre.
                if label and label in intro["labels"]:
                    labels_a_buscar = [label]
                else:
                    labels_a_buscar = [
                        l for l, props in intro["props"].items() if _prop_nombre(props)
                    ]

                # Probamos cada label hasta encontrar una coincidencia.
                for lbl in labels_a_buscar:
                    # Detectamos cual es la prop de nombre y cual la de id de este label.
                    prop_nombre = _prop_nombre(intro["props"].get(lbl, []))
                    prop_id = _prop_id(intro["props"].get(lbl, []))
                    # Sin prop de nombre no podemos comparar: pasamos al siguiente label.
                    if not prop_nombre:
                        continue

                    # Partimos el texto en palabras: todas deben aparecer en el nombre.
                    palabras = texto.split()
                    # Comparamos normalizando AMBOS lados con apoc.text.clean (sin tildes,
                    # minusculas, sin signos). Asi no dependemos de nombre_norm.
                    condiciones = [
                        f"apoc.text.clean(n.`{prop_nombre}`) CONTAINS apoc.text.clean($q{i})"
                        for i in range(len(palabras))
                    ]
                    where = " AND ".join(condiciones)

                    # Armamos la consulta: trae el nombre real y el id (si existe).
                    cypher = (
                        f"MATCH (n:`{lbl}`) WHERE {where} "
                        f"RETURN n.`{prop_nombre}` AS nombre"
                        + (f", n.`{prop_id}` AS id" if prop_id else "")
                        + " LIMIT 1"
                    )
                    params = {f"q{i}": palabra for i, palabra in enumerate(palabras)}
                    filas = sesion.execute_read(
                        lambda tx, c=cypher, p=params: [dict(r) for r in tx.run(c, **p)]
                    )

                    # Si encontramos algo, lo guardamos y dejamos de probar mas labels.
                    if filas:
                        fila = filas[0]
                        entidades_resueltas.append({
                            "texto": texto,
                            "label": lbl,
                            "nombre": fila.get("nombre"),
                            "id": fila.get("id"),
                        })
                        break

        # Guardamos en el estado las entidades que logramos resolver.
        return {"entidades": entidades_resueltas}
