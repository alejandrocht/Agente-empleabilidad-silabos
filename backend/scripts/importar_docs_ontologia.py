"""Carga los CSV curriculares de ``empleabilidad_normalizacion/docs`` en Neo4j.

El script usa los nombres de la ontología vigente y es idempotente por
identificador. Antes de escribir valida IDs repetidos, referencias, carreras
existentes y colisiones con nodos ya almacenados. La escritura requiere
``--confirm`` de forma explícita.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase, WRITE_ACCESS

from agente.config.settings import texto


MAPA_CARRERAS = "carrera_id_map.json"


ARCHIVOS: dict[str, tuple[str, tuple[str, ...]]] = {
    "competencias": (
        "catalogo_competencias.csv",
        (
            "id_competencia",
            "nombre_competencia",
            "descripcion_breve",
            "tipo_competencia",
            "codigo_competencia",
        ),
    ),
    "habilidades": (
        "catalogo_habilidades.csv",
        ("id_habilidad", "id_carrera", "nombre_habilidad", "desc_breve"),
    ),
    "logros": ("catalogo_logro.csv", ("id_logro", "logro")),
    "coberturas": (
        "cobertura_curricular.csv",
        (
            "id_cobertura_curricular",
            "id_curso",
            "id_silabo",
            "id_competencia",
            "id_habilidad",
            "id_logro",
        ),
    ),
    "cursos": (
        "curso (2).csv",
        (
            "id_curso",
            "nombre_curso",
            "coordinador",
            "creditos",
            "nivel",
            "tipo_curso",
            "naturaleza",
            "codigo_curso",
            "id_carrera",
        ),
    ),
    "silabos": (
        "silabo (2).csv",
        ("id_silabo", "codigo_silabo", "sumilla", "id_curso", "periodo_academico"),
    ),
}

NODOS: tuple[tuple[str, str, str], ...] = (
    ("Competencia", "id_competencia", "competencias"),
    ("Habilidad", "id_habilidad", "habilidades"),
    ("Logros", "id_logros", "logros"),
    ("Curso", "id_curso", "cursos"),
    ("Silabo", "id_silabo", "silabos"),
)

RESTRICCIONES: tuple[tuple[str, str, str], ...] = (
    ("ciar_docs_competencia_id_unique", "Competencia", "id_competencia"),
    ("ciar_docs_habilidad_id_unique", "Habilidad", "id_habilidad"),
    ("ciar_docs_logros_id_unique", "Logros", "id_logros"),
    ("ciar_docs_curso_id_unique", "Curso", "id_curso"),
    ("ciar_docs_silabo_id_unique", "Silabo", "id_silabo"),
    ("ciar_docs_cobertura_id_unique", "Cobertura_Curricular", "id_cob_curricular"),
)


class ImportacionDocsError(RuntimeError):
    """Error de preflight o publicación que debe detener la carga."""


def _leer_csv(raiz: Path, clave: str) -> list[dict[str, str]]:
    nombre, encabezado = ARCHIVOS[clave]
    ruta = _resolver_ruta_csv(raiz, clave)
    try:
        with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
            lector = csv.DictReader(archivo)
            if lector.fieldnames != list(encabezado):
                raise ImportacionDocsError(
                    f"{nombre}: encabezado inesperado. Se esperaba {list(encabezado)}."
                )
            filas: list[dict[str, str]] = []
            for numero, fila in enumerate(lector, start=2):
                if not fila or all(not str(valor or "").strip() for valor in fila.values()):
                    continue
                if None in fila:
                    raise ImportacionDocsError(f"{nombre}, fila {numero}: columnas adicionales.")
                filas.append({campo: str(fila.get(campo) or "").strip() for campo in encabezado})
            return filas
    except UnicodeDecodeError as exc:
        raise ImportacionDocsError(f"{nombre}: no está codificado como UTF-8.") from exc


def _resolver_ruta_csv(raiz: Path, clave: str) -> Path:
    """Identifica un CSV por encabezado, aunque el nombre tenga sufijos de subida."""

    nombre, encabezado = ARCHIVOS[clave]
    exacta = raiz / nombre
    if exacta.is_file():
        return exacta
    coincidencias: list[Path] = []
    for ruta in sorted(raiz.glob("*.csv")):
        try:
            with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
                if csv.reader(archivo).__next__() == list(encabezado):
                    coincidencias.append(ruta)
        except (OSError, UnicodeDecodeError, StopIteration):
            continue
    if len(coincidencias) == 1:
        return coincidencias[0]
    if not coincidencias:
        raise ImportacionDocsError(
            f"No se encontró un CSV con la estructura de {nombre} en {raiz}."
        )
    raise ImportacionDocsError(
        f"Hay varios CSV candidatos para {nombre}: {[ruta.name for ruta in coincidencias]}."
    )


def cargar_bundle(raiz: Path) -> dict[str, list[dict[str, str]]]:
    raiz = raiz.resolve()
    return {clave: _leer_csv(raiz, clave) for clave in ARCHIVOS}


def cargar_mapeo_carreras(raiz: Path) -> dict[str, str]:
    ruta = raiz / MAPA_CARRERAS
    if not ruta.is_file():
        return {}
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ImportacionDocsError(f"El mapeo de carreras no es JSON válido: {ruta}") from exc
    valores = contenido.get("source_to_target") if isinstance(contenido, dict) else None
    if not isinstance(valores, dict):
        raise ImportacionDocsError(
            f"{ruta.name}: se esperaba el objeto 'source_to_target'."
        )
    mapeo: dict[str, str] = {}
    for origen, destino in valores.items():
        if isinstance(destino, dict):
            destino = destino.get("id_carrera")
        if not isinstance(origen, str) or not isinstance(destino, str) or not destino:
            raise ImportacionDocsError(f"{ruta.name}: mapeo de carrera inválido para {origen!r}.")
        mapeo[origen.strip()] = destino.strip()
    if len(set(mapeo.values())) != len(mapeo):
        raise ImportacionDocsError(f"{ruta.name}: dos IDs fuente apuntan a la misma carrera destino.")
    return mapeo


def aplicar_mapeo_carreras(
    bundle: dict[str, list[dict[str, str]]], mapeo: dict[str, str]
) -> dict[str, str]:
    ids_fuente = {
        fila["id_carrera"]
        for clave in ("cursos", "habilidades")
        for fila in bundle[clave]
        if fila.get("id_carrera")
    }
    if not ids_fuente:
        return {}
    faltantes = sorted(ids_fuente - set(mapeo))
    if faltantes:
        raise ImportacionDocsError(
            f"El mapeo de carreras no cubre todos los IDs fuente: {faltantes}"
        )
    aplicados = {origen: mapeo[origen] for origen in sorted(ids_fuente)}
    for clave in ("cursos", "habilidades"):
        for fila in bundle[clave]:
            fila["id_carrera"] = mapeo[fila["id_carrera"]]
    return aplicados


def _ids(filas: list[dict[str, str]], campo: str) -> list[str]:
    return [fila.get(campo, "") for fila in filas]


def validar_local(bundle: dict[str, list[dict[str, str]]]) -> list[str]:
    errores: list[str] = []
    campos_id = {
        "competencias": "id_competencia",
        "habilidades": "id_habilidad",
        "logros": "id_logro",
        "coberturas": "id_cobertura_curricular",
        "cursos": "id_curso",
        "silabos": "id_silabo",
    }
    for clave, campo in campos_id.items():
        valores = _ids(bundle[clave], campo)
        vacios = sum(not valor for valor in valores)
        repetidos = [valor for valor, total in Counter(valores).items() if valor and total > 1]
        if vacios:
            errores.append(f"{clave}: {vacios} filas sin {campo}.")
        if repetidos:
            errores.append(f"{clave}: IDs repetidos: {repetidos[:5]}.")

    cursos = {fila["id_curso"] for fila in bundle["cursos"]}
    silabos = {fila["id_silabo"]: fila["id_curso"] for fila in bundle["silabos"]}
    competencias = {fila["id_competencia"] for fila in bundle["competencias"]}
    habilidades = {fila["id_habilidad"] for fila in bundle["habilidades"]}
    logros = {fila["id_logro"] for fila in bundle["logros"]}
    carreras = {fila["id_carrera"] for fila in bundle["cursos"]} | {
        fila["id_carrera"] for fila in bundle["habilidades"]
    }

    for fila in bundle["silabos"]:
        if fila["id_curso"] not in cursos:
            errores.append(
                f"silabos: {fila['id_silabo']} referencia curso inexistente {fila['id_curso']}."
            )
    claves_cobertura: Counter[tuple[str, ...]] = Counter()
    for fila in bundle["coberturas"]:
        if fila["id_curso"] not in cursos:
            errores.append(f"coberturas: curso inexistente {fila['id_curso']}.")
        if fila["id_silabo"] not in silabos:
            errores.append(f"coberturas: sílabo inexistente {fila['id_silabo']}.")
        elif silabos[fila["id_silabo"]] != fila["id_curso"]:
            errores.append(
                f"coberturas: {fila['id_cobertura_curricular']} no coincide con el curso del sílabo."
            )
        if fila["id_competencia"] and fila["id_competencia"] not in competencias:
            errores.append(f"coberturas: competencia inexistente {fila['id_competencia']}.")
        if fila["id_habilidad"] and fila["id_habilidad"] not in habilidades:
            errores.append(f"coberturas: habilidad inexistente {fila['id_habilidad']}.")
        if fila["id_logro"] and fila["id_logro"] not in logros:
            errores.append(f"coberturas: logro inexistente {fila['id_logro']}.")
        if bool(fila["id_competencia"]) == bool(fila["id_habilidad"]):
            errores.append(
                f"coberturas: {fila['id_cobertura_curricular']} debe tener competencia o habilidad, no ambas."
            )
        claves_cobertura[
            tuple(fila[campo] for campo in ARCHIVOS["coberturas"][1][1:])
        ] += 1
    repetidas = [clave for clave, total in claves_cobertura.items() if total > 1]
    if repetidas:
        errores.append(f"coberturas: combinaciones repetidas: {repetidas[:3]}.")
    if not carreras:
        errores.append("No se encontraron referencias a carreras.")
    return errores


def _conexion() -> Any:
    uri = texto("NEO4J_INGEST_URI") or texto("NEO4J_URI")
    usuario = texto("NEO4J_INGEST_USER") or texto("NEO4J_USER")
    contrasena = texto("NEO4J_INGEST_PASSWORD") or texto("NEO4J_PASSWORD")
    base = texto("NEO4J_INGEST_DATABASE") or texto("NEO4J_DATABASE", "neo4j")
    if not uri or not usuario or not contrasena:
        raise ImportacionDocsError("Faltan las credenciales de ingestión Neo4j.")
    driver = GraphDatabase.driver(uri, auth=(usuario, contrasena))
    driver.verify_connectivity()
    return driver, base


def _conteos(session: Any) -> dict[str, int]:
    return {
        str(fila["label"]): int(fila["total"])
        for fila in session.run(
            "MATCH (n) UNWIND labels(n) AS label "
            "RETURN label, count(n) AS total ORDER BY label"
        )
        if fila["label"]
    }


def _duplicados(session: Any) -> list[dict[str, Any]]:
    encontrados: list[dict[str, Any]] = []
    campos = [(label, campo) for label, campo, _ in NODOS]
    campos += [
        ("Cobertura_Curricular", "id_cob_curricular"),
        ("Cobertura_Curricular", "id_cobertura_curricular"),
        ("Logros", "id_herramienta"),
    ]
    for label, campo in campos:
        consulta = (
            f"MATCH (n:`{label}`) WHERE n.`{campo}` IS NOT NULL AND n.`{campo}` <> '' "
            f"WITH n.`{campo}` AS id, count(*) AS total WHERE total > 1 "
            "RETURN id, total ORDER BY total DESC LIMIT 20"
        )
        for fila in session.run(consulta):
            encontrados.append({"label": label, "propiedad": campo, **dict(fila)})
    return encontrados


def _faltantes(session: Any, label: str, campo: str, valores: list[str]) -> list[str]:
    consulta = (
        f"UNWIND $ids AS id OPTIONAL MATCH (n:`{label}`) WHERE n.`{campo}` = id "
        "WITH id, count(n) AS total WHERE total <> 1 RETURN id, total ORDER BY id"
    )
    return [str(fila["id"]) for fila in session.run(consulta, ids=valores)]


def _faltantes_coberturas(session: Any, valores: list[str]) -> list[str]:
    consulta = (
        "UNWIND $ids AS id OPTIONAL MATCH (n:Cobertura_Curricular) "
        "WHERE n.id_cob_curricular = id OR n.id_cobertura_curricular = id "
        "WITH id, count(n) AS total WHERE total <> 1 RETURN id, total ORDER BY id"
    )
    return [str(fila["id"]) for fila in session.run(consulta, ids=valores)]


def _colisiones_coberturas(session: Any, valores: list[str]) -> list[dict[str, Any]]:
    consulta = (
        "MATCH (n:Cobertura_Curricular) "
        "UNWIND [n.id_cob_curricular, n.id_cobertura_curricular] AS id "
        "WITH id, collect(DISTINCT elementId(n)) AS nodos "
        "WHERE id IN $ids AND size(nodos) > 1 "
        "RETURN id, size(nodos) AS total ORDER BY id"
    )
    return [dict(fila) for fila in session.run(consulta, ids=valores)]


def _filas_nodo(bundle: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]:
    return {
        "Competencia": [
            {
                "id_competencia": fila["id_competencia"],
                "nombre_competencia": fila["nombre_competencia"],
                "descripcion_breve": fila["descripcion_breve"],
                "tipo_competencia": fila["tipo_competencia"],
                "codigo_competencia": fila["codigo_competencia"],
            }
            for fila in bundle["competencias"]
        ],
        "Habilidad": [
            {
                "id_habilidad": fila["id_habilidad"],
                "nombre_habilidad": fila["nombre_habilidad"],
                "descripcion_breve": fila["desc_breve"],
            }
            for fila in bundle["habilidades"]
        ],
        "Logros": [
            {"id_logros": fila["id_logro"], "logro": fila["logro"]}
            for fila in bundle["logros"]
        ],
        "Curso": [
            {
                campo: fila[campo]
                for campo in (
                    "id_curso",
                    "nombre_curso",
                    "coordinador",
                    "creditos",
                    "nivel",
                    "tipo_curso",
                    "codigo_curso",
                )
            }
            for fila in bundle["cursos"]
        ],
        "Silabo": [
            {campo: fila[campo] for campo in ("id_silabo", "codigo_silabo", "sumilla")}
            for fila in bundle["silabos"]
        ],
    }


def _conflictos_existentes(session: Any, filas: dict[str, list[dict[str, str]]]) -> list[dict[str, Any]]:
    conflictos: list[dict[str, Any]] = []
    for label, campo, _ in NODOS:
        esperados = {fila[campo]: fila for fila in filas[label]}
        if not esperados:
            continue
        for registro in session.run(
            f"MATCH (n:`{label}`) WHERE n.`{campo}` IN $ids RETURN n",
            ids=list(esperados),
        ):
            nodo = dict(registro["n"])
            esperado = esperados.get(str(nodo.get(campo)))
            if esperado is None:
                continue
            diferencias = {
                clave: {"neo4j": nodo.get(clave, ""), "archivo": valor}
                for clave, valor in esperado.items()
                if str(nodo.get(clave, "") or "") != str(valor or "")
            }
            if diferencias:
                conflictos.append({"label": label, "id": nodo.get(campo), "diferencias": diferencias})
    return conflictos


def preflight(session: Any, bundle: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    errores = validar_local(bundle)
    if errores:
        raise ImportacionDocsError("; ".join(errores[:10]))

    ids_carreras = sorted({fila["id_carrera"] for fila in bundle["cursos"]})
    ids_carreras += sorted(
        {fila["id_carrera"] for fila in bundle["habilidades"] if fila["id_carrera"] not in ids_carreras}
    )
    carreras_faltantes = _faltantes(session, "Carrera", "id_carrera", ids_carreras)
    if carreras_faltantes:
        raise ImportacionDocsError(
            f"La base no contiene las carreras referenciadas: {carreras_faltantes[:10]}"
        )

    duplicados = _duplicados(session)
    if duplicados:
        raise ImportacionDocsError(
            "La base ya contiene identificadores duplicados en el modelo objetivo: "
            + json.dumps(duplicados[:10], ensure_ascii=False)
        )

    ids_cobertura = _ids(bundle["coberturas"], "id_cobertura_curricular")
    colisiones_cobertura = _colisiones_coberturas(session, ids_cobertura)
    if colisiones_cobertura:
        raise ImportacionDocsError(
            "Hay coberturas con el mismo ID en más de un nodo: "
            + json.dumps(colisiones_cobertura[:10], ensure_ascii=False)
        )

    filas_nodo = _filas_nodo(bundle)
    existentes = {
        label: len(
            list(
                session.run(
                    f"MATCH (n:`{label}`) WHERE n.`{campo}` IN $ids RETURN n",
                    ids=[fila[campo] for fila in filas],
                )
            )
        )
        for label, campo, _ in NODOS
        for filas in [filas_nodo[label]]
    }
    conflictos = _conflictos_existentes(session, filas_nodo)
    return {
        "filas_fuente": {clave: len(filas) for clave, filas in bundle.items()},
        "ids_existentes_preservados": existentes,
        "conflictos_de_atributos_preservados": conflictos,
        "duplicados_detectados": [],
        "carreras_verificadas": len(ids_carreras),
    }


def _crear_restricciones(session: Any) -> None:
    for nombre, label, campo in RESTRICCIONES:
        session.run(
            f"CREATE CONSTRAINT {nombre} IF NOT EXISTS "
            f"FOR (n:`{label}`) REQUIRE n.`{campo}` IS UNIQUE"
        ).consume()


def _normalizar_clave_cobertura(session: Any) -> int:
    fila = session.run(
        "MATCH (n:Cobertura_Curricular) "
        "WHERE n.id_cob_curricular IS NULL AND n.id_cobertura_curricular IS NOT NULL "
        "SET n.id_cob_curricular = n.id_cobertura_curricular "
        "RETURN count(n) AS total"
    ).single()
    return int(fila["total"] if fila else 0)


def _escribir_tx(tx: Any, bundle: dict[str, list[dict[str, str]]]) -> int:
    filas = _filas_nodo(bundle)
    for label, campo, _ in NODOS:
        rows = filas[label]
        if not rows:
            continue
        tx.run(
            f"UNWIND $rows AS row MERGE (n:`{label}` {{`{campo}`: row.`{campo}`}}) "
            "ON CREATE SET n += row",
            rows=rows,
        ).consume()

    fila_carreras = tx.run(
        "UNWIND $rows AS row MATCH (cu:Curso {id_curso: row.id_curso}) "
        "OPTIONAL MATCH (antigua:Carrera)-[rel:ENSENIA]->(cu) "
        "WHERE antigua.id_carrera <> row.id_carrera "
        "WITH row, cu, [item IN collect(rel) WHERE item IS NOT NULL] AS relaciones "
        "FOREACH (item IN relaciones | DELETE item) "
        "SET cu.id_carrera = row.id_carrera "
        "RETURN sum(size(relaciones)) AS total",
        rows=bundle["cursos"],
    ).single()
    relaciones_carrera_corregidas = int(fila_carreras["total"] if fila_carreras else 0)

    tx.run(
        "UNWIND $rows AS row MATCH (ca:Carrera {id_carrera: row.id_carrera}) "
        "MATCH (cu:Curso {id_curso: row.id_curso}) MERGE (ca)-[:ENSENIA]->(cu)",
        rows=bundle["cursos"],
    ).consume()
    tx.run(
        "UNWIND $rows AS row MATCH (cu:Curso {id_curso: row.id_curso}) "
        "MATCH (si:Silabo {id_silabo: row.id_silabo}) MERGE (cu)-[:TIENE]->(si)",
        rows=bundle["silabos"],
    ).consume()

    coberturas = bundle["coberturas"]
    tx.run(
        "UNWIND $rows AS row "
        "MERGE (co:Cobertura_Curricular {id_cob_curricular: row.id_cobertura_curricular})",
        rows=coberturas,
    ).consume()
    tx.run(
        "UNWIND $rows AS row MATCH (cu:Curso {id_curso: row.id_curso}) "
        "MATCH (co:Cobertura_Curricular {id_cob_curricular: row.id_cobertura_curricular}) "
        "MERGE (cu)-[:TIENE]->(co)",
        rows=coberturas,
    ).consume()
    tx.run(
        "UNWIND $rows AS row MATCH (si:Silabo {id_silabo: row.id_silabo}) "
        "MATCH (co:Cobertura_Curricular {id_cob_curricular: row.id_cobertura_curricular}) "
        "MERGE (si)-[:DECLARA]->(co)",
        rows=coberturas,
    ).consume()

    relaciones = (
        ("id_competencia", "Competencia", "id_competencia", "CUBRE"),
        ("id_habilidad", "Habilidad", "id_habilidad", "CUBRE"),
        ("id_logro", "Logros", "id_logros", "CUBRE"),
    )
    for campo_fuente, label, campo_destino, tipo in relaciones:
        rows = [fila for fila in coberturas if fila[campo_fuente]]
        if not rows:
            continue
        tx.run(
            f"UNWIND $rows AS row MATCH (co:Cobertura_Curricular {{id_cob_curricular: row.id_cobertura_curricular}}) "
            f"MATCH (destino:`{label}` {{`{campo_destino}`: row.`{campo_fuente}`}}) "
            f"MERGE (co)-[:{tipo}]->(destino)",
            rows=rows,
        ).consume()

    rows_habilidad = [fila for fila in coberturas if fila["id_habilidad"]]
    if rows_habilidad:
        for origen, tipo in (("Curso", "DESARROLLA"), ("Silabo", "DECLARA")):
            origen_id = "id_curso" if origen == "Curso" else "id_silabo"
            origen_label = "Curso" if origen == "Curso" else "Silabo"
            tx.run(
                f"UNWIND $rows AS row MATCH (origen:`{origen_label}` {{`{origen_id}`: row.`{origen_id}`}}) "
                "MATCH (habilidad:Habilidad {id_habilidad: row.id_habilidad}) "
                f"MERGE (origen)-[:{tipo}]->(habilidad)",
                rows=rows_habilidad,
            ).consume()

    return relaciones_carrera_corregidas


def _relacion_faltante(session: Any, filas: list[dict[str, str]], tipo: str, origen: str, destino: str) -> int:
    if not filas:
        return 0
    origen_id, destino_id = {
        ("Carrera", "Curso"): ("id_carrera", "id_curso"),
        ("Curso", "Silabo"): ("id_curso", "id_silabo"),
        ("Curso", "Cobertura_Curricular"): ("id_curso", "id_cobertura_curricular"),
        ("Silabo", "Cobertura_Curricular"): ("id_silabo", "id_cobertura_curricular"),
        ("Cobertura_Curricular", "Competencia"): ("id_cobertura_curricular", "id_competencia"),
        ("Cobertura_Curricular", "Habilidad"): ("id_cobertura_curricular", "id_habilidad"),
        ("Cobertura_Curricular", "Logros"): ("id_cobertura_curricular", "id_logro"),
        ("Curso", "Habilidad"): ("id_curso", "id_habilidad"),
        ("Silabo", "Habilidad"): ("id_silabo", "id_habilidad"),
    }[(origen, destino)]
    destino_prop = (
        "id_logros"
        if destino == "Logros"
        else "id_cob_curricular"
        if destino == "Cobertura_Curricular"
        else destino_id
    )
    origen_prop = "id_cob_curricular" if origen == "Cobertura_Curricular" else origen_id
    consulta = (
        f"UNWIND $rows AS row OPTIONAL MATCH (a:`{origen}` {{`{origen_prop}`: row.`{origen_id}`}}) "
        f"OPTIONAL MATCH (b:`{destino}` {{`{destino_prop}`: row.`{destino_id}`}}) "
        f"OPTIONAL MATCH (a)-[r:{tipo}]->(b) WITH row, count(r) AS total "
        "WHERE total <> 1 RETURN count(*) AS total"
    )
    fila = session.run(consulta, rows=filas).single()
    return int(fila["total"] if fila else 0)


def verificar(session: Any, bundle: dict[str, list[dict[str, str]]], antes: dict[str, int]) -> dict[str, Any]:
    ids_por_nodo = {
        "Competencia": ("id_competencia", _ids(bundle["competencias"], "id_competencia")),
        "Habilidad": ("id_habilidad", _ids(bundle["habilidades"], "id_habilidad")),
        "Logros": ("id_logros", _ids(bundle["logros"], "id_logro")),
        "Curso": ("id_curso", _ids(bundle["cursos"], "id_curso")),
        "Silabo": ("id_silabo", _ids(bundle["silabos"], "id_silabo")),
    }
    faltantes = {
        label: _faltantes(session, label, campo, ids)
        for label, (campo, ids) in ids_por_nodo.items()
    }
    faltantes["Cobertura_Curricular"] = _faltantes_coberturas(
        session, _ids(bundle["coberturas"], "id_cobertura_curricular")
    )
    coberturas = bundle["coberturas"]
    relaciones = {
        "ENSENIA": _relacion_faltante(session, bundle["cursos"], "ENSENIA", "Carrera", "Curso"),
        "Curso-TIENE-Silabo": _relacion_faltante(session, bundle["silabos"], "TIENE", "Curso", "Silabo"),
        "Curso-TIENE-Cobertura": _relacion_faltante(session, coberturas, "TIENE", "Curso", "Cobertura_Curricular"),
        "Silabo-DECLARA-Cobertura": _relacion_faltante(session, coberturas, "DECLARA", "Silabo", "Cobertura_Curricular"),
        "Cobertura-CUBRE-Competencia": _relacion_faltante(session, [r for r in coberturas if r["id_competencia"]], "CUBRE", "Cobertura_Curricular", "Competencia"),
        "Cobertura-CUBRE-Habilidad": _relacion_faltante(session, [r for r in coberturas if r["id_habilidad"]], "CUBRE", "Cobertura_Curricular", "Habilidad"),
        "Cobertura-CUBRE-Logros": _relacion_faltante(session, [r for r in coberturas if r["id_logro"]], "CUBRE", "Cobertura_Curricular", "Logros"),
        "Curso-DESARROLLA-Habilidad": _relacion_faltante(session, [r for r in coberturas if r["id_habilidad"]], "DESARROLLA", "Curso", "Habilidad"),
        "Silabo-DECLARA-Habilidad": _relacion_faltante(session, [r for r in coberturas if r["id_habilidad"]], "DECLARA", "Silabo", "Habilidad"),
    }
    return {
        "conteos_antes": antes,
        "conteos_despues": _conteos(session),
        "duplicados_ids": _duplicados(session),
        "ids_faltantes": {clave: valor for clave, valor in faltantes.items() if valor},
        "relaciones_faltantes": {clave: valor for clave, valor in relaciones.items() if valor},
        "ok": not any(faltantes.values()) and not any(relaciones.values()) and not _duplicados(session),
    }


def ejecutar(raiz: Path, confirmar: bool) -> dict[str, Any]:
    bundle = cargar_bundle(raiz)
    mapeo_carreras = aplicar_mapeo_carreras(bundle, cargar_mapeo_carreras(raiz))
    driver, database = _conexion()
    try:
        with driver.session(database=database, default_access_mode=WRITE_ACCESS) as session:
            antes = _conteos(session)
            resumen = preflight(session, bundle)
            resumen["mapeo_carreras_aplicado"] = mapeo_carreras
            if not confirmar:
                return {"modo": "previsualizacion", "preflight": resumen, "conteos": antes}

            migradas = _normalizar_clave_cobertura(session)
            _crear_restricciones(session)
            relaciones_carrera_corregidas = session.execute_write(_escribir_tx, bundle)
            resultado = verificar(session, bundle, antes)
            resultado["modo"] = "importacion"
            resultado["coberturas_clave_normalizadas"] = migradas
            resultado["relaciones_carrera_corregidas"] = relaciones_carrera_corregidas
            resultado["preflight"] = resumen
            if not resultado["ok"]:
                raise ImportacionDocsError(
                    "La verificación posterior a la carga detectó inconsistencias: "
                    + json.dumps(resultado, ensure_ascii=False)
                )
            return resultado
    finally:
        driver.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "empleabilidad_normalizacion" / "docs",
    )
    parser.add_argument("--confirm", action="store_true", help="Confirma la escritura en Neo4j.")
    argumentos = parser.parse_args()
    try:
        resultado = ejecutar(argumentos.docs_dir, argumentos.confirm)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
