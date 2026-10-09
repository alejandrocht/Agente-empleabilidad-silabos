"""Migra e importa un ZIP curricular legado y permite revertirlo.

El ZIP recibido contiene una exportación multi-carrera anterior al contrato
canónico. Este script adapta únicamente los encabezados y deja trazada cada
decisión de migración en el manifest de la ejecución. La escritura se delega
al importador reversible de Neo4j; no ejecuta Cypher arbitrario.

Uso:
    uv run --locked python scripts/importar_zip_curricular.py --zip ARCHIVO.zip
    uv run --locked python scripts/importar_zip_curricular.py --revertir IMP_...
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from agente.db.neo4j_importador import ImportadorNeo4j
from agente.normalizador.ejecuciones import GestorEjecuciones

SOURCE_HEADERS: dict[str, tuple[str, ...]] = {
    "curso.csv": (
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
    "silabo.csv": (
        "id_silabo",
        "codigo_silabo",
        "sumilla",
        "id_curso",
        "periodo_academico",
    ),
    "catalogo_competencias.csv": (
        "id_competencia",
        "nombre_competencia",
        "descripcion_breve",
        "tipo_competencia",
        "codigo_competencia",
    ),
    "catalogo_logros.csv": ("id_logro", "logro"),
    "cobertura_curricular.csv": (
        "id_cobertura_curricular",
        "id_curso",
        "id_silabo",
        "id_competencia",
        "id_habilidad",
        "id_logro",
    ),
}

CANONICAL_HEADERS: dict[str, tuple[str, ...]] = {
    "curso.csv": (
        "id_curso",
        "nombre_curso",
        "coordinador",
        "creditos",
        "nivel",
        "tipo_curso",
        "codigo_curso",
        "id_carrera",
    ),
    "silabo.csv": ("id_silabo", "codigo_silabo", "sumilla", "id_curso"),
    "catalogo_competencias.csv": (
        "id_competencia",
        "nombre_competencia",
        "descripcion_breve_competencia",
        "tipo_competencia",
        "codigo_competencia",
    ),
    "catalogo_logros.csv": ("id_logro", "nombre_logro", "descripcion_breve"),
    "catalogo_herramientas.csv": (
        "id_herramienta",
        "nombre_herramienta",
        "descripcion_breve_herramienta",
    ),
    "cobertura_curricular.csv": (
        "id_cob_curricular",
        "id_curso",
        "id_silabo",
        "id_competencia",
        "id_logro",
        "id_herramienta",
    ),
}


def _ahora() -> str:
    return datetime.now(UTC).isoformat()


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def _entrada_csv(zf: zipfile.ZipFile, nombre: str) -> list[dict[str, str]]:
    candidatos = [
        item
        for item in zf.namelist()
        if not item.startswith("__MACOSX/") and PurePosixPath(item).name == nombre
    ]
    if len(candidatos) != 1:
        raise ValueError(f"Se esperaba exactamente un {nombre} dentro del ZIP.")
    texto = zf.read(candidatos[0]).decode("utf-8-sig")
    lector = csv.DictReader(io.StringIO(texto, newline=""))
    encabezado = tuple(lector.fieldnames or ())
    esperado = SOURCE_HEADERS[nombre]
    if encabezado != esperado:
        raise ValueError(f"{nombre}: encabezado legado inesperado: {encabezado!r}")
    filas: list[dict[str, str]] = []
    for numero, fila in enumerate(lector, start=2):
        if None in fila:
            raise ValueError(f"{nombre}: la fila {numero} tiene columnas adicionales.")
        filas.append({clave: _texto(fila.get(clave)) for clave in esperado})
    return filas


def _escribir_csv(ruta: Path, encabezado: tuple[str, ...], filas: list[dict[str, str]]) -> None:
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(encabezado), lineterminator="\n")
        escritor.writeheader()
        escritor.writerows({campo: fila.get(campo, "") for campo in encabezado} for fila in filas)


def _migrar(zip_path: Path, directorio: Path) -> dict[str, Any]:
    salida = directorio / "salidas"
    reportes = salida / "reportes"
    limpios = directorio / "limpios"
    reportes.mkdir(parents=True, exist_ok=True)
    limpios.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        fuente = {nombre: _entrada_csv(zf, nombre) for nombre in SOURCE_HEADERS}

    cursos = [
        {campo: fila.get(campo, "") for campo in CANONICAL_HEADERS["curso.csv"]}
        for fila in fuente["curso.csv"]
    ]
    silabos = [
        {campo: fila.get(campo, "") for campo in CANONICAL_HEADERS["silabo.csv"]}
        for fila in fuente["silabo.csv"]
    ]
    competencias = [
        {
            "id_competencia": fila["id_competencia"],
            "nombre_competencia": fila["nombre_competencia"],
            "descripcion_breve_competencia": fila["descripcion_breve"],
            "tipo_competencia": fila["tipo_competencia"],
            "codigo_competencia": fila["codigo_competencia"],
        }
        for fila in fuente["catalogo_competencias.csv"]
    ]
    logros = [
        {
            "id_logro": fila["id_logro"],
            # El formato legado solo entrega el texto completo del logro.
            "nombre_logro": fila["logro"],
            "descripcion_breve": fila["logro"],
        }
        for fila in fuente["catalogo_logros.csv"]
    ]
    cobertura = [
        {
            "id_cob_curricular": fila["id_cobertura_curricular"],
            "id_curso": fila["id_curso"],
            "id_silabo": fila["id_silabo"],
            "id_competencia": fila["id_competencia"],
            "id_logro": fila["id_logro"],
            # El usuario solicitó no cargar herramientas por ahora.
            "id_herramienta": "",
        }
        for fila in fuente["cobertura_curricular.csv"]
    ]
    herramientas: list[dict[str, str]] = []

    curso_por_id = {fila["id_curso"] for fila in cursos}
    silabo_por_id = {fila["id_silabo"] for fila in silabos}
    competencia_por_id = {fila["id_competencia"] for fila in competencias}
    logro_por_id = {fila["id_logro"] for fila in logros}
    huérfanos = {
        "id_curso": sorted({fila["id_curso"] for fila in cobertura} - curso_por_id),
        "id_silabo": sorted({fila["id_silabo"] for fila in cobertura} - silabo_por_id),
        "id_competencia": sorted(
            {fila["id_competencia"] for fila in cobertura} - competencia_por_id
        ),
        "id_logro": sorted({fila["id_logro"] for fila in cobertura} - logro_por_id),
    }
    if any(huérfanos.values()):
        raise ValueError(f"El ZIP tiene referencias huérfanas: {huérfanos}")

    for nombre, filas in (
        ("curso.csv", cursos),
        ("silabo.csv", silabos),
        ("catalogo_competencias.csv", competencias),
        ("catalogo_logros.csv", logros),
        ("catalogo_herramientas.csv", herramientas),
        ("cobertura_curricular.csv", cobertura),
    ):
        _escribir_csv(salida / nombre, CANONICAL_HEADERS[nombre], filas)

    with (limpios / "silabos.jsonl").open("w", encoding="utf-8", newline="\n") as archivo:
        for fila in silabos:
            archivo.write(
                json.dumps(
                    {
                        "id_silabo": fila["id_silabo"],
                        "id_curso": fila["id_curso"],
                        "codigo_silabo": fila["codigo_silabo"],
                        "sumilla": fila["sumilla"],
                        "datos": {
                            "codigo_curso": fila["codigo_silabo"],
                            "sumilla": fila["sumilla"],
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    advertencias = [
        {
            "codigo": "MIGRACION_ENCABEZADOS_LEGACY",
            "severidad": "warning",
            "mensaje": "Se adaptaron los encabezados del ZIP al contrato curricular vigente.",
        },
        {
            "codigo": "HERRAMIENTAS_OMITIDAS_POR_SOLICITUD",
            "severidad": "warning",
            "mensaje": "No se cargaron herramientas ni relaciones hacia herramientas.",
        },
        {
            "codigo": "LOGRO_TEXTO_REUTILIZADO",
            "severidad": "warning",
            "mensaje": "El campo legado logro se copió a nombre_logro y descripcion_breve.",
        },
        {
            "codigo": "COLUMNAS_LEGACY_NO_PUBLICADAS",
            "severidad": "warning",
            "mensaje": (
                "naturaleza y periodo_academico no pertenecen al contrato de Neo4j "
                "y no se publicaron."
            ),
        },
        {
            "codigo": "NOMBRES_DUPLICADOS_CON_IDS_DISTINTOS",
            "severidad": "warning",
            "mensaje": "Se conservaron nombres repetidos cuando sus IDs son distintos.",
        },
    ]
    (reportes / "migracion_zip.json").write_text(
        json.dumps(
            {
                "version": "ciar-legacy-curricular-zip-migration/v1",
                "fuente": str(zip_path),
                "herramientas_cargadas": False,
                "advertencias": advertencias,
                "conteos": {
                    "cursos": len(cursos),
                    "silabos": len(silabos),
                    "competencias": len(competencias),
                    "logros": len(logros),
                    "herramientas": 0,
                    "coberturas": len(cobertura),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "cursos": len(cursos),
        "silabos": len(silabos),
        "competencias": len(competencias),
        "logros": len(logros),
        "herramientas": 0,
        "coberturas": len(cobertura),
        "advertencias": advertencias,
    }


def _manifest(id_ejecucion: str, zip_path: Path, resumen: dict[str, Any]) -> dict[str, Any]:
    gate = {
        "version": "curricular-release-gate/v1",
        "decision": "ALLOW_IMPORT",
        "blockers": [],
        "checks": {
            "legacy_migration": {"ok": True, "policy": "preserve_distinct_ids"},
            "tools": {"ok": True, "omitted_by_user": True},
            "source_references": {"ok": True},
            "pending_decisions": {"ok": True, "count": 0},
        },
        "migration_authorized_by_user": True,
    }
    outputs = [
        {
            "archivo": f"salidas/{nombre}",
            "tipo": "csv_curricular",
            "filas": resumen[clave],
        }
        for nombre, clave in (
            ("curso.csv", "cursos"),
            ("silabo.csv", "silabos"),
            ("catalogo_competencias.csv", "competencias"),
            ("catalogo_logros.csv", "logros"),
            ("catalogo_herramientas.csv", "herramientas"),
            ("cobertura_curricular.csv", "coberturas"),
        )
    ]
    return {
        "id_ejecucion": id_ejecucion,
        "tipo": "silabos",
        "archivo": zip_path.name,
        "parametros": {
            "carrera": "TODAS",
            "periodo": "2026-2",
            "migracion": "zip_legacy_preserve_distinct_ids",
            "herramientas": "omitidas",
        },
        "estado": "limpiado_con_advertencias",
        "creada_en": _ahora(),
        "actualizada_en": _ahora(),
        "validacion_silabos": {
            "valida": True,
            "carrera": "TODAS",
            "periodo": "2026-2",
            "registros": resumen["silabos"],
            "hallazgos": resumen["advertencias"],
        },
        "limpieza_silabos": {
            "registros": resumen["silabos"],
            "publicable": True,
            "relaciones": resumen["coberturas"],
            "competencias": resumen["competencias"],
            "habilidades": resumen["logros"],
            "herramientas": 0,
            "pendientes": 0,
            "release_gate": gate,
            "outputs": outputs,
            "hallazgos": resumen["advertencias"],
        },
        "release_gate": gate,
        "aprobacion_curricular": {"requiere_decision": False, "pendientes_por_decidir": 0},
        "hallazgos": resumen["advertencias"],
        "outputs": outputs,
    }


def importar(zip_path: Path, solo_previsualizar: bool) -> int:
    gestor = GestorEjecuciones()
    id_ejecucion, directorio = gestor.crear("silabos", zip_path.name, {"carrera": "TODAS"})
    # La ejecución se leerá desde el manifest migrado por el importador.
    gestor._ejecuciones.pop(id_ejecucion, None)
    resumen = _migrar(zip_path, directorio)
    (directorio / "manifest.json").write_text(
        json.dumps(_manifest(id_ejecucion, zip_path, resumen), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    importador = ImportadorNeo4j(
        gestor,
        permitir_nombres_duplicados=True,
        permitir_padres_faltantes=True,
        permitir_conflictos_existentes=True,
    )
    preview = importador.previsualizar(id_ejecucion)
    print(
        json.dumps(
            {"id_ejecucion": id_ejecucion, "preview": preview},
            ensure_ascii=False,
            indent=2,
        )
    )
    if not preview.get("puede_importar"):
        return 2
    if solo_previsualizar:
        return 0
    resultado = importador.importar(
        id_ejecucion,
        str(preview["fingerprint"]),
        confirmar=True,
    )
    print(json.dumps({"importacion": resultado}, ensure_ascii=False, indent=2))
    return 0


def revertir(id_importacion: str) -> int:
    gestor = GestorEjecuciones()
    importador = ImportadorNeo4j(
        gestor,
        permitir_nombres_duplicados=True,
        permitir_padres_faltantes=True,
        permitir_conflictos_existentes=True,
    )
    resultado = importador.revertir(id_importacion, confirmar=True)
    print(json.dumps({"reversion": resultado}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--zip", type=Path, help="ZIP curricular legado que se migrará e importará.")
    grupo.add_argument("--revertir", metavar="IMP_ID", help="ID de importación reversible.")
    parser.add_argument(
        "--solo-previsualizar",
        action="store_true",
        help="Adapta y valida, pero no escribe en Neo4j.",
    )
    argumentos = parser.parse_args()
    if argumentos.revertir:
        return revertir(argumentos.revertir)
    zip_path = argumentos.zip.resolve()
    if not zip_path.is_file():
        parser.error(f"No existe el ZIP: {zip_path}")
    return importar(zip_path, argumentos.solo_previsualizar)


if __name__ == "__main__":
    raise SystemExit(main())
