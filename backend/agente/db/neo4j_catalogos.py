"""Neo4j writer for the canonical five-file syllabus curriculum contract."""

from __future__ import annotations

import csv
import importlib
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

_salida_catalogos = importlib.import_module("agente.normalizador.silabos.salida_catalogos")
ARCHIVOS_CATALOGO: tuple[tuple[str, tuple[str, ...]], ...] = _salida_catalogos.ARCHIVOS_CATALOGO

_ID_PATTERNS = {
    "id_curso": re.compile(r"CUR_[0-9a-f]{16}"),
    "id_silabo": re.compile(r"SIL_[0-9a-f]{16}"),
    "id_competencia": re.compile(r"COMP_[0-9a-f]{16}"),
    "id_logro": re.compile(r"LOGRO_[0-9a-f]{16}"),
    "id_cob_curricular": re.compile(r"COB_CUR_[0-9a-f]{16}"),
    "id_carrera": re.compile(r"CAR_[0-9a-f]{16}"),
}


class TransaccionNeo4j(Protocol):
    def run(self, cypher: str, parametros: Mapping[str, object]) -> Iterable[Any]: ...


def leer_catalogos(directorio: Path) -> dict[str, list[dict[str, str]]]:
    """Read only the five CSV artifacts authorized by the technical contract."""

    raiz = directorio.resolve()
    if not raiz.is_dir():
        raise ValueError("No existe el directorio de catálogos curriculares")
    filas: dict[str, list[dict[str, str]]] = {}
    for nombre, columnas in ARCHIVOS_CATALOGO:
        ruta = (raiz / nombre).resolve()
        if ruta.parent != raiz or not ruta.is_file():
            raise ValueError(f"Falta el catálogo requerido: {nombre}")
        with ruta.open(encoding="utf-8-sig", newline="") as archivo:
            lector = csv.DictReader(archivo)
            if tuple(lector.fieldnames or ()) != columnas:
                raise ValueError(f"Esquema inválido para {nombre}")
            contenido = [
                {columna: str(fila.get(columna) or "") for columna in columnas} for fila in lector
            ]
        if len(contenido) > 100_000:
            raise ValueError(f"{nombre} excede el límite de filas")
        filas[nombre] = contenido
    _validar_ids(filas)
    return filas


def _validar_ids(filas: Mapping[str, list[dict[str, str]]]) -> None:
    for nombre, contenido in filas.items():
        for numero, fila in enumerate(contenido, start=2):
            for campo, patron in _ID_PATTERNS.items():
                valor = fila.get(campo, "")
                if valor and patron.fullmatch(valor) is None:
                    raise ValueError(f"{nombre}:{numero} contiene {campo} inválido")
    ids_curso = {fila["id_curso"] for fila in filas["curso.csv"]}
    ids_silabo = {fila["id_silabo"] for fila in filas["silabo.csv"]}
    ids_competencia = {fila["id_competencia"] for fila in filas["catalogo_competencias.csv"]}
    ids_logro = {fila["id_logro"] for fila in filas["catalogo_logros.csv"]}
    for fila in filas["silabo.csv"]:
        if fila["id_curso"] not in ids_curso:
            raise ValueError("silabo.csv referencia un curso inexistente")
    for fila in filas["cobertura_curricular.csv"]:
        if fila["id_curso"] not in ids_curso or fila["id_silabo"] not in ids_silabo:
            raise ValueError("cobertura_curricular.csv referencia curso o sílabo inexistente")
        if fila["id_competencia"] and fila["id_competencia"] not in ids_competencia:
            raise ValueError("cobertura_curricular.csv referencia una competencia inexistente")
        if fila["id_logro"] and fila["id_logro"] not in ids_logro:
            raise ValueError("cobertura_curricular.csv referencia un logro inexistente")
        if fila["id_logro"] and not fila["id_competencia"]:
            raise ValueError("Todo logro debe relacionarse con una competencia")
        if not fila["id_competencia"] and not fila["id_logro"]:
            raise ValueError("Una cobertura debe relacionar una competencia o un logro")


def _total(resultado: Iterable[Any]) -> int:
    for registro in resultado:
        valor = registro.get("total", 0) if hasattr(registro, "get") else 0
        try:
            return int(valor)
        except (TypeError, ValueError):
            return 0
    return 0


def _ejecutar_lote(
    tx: TransaccionNeo4j,
    cypher: str,
    filas: list[dict[str, str]],
    import_id: str,
    **parametros_extra: object,
) -> None:
    if not filas:
        return
    parametros: dict[str, object] = {"rows": filas, "import_id": import_id}
    parametros.update(parametros_extra)
    total = _total(tx.run(cypher, parametros))
    if total != len(filas):
        raise RuntimeError(
            "Neo4j encontró una entidad curricular existente con propiedades conflictivas"
        )


def escribir_catalogos(
    tx: TransaccionNeo4j,
    filas: Mapping[str, list[dict[str, str]]],
    import_id: str,
) -> None:
    """Materialize the technical graph without mutating matched entities."""

    _validar_ids(filas)
    _ejecutar_lote(
        tx,
        "UNWIND $rows AS row "
        "OPTIONAL MATCH (existente:Curso {id_curso: row.id_curso}) "
        "WITH row, existente "
        "WHERE existente IS NULL OR NOT any(campo IN $campos WHERE "
        "existente[campo] IS NOT NULL AND existente[campo] <> row[campo]) "
        "MERGE (carrera:Carrera {id_carrera: row.id_carrera}) "
        "ON CREATE SET carrera._ciar_import_id = $import_id, "
        "carrera._ciar_import_created = true "
        "MERGE (curso:Curso {id_curso: row.id_curso}) "
        "ON CREATE SET curso.nombre_curso = row.nombre_curso, "
        "curso.coordinador = row.coordinador, curso.creditos = row.creditos, "
        "curso.nivel = row.nivel, curso.tipo_curso = row.tipo_curso, "
        "curso.codigo_curso = row.codigo_curso, curso.id_carrera = row.id_carrera, "
        "curso._ciar_import_id = $import_id, curso._ciar_import_created = true "
        "MERGE (carrera)-[rel:TIENE_CURSO]->(curso) "
        "ON CREATE SET rel._ciar_import_id = $import_id, rel._ciar_import_created = true "
        "RETURN count(curso) AS total",
        filas["curso.csv"],
        import_id,
        campos=list(_salida_catalogos.CURSOS_SCHEMA[1:]),
    )
    _ejecutar_lote(
        tx,
        "UNWIND $rows AS row "
        "MATCH (curso:Curso {id_curso: row.id_curso}) "
        "OPTIONAL MATCH (existente:Silabo {id_silabo: row.id_silabo}) "
        "WITH row, curso, existente "
        "WHERE existente IS NULL OR NOT any(campo IN $campos WHERE "
        "existente[campo] IS NOT NULL AND existente[campo] <> row[campo]) "
        "MERGE (silabo:Silabo {id_silabo: row.id_silabo}) "
        "ON CREATE SET silabo.codigo_silabo = row.codigo_silabo, "
        "silabo.sumilla = row.sumilla, silabo.id_curso = row.id_curso, "
        "silabo.periodo_academico = row.periodo_academico, "
        "silabo._ciar_import_id = $import_id, silabo._ciar_import_created = true "
        "MERGE (curso)-[rel:TIENE_SILABO]->(silabo) "
        "ON CREATE SET rel._ciar_import_id = $import_id, rel._ciar_import_created = true "
        "RETURN count(silabo) AS total",
        filas["silabo.csv"],
        import_id,
        campos=list(_salida_catalogos.SILABOS_SCHEMA[1:]),
    )
    _ejecutar_lote(
        tx,
        "UNWIND $rows AS row "
        "OPTIONAL MATCH (existente:Competencia {id_competencia: row.id_competencia}) "
        "WITH row, existente "
        "WHERE existente IS NULL OR NOT any(campo IN $campos WHERE "
        "existente[campo] IS NOT NULL AND existente[campo] <> row[campo]) "
        "MERGE (competencia:Competencia {id_competencia: row.id_competencia}) "
        "ON CREATE SET competencia.nombre_competencia = row.nombre_competencia, "
        "competencia.descripcion_breve_competencia = row.descripcion_breve_competencia, "
        "competencia.tipo_competencia = row.tipo_competencia, "
        "competencia.codigo_competencia = row.codigo_competencia, "
        "competencia._ciar_import_id = $import_id, competencia._ciar_import_created = true "
        "RETURN count(competencia) AS total",
        filas["catalogo_competencias.csv"],
        import_id,
        campos=list(_salida_catalogos.COMPETENCIAS_SCHEMA[1:]),
    )
    _ejecutar_lote(
        tx,
        "UNWIND $rows AS row "
        "OPTIONAL MATCH (existente:Logro {id_logro: row.id_logro}) "
        "WITH row, existente "
        "WHERE existente IS NULL OR NOT any(campo IN $campos WHERE "
        "existente[campo] IS NOT NULL AND existente[campo] <> row[campo]) "
        "MERGE (logro:Logro {id_logro: row.id_logro}) "
        "ON CREATE SET logro.logro = row.logro, logro._ciar_import_id = $import_id, "
        "logro._ciar_import_created = true "
        "RETURN count(logro) AS total",
        filas["catalogo_logros.csv"],
        import_id,
        campos=["logro"],
    )
    coberturas = filas["cobertura_curricular.csv"]
    for requiere_logro in (False, True):
        lote = [fila for fila in coberturas if bool(fila["id_logro"]) is requiere_logro]
        if not lote:
            continue
        match_logro = "MATCH (logro:Logro {id_logro: row.id_logro}) " if requiere_logro else ""
        variable_logro = ", logro" if requiere_logro else ""
        evidencia = (
            "MERGE (cobertura)-[revid:EVIDENCIA]->(logro) "
            "ON CREATE SET revid._ciar_import_id = $import_id, "
            "revid._ciar_import_created = true "
            if requiere_logro
            else ""
        )
        _ejecutar_lote(
            tx,
            "UNWIND $rows AS row "
            "MATCH (curso:Curso {id_curso: row.id_curso}) "
            "MATCH (silabo:Silabo {id_silabo: row.id_silabo}) "
            "MATCH (competencia:Competencia {id_competencia: row.id_competencia}) "
            f"{match_logro}"
            "OPTIONAL MATCH (existente:CoberturaCurricular "
            "{id_cob_curricular: row.id_cob_curricular}) "
            f"WITH row, curso, silabo, competencia{variable_logro}, existente "
            "WHERE existente IS NULL OR NOT any(campo IN $campos WHERE "
            "existente[campo] IS NOT NULL AND existente[campo] <> row[campo]) "
            "MERGE (cobertura:CoberturaCurricular "
            "{id_cob_curricular: row.id_cob_curricular}) "
            "ON CREATE SET cobertura.id_curso = row.id_curso, "
            "cobertura.id_silabo = row.id_silabo, "
            "cobertura.id_competencia = row.id_competencia, "
            "cobertura.id_logro = row.id_logro, cobertura._ciar_import_id = $import_id, "
            "cobertura._ciar_import_created = true "
            "MERGE (curso)-[relcurso:TIENE_COBERTURA]->(cobertura) "
            "ON CREATE SET relcurso._ciar_import_id = $import_id, "
            "relcurso._ciar_import_created = true "
            "MERGE (silabo)-[relsilabo:TIENE_COBERTURA]->(cobertura) "
            "ON CREATE SET relsilabo._ciar_import_id = $import_id, "
            "relsilabo._ciar_import_created = true "
            "MERGE (cobertura)-[relcompetencia:CUBRE]->(competencia) "
            "ON CREATE SET relcompetencia._ciar_import_id = $import_id, "
            "relcompetencia._ciar_import_created = true "
            f"{evidencia}"
            "RETURN count(cobertura) AS total",
            lote,
            import_id,
            campos=list(_salida_catalogos.COBERTURA_SCHEMA[1:]),
        )
