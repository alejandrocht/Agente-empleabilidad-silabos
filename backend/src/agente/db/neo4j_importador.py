"""Importación incremental y reversible de los CSV curriculares hacia Neo4j.

Este módulo está separado del cliente del agente conversacional: la conversación
continúa siendo de solo lectura y la escritura solo ocurre detrás de los
endpoints explícitos de publicación.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Protocol, cast
from uuid import uuid4

from neo4j import READ_ACCESS, WRITE_ACCESS

from agente.config.settings import texto
from agente.db.neo4j import obtener_driver
from agente.normalizador.ejecuciones import GestorEjecuciones, gestor_ejecuciones
from agente.normalizador.silabos.salida import (
    ARCHIVOS_SALIDA,
    COBERTURA_SCHEMA,
    COMPETENCIAS_SCHEMA,
    HABILIDADES_SCHEMA,
    HERRAMIENTAS_SCHEMA,
)

ID_EJECUCION_RE = re.compile(r"NOR_[0-9a-f]{16}")
ID_IMPORTACION_RE = re.compile(r"IMP_[0-9a-f]{16}")
ID_PATTERNS = {
    "id_competencia": re.compile(r"COMP_[0-9a-f]{16}"),
    "id_habilidad": re.compile(r"HAB_[0-9a-f]{16}"),
    "id_herramienta": re.compile(r"HERR_[0-9a-f]{16}"),
    "id_cob_curricular": re.compile(r"COB_CUR_CAN_[0-9a-f]{16}"),
    "id_curso": re.compile(r"CUR_[0-9a-f]{16}"),
    "id_silabo": re.compile(r"SIL_[0-9a-f]{16}"),
}

RECOMENDACION = "Recomendamos revisar los datos antes de subirlos a la base de datos."
ESTADOS_CURRICULARES_PUBLICABLES = {"limpiado", "limpiado_con_advertencias"}
MAX_FILAS_POR_ARCHIVO = 100_000


class SesionNeo4j(Protocol):
    """Parte mínima de una sesión Neo4j usada por el adaptador y sus pruebas."""

    def __enter__(self) -> SesionNeo4j: ...

    def __exit__(self, tipo: Any, valor: Any, traza: Any) -> None: ...

    def run(self, cypher: str, parametros: dict[str, Any] | None = None) -> Iterable[Any]: ...

    def execute_write(self, funcion: Callable[[Any], Any]) -> Any: ...


class ImportacionNeo4jError(RuntimeError):
    """Error controlado que puede convertirse en un mensaje HTTP seguro."""

    def __init__(self, mensaje: str, status_code: int = 400) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class FuenteCurricular:
    """Filas validadas y fingerprint de los cuatro archivos de una ejecución."""

    filas: dict[str, list[dict[str, str]]]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class AnalisisImportacion:
    """Resultado interno del preview, incluyendo las filas que sí se escribirán."""

    preview: dict[str, Any]
    fuente: FuenteCurricular
    filas_nuevas: dict[str, list[dict[str, str]]]


def _ahora() -> str:
    return datetime.now(UTC).isoformat()


def _normalizar_nombre(valor: str) -> str:
    """Normaliza acentos, mayúsculas y puntuación para detectar duplicados semánticos."""

    sin_acentos = "".join(
        caracter
        for caracter in unicodedata.normalize("NFKD", valor)
        if not unicodedata.combining(caracter)
    )
    return re.sub(r"[^a-z0-9]+", " ", sin_acentos.casefold()).strip()


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def _filas_registro(resultado: Iterable[Any]) -> list[dict[str, Any]]:
    """Convierte Records reales o diccionarios de prueba en datos simples."""

    filas: list[dict[str, Any]] = []
    for registro in resultado:
        if isinstance(registro, dict):
            filas.append(dict(registro))
            continue
        try:
            filas.append(dict(registro))
        except (TypeError, ValueError):
            filas.append({})
    return filas


def _resultado_count(resultado: Iterable[Any]) -> int:
    filas = _filas_registro(resultado)
    if not filas:
        return 0
    return int(filas[0].get("total", 0) or 0)


class ImportadorNeo4j:
    """Valida, previsualiza, importa y revierte una ejecución curricular."""

    def __init__(
        self,
        gestor: GestorEjecuciones,
        driver_factory: Callable[[], Any] = obtener_driver,
        base_dir: Path | None = None,
    ) -> None:
        self.gestor = gestor
        self.driver_factory = driver_factory
        self.base_dir = base_dir or gestor.base_dir
        self._bloqueo = RLock()

    @property
    def _historial_path(self) -> Path:
        return self.base_dir / "neo4j_importaciones" / "historial.json"

    def previsualizar(self, id_ejecucion: str) -> dict[str, Any]:
        """Valida archivos y grafo sin ejecutar ninguna escritura."""

        return self._analizar(id_ejecucion).preview

    def importar(
        self,
        id_ejecucion: str,
        fingerprint: str,
        confirmar: bool,
    ) -> dict[str, Any]:
        """Importa solo filas nuevas y registra un identificador reversible."""

        if not confirmar:
            raise ImportacionNeo4jError(
                "La importación requiere confirmación explícita antes de escribir en Neo4j."
            )

        with self._bloqueo:
            analisis = self._analizar(id_ejecucion)
            if analisis.preview["fingerprint"] != fingerprint:
                raise ImportacionNeo4jError(
                    "Los archivos cambiaron desde la validación. Vuelve a revisar los datos.",
                    status_code=409,
                )
            if not analisis.preview["puede_importar"]:
                raise ImportacionNeo4jError(
                    analisis.preview["mensaje"],
                    status_code=409,
                )

            id_importacion = f"IMP_{uuid4().hex[:16]}"
            registro = {
                "id_importacion": id_importacion,
                "id_ejecucion": id_ejecucion,
                "fingerprint": fingerprint,
                "estado": "en_progreso",
                "creada_en": _ahora(),
                "actualizada_en": _ahora(),
                "resumen": analisis.preview["resumen"],
            }
            self._agregar_historial(registro)
            try:
                self._escribir_grafo(id_importacion, analisis.filas_nuevas)
            except Exception:
                self._actualizar_historial(
                    id_importacion,
                    {"estado": "fallida", "actualizada_en": _ahora()},
                )
                raise

            completada = {
                **registro,
                "estado": "completada",
                "actualizada_en": _ahora(),
                "resumen": analisis.preview["resumen"],
            }
            self._reemplazar_historial(completada)
            return {
                "mensaje": "La información nueva fue agregada a Neo4j.",
                "recomendacion": RECOMENDACION,
                **completada,
            }

    def historial(self) -> list[dict[str, Any]]:
        """Devuelve importaciones conocidas sin rutas internas ni credenciales."""

        with self._bloqueo:
            registros = self._leer_historial()
        return sorted(
            registros,
            key=lambda registro: _texto(registro.get("creada_en")),
            reverse=True,
        )

    def revertir(self, id_importacion: str, confirmar: bool) -> dict[str, Any]:
        """Elimina únicamente elementos marcados como creados por esa importación."""

        if not confirmar:
            raise ImportacionNeo4jError("La reversión requiere confirmación explícita.")
        if ID_IMPORTACION_RE.fullmatch(id_importacion) is None:
            raise ImportacionNeo4jError("La importación solicitada no es válida.")

        with self._bloqueo:
            registro = next(
                (
                    item
                    for item in self._leer_historial()
                    if item.get("id_importacion") == id_importacion
                ),
                None,
            )
            if registro is None:
                raise ImportacionNeo4jError("La importación no existe.", status_code=404)
            if registro.get("estado") in {"revertida", "revertida_parcial"}:
                raise ImportacionNeo4jError("La importación ya fue revertida.", status_code=409)
            if registro.get("estado") != "completada":
                raise ImportacionNeo4jError(
                    "Solo se pueden revertir importaciones completadas.",
                    status_code=409,
                )

            resultado = self._revertir_grafo(id_importacion)
            estado = "revertida_parcial" if resultado["conservados"] else "revertida"
            actualizado = {
                **registro,
                "estado": estado,
                "actualizada_en": _ahora(),
                "reversion": resultado,
            }
            self._reemplazar_historial(actualizado)
            return {
                "mensaje": (
                    "La importación fue revertida. Los datos existentes o conectados "
                    "se conservaron."
                ),
                **actualizado,
            }

    def _analizar(self, id_ejecucion: str) -> AnalisisImportacion:
        try:
            fuente = self._cargar_fuente(id_ejecucion)
        except ImportacionNeo4jError as exc:
            if exc.status_code != 400:
                raise
            preview = self._preview_base(id_ejecucion, "")
            preview.update(
                {
                    "puede_importar": False,
                    "mensaje": "La data no cumple el formato de los catálogos.",
                    "errores": [{"codigo": "FORMATO_CSV_INVALIDO", "mensaje": exc.mensaje}],
                }
            )
            return AnalisisImportacion(
                preview,
                FuenteCurricular(self._filas_vacias(), ""),
                self._filas_vacias(),
            )
        errores = self._validar_formato(fuente.filas)
        if errores:
            preview = self._preview_base(id_ejecucion, fuente.fingerprint)
            preview.update(
                {
                    "puede_importar": False,
                    "mensaje": "La data no cumple el formato de los catálogos.",
                    "errores": errores,
                }
            )
            return AnalisisImportacion(preview, fuente, self._filas_vacias())

        analisis = self._comparar_con_grafo(id_ejecucion, fuente)
        return analisis

    def _cargar_fuente(self, id_ejecucion: str) -> FuenteCurricular:
        if ID_EJECUCION_RE.fullmatch(id_ejecucion) is None:
            raise ImportacionNeo4jError("La ejecución solicitada no es válida.")
        try:
            estado = self.gestor.obtener(id_ejecucion)
        except KeyError as exc:
            raise ImportacionNeo4jError("La ejecución no existe.", status_code=404) from exc
        if (
            estado.get("tipo") != "silabos"
            or estado.get("estado") not in ESTADOS_CURRICULARES_PUBLICABLES
        ):
            raise ImportacionNeo4jError(
                "La ejecución no tiene CSV curriculares publicables.",
                status_code=409,
            )
        validacion = estado.get("validacion_silabos")
        if not isinstance(validacion, dict) or validacion.get("valida") is not True:
            raise ImportacionNeo4jError(
                "La ejecución curricular no superó la validación requerida.",
                status_code=409,
            )

        directorio = (self.base_dir / id_ejecucion / "salidas").resolve()
        raiz = (self.base_dir / id_ejecucion).resolve()
        if raiz not in directorio.parents or not directorio.is_dir():
            raise ImportacionNeo4jError(
                "No se encontraron las salidas curriculares.",
                status_code=404,
            )

        filas: dict[str, list[dict[str, str]]] = {}
        digest = hashlib.sha256()
        for archivo, esquema in ARCHIVOS_SALIDA:
            ruta = directorio / archivo
            if not ruta.is_file() or ruta.resolve().parent != directorio:
                raise ImportacionNeo4jError(
                    "La ejecución no contiene todos los catálogos curriculares.",
                    status_code=404,
                )
            contenido = ruta.read_bytes()
            digest.update(archivo.encode("utf-8"))
            digest.update(b"\0")
            digest.update(contenido)
            filas[archivo] = self._leer_csv(ruta, esquema)
        digest.update(id_ejecucion.encode("utf-8"))
        return FuenteCurricular(filas, digest.hexdigest())

    @staticmethod
    def _leer_csv(ruta: Path, esquema: tuple[str, ...]) -> list[dict[str, str]]:
        try:
            with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
                lector = csv.DictReader(archivo)
                if lector.fieldnames != list(esquema):
                    raise ImportacionNeo4jError(
                        f"El archivo {ruta.name} no tiene el encabezado establecido "
                        "por su catálogo."
                    )
                filas: list[dict[str, str]] = []
                for numero, fila in enumerate(lector, start=2):
                    if numero > MAX_FILAS_POR_ARCHIVO + 1:
                        raise ImportacionNeo4jError(
                            f"El archivo {ruta.name} supera el máximo de filas permitido."
                        )
                    if not fila or all(
                        not _texto(valor) for valor in fila.values() if valor is not None
                    ):
                        continue
                    if None in fila or any(clave not in fila for clave in esquema):
                        raise ImportacionNeo4jError(
                            f"La fila {numero} de {ruta.name} no respeta el número de columnas."
                        )
                    filas.append({clave: _texto(fila.get(clave)) for clave in esquema})
                return filas
        except UnicodeDecodeError as exc:
            raise ImportacionNeo4jError(
                f"El archivo {ruta.name} no está codificado como UTF-8."
            ) from exc

    def _validar_formato(self, filas: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
        errores: list[dict[str, str]] = []
        reglas = {
            "catalogo_competencias.csv": (
                COMPETENCIAS_SCHEMA,
                "id_competencia",
                "nombre_competencia",
            ),
            "catalogo_habilidades.csv": (HABILIDADES_SCHEMA, "id_habilidad", "nombre_habilidad"),
            "catalogo_herramientas.csv": (
                HERRAMIENTAS_SCHEMA,
                "id_herramienta",
                "nombre_herramienta",
            ),
            "cobertura_curricular.csv": (COBERTURA_SCHEMA, "id_cob_curricular", ""),
        }
        for archivo, (_, columna_id, columna_nombre) in reglas.items():
            vistos_id: dict[str, int] = {}
            vistos_nombre: dict[str, str] = {}
            for numero, fila in enumerate(filas[archivo], start=2):
                id_fila = fila.get(columna_id, "")
                patron = ID_PATTERNS.get(columna_id)
                if not id_fila or patron is None or patron.fullmatch(id_fila) is None:
                    errores.append(
                        self._error(
                            "ID_INVALIDO",
                            archivo,
                            numero,
                            f"{columna_id} no sigue el formato del catálogo.",
                        )
                    )
                elif id_fila in vistos_id:
                    errores.append(
                        self._error(
                            "ID_DUPLICADO",
                            archivo,
                            numero,
                            f"{columna_id} está repetido en la fila {vistos_id[id_fila]}.",
                        )
                    )
                else:
                    vistos_id[id_fila] = numero

                for campo in filas[archivo][0].keys() if filas[archivo] else ():
                    if campo == "id_herramienta" and archivo == "cobertura_curricular.csv":
                        continue
                    if not fila.get(campo):
                        errores.append(
                            self._error(
                                "CAMPO_OBLIGATORIO_VACIO",
                                archivo,
                                numero,
                                f"{campo} no puede estar vacío.",
                            )
                        )
                if columna_nombre:
                    nombre_norm = _normalizar_nombre(fila.get(columna_nombre, ""))
                    if nombre_norm and nombre_norm in vistos_nombre:
                        errores.append(
                            self._error(
                                "NOMBRE_DUPLICADO",
                                archivo,
                                numero,
                                f"El nombre es equivalente a la fila {vistos_nombre[nombre_norm]}.",
                            )
                        )
                    elif nombre_norm:
                        vistos_nombre[nombre_norm] = str(numero)

            if archivo == "cobertura_curricular.csv":
                vistos_clave: dict[tuple[str, ...], int] = {}
                for numero, fila in enumerate(filas[archivo], start=2):
                    clave = tuple(fila[campo] for campo in COBERTURA_SCHEMA[1:])
                    if clave in vistos_clave:
                        errores.append(
                            self._error(
                                "COBERTURA_DUPLICADA",
                                archivo,
                                numero,
                                "La combinación curricular está repetida en la fila "
                                f"{vistos_clave[clave]}."
                            )
                        )
                    else:
                        vistos_clave[clave] = numero
                    for campo in COBERTURA_SCHEMA[1:]:
                        if campo == "id_herramienta" and not fila[campo]:
                            continue
                        patron = ID_PATTERNS[campo]
                        if not fila[campo] or patron.fullmatch(fila[campo]) is None:
                            errores.append(
                                self._error(
                                    "REFERENCIA_INVALIDA",
                                    archivo,
                                    numero,
                                    f"{campo} no sigue el formato del catálogo.",
                                )
                            )
        return errores

    @staticmethod
    def _error(codigo: str, archivo: str, fila: int, mensaje: str) -> dict[str, str]:
        return {"codigo": codigo, "archivo": archivo, "fila": str(fila), "mensaje": mensaje}

    def _comparar_con_grafo(
        self,
        id_ejecucion: str,
        fuente: FuenteCurricular,
    ) -> AnalisisImportacion:
        existentes = self._leer_estado_grafo(fuente.filas)
        conflictos: list[dict[str, str]] = []
        filas_nuevas: dict[str, list[dict[str, str]]] = {
            archivo: [] for archivo, _ in ARCHIVOS_SALIDA
        }
        resumen = {
            "nuevas_competencias": 0,
            "nuevas_habilidades": 0,
            "nuevas_herramientas": 0,
            "nuevas_coberturas": 0,
            "sin_cambios": 0,
        }
        catalogo_info = {
            "catalogo_competencias.csv": (
                "competencias",
                "id_competencia",
                ("nombre_competencia", "descripcion_breve_competencia", "tipo_competencia"),
                "Competencia",
            ),
            "catalogo_habilidades.csv": (
                "habilidades",
                "id_habilidad",
                ("nombre_habilidad", "descripcion_breve"),
                "Habilidad",
            ),
            "catalogo_herramientas.csv": (
                "herramientas",
                "id_herramienta",
                ("nombre_herramienta", "descripcion_breve_herramienta"),
                "Herramienta",
            ),
        }
        for archivo, (resumen_key, columna_id, campos, label) in catalogo_info.items():
            existentes_id = existentes[label]["por_id"]
            existentes_nombre = existentes[label]["por_nombre"]
            for fila in fuente.filas[archivo]:
                id_fila = fila[columna_id]
                actual = existentes_id.get(id_fila)
                nombre_norm = _normalizar_nombre(fila[campos[0]])
                mismo_nombre = existentes_nombre.get(nombre_norm)
                if actual is not None:
                    if any(_texto(actual.get(campo)) != fila[campo] for campo in campos):
                        conflictos.append(
                            self._conflicto(
                                "ID_EXISTENTE_CON_CONFLICTO",
                                archivo,
                                f"El ID {id_fila} ya existe con otros atributos.",
                            )
                        )
                    else:
                        resumen["sin_cambios"] += 1
                    continue
                if mismo_nombre is not None and _texto(mismo_nombre.get(columna_id)) != id_fila:
                    conflictos.append(
                        self._conflicto(
                            "NOMBRE_EXISTENTE_CON_OTRO_ID",
                            archivo,
                            f"El nombre de {id_fila} ya existe con otro ID en Neo4j.",
                        )
                    )
                    continue
                filas_nuevas[archivo].append(fila)
                resumen[f"nuevas_{resumen_key}"] += 1

        existentes_coberturas = existentes["Cobertura_Curricular"]
        cursos = existentes["cursos"]
        silabos = existentes["silabos"]
        pares_curso_silabo = existentes["pares_curso_silabo"]
        ids_catalogo = {
            "id_competencia": {
                fila["id_competencia"] for fila in fuente.filas["catalogo_competencias.csv"]
            }
            | set(existentes["Competencia"]["por_id"]),
            "id_habilidad": {
                fila["id_habilidad"] for fila in fuente.filas["catalogo_habilidades.csv"]
            }
            | set(existentes["Habilidad"]["por_id"]),
            "id_herramienta": {
                fila["id_herramienta"] for fila in fuente.filas["catalogo_herramientas.csv"]
            }
            | set(existentes["Herramienta"]["por_id"]),
        }
        claves_cobertura: set[tuple[str, ...]] = set()
        for fila in fuente.filas["cobertura_curricular.csv"]:
            id_cobertura = fila["id_cob_curricular"]
            clave = tuple(fila[campo] for campo in COBERTURA_SCHEMA[1:])
            actual = existentes_coberturas["por_id"].get(id_cobertura)
            if actual is not None:
                actual_clave = tuple(_texto(actual.get(campo)) for campo in COBERTURA_SCHEMA[1:])
                if actual_clave != clave:
                    conflictos.append(
                        self._conflicto(
                            "COBERTURA_ID_CON_CONFLICTO",
                            "cobertura_curricular.csv",
                            f"El ID {id_cobertura} ya existe con otra cobertura.",
                        )
                    )
                else:
                    resumen["sin_cambios"] += 1
                continue
            if clave in existentes_coberturas["por_clave"] or clave in claves_cobertura:
                conflictos.append(
                    self._conflicto(
                        "COBERTURA_REPETIDA",
                        "cobertura_curricular.csv",
                        f"La cobertura {id_cobertura} ya existe con otro ID o está repetida.",
                    )
                )
                continue
            claves_cobertura.add(clave)
            if fila["id_curso"] not in cursos or fila["id_silabo"] not in silabos:
                conflictos.append(
                    self._conflicto(
                        "REFERENCIA_PARENT_NO_EXISTE",
                        "cobertura_curricular.csv",
                        f"La cobertura {id_cobertura} no encuentra su Curso o Silabo en Neo4j.",
                    )
                )
                continue
            if (fila["id_curso"], fila["id_silabo"]) not in pares_curso_silabo:
                conflictos.append(
                    self._conflicto(
                        "RELACION_CURSO_SILABO_NO_EXISTE",
                        "cobertura_curricular.csv",
                        f"La cobertura {id_cobertura} no tiene un vínculo Curso-Silabo válido.",
                    )
                )
                continue
            referencia_catalogo_valida = True
            for campo in ("id_competencia", "id_habilidad"):
                if fila[campo] not in ids_catalogo[campo]:
                    referencia_catalogo_valida = False
                    conflictos.append(
                        self._conflicto(
                            "REFERENCIA_CATALOGO_NO_EXISTE",
                            "cobertura_curricular.csv",
                            f"{campo} no existe en los catálogos disponibles.",
                        )
                    )
            if (
                fila["id_herramienta"]
                and fila["id_herramienta"] not in ids_catalogo["id_herramienta"]
            ):
                referencia_catalogo_valida = False
                conflictos.append(
                    self._conflicto(
                        "REFERENCIA_CATALOGO_NO_EXISTE",
                        "cobertura_curricular.csv",
                        "id_herramienta no existe en los catálogos disponibles.",
                    )
                )
            if referencia_catalogo_valida:
                filas_nuevas["cobertura_curricular.csv"].append(fila)
                resumen["nuevas_coberturas"] += 1

        total_nuevo = sum(
            len(filas_nuevas[archivo])
            for archivo, _ in ARCHIVOS_SALIDA
        )
        preview = self._preview_base(id_ejecucion, fuente.fingerprint)
        preview.update(
            {
                "puede_importar": not conflictos and total_nuevo > 0,
                "mensaje": (
                    "La data está validada y lista para confirmar."
                    if not conflictos and total_nuevo > 0
                    else "No hay datos nuevos para importar."
                    if not conflictos
                    else "La data requiere correcciones antes de importarse."
                ),
                "resumen": resumen,
                "conflictos": conflictos,
                "archivos": self._resumen_archivos(fuente.filas, filas_nuevas, existentes),
            }
        )
        return AnalisisImportacion(preview, fuente, filas_nuevas)

    @staticmethod
    def _conflicto(codigo: str, archivo: str, mensaje: str) -> dict[str, str]:
        return {"codigo": codigo, "archivo": archivo, "mensaje": mensaje}

    @staticmethod
    def _preview_base(id_ejecucion: str, fingerprint: str) -> dict[str, Any]:
        return {
            "id_ejecucion": id_ejecucion,
            "fingerprint": fingerprint,
            "puede_importar": False,
            "mensaje": "La data requiere revisión.",
            "recomendacion": RECOMENDACION,
            "archivos": [],
            "resumen": {
                "nuevas_competencias": 0,
                "nuevas_habilidades": 0,
                "nuevas_herramientas": 0,
                "nuevas_coberturas": 0,
                "sin_cambios": 0,
            },
            "conflictos": [],
            "errores": [],
            "advertencias": [],
        }

    @staticmethod
    def _filas_vacias() -> dict[str, list[dict[str, str]]]:
        return {archivo: [] for archivo, _ in ARCHIVOS_SALIDA}

    @staticmethod
    def _resumen_archivos(
        filas: dict[str, list[dict[str, str]]],
        filas_nuevas: dict[str, list[dict[str, str]]],
        existentes: dict[str, Any],
    ) -> list[dict[str, Any]]:
        mapa = {
            "catalogo_competencias.csv": ("Competencia", "id_competencia"),
            "catalogo_habilidades.csv": ("Habilidad", "id_habilidad"),
            "catalogo_herramientas.csv": ("Herramienta", "id_herramienta"),
            "cobertura_curricular.csv": ("Cobertura_Curricular", "id_cob_curricular"),
        }
        resultado: list[dict[str, Any]] = []
        for archivo, _ in ARCHIVOS_SALIDA:
            label, campo = mapa[archivo]
            existentes_ids = (
                set(existentes[label]["por_id"])
                if label != "Cobertura_Curricular"
                else set(existentes[label]["por_id"])
            )
            resultado.append(
                {
                    "archivo": archivo,
                    "filas": len(filas[archivo]),
                    "nuevas": len(filas_nuevas[archivo]),
                    "existentes": sum(
                        1 for fila in filas[archivo] if fila[campo] in existentes_ids
                    ),
                    "sin_cambios": sum(
                        1 for fila in filas[archivo] if fila[campo] in existentes_ids
                    ),
                }
            )
        return resultado

    def _leer_estado_grafo(self, filas: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
        with self._sesion(READ_ACCESS) as sesion:
            competencias = _filas_registro(
                sesion.run(
                    "MATCH (n:Competencia) RETURN n.id_competencia AS id_competencia, "
                    "n.nombre_competencia AS nombre_competencia, "
                    "n.descripcion_breve_competencia AS descripcion_breve_competencia, "
                    "n.tipo_competencia AS tipo_competencia"
                )
            )
            habilidades = _filas_registro(
                sesion.run(
                    "MATCH (n:Habilidad) RETURN n.id_habilidad AS id_habilidad, "
                    "n.nombre_habilidad AS nombre_habilidad, "
                    "n.descripcion_breve AS descripcion_breve"
                )
            )
            herramientas = _filas_registro(
                sesion.run(
                    "MATCH (n:Herramienta) RETURN n.id_herramienta AS id_herramienta, "
                    "n.nombre_herramienta AS nombre_herramienta, "
                    "n.descripcion_breve_herramienta AS descripcion_breve_herramienta"
                )
            )
            coberturas = _filas_registro(
                sesion.run(
                    "MATCH (n:Cobertura_Curricular) "
                    "RETURN n.id_cob_curricular AS id_cob_curricular, "
                    "n.id_curso AS id_curso, n.id_silabo AS id_silabo, "
                    "n.id_competencia AS id_competencia, n.id_habilidad AS id_habilidad, "
                    "n.id_herramienta AS id_herramienta"
                )
            )
            cursos = {
                _texto(registro.get("id"))
                for registro in _filas_registro(
                    sesion.run("MATCH (n:Curso) RETURN n.id_curso AS id")
                )
                if _texto(registro.get("id"))
            }
            silabos = {
                _texto(registro.get("id"))
                for registro in _filas_registro(
                    sesion.run("MATCH (n:Silabo) RETURN n.id_silabo AS id")
                )
                if _texto(registro.get("id"))
            }
            pares = {
                (_texto(registro.get("id_curso")), _texto(registro.get("id_silabo")))
                for registro in _filas_registro(
                    sesion.run(
                        "MATCH (curso:Curso)-[:TIENE]-(silabo:Silabo) "
                        "RETURN curso.id_curso AS id_curso, silabo.id_silabo AS id_silabo"
                    )
                )
            }
        return {
            "Competencia": self._indexar_catalogo(
                competencias, "id_competencia", "nombre_competencia"
            ),
            "Habilidad": self._indexar_catalogo(habilidades, "id_habilidad", "nombre_habilidad"),
            "Herramienta": self._indexar_catalogo(
                herramientas, "id_herramienta", "nombre_herramienta"
            ),
            "Cobertura_Curricular": {
                "por_id": {
                    _texto(registro.get("id_cob_curricular")): registro for registro in coberturas
                },
                "por_clave": {
                    tuple(_texto(registro.get(campo)) for campo in COBERTURA_SCHEMA[1:])
                    for registro in coberturas
                },
            },
            "cursos": cursos,
            "silabos": silabos,
            "pares_curso_silabo": pares,
        }

    @staticmethod
    def _indexar_catalogo(
        registros: list[dict[str, Any]],
        campo_id: str,
        campo_nombre: str,
    ) -> dict[str, Any]:
        por_id = {
            _texto(registro.get(campo_id)): registro
            for registro in registros
            if registro.get(campo_id)
        }
        por_nombre = {
            _normalizar_nombre(_texto(registro.get(campo_nombre))): registro
            for registro in registros
            if _normalizar_nombre(_texto(registro.get(campo_nombre)))
        }
        return {"por_id": por_id, "por_nombre": por_nombre}

    def _escribir_grafo(
        self,
        id_importacion: str,
        filas_nuevas: dict[str, list[dict[str, str]]],
    ) -> None:
        with self._sesion(WRITE_ACCESS) as sesion:
            def transaccion(tx: Any) -> None:
                self._escribir_catalogo(
                    tx,
                    "Competencia",
                    "id_competencia",
                    [
                        "nombre_competencia",
                        "descripcion_breve_competencia",
                        "tipo_competencia",
                    ],
                    filas_nuevas["catalogo_competencias.csv"],
                    id_importacion,
                )
                self._escribir_catalogo(
                    tx,
                    "Habilidad",
                    "id_habilidad",
                    ["nombre_habilidad", "descripcion_breve"],
                    filas_nuevas["catalogo_habilidades.csv"],
                    id_importacion,
                )
                self._escribir_catalogo(
                    tx,
                    "Herramienta",
                    "id_herramienta",
                    ["nombre_herramienta", "descripcion_breve_herramienta"],
                    filas_nuevas["catalogo_herramientas.csv"],
                    id_importacion,
                )
                filas_cobertura = filas_nuevas["cobertura_curricular.csv"]
                if not filas_cobertura:
                    return
                for requiere_herramienta in (False, True):
                    lote = [
                        fila
                        for fila in filas_cobertura
                        if bool(fila["id_herramienta"]) is requiere_herramienta
                    ]
                    if not lote:
                        continue
                    procesadas = _resultado_count(
                        tx.run(
                            self._cypher_cobertura(requiere_herramienta),
                            {"rows": lote, "import_id": id_importacion},
                        )
                    )
                    if procesadas != len(lote):
                        raise ImportacionNeo4jError(
                            "Neo4j cambió mientras se validaba la importación; "
                            "no se escribió la cobertura.",
                            status_code=409,
                        )

            sesion.execute_write(transaccion)

    @staticmethod
    def _escribir_catalogo(
        tx: Any,
        label: str,
        campo_id: str,
        campos: list[str],
        filas: list[dict[str, str]],
        id_importacion: str,
    ) -> None:
        if not filas:
            return
        propiedades = ", ".join(f"n.{campo} = row.{campo}" for campo in campos)
        consulta = (
            f"UNWIND $rows AS row MERGE (n:{label} {{{campo_id}: row.{campo_id}}}) "
            f"ON CREATE SET {propiedades}, n._ciar_import_id = $import_id, "
            "n._ciar_import_created = true RETURN count(n) AS total"
        )
        _resultado_count(tx.run(consulta, {"rows": filas, "import_id": id_importacion}))

    @staticmethod
    def _cypher_cobertura(requiere_herramienta: bool) -> str:
        match_herramienta = (
            "MATCH (herramienta:Herramienta {id_herramienta: row.id_herramienta}) "
            if requiere_herramienta
            else ""
        )
        merge_herramienta = (
            "MERGE (cob)-[rh:ENSENIA]->(herramienta) "
            "ON CREATE SET rh._ciar_import_id = $import_id, rh._ciar_import_created = true "
            if requiere_herramienta
            else ""
        )
        return (
            "UNWIND $rows AS row "
            "MATCH (curso:Curso {id_curso: row.id_curso})-[:TIENE]-(silabo:Silabo "
            "{id_silabo: row.id_silabo}) "
            "MATCH (competencia:Competencia {id_competencia: row.id_competencia}) "
            "MATCH (habilidad:Habilidad {id_habilidad: row.id_habilidad}) "
            f"{match_herramienta}"
            "MERGE (cob:Cobertura_Curricular {id_cob_curricular: row.id_cob_curricular}) "
            "ON CREATE SET cob.id_curso = row.id_curso, cob.id_silabo = row.id_silabo, "
            "cob.id_competencia = row.id_competencia, cob.id_habilidad = row.id_habilidad, "
            "cob.id_herramienta = row.id_herramienta, cob._ciar_import_id = $import_id, "
            "cob._ciar_import_created = true "
            "MERGE (curso)-[rt:TIENE]->(cob) "
            "ON CREATE SET rt._ciar_import_id = $import_id, rt._ciar_import_created = true "
            "MERGE (cob)-[rc:CUBRE]->(competencia) "
            "ON CREATE SET rc._ciar_import_id = $import_id, rc._ciar_import_created = true "
            "MERGE (cob)-[rhb:ENSENIA]->(habilidad) "
            "ON CREATE SET rhb._ciar_import_id = $import_id, rhb._ciar_import_created = true "
            f"{merge_herramienta}"
            "RETURN count(cob) AS total"
        )

    def _revertir_grafo(self, id_importacion: str) -> dict[str, int]:
        with self._sesion(WRITE_ACCESS) as sesion:
            def transaccion(tx: Any) -> dict[str, int]:
                relaciones = _resultado_count(
                    tx.run(
                        "MATCH ()-[r]-() WHERE r._ciar_import_id = $import_id "
                        "AND r._ciar_import_created = true DELETE r RETURN count(r) AS total",
                        {"import_id": id_importacion},
                    )
                )
                nodos = _resultado_count(
                    tx.run(
                        "MATCH (n) WHERE n._ciar_import_id = $import_id "
                        "AND n._ciar_import_created = true AND NOT (n)--() "
                        "DELETE n RETURN count(n) AS total",
                        {"import_id": id_importacion},
                    )
                )
                conservados = _resultado_count(
                    tx.run(
                        "MATCH (n) WHERE n._ciar_import_id = $import_id "
                        "AND n._ciar_import_created = true "
                        "SET n._ciar_import_id = NULL, n._ciar_import_created = NULL "
                        "RETURN count(n) AS total",
                        {"import_id": id_importacion},
                    )
                )
                return {
                    "relaciones_eliminadas": relaciones,
                    "nodos_eliminados": nodos,
                    "conservados": conservados,
                }

            return cast(dict[str, int], sesion.execute_write(transaccion))

    def _sesion(self, modo: str) -> AbstractContextManager[SesionNeo4j]:
        argumentos: dict[str, Any] = {"default_access_mode": modo}
        database = texto("NEO4J_DATABASE")
        if database:
            argumentos["database"] = database
        sesion = self.driver_factory().session(**argumentos)
        return cast(AbstractContextManager[SesionNeo4j], sesion)

    def _leer_historial(self) -> list[dict[str, Any]]:
        ruta = self._historial_path
        if not ruta.exists():
            return []
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ImportacionNeo4jError(
                "No se pudo leer el historial seguro de importaciones.",
                status_code=500,
            ) from exc
        if not isinstance(datos, list) or not all(isinstance(item, dict) for item in datos):
            raise ImportacionNeo4jError(
                "El historial de importaciones no es válido.",
                status_code=500,
            )
        return [dict(item) for item in datos]

    def _escribir_historial(self, registros: list[dict[str, Any]]) -> None:
        ruta = self._historial_path
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_suffix(".json.tmp")
        temporal.write_text(
            json.dumps(registros[-100:], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporal.replace(ruta)

    def _agregar_historial(self, registro: dict[str, Any]) -> None:
        registros = self._leer_historial()
        registros.append(registro)
        self._escribir_historial(registros)

    def _actualizar_historial(self, id_importacion: str, cambios: dict[str, Any]) -> None:
        registros = self._leer_historial()
        for registro in registros:
            if registro.get("id_importacion") == id_importacion:
                registro.update(cambios)
                break
        self._escribir_historial(registros)

    def _reemplazar_historial(self, actualizado: dict[str, Any]) -> None:
        registros = self._leer_historial()
        reemplazado = False
        for indice, registro in enumerate(registros):
            if registro.get("id_importacion") == actualizado.get("id_importacion"):
                registros[indice] = actualizado
                reemplazado = True
                break
        if not reemplazado:
            registros.append(actualizado)
        self._escribir_historial(registros)


importador_neo4j = ImportadorNeo4j(gestor_ejecuciones)
