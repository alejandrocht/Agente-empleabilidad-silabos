"""
Nodo 5: valida_cypher  (SEGURIDAD, no usa LLM)

Antes de ejecutar la consulta, este nodo revisa que sea segura y correcta:
  - Solo lectura (prohibido CREATE, DELETE, SET, etc. -> protege la base).
  - Sin labels ni relaciones inventados (deben existir en el schema real).
  - Sin CONTAINS ni nombre_norm en el Cypher final (eso lo hace resuelve_entidad).
  - Sin flechas de direccion (-> o <-), para evitar errores de direccion.

Si encuentra un problema, NO lanza excepcion: guarda el mensaje en estado["error"].
El grafo usara ese error para saltarse la ejecucion e ir directo a devolver el error.
"""
from __future__ import annotations

import re

from estado import EstadoAgente
from nodos.nodo import Nodo
from utils.neo4j import introspeccionar_schema, validar_sintaxis

# Una consulta de lectura valida empieza con alguna de estas palabras.
INICIO_LECTURA = ("match", "with", "return", "call db.", "call apoc.meta")

# Palabras que indican ESCRITURA o cambios: estan prohibidas.
PALABRAS_ESCRITURA = {
    "create", "merge", "delete", "detach", "set", "remove", "drop", "load",
    "periodic", "dbms", "constraint", "index",
}


class ValidaCypher(Nodo):
    """Valida que el Cypher sea seguro y respete el schema. Marca error si no."""

    nombre = "valida_cypher"

    def __call__(self, estado: EstadoAgente) -> dict:
        cypher = estado.get("cypher", "")

        # Juntamos todos los problemas encontrados en esta lista.
        problemas: list[str] = []

        # --- 1) Debe empezar como lectura y no contener palabras de escritura ---
        # Pasamos a minusculas y colapsamos espacios para comparar facil.
        plano = re.sub(r"\s+", " ", cypher.lower()).strip()
        if not plano.startswith(INICIO_LECTURA):
            problemas.append("la consulta no empieza como lectura segura (MATCH/WITH/RETURN/CALL db.)")
        # Buscamos palabras de escritura dentro del texto.
        palabras = set(re.findall(r"[a-zA-Z_.]+", plano))
        bloqueadas = sorted(palabras & PALABRAS_ESCRITURA)
        if bloqueadas:
            problemas.append(f"operaciones no permitidas: {', '.join(bloqueadas)}")

        # --- 2) Labels y relaciones deben existir en el schema real ---
        intro = introspeccionar_schema()
        labels_conocidos = set(intro["labels"].keys())
        rels_conocidas = {t["rel"] for t in intro["topology"]}

        # Sacamos los rel types usados: estan dentro de corchetes [:REL].
        rels_usadas: set[str] = set()
        for bloque in re.findall(r"\[[^\]]*\]", cypher):
            m = re.search(r":\s*([\w|`Ññ]+)", bloque)
            if m:
                for token in m.group(1).split("|"):
                    token = token.strip("`").strip()
                    if token and token not in {"r", "rel"}:
                        rels_usadas.add(token)

        # Sacamos los labels usados: estan dentro de parentesis (n:Label).
        labels_usados: set[str] = set()
        for bloque in re.findall(r"\(\s*\w*\s*:\s*([\w:`Ññ]+)", cypher):
            for token in bloque.split(":"):
                token = token.strip("`").strip()
                if token:
                    labels_usados.add(token)

        # Comparamos lo usado contra lo que realmente existe.
        labels_inventados = sorted(labels_usados - labels_conocidos)
        rels_inventadas = sorted(rels_usadas - rels_conocidas)
        if labels_inventados:
            problemas.append(f"labels inventados {labels_inventados}")
        if rels_inventadas:
            problemas.append(f"relaciones inventadas {rels_inventadas}")

        # --- 3) Prohibido buscar por texto en el Cypher final ---
        if re.search(r"\bCONTAINS\b", cypher, re.IGNORECASE):
            problemas.append("CONTAINS no permitido en el Cypher final (usa el id_* de la entidad)")
        if re.search(r"nombre_norm\s*[=:]\s*['\"]", cypher, re.IGNORECASE):
            problemas.append("nombre_norm con igualdad no permitido (usa el id_* de la entidad)")

        # --- 4) Prohibidas las flechas de direccion ---
        if "->" in cypher or "<-" in cypher:
            problemas.append("uso de flechas (-> o <-) no permitido; escribe las relaciones sin direccion")

        # Si hubo problemas de seguridad/esquema, devolvemos el error (sin gastar EXPLAIN).
        if problemas:
            return {"error": "Cypher invalido: " + " | ".join(problemas)}

        # --- 5) Validacion de SINTAXIS con EXPLAIN (no ejecuta, solo compila) ---
        # Atrapa errores como un WHERE mal colocado antes de llegar a ejecutar.
        error_sintaxis = validar_sintaxis(cypher)
        if error_sintaxis:
            return {"error": "Cypher con error de sintaxis: " + error_sintaxis}

        # Si paso todo, no hay error.
        return {"error": None}
