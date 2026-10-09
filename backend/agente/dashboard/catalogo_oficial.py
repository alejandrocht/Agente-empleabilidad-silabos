"""Carga y consolida el catálogo oficial de competencias técnicas.

El Excel oficial conserva una fila por carrera. Para medir cobertura curricular
se agrupan las filas por nombre normalizado y se mantiene la lista de carreras
de origen. La cobertura se resuelve contra los nodos Habilidad del grafo.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import openpyxl

_RAIZ = Path(__file__).resolve().parents[3]
_CATALOGO_CANDIDATOS = (
    _RAIZ / "empleabilidad_normalizacion" / "catalogo_competencias_tecnicas.xlsx",
    _RAIZ / "backend" / "catalogos" / "catalogo_competencias_tecnicas.xlsx",
)


def _texto(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clave(value: object) -> str:
    texto = unicodedata.normalize("NFKD", _texto(value))
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", texto.casefold()).strip()


@lru_cache(maxsize=1)
def cargar_catalogo_oficial() -> tuple[dict[str, Any], ...]:
    """Return one row per official concept, preserving career provenance."""

    catalogo = next((ruta for ruta in _CATALOGO_CANDIDATOS if ruta.is_file()), None)
    if catalogo is None:
        raise FileNotFoundError(
            "No se encontró el catálogo oficial de competencias técnicas."
        )
    workbook = openpyxl.load_workbook(catalogo, read_only=True, data_only=True)
    sheet = workbook["Catalogo"]
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ValueError("El catálogo oficial está vacío.")

    headers = [_texto(value) for value in rows[0]]
    required = {"Carrera", "Habilidad tecnica", "Descripcion"}
    missing = required - set(headers)
    if missing:
        raise ValueError("Faltan columnas en el catálogo oficial: " + ", ".join(sorted(missing)))
    index = {header: position for position, header in enumerate(headers)}

    grouped: dict[str, dict[str, Any]] = {}
    for values in rows[1:]:
        if not any(_texto(value) for value in values):
            continue
        nombre = _texto(values[index["Habilidad tecnica"]])
        if not nombre:
            continue
        key = _clave(nombre)
        registro = grouped.setdefault(
            key,
            {
                "id": f"OFICIAL_TEC_{len(grouped) + 1:04d}",
                "nombre": nombre,
                "descripcion": _texto(values[index["Descripcion"]]),
                "carreras": set(),
            },
        )
        carrera = _texto(values[index["Carrera"]])
        if carrera:
            registro["carreras"].add(carrera)
        if not registro["descripcion"]:
            registro["descripcion"] = _texto(values[index["Descripcion"]])

    resultado = []
    for registro in sorted(grouped.values(), key=lambda item: item["nombre"].casefold()):
        resultado.append(
            {
                "id": registro["id"],
                "nombre": registro["nombre"],
                "descripcion": registro["descripcion"],
                "carreras": sorted(registro["carreras"], key=str.casefold),
            }
        )
    return tuple(resultado)


def construir_brecha_catalogo(
    filas_grafo: list[dict[str, Any]],
) -> dict[str, Any]:
    """Join official concepts with read-only graph coverage rows."""

    por_nombre = {
        _clave(row.get("nombre")): row
        for row in filas_grafo
        if _clave(row.get("nombre"))
    }
    conceptos = []
    for oficial in cargar_catalogo_oficial():
        grafo = por_nombre.get(_clave(oficial["nombre"]), {})
        cursos = int(grafo.get("cursos_con_cobertura") or 0)
        conceptos.append(
            {
                **oficial,
                "id_habilidad": grafo.get("id"),
                "cursos_con_cobertura": cursos,
                "cubierta": cursos > 0,
            }
        )

    por_carrera: dict[str, dict[str, Any]] = {}
    for concepto in conceptos:
        for carrera in concepto["carreras"]:
            resumen = por_carrera.setdefault(
                carrera,
                {"carrera": carrera, "total": 0, "cubiertas": 0, "no_cubiertas": 0},
            )
            resumen["total"] += 1
            if concepto["cubierta"]:
                resumen["cubiertas"] += 1
            else:
                resumen["no_cubiertas"] += 1

    cubiertas = sum(1 for concepto in conceptos if concepto["cubierta"])
    total = len(conceptos)
    return {
        "fuente": next(
            (ruta.name for ruta in _CATALOGO_CANDIDATOS if ruta.is_file()),
            _CATALOGO_CANDIDATOS[-1].name,
        ),
        "filas_hoja": sum(len(concepto["carreras"]) for concepto in conceptos) + 1,
        "registros_fuente": sum(len(concepto["carreras"]) for concepto in conceptos),
        "conceptos_unicos": total,
        "cubiertas": cubiertas,
        "no_cubiertas": total - cubiertas,
        "porcentaje_cubierto": round((cubiertas / total) * 100, 1) if total else 0.0,
        "conceptos": conceptos,
        "por_carrera": sorted(
            (
                {
                    **resumen,
                    "porcentaje_cubierto": round(
                        (resumen["cubiertas"] / resumen["total"]) * 100, 1
                    )
                    if resumen["total"]
                    else 0.0,
                }
                for resumen in por_carrera.values()
            ),
            key=lambda item: item["carrera"].casefold(),
        ),
    }
