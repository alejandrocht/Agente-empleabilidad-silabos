"""Servicio tipado del dashboard, aislado del flujo conversacional y del LLM."""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from time import perf_counter
from typing import Any

from agente.dashboard.consultas import (
    CONSULTA_CARRERA,
    CONSULTA_CARRERAS,
    CONSULTA_RANGO_OFERTAS,
    CONSULTA_TENDENCIA_CARRERA,
    CONSULTA_TENDENCIA_GLOBAL,
    CONSULTAS_BRECHAS,
    CONSULTAS_COBERTURA,
    CONSULTAS_DEMANDA,
    CONSULTAS_INDUSTRIAS,
    DIMENSIONES,
    todas_las_plantillas,
)
from agente.db.neo4j import ejecutar_lectura
from agente.guardas.cypher import validar_consulta
from agente.observabilidad.logger import log_paso

MAX_LIMITE = 25
MAX_DIAS_RANGO = 3660
PARAMETROS_VALIDACION = {
    "carrera_id": "__validacion__",
    "desde": "2022-01-01T00:00:00Z",
    "hasta": "2022-01-02T00:00:00Z",
    "limite": 1,
    "elemento_id": "__validacion__",
}


class ErrorDashboard(ValueError):
    """Error de entrada o disponibilidad que puede exponerse de forma segura."""


def _entero(valor: Any) -> int:
    return int(valor or 0)


def _decimal(valor: Any) -> float:
    return float(valor or 0.0)


def _parametros_periodo(desde: date, hasta: date) -> dict[str, str]:
    if desde > hasta:
        raise ErrorDashboard("La fecha inicial no puede ser posterior a la fecha final.")
    if (hasta - desde).days > MAX_DIAS_RANGO:
        raise ErrorDashboard("El período máximo de consulta es de diez años.")
    hasta_exclusiva = hasta + timedelta(days=1)
    return {
        "desde": f"{desde.isoformat()}T00:00:00Z",
        "hasta": f"{hasta_exclusiva.isoformat()}T00:00:00Z",
    }


def _dimension(slug: str) -> str:
    if slug not in DIMENSIONES:
        permitidas = ", ".join(DIMENSIONES)
        raise ErrorDashboard(f"Dimensión no válida. Usa: {permitidas}.")
    return slug


def _limite(limite: int) -> int:
    if not 1 <= limite <= MAX_LIMITE:
        raise ErrorDashboard(f"El límite debe estar entre 1 y {MAX_LIMITE}.")
    return limite


def _fecha_iso(valor: Any) -> str | None:
    if valor is None:
        return None
    return str(valor)[:10]


@lru_cache(maxsize=1)
def verificar_plantillas() -> None:
    """Valida seguridad, schema y sintaxis de cada plantilla estática una vez."""

    errores = {
        nombre: error
        for nombre, consulta in todas_las_plantillas().items()
        if (error := validar_consulta(consulta, PARAMETROS_VALIDACION)) is not None
    }
    if errores:
        detalle = " | ".join(f"{nombre}: {error}" for nombre, error in errores.items())
        raise RuntimeError(f"Las plantillas del dashboard no son válidas: {detalle}")


def _ejecutar(nombre: str, consulta: str, parametros: dict[str, Any]) -> list[dict[str, Any]]:
    verificar_plantillas()
    inicio = perf_counter()
    filas = ejecutar_lectura(consulta, parametros)
    log_paso(
        "dashboard",
        "consulta_ejecutada",
        data={
            "plantilla": nombre,
            "filtros": parametros,
            "filas": len(filas),
            "duracion_ms": round((perf_counter() - inicio) * 1000, 1),
        },
    )
    return filas


def listar_carreras() -> list[dict[str, Any]]:
    """Devuelve carreras y si su lado curricular está disponible en el grafo."""

    filas = _ejecutar("dashboard_catalogo_carreras", CONSULTA_CARRERAS, {})
    return [
        {
            "id": str(fila["id"]),
            "nombre": str(fila["nombre"]),
            "cursos_conectados": _entero(fila["cursos_conectados"]),
            "cobertura_disponible": _entero(fila["cursos_conectados"]) > 0,
        }
        for fila in filas
    ]


def metadatos() -> dict[str, Any]:
    """Expone solo metadatos necesarios para inicializar filtros del frontend."""

    filas = _ejecutar("dashboard_rango_ofertas", CONSULTA_RANGO_OFERTAS, {})
    fila = filas[0] if filas else {}
    return {
        "periodo_disponible": {
            "desde": _fecha_iso(fila.get("desde")),
            "hasta": _fecha_iso(fila.get("hasta")),
        },
        "dimensiones": [
            {"id": slug, "nombre": dimension.etiqueta_visible}
            for slug, dimension in DIMENSIONES.items()
        ],
    }


def obtener_carrera(carrera_id: str) -> dict[str, Any]:
    """Obtiene una carrera válida y el estado de sus relaciones curriculares."""

    identificador = carrera_id.strip()
    if not identificador:
        raise ErrorDashboard("Debes seleccionar una carrera.")
    filas = _ejecutar(
        "dashboard_carrera",
        CONSULTA_CARRERA,
        {"carrera_id": identificador},
    )
    if not filas:
        raise ErrorDashboard("La carrera seleccionada no existe.")
    fila = filas[0]
    cursos = _entero(fila["cursos_conectados"])
    return {
        "id": str(fila["id"]),
        "nombre": str(fila["nombre"]),
        "cursos_conectados": cursos,
        "cobertura_disponible": cursos > 0,
    }


def tendencia_ofertas(
    desde: date,
    hasta: date,
    carrera_id: str | None = None,
) -> dict[str, Any]:
    """Devuelve una serie mensual global o limitada a una carrera."""

    parametros = _parametros_periodo(desde, hasta)
    carrera: dict[str, Any] | None = None
    if carrera_id:
        carrera = obtener_carrera(carrera_id)
        parametros["carrera_id"] = carrera["id"]
        nombre = "dashboard_ofertas_por_mes_carrera"
        consulta = CONSULTA_TENDENCIA_CARRERA
    else:
        nombre = "dashboard_ofertas_por_mes"
        consulta = CONSULTA_TENDENCIA_GLOBAL

    filas = _ejecutar(nombre, consulta, parametros)
    return {
        "carrera": carrera,
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "filas": [
            {
                "anio": _entero(fila["anio"]),
                "mes": _entero(fila["mes"]),
                "ofertas": _entero(fila["ofertas"]),
            }
            for fila in filas
        ],
    }


def demanda_dimension(
    tipo: str,
    carrera_id: str,
    desde: date,
    hasta: date,
    limite: int = 10,
) -> dict[str, Any]:
    """Lista elementos demandados en ofertas dirigidas a una carrera."""

    slug = _dimension(tipo)
    carrera = obtener_carrera(carrera_id)
    parametros = {
        **_parametros_periodo(desde, hasta),
        "carrera_id": carrera["id"],
        "limite": _limite(limite),
    }
    filas = _ejecutar(
        f"dashboard_demanda_{slug}",
        CONSULTAS_DEMANDA[slug],
        parametros,
    )
    return {
        "tipo": slug,
        "titulo": DIMENSIONES[slug].etiqueta_visible,
        "carrera": carrera,
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "filas": [
            {
                "id": str(fila["id"]),
                "elemento": str(fila["elemento"]),
                "ofertas": _entero(fila["ofertas"]),
            }
            for fila in filas
        ],
    }


def cobertura_dimension(
    tipo: str,
    carrera_id: str,
    limite: int = 10,
) -> dict[str, Any]:
    """Lista coberturas curriculares sin confundir ausencia de datos con cero."""

    slug = _dimension(tipo)
    carrera = obtener_carrera(carrera_id)
    if not carrera["cobertura_disponible"]:
        return {
            "tipo": slug,
            "titulo": DIMENSIONES[slug].etiqueta_visible,
            "carrera": carrera,
            "disponible": False,
            "motivo": "La carrera no tiene cursos enlazados a cobertura curricular en Neo4j.",
            "filas": [],
        }

    filas = _ejecutar(
        f"dashboard_cobertura_{slug}",
        CONSULTAS_COBERTURA[slug],
        {"carrera_id": carrera["id"], "limite": _limite(limite)},
    )
    return {
        "tipo": slug,
        "titulo": DIMENSIONES[slug].etiqueta_visible,
        "carrera": carrera,
        "disponible": True,
        "motivo": None,
        "filas": [
            {
                "id": str(fila["id"]),
                "elemento": str(fila["elemento"]),
                "cursos_con_cobertura": _entero(fila["cursos_con_cobertura"]),
                "total_cursos": _entero(fila["total_cursos"]),
                "cobertura": (
                    _entero(fila["cursos_con_cobertura"]) / _entero(fila["total_cursos"])
                    if _entero(fila["total_cursos"])
                    else 0.0
                ),
            }
            for fila in filas
        ],
    }


def brechas_dimension(
    tipo: str,
    carrera_id: str,
    desde: date,
    hasta: date,
    limite: int = 10,
) -> dict[str, Any]:
    """Compara índices de demanda y cobertura solo con denominador curricular válido."""

    slug = _dimension(tipo)
    carrera = obtener_carrera(carrera_id)
    if not carrera["cobertura_disponible"]:
        return {
            "tipo": slug,
            "titulo": DIMENSIONES[slug].etiqueta_visible,
            "carrera": carrera,
            "disponible": False,
            "motivo": "No se pueden calcular brechas: falta cobertura curricular enlazada.",
            "filas": [],
        }

    parametros = {
        **_parametros_periodo(desde, hasta),
        "carrera_id": carrera["id"],
        "limite": _limite(limite),
    }
    filas = _ejecutar(
        f"dashboard_brechas_{slug}",
        CONSULTAS_BRECHAS[slug],
        parametros,
    )
    return {
        "tipo": slug,
        "titulo": DIMENSIONES[slug].etiqueta_visible,
        "carrera": carrera,
        "disponible": True,
        "motivo": None,
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "filas": [
            {
                "id": str(fila["id"]),
                "elemento": str(fila["elemento"]),
                "cursos_con_cobertura": _entero(fila["cursos_con_cobertura"]),
                "total_cursos": _entero(fila["total_cursos"]),
                "ofertas_que_requieren": _entero(fila["ofertas_que_requieren"]),
                "total_ofertas": _entero(fila["total_ofertas"]),
                "cobertura": _decimal(fila["cobertura"]),
                "demanda": _decimal(fila["demanda"]),
                "brecha": _decimal(fila["brecha"]),
            }
            for fila in filas
        ],
    }


def industrias_elemento(
    tipo: str,
    elemento_id: str,
    desde: date,
    hasta: date,
    limite: int = 10,
) -> dict[str, Any]:
    """Explica en qué industrias se concentra la demanda de un elemento elegido."""

    slug = _dimension(tipo)
    identificador = elemento_id.strip()
    if not identificador:
        raise ErrorDashboard("Debes seleccionar un elemento.")
    parametros = {
        **_parametros_periodo(desde, hasta),
        "elemento_id": identificador,
        "limite": _limite(limite),
    }
    filas = _ejecutar(
        f"dashboard_industrias_{slug}",
        CONSULTAS_INDUSTRIAS[slug],
        parametros,
    )
    return {
        "tipo": slug,
        "titulo": DIMENSIONES[slug].etiqueta_visible,
        "filas": [
            {
                "industria": str(fila["industria"] or "Sin industria"),
                "ofertas": _entero(fila["ofertas"]),
            }
            for fila in filas
        ],
    }
