"""Importación técnica incremental y reversible hacia Neo4j.

Este módulo está separado del cliente del agente conversacional: la conversación
continúa siendo de solo lectura y la escritura solo ocurre detrás de los
endpoints explícitos de publicación.
"""

from __future__ import annotations

import hashlib
import json
import re
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
from agente.db import neo4j_catalogos
from agente.db.neo4j import obtener_driver
from agente.normalizador.ejecuciones import GestorEjecuciones, gestor_ejecuciones

_TECHNICAL_SCHEMAS = dict(neo4j_catalogos.ARCHIVOS_CATALOGO)


ID_EJECUCION_RE = re.compile(r"NOR_[0-9a-f]{16}")
ID_IMPORTACION_RE = re.compile(r"IMP_[0-9a-f]{16}")
RECOMENDACION = "Recomendamos revisar los datos antes de subirlos a la base de datos."
ESTADOS_CURRICULARES_PUBLICABLES = {"limpiado", "limpiado_con_advertencias"}
RELEASE_GATE_DECISION = "ALLOW_IMPORT"


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
    """Filas validadas y fingerprint de una ejecución curricular."""

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
    try:
        return int(filas[0].get("total", 0) or 0)
    except (TypeError, ValueError):
        return 0


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
                self._escribir_grafo_tecnico(id_importacion, analisis.fuente.filas)
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
        gate_error = self._validar_release_gate(id_ejecucion)
        if gate_error is not None:
            filas_vacias = self._filas_vacias_tecnicas()
            preview = self._preview_base_tecnico(id_ejecucion, "")
            preview.update(
                {
                    "puede_importar": False,
                    "mensaje": gate_error["mensaje"],
                    "errores": [gate_error],
                }
            )
            return AnalisisImportacion(
                preview,
                FuenteCurricular(filas_vacias, ""),
                filas_vacias,
            )
        try:
            fuente = self._cargar_fuente_tecnica(id_ejecucion)
        except ImportacionNeo4jError as exc:
            if exc.status_code != 400:
                raise
            preview = self._preview_base_tecnico(id_ejecucion, "")
            preview.update(
                {
                    "puede_importar": False,
                    "mensaje": "La data no cumple el formato de los catálogos técnicos.",
                    "errores": [{"codigo": "FORMATO_CSV_INVALIDO", "mensaje": exc.mensaje}],
                }
            )
            filas_vacias = self._filas_vacias_tecnicas()
            return AnalisisImportacion(
                preview,
                FuenteCurricular(filas_vacias, ""),
                filas_vacias,
            )
        return self._comparar_con_grafo_tecnico(id_ejecucion, fuente)

    def _leer_manifesto_tecnico(self, id_ejecucion: str) -> dict[str, Any] | None:
        if ID_EJECUCION_RE.fullmatch(id_ejecucion) is None:
            return None
        ruta = (self.base_dir / id_ejecucion / "manifest.json").resolve()
        raiz = (self.base_dir / id_ejecucion).resolve()
        if ruta.parent != raiz or not ruta.is_file():
            return None
        try:
            manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(manifiesto, dict):
            return None
        if manifiesto.get("tipo") != "silabos":
            return None
        return manifiesto

    def _cargar_fuente_tecnica(self, id_ejecucion: str) -> FuenteCurricular:
        if ID_EJECUCION_RE.fullmatch(id_ejecucion) is None:
            raise ImportacionNeo4jError("La ejecución solicitada no es válida.")
        estado = self._leer_manifesto_tecnico(id_ejecucion)
        if estado is None:
            raise ImportacionNeo4jError(
                "La ejecución técnica no tiene un manifiesto inmutable válido.",
                status_code=409,
            )
        if (
            estado.get("tipo") != "silabos"
            or estado.get("estado") not in ESTADOS_CURRICULARES_PUBLICABLES
        ):
            raise ImportacionNeo4jError(
                "La ejecución no tiene CSV curriculares técnicos publicables.",
                status_code=409,
            )
        validacion = estado.get("validacion_silabos")
        if (
            not isinstance(validacion, dict)
            or type(validacion.get("valida")) is not bool
            or not validacion.get("valida")
        ):
            raise ImportacionNeo4jError(
                "La ejecución curricular no superó la validación requerida.",
                status_code=409,
            )
        gate_error = self._validar_release_gate(id_ejecucion)
        if gate_error is not None:
            raise ImportacionNeo4jError(gate_error["mensaje"], status_code=409)
        directorio = (self.base_dir / id_ejecucion / "salidas").resolve()
        raiz = (self.base_dir / id_ejecucion).resolve()
        if raiz not in directorio.parents or not directorio.is_dir():
            raise ImportacionNeo4jError(
                "No se encontraron las salidas curriculares técnicas.",
                status_code=404,
            )
        try:
            filas = neo4j_catalogos.leer_catalogos(directorio)
        except ValueError as exc:
            raise ImportacionNeo4jError(str(exc), status_code=400) from exc
        digest = hashlib.sha256()
        for archivo, _ in neo4j_catalogos.ARCHIVOS_CATALOGO:
            ruta = directorio / archivo
            digest.update(archivo.encode("utf-8"))
            digest.update(b"\\0")
            digest.update(ruta.read_bytes())
        digest.update(id_ejecucion.encode("utf-8"))
        return FuenteCurricular(filas, digest.hexdigest())

    def _leer_estado_grafo_tecnico(self) -> dict[str, dict[str, dict[str, Any]]]:
        consultas = {
            "Curso": (
                "MATCH (n:Curso) RETURN n.id_curso AS id_curso, n.nombre_curso AS nombre_curso, "
                "n.coordinador AS coordinador, n.creditos AS creditos, n.nivel AS nivel, "
                "n.tipo_curso AS tipo_curso, n.codigo_curso AS codigo_curso, "
                "n.id_carrera AS id_carrera"
            ),
            "Silabo": (
                "MATCH (n:Silabo) RETURN n.id_silabo AS id_silabo, "
                "n.codigo_silabo AS codigo_silabo, "
                "n.sumilla AS sumilla, n.id_curso AS id_curso, "
                "n.periodo_academico AS periodo_academico"
            ),
            "Competencia": (
                "MATCH (n:Competencia) RETURN n.id_competencia AS id_competencia, "
                "n.nombre_competencia AS nombre_competencia, "
                "n.descripcion_breve_competencia AS descripcion_breve_competencia, "
                "n.tipo_competencia AS tipo_competencia, n.codigo_competencia AS codigo_competencia"
            ),
            "Logro": "MATCH (n:Logro) RETURN n.id_logro AS id_logro, n.logro AS logro",
            "CoberturaCurricular": (
                "MATCH (n:CoberturaCurricular) RETURN n.id_cob_curricular AS id_cob_curricular, "
                "n.id_curso AS id_curso, n.id_silabo AS id_silabo, "
                "n.id_competencia AS id_competencia, n.id_logro AS id_logro"
            ),
        }
        with self._sesion(READ_ACCESS) as sesion:
            resultado: dict[str, dict[str, dict[str, Any]]] = {}
            for etiqueta, consulta in consultas.items():
                filas = _filas_registro(sesion.run(consulta))
                campo_id = {
                    "Curso": "id_curso",
                    "Silabo": "id_silabo",
                    "Competencia": "id_competencia",
                    "Logro": "id_logro",
                    "CoberturaCurricular": "id_cob_curricular",
                }[etiqueta]
                resultado[etiqueta] = {
                    _texto(fila.get(campo_id)): fila for fila in filas if _texto(fila.get(campo_id))
                }
        return resultado

    def _comparar_con_grafo_tecnico(
        self,
        id_ejecucion: str,
        fuente: FuenteCurricular,
    ) -> AnalisisImportacion:
        existentes = self._leer_estado_grafo_tecnico()
        definiciones = {
            "curso.csv": ("Curso", "id_curso", _TECHNICAL_SCHEMAS["curso.csv"]),
            "silabo.csv": ("Silabo", "id_silabo", _TECHNICAL_SCHEMAS["silabo.csv"]),
            "catalogo_competencias.csv": (
                "Competencia",
                "id_competencia",
                _TECHNICAL_SCHEMAS["catalogo_competencias.csv"],
            ),
            "catalogo_logros.csv": (
                "Logro",
                "id_logro",
                _TECHNICAL_SCHEMAS["catalogo_logros.csv"],
            ),
            "cobertura_curricular.csv": (
                "CoberturaCurricular",
                "id_cob_curricular",
                _TECHNICAL_SCHEMAS["cobertura_curricular.csv"],
            ),
        }
        filas_nuevas = self._filas_vacias_tecnicas()
        conflictos: list[dict[str, str]] = []
        resumen = {
            "nuevos_cursos": 0,
            "nuevos_silabos": 0,
            "nuevas_competencias": 0,
            "nuevos_logros": 0,
            "nuevas_coberturas": 0,
            "sin_cambios": 0,
        }
        for archivo, (etiqueta, campo_id, esquema) in definiciones.items():
            existentes_por_id = existentes[etiqueta]
            for fila in fuente.filas[archivo]:
                actual = existentes_por_id.get(fila[campo_id])
                if actual is None:
                    filas_nuevas[archivo].append(fila)
                    resumen_key = {
                        "curso.csv": "nuevos_cursos",
                        "silabo.csv": "nuevos_silabos",
                        "catalogo_competencias.csv": "nuevas_competencias",
                        "catalogo_logros.csv": "nuevos_logros",
                        "cobertura_curricular.csv": "nuevas_coberturas",
                    }[archivo]
                    resumen[resumen_key] += 1
                    continue
                diferencias = [
                    campo
                    for campo in esquema[1:]
                    if actual.get(campo) is not None and _texto(actual.get(campo)) != fila[campo]
                ]
                if diferencias:
                    conflictos.append(
                        self._conflicto(
                            "ID_EXISTENTE_CON_CONFLICTO",
                            archivo,
                            f"El ID {fila[campo_id]} ya existe con propiedades distintas: "
                            f"{', '.join(diferencias)}.",
                        )
                    )
                else:
                    resumen["sin_cambios"] += 1
        total_nuevo = sum(len(filas) for filas in filas_nuevas.values())
        preview = self._preview_base_tecnico(id_ejecucion, fuente.fingerprint)
        preview.update(
            {
                "puede_importar": not conflictos and total_nuevo > 0,
                "mensaje": (
                    "La data técnica está validada y lista para confirmar."
                    if not conflictos and total_nuevo > 0
                    else "No hay datos técnicos nuevos para importar."
                    if not conflictos
                    else "La data técnica requiere correcciones antes de importarse."
                ),
                "resumen": resumen,
                "conflictos": conflictos,
                "archivos": self._resumen_archivos_tecnico(fuente.filas, filas_nuevas, existentes),
                "release_gate": {"decision": RELEASE_GATE_DECISION},
            }
        )
        return AnalisisImportacion(preview, fuente, filas_nuevas)

    def _validar_release_gate(self, id_ejecucion: str) -> dict[str, str] | None:
        """Require the producer-owned gate before reading importable CSVs."""

        if ID_EJECUCION_RE.fullmatch(id_ejecucion) is None:
            return None
        estado = self._leer_manifesto_tecnico(id_ejecucion)
        if estado is None:
            try:
                estado = self.gestor.obtener(id_ejecucion)
            except KeyError as exc:
                raise ImportacionNeo4jError("La ejecución no existe.", status_code=404) from exc
        gate = estado.get("release_gate")
        if not isinstance(gate, dict):
            limpieza = estado.get("limpieza_silabos")
            gate = limpieza.get("release_gate") if isinstance(limpieza, dict) else None
        if not isinstance(gate, dict):
            return {
                "codigo": "RELEASE_GATE_AUSENTE",
                "mensaje": "La ejecución no tiene un release gate curricular verificable.",
            }
        aprobacion = estado.get("aprobacion_curricular")
        pendientes_por_decidir = 0
        if isinstance(aprobacion, dict):
            try:
                pendientes_por_decidir = int(aprobacion.get("pendientes_por_decidir", 0) or 0)
            except (TypeError, ValueError):
                pendientes_por_decidir = 1
        requiere_decision = (
            isinstance(aprobacion, dict)
            and type(aprobacion.get("requiere_decision")) is bool
            and bool(aprobacion.get("requiere_decision"))
        )
        if isinstance(aprobacion, dict) and (requiere_decision or pendientes_por_decidir > 0):
            return {
                "codigo": "PENDING_DECISIONS",
                "mensaje": (
                    "La ejecución no puede importarse mientras existan propuestas "
                    "curriculares sin una decisión explícita."
                ),
            }
        if gate.get("decision") != RELEASE_GATE_DECISION:
            blockers = gate.get("blockers")
            detalle = (
                "; ".join(str(item) for item in blockers)
                if isinstance(blockers, list)
                else "sin detalle"
            )
            return {
                "codigo": "RELEASE_GATE_BLOQUEADO",
                "mensaje": (
                    "La ejecución no puede importarse porque el release gate está bloqueado. "
                    f"Motivos: {detalle}."
                ),
            }
        return None

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
                "nuevos_cursos": 0,
                "nuevos_silabos": 0,
                "nuevas_competencias": 0,
                "nuevos_logros": 0,
                "nuevas_coberturas": 0,
                "sin_cambios": 0,
            },
            "conflictos": [],
            "errores": [],
            "advertencias": [],
            "release_gate": None,
        }

    @staticmethod
    def _filas_vacias_tecnicas() -> dict[str, list[dict[str, str]]]:
        return {archivo: [] for archivo, _ in neo4j_catalogos.ARCHIVOS_CATALOGO}

    @staticmethod
    def _preview_base_tecnico(id_ejecucion: str, fingerprint: str) -> dict[str, Any]:
        return ImportadorNeo4j._preview_base(id_ejecucion, fingerprint)

    @staticmethod
    def _resumen_archivos_tecnico(
        filas: dict[str, list[dict[str, str]]],
        filas_nuevas: dict[str, list[dict[str, str]]],
        existentes: dict[str, dict[str, dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        definiciones = {
            "curso.csv": ("Curso", "id_curso"),
            "silabo.csv": ("Silabo", "id_silabo"),
            "catalogo_competencias.csv": ("Competencia", "id_competencia"),
            "catalogo_logros.csv": ("Logro", "id_logro"),
            "cobertura_curricular.csv": ("CoberturaCurricular", "id_cob_curricular"),
        }
        return [
            {
                "archivo": archivo,
                "filas": len(filas[archivo]),
                "nuevas": len(filas_nuevas[archivo]),
                "existentes": sum(
                    1 for fila in filas[archivo] if fila[campo] in existentes[etiqueta]
                ),
                "sin_cambios": sum(
                    1 for fila in filas[archivo] if fila[campo] in existentes[etiqueta]
                ),
            }
            for archivo, (etiqueta, campo) in definiciones.items()
        ]

    def _escribir_grafo_tecnico(
        self,
        id_importacion: str,
        filas: dict[str, list[dict[str, str]]],
    ) -> None:
        with self._sesion(WRITE_ACCESS) as sesion:

            def transaccion(tx: Any) -> None:
                neo4j_catalogos.escribir_catalogos(tx, filas, id_importacion)

            sesion.execute_write(transaccion)

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
                propiedades_restauradas = _resultado_count(
                    tx.run(
                        "MATCH (reversion:CiarImportacionCursoReversion "
                        "{id_importacion: $import_id}) "
                        "MATCH (curso:Curso {id_curso: reversion.id_curso}) "
                        "SET curso.nombre_curso = CASE WHEN 'nombre_curso' "
                        "IN reversion.propiedades_presentes THEN "
                        "reversion.nombre_curso ELSE NULL END, "
                        "curso.coordinador = CASE WHEN 'coordinador' "
                        "IN reversion.propiedades_presentes THEN "
                        "reversion.coordinador ELSE NULL END, "
                        "curso.creditos = CASE WHEN 'creditos' "
                        "IN reversion.propiedades_presentes THEN reversion.creditos ELSE NULL END, "
                        "curso.nivel = CASE WHEN 'nivel' "
                        "IN reversion.propiedades_presentes THEN reversion.nivel ELSE NULL END, "
                        "curso.tipo_curso = CASE WHEN 'tipo_curso' "
                        "IN reversion.propiedades_presentes THEN "
                        "reversion.tipo_curso ELSE NULL END, "
                        "curso.codigo_curso = CASE WHEN 'codigo_curso' "
                        "IN reversion.propiedades_presentes THEN "
                        "reversion.codigo_curso ELSE NULL END, "
                        "curso.id_carrera = CASE WHEN 'id_carrera' "
                        "IN reversion.propiedades_presentes THEN "
                        "reversion.id_carrera ELSE NULL END "
                        "RETURN count(curso) AS total",
                        {"import_id": id_importacion},
                    )
                )
                _resultado_count(
                    tx.run(
                        "MATCH (reversion:CiarImportacionCursoReversion "
                        "{id_importacion: $import_id}) DELETE reversion "
                        "RETURN count(reversion) AS total",
                        {"import_id": id_importacion},
                    )
                )
                return {
                    "relaciones_eliminadas": relaciones,
                    "nodos_eliminados": nodos,
                    "conservados": conservados,
                    "propiedades_restauradas": propiedades_restauradas,
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
