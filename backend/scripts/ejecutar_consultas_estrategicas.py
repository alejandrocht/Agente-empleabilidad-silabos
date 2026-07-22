#!/usr/bin/env python3
"""Lista, muestra o ejecuta una consulta Cypher estratégica fija en Neo4j."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypeAlias, cast

from agente.dashboard.consultas_estrategicas import (
    CONSULTAS_ESTRATEGICAS,
    ConsultaEstrategica,
    todas_las_consultas_estrategicas,
)
from agente.db.neo4j import ejecutar_lectura

Vista: TypeAlias = Literal["general", "especifica"]
ValorParametro: TypeAlias = bool | int | float | str | None
TIPOS_CONOCIMIENTO: frozenset[str] = frozenset(
    {"competencia", "habilidad", "herramienta"}
)


def crear_parser() -> argparse.ArgumentParser:
    """Construye la interfaz de línea de comandos."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consulta", metavar="SLUG", help="Slug de la consulta.")
    parser.add_argument(
        "--vista",
        choices=("general", "especifica"),
        default="general",
        help="Vista macro sin parámetros o drill-down parametrizado.",
    )
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="CLAVE=VALOR",
        help="Parámetro de la vista específica; puede repetirse.",
    )
    parser.add_argument("--salida", type=Path, help="Ruta del resultado JSON.")
    parser.add_argument("--listar", action="store_true", help="Lista el catálogo sin conectarse.")
    parser.add_argument(
        "--mostrar-query",
        action="store_true",
        help="Imprime el Cypher seleccionado sin conectarse.",
    )
    return parser


def convertir_valor(valor: str) -> ValorParametro:
    """Convierte escalares CLI evidentes y conserva el resto como texto."""

    normalizado = valor.casefold()
    if normalizado in {"null", "none"}:
        return None
    if normalizado == "true":
        return True
    if normalizado == "false":
        return False
    if re.fullmatch(r"[+-]?\d+", valor):
        return int(valor)
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?", valor):
        return float(valor)
    return valor


def parsear_parametros(argumentos: list[str]) -> dict[str, ValorParametro]:
    """Interpreta CLAVE=VALOR y rechaza claves vacías o repetidas."""

    parametros: dict[str, ValorParametro] = {}
    for argumento in argumentos:
        if "=" not in argumento:
            raise ValueError(f"Parámetro inválido {argumento!r}; usá CLAVE=VALOR.")
        clave, valor = argumento.split("=", 1)
        if not clave:
            raise ValueError(f"Parámetro inválido {argumento!r}; la clave está vacía.")
        if clave in parametros:
            raise ValueError(f"El parámetro {clave!r} fue indicado más de una vez.")
        parametros[clave] = convertir_valor(valor)
    return parametros


def preparar_parametros(
    consulta: ConsultaEstrategica,
    vista: Vista,
    recibidos: dict[str, ValorParametro],
) -> dict[str, ValorParametro]:
    """Exige exactamente los parámetros declarados para la vista."""

    esperados = set(consulta.parametros_especificos) if vista == "especifica" else set()
    recibidos_claves = set(recibidos)
    faltantes = sorted(esperados - recibidos_claves)
    desconocidos = sorted(recibidos_claves - esperados)
    nulos = sorted(clave for clave, valor in recibidos.items() if valor is None)
    problemas: list[str] = []
    if faltantes:
        problemas.append("faltan: " + ", ".join(faltantes))
    if desconocidos:
        problemas.append("no reconocidos: " + ", ".join(desconocidos))
    if nulos:
        problemas.append("no pueden ser null: " + ", ".join(nulos))
    if problemas:
        raise ValueError("Parámetros inválidos (" + "; ".join(problemas) + ").")
    _validar_semantica_parametros(recibidos)
    return dict(recibidos)


def _parsear_fecha_iso(clave: str, valor: ValorParametro) -> datetime:
    """Convierte una fecha ISO y produce un error orientado al parámetro."""

    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"El parámetro {clave!r} debe ser una fecha ISO no vacía.")
    try:
        return datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"El parámetro {clave!r} debe usar formato ISO válido.") from exc


def _cantidad_buckets_mensuales(desde: datetime, hasta: datetime) -> int:
    """Cuenta meses calendario tocados por el rango semiabierto [desde, hasta)."""

    inicio = desde.year * 12 + desde.month - 1
    fin = hasta.year * 12 + hasta.month - 1
    hasta_es_inicio_de_mes = (
        hasta.day == 1
        and hasta.hour == 0
        and hasta.minute == 0
        and hasta.second == 0
        and hasta.microsecond == 0
    )
    ultimo = fin - 1 if hasta_es_inicio_de_mes else fin
    return ultimo - inicio + 1


def _validar_semantica_parametros(parametros: dict[str, ValorParametro]) -> None:
    """Valida IDs, dimensiones, períodos y comparaciones antes de tocar Neo4j."""

    for clave, valor in parametros.items():
        if clave.endswith("_id") and (not isinstance(valor, str) or not valor.strip()):
            raise ValueError(f"El parámetro {clave!r} debe ser un string no vacío.")

    tipo = parametros.get("tipo_conocimiento")
    if tipo is not None and tipo not in TIPOS_CONOCIMIENTO:
        permitidos = ", ".join(sorted(TIPOS_CONOCIMIENTO))
        raise ValueError(f"tipo_conocimiento debe ser uno de: {permitidos}.")

    if "desde" in parametros or "hasta" in parametros:
        desde = _parsear_fecha_iso("desde", parametros.get("desde"))
        hasta = _parsear_fecha_iso("hasta", parametros.get("hasta"))
        try:
            orden_valido = desde < hasta
        except TypeError as exc:
            raise ValueError("desde y hasta deben usar zonas horarias compatibles.") from exc
        if not orden_valido:
            raise ValueError("El rango requiere desde < hasta.")
        if _cantidad_buckets_mensuales(desde, hasta) > 20:
            raise ValueError("El rango no puede abarcar más de 20 meses calendario.")

    empresa_a = parametros.get("empresa_a_id")
    empresa_b = parametros.get("empresa_b_id")
    if empresa_a is not None and empresa_a == empresa_b:
        raise ValueError("empresa_a_id y empresa_b_id deben ser distintos.")


def validar_parametros(
    consulta: ConsultaEstrategica,
    parametros: dict[str, ValorParametro],
    vista: Vista = "general",
) -> None:
    """Valida parámetros conservando la API de verificaciones externas."""

    preparar_parametros(consulta, vista, parametros)


def seleccionar_cypher(consulta: ConsultaEstrategica, vista: Vista) -> str:
    """Selecciona el Cypher ya materializado de la vista solicitada."""

    return consulta.cypher_general if vista == "general" else consulta.cypher_especifica


def listar_catalogo() -> None:
    """Imprime el contrato de ambas vistas para las doce consultas."""

    comando = "python scripts/ejecutar_consultas_estrategicas.py"
    for indice, consulta in enumerate(todas_las_consultas_estrategicas(), start=1):
        parametros = ", ".join(consulta.parametros_especificos)
        argumentos = " ".join(
            f"--param {parametro}=VALOR" for parametro in consulta.parametros_especificos
        )
        print(f"{indice:02d}. {consulta.slug}")
        print(f"    [{consulta.categoria}]")
        print(f"    {consulta.pregunta_medible}")
        print(
            "    Tendencia: "
            f"{consulta.metrica_principal} | gráfico={consulta.chart_hint} | "
            f"requiere_curricula={consulta.requiere_curricula}"
        )
        print(
            "    General: "
            f"{consulta.granularidad_general} (máximo {consulta.limite_general} filas)"
        )
        print(
            "    Específica: "
            f"{consulta.granularidad_especifica} "
            f"(máximo {consulta.limite_especifico} filas)"
        )
        print(f"    Salidas generales: {', '.join(consulta.salidas_general)}")
        print(f"    Salidas específicas: {', '.join(consulta.salidas_especifica)}")
        print(f"    Parámetros específicos: {parametros}")
        print(f"    Comando general: {comando} --consulta {consulta.slug} --vista general")
        print(
            "    Comando específico: "
            f"{comando} --consulta {consulta.slug} --vista especifica {argumentos}"
        )


def _json_predeterminado(valor: Any) -> str:
    """Representa tipos Neo4j no nativos de forma legible."""

    return str(valor)


def ejecutar(
    consulta: ConsultaEstrategica,
    parametros: dict[str, Any],
    vista: Vista = "general",
) -> dict[str, Any]:
    """Ejecuta una consulta fija y construye su reporte."""

    cypher = seleccionar_cypher(consulta, vista)
    print(f"Vista: {vista}\n")
    print(f"Pregunta original:\n{consulta.pregunta_original}\n")
    print(f"Pregunta medible:\n{consulta.pregunta_medible}\n")
    print(f"Limitación semántica:\n{consulta.limitacion_semantica}\n")
    print(f"Cypher:\n{cypher}\n")
    print("Parámetros efectivos:")
    print(json.dumps(parametros, ensure_ascii=False, indent=2))
    inicio = time.perf_counter()
    filas = ejecutar_lectura(cypher, parametros)
    duracion = round(time.perf_counter() - inicio, 3)
    print("Resultados:")
    print(json.dumps(filas, ensure_ascii=False, indent=2, default=_json_predeterminado))
    return {
        "generado_en": datetime.now(UTC).isoformat(),
        "slug": consulta.slug,
        "vista": vista,
        "categoria": consulta.categoria,
        "pregunta_original": consulta.pregunta_original,
        "pregunta_medible": consulta.pregunta_medible,
        "limitacion_semantica": consulta.limitacion_semantica,
        "metadata_tendencia": {
            "granularidad_general": consulta.granularidad_general,
            "granularidad_especifica": consulta.granularidad_especifica,
            "metrica_principal": consulta.metrica_principal,
            "limite_general": consulta.limite_general,
            "limite_especifico": consulta.limite_especifico,
            "chart_hint": consulta.chart_hint,
            "requiere_curricula": consulta.requiere_curricula,
            "salidas_general": consulta.salidas_general,
            "salidas_especifica": consulta.salidas_especifica,
        },
        "cypher": cypher,
        "parametros": parametros,
        "total_resultados": len(filas),
        "duracion_segundos": duracion,
        "resultados": filas,
    }


def main() -> None:
    """Resuelve selección y parámetros; ejecuta como máximo una consulta."""

    for salida in (sys.stdout, sys.stderr):
        reconfigurar = getattr(salida, "reconfigure", None)
        if callable(reconfigurar):
            reconfigurar(encoding="utf-8", errors="replace")

    parser = crear_parser()
    args = parser.parse_args()
    if args.listar or args.consulta is None:
        listar_catalogo()
        return

    consulta = CONSULTAS_ESTRATEGICAS.get(args.consulta)
    if consulta is None:
        disponibles = ", ".join(CONSULTAS_ESTRATEGICAS)
        raise SystemExit(f"Consulta desconocida: {args.consulta}. Disponibles: {disponibles}")

    vista = cast(Vista, args.vista)
    try:
        parametros = preparar_parametros(consulta, vista, parsear_parametros(args.param))
    except ValueError as exc:
        parser.error(str(exc))

    if args.mostrar_query:
        print(seleccionar_cypher(consulta, vista))
        return

    reporte = ejecutar(consulta, parametros, vista)
    marca_tiempo = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    salida = args.salida or (
        Path("reportes") / f"consulta_estrategica_{consulta.slug}_{vista}_{marca_tiempo}.json"
    )
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(
        json.dumps(reporte, ensure_ascii=False, indent=2, default=_json_predeterminado),
        encoding="utf-8",
    )
    print(f"\nReporte guardado en: {salida.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrumpido por el usuario.", file=sys.stderr)
        raise SystemExit(130) from None
