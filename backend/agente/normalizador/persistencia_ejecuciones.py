"""Persistencia y lectura segura del historial de ejecuciones del normalizador."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol, cast

from agente.normalizador.modelos import (
    EstadoEjecucion,
    Hallazgo,
    ProgresoLimpiezaLLM,
    ResultadoLimpieza,
    ResultadoLimpiezaSilabos,
    ResultadoNormalizacion,
    ResultadoValidacionEntrada,
    ResultadoValidacionSilabos,
)
from agente.normalizador.silabos.salida import (
    _REPORTES_CURRICULARES_PRE_HITL,
    _filtrar_estado_publico,
    _filtrar_outputs_curriculares,
    _hitl_curricular_completado,
)

_ESTADOS_TERMINALES: frozenset[str] = frozenset(
    {
        "normalizado",
        "normalizado_con_advertencias",
        "no_publicado",
        "limpiado",
        "limpiado_con_advertencias",
        "rechazado",
        "error",
        "cancelado",
    }
)
_ID_EJECUCION = r"NOR_[0-9a-f]{16}"
_WARNING_MACOS_OBSOLETO = "METADATO_MACOS_IGNORADO"
_ESTADOS_SIN_ADVERTENCIAS = {
    "validado_con_advertencias": "validado",
    "limpiado_con_advertencias": "limpiado",
    "normalizado_con_advertencias": "normalizado",
}


class EjecucionPersistible(Protocol):
    """Datos que el repositorio necesita, sin acoplarse a la fachada de workers."""

    id_ejecucion: str
    tipo: str
    archivo: str
    directorio: Path
    parametros: dict[str, str]
    configuracion_curricular: dict[str, object] | None
    estado: EstadoEjecucion
    creada_en: str
    actualizada_en: str
    cancelacion_solicitada: bool
    cancelada_en: str | None
    validacion: ResultadoValidacionEntrada | None
    validacion_silabos: ResultadoValidacionSilabos | None
    limpieza: ResultadoLimpieza | None
    limpieza_silabos: ResultadoLimpiezaSilabos | None
    normalizacion: ResultadoNormalizacion | None
    catalogo_chh: dict[str, object] | None
    hallazgos: list[Hallazgo]
    progreso_llm: ProgresoLimpiezaLLM | None
    fuente: dict[str, object] | None
    progreso_fuente: dict[str, object] | None
    outputs_fuente: list[dict[str, object]]

    def a_dict(self) -> dict[str, object]: ...


ResumenAprobacion = Callable[[Path], dict[str, object] | None]
ObtenerActiva = Callable[[str], EjecucionPersistible]


def _actualizar_metadatos_outputs(
    directorio: Path,
    outputs: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Recalcula hashes cuando una aprobación cambia un CSV ya publicado."""

    resultado: list[dict[str, object]] = []
    vistos: set[str] = set()
    for output in outputs:
        if not isinstance(output, dict):
            continue
        archivo = output.get("archivo")
        if not isinstance(archivo, str) or not archivo:
            continue
        vistos.add(archivo)
        actualizado = dict(output)
        ruta = (directorio / archivo).resolve()
        raiz = directorio.resolve()
        if raiz in ruta.parents and ruta.is_file():
            digest = hashlib.sha256()
            with ruta.open("rb") as contenido:
                for bloque in iter(lambda: contenido.read(1024 * 1024), b""):
                    digest.update(bloque)
            actualizado["bytes"] = ruta.stat().st_size
            actualizado["sha256"] = digest.hexdigest()
        resultado.append(actualizado)

    decisiones = directorio / "salidas" / "reportes" / "decisiones_curriculares.jsonl"
    relativo = "salidas/reportes/decisiones_curriculares.jsonl"
    if relativo not in vistos and decisiones.is_file():
        decision_digest = hashlib.sha256(decisiones.read_bytes()).hexdigest()
        resultado.append(
            {
                "tipo": "decisiones_curriculares",
                "archivo": relativo,
                "registros": sum(
                    1
                    for linea in decisiones.read_text(encoding="utf-8").splitlines()
                    if linea.strip()
                ),
                "bytes": decisiones.stat().st_size,
                "sha256": decision_digest,
            }
        )
    return resultado


def _es_warning_macos_obsoleto(valor: object) -> bool:
    return isinstance(valor, dict) and valor.get("codigo") == _WARNING_MACOS_OBSOLETO


def _limpiar_warning_macos(valor: object) -> tuple[object, int]:
    """Quita solo entradas de warning obsoletas y conserva el resto del JSON."""

    if isinstance(valor, list):
        limpio: list[object] = []
        eliminados = 0
        for elemento in valor:
            if _es_warning_macos_obsoleto(elemento):
                eliminados += 1
                continue
            elemento_limpio, cantidad = _limpiar_warning_macos(elemento)
            limpio.append(elemento_limpio)
            eliminados += cantidad
        return limpio, eliminados
    if isinstance(valor, dict):
        if _es_warning_macos_obsoleto(valor):
            return {}, 1
        limpio_dict: dict[str, object] = {}
        eliminados = 0
        for clave, elemento in valor.items():
            if _es_warning_macos_obsoleto(elemento):
                eliminados += 1
                continue
            elemento_limpio, cantidad = _limpiar_warning_macos(elemento)
            limpio_dict[clave] = elemento_limpio
            eliminados += cantidad

        hallazgos = limpio_dict.get("hallazgos")
        if isinstance(hallazgos, list):
            advertencias = sum(
                1
                for hallazgo in hallazgos
                if isinstance(hallazgo, dict) and hallazgo.get("severidad") == "warning"
            )
            for clave in ("advertencias", "warnings", "warning_count", "warnings_count"):
                valor_derivado = limpio_dict.get(clave)
                if isinstance(valor_derivado, int) and not isinstance(valor_derivado, bool):
                    limpio_dict[clave] = advertencias
        return limpio_dict, eliminados
    return valor, 0


class RepositorioEjecucionesPersistidas:
    """Encapsula manifests, artefactos y retención sin gestionar workers."""

    def __init__(
        self,
        base_dir: Path,
        max_historial: int,
        retencion_dias: int,
        obtener_activa: ObtenerActiva,
    ) -> None:
        self.base_dir = base_dir
        self.max_historial = max_historial
        self.retencion_dias = retencion_dias
        self._obtener_activa = obtener_activa
        self._migrar_warning_macos_legacy()

    @staticmethod
    def serializar_ejecucion(
        ejecucion: EjecucionPersistible,
        resumen_aprobacion: ResumenAprobacion,
    ) -> dict[str, object]:
        """Expone el contrato público sin filtrar rutas internas del servidor."""

        limpieza_actual = ejecucion.limpieza_silabos
        release_gate = dict(limpieza_actual.release_gate) if limpieza_actual else None
        if ejecucion.tipo == "silabos":
            reporte_gate = ejecucion.directorio / "salidas" / "reportes" / "release_gate.json"
            try:
                contenido_gate = json.loads(reporte_gate.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                contenido_gate = None
            if isinstance(contenido_gate, dict):
                release_gate = contenido_gate

        outputs_procesamiento = (
            list(ejecucion.normalizacion.outputs)
            if ejecucion.normalizacion
            else list(ejecucion.limpieza.outputs)
            if ejecucion.limpieza
            else list(limpieza_actual.outputs)
            if limpieza_actual
            else []
        )
        outputs = [*ejecucion.outputs_fuente, *outputs_procesamiento]
        outputs = _actualizar_metadatos_outputs(ejecucion.directorio, outputs)
        aprobacion_curricular = (
            resumen_aprobacion(ejecucion.directorio) if ejecucion.tipo == "silabos" else None
        )

        limpieza_silabos = limpieza_actual.a_dict() if limpieza_actual else None
        if ejecucion.tipo == "silabos":
            hitl_completado = _hitl_curricular_completado(release_gate)
            outputs = _filtrar_outputs_curriculares(outputs, hitl_completado=hitl_completado)
            if isinstance(limpieza_silabos, dict):
                outputs_limpieza = limpieza_silabos.get("outputs")
                if isinstance(outputs_limpieza, list):
                    limpieza_silabos = dict(limpieza_silabos)
                    limpieza_silabos["outputs"] = _filtrar_outputs_curriculares(
                        [dict(output) for output in outputs_limpieza if isinstance(output, dict)],
                        hitl_completado=hitl_completado,
                    )

        return {
            "id_ejecucion": ejecucion.id_ejecucion,
            "tipo": ejecucion.tipo,
            "archivo": ejecucion.archivo,
            "parametros": dict(ejecucion.parametros),
            "configuracion_curricular": ejecucion.configuracion_curricular,
            "estado": ejecucion.estado,
            "creada_en": ejecucion.creada_en,
            "actualizada_en": ejecucion.actualizada_en,
            "cancelacion_solicitada": ejecucion.cancelacion_solicitada,
            "cancelada_en": ejecucion.cancelada_en,
            "validacion": ejecucion.validacion.a_dict() if ejecucion.validacion else None,
            "validacion_silabos": (
                ejecucion.validacion_silabos.a_dict() if ejecucion.validacion_silabos else None
            ),
            "limpieza": ejecucion.limpieza.a_dict() if ejecucion.limpieza else None,
            "limpieza_silabos": limpieza_silabos,
            "normalizacion": ejecucion.normalizacion.a_dict() if ejecucion.normalizacion else None,
            "release_gate": release_gate,
            "aprobacion_curricular": aprobacion_curricular,
            "catalogo_chh": ejecucion.catalogo_chh,
            "fuente": ejecucion.fuente,
            "progreso_fuente": ejecucion.progreso_fuente,
            "progreso_llm": ejecucion.progreso_llm.a_dict() if ejecucion.progreso_llm else None,
            "hallazgos": [hallazgo.a_dict() for hallazgo in ejecucion.hallazgos],
            "outputs": outputs,
        }

    @staticmethod
    def actualizar_metadatos_outputs(
        directorio: Path,
        outputs: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        return _actualizar_metadatos_outputs(directorio, outputs)

    @staticmethod
    def es_terminal(estado: str) -> bool:
        return estado in _ESTADOS_TERMINALES

    def persistir(self, ejecucion: EjecucionPersistible) -> None:
        manifest = ejecucion.directorio / "manifest.json"
        temporal = manifest.with_suffix(".json.tmp")
        temporal.write_text(
            json.dumps(ejecucion.a_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporal.replace(manifest)

    def listar_historial(self, limite: int = 20) -> dict[str, object]:
        self.aplicar_retencion()
        limite_seguro = min(max(1, limite), 100)
        ejecuciones = sorted(
            (self._resumen_historial(datos) for datos in self._leer_manifests()),
            key=lambda datos: str(datos.get("actualizada_en") or datos.get("creada_en") or ""),
            reverse=True,
        )
        return {
            "ejecuciones": ejecuciones[:limite_seguro],
            "total": len(ejecuciones),
            "retencion": {
                "max_ejecuciones": self.max_historial,
                "dias": self.retencion_dias,
            },
        }

    def obtener(self, id_ejecucion: str) -> dict[str, object]:
        try:
            return self._obtener_activa(id_ejecucion).a_dict()
        except KeyError:
            try:
                manifest = self.directorio_seguro(id_ejecucion) / "manifest.json"
            except KeyError:
                raise KeyError(id_ejecucion) from None
            if not manifest.exists():
                raise
            datos = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(datos, dict):
                raise ValueError("El manifest de la ejecución no tiene un objeto raíz.")
            return _filtrar_estado_publico(cast(dict[str, object], datos))

    def obtener_reporte(self, id_ejecucion: str) -> dict[str, object]:
        estado = self.obtener(id_ejecucion)
        reportes: dict[str, object] = {}
        directorio_reportes = self.directorio_seguro(id_ejecucion) / "salidas" / "reportes"
        hitl_completado = _hitl_curricular_completado(estado.get("release_gate"))
        if directorio_reportes.is_dir():
            for ruta in sorted(directorio_reportes.iterdir()):
                if not ruta.is_file() or ruta.suffix.lower() not in {".json", ".jsonl"}:
                    continue
                if (
                    estado.get("tipo") == "silabos"
                    and not hitl_completado
                    and ruta.name not in _REPORTES_CURRICULARES_PRE_HITL
                ):
                    continue
                reportes[ruta.name] = self._leer_reporte(ruta)
        return {
            "id_ejecucion": id_ejecucion,
            "manifest": estado,
            "reportes": reportes,
        }

    def eliminar_historial(self, id_ejecucion: str) -> dict[str, object]:
        directorio = self.directorio_seguro(id_ejecucion)
        if not directorio.is_dir():
            raise KeyError(id_ejecucion)
        shutil.rmtree(directorio)
        return {"id_ejecucion": id_ejecucion, "eliminado": True}

    def directorio_seguro(self, id_ejecucion: str) -> Path:
        if re.fullmatch(_ID_EJECUCION, id_ejecucion) is None:
            raise KeyError(id_ejecucion)
        raiz = self.base_dir.resolve()
        directorio = (raiz / id_ejecucion).resolve()
        if directorio.parent != raiz:
            raise KeyError(id_ejecucion)
        return directorio

    def aplicar_retencion(self) -> None:
        """Elimina ejecuciones terminales por TTL o por exceso de antigüedad LRU."""

        ahora = datetime.now(UTC)
        limite_fecha = ahora - timedelta(days=self.retencion_dias)
        candidatos: list[tuple[Path, datetime]] = []
        for datos in self._leer_manifests():
            id_ejecucion = str(datos.get("id_ejecucion") or "")
            if not self.es_terminal(str(datos.get("estado") or "")):
                continue
            try:
                directorio = self.directorio_seguro(id_ejecucion)
            except KeyError:
                continue
            fecha = self._fecha_manifest(datos)
            if fecha is not None:
                candidatos.append((directorio, fecha))
        candidatos.sort(key=lambda item: item[1], reverse=True)
        eliminar: set[Path] = {
            directorio for directorio, fecha in candidatos if fecha < limite_fecha
        }
        eliminar.update(directorio for directorio, _fecha in candidatos[self.max_historial :])
        for directorio in eliminar:
            try:
                shutil.rmtree(directorio)
            except OSError:
                # La retención es mantenimiento best-effort; no debe tumbar la API.
                continue

    def _migrar_warning_macos_legacy(self) -> None:
        """Limpia una vez los warnings obsoletos sin hacer fallar el arranque."""

        try:
            if not self.base_dir.is_dir() or self.base_dir.is_symlink():
                return
            ejecuciones = list(self.base_dir.iterdir())
        except OSError:
            return

        for candidato in ejecuciones:
            if (
                not candidato.is_dir()
                or candidato.is_symlink()
                or not candidato.name.startswith("NOR_")
            ):
                continue
            try:
                raiz = self.base_dir.resolve()
                directorio = candidato.resolve()
                if directorio.parent != raiz:
                    continue
                self._migrar_json_legacy(directorio / "manifest.json", es_manifest=True)
                reportes = directorio / "salidas" / "reportes"
                if not reportes.is_dir() or reportes.is_symlink():
                    continue
                for reporte in reportes.iterdir():
                    if (
                        reporte.is_file()
                        and not reporte.is_symlink()
                        and reporte.suffix in {".json", ".jsonl"}
                    ):
                        self._migrar_json_legacy(reporte)
            except OSError:
                # Una ejecución legacy aislada no debe impedir leer las demás.
                continue

    def _migrar_json_legacy(self, ruta: Path, *, es_manifest: bool = False) -> int:
        """Reescribe un JSON/JSONL solo cuando contiene el warning obsoleto."""

        if not ruta.is_file() or ruta.is_symlink():
            return 0
        try:
            contenido = ruta.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return 0

        if ruta.suffix == ".jsonl":
            lineas: list[str] = []
            eliminados = 0
            for linea in contenido.splitlines(keepends=True):
                if not linea.strip():
                    lineas.append(linea)
                    continue
                try:
                    valor = json.loads(linea)
                except (json.JSONDecodeError, TypeError):
                    # No se toca un reporte parcialmente escrito o corrupto.
                    return 0
                valor_limpio, cantidad = _limpiar_warning_macos(valor)
                eliminados += cantidad
                if cantidad and _es_warning_macos_obsoleto(valor):
                    continue
                if cantidad:
                    lineas.append(
                        json.dumps(valor_limpio, ensure_ascii=False, separators=(",", ":"))
                        + ("\n" if linea.endswith(("\n", "\r")) else "")
                    )
                else:
                    lineas.append(linea)
            if eliminados:
                self._escribir_migracion_atomica(ruta, "".join(lineas))
            return eliminados

        try:
            valor = json.loads(contenido)
        except (json.JSONDecodeError, TypeError):
            return 0
        valor_limpio, eliminados = _limpiar_warning_macos(valor)
        if not eliminados:
            return 0
        if es_manifest and isinstance(valor_limpio, dict):
            self._actualizar_estado_migrado(valor_limpio)
        self._escribir_migracion_atomica(
            ruta,
            json.dumps(valor_limpio, ensure_ascii=False, indent=2) + "\n",
        )
        return eliminados

    def _leer_manifests(self) -> list[dict[str, object]]:
        resultados: list[dict[str, object]] = []
        if not self.base_dir.exists():
            return resultados
        for manifest in self.base_dir.glob("NOR_*/manifest.json"):
            id_ejecucion = manifest.parent.name
            if re.fullmatch(_ID_EJECUCION, id_ejecucion) is None:
                continue
            try:
                datos = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(datos, dict):
                continue
            try:
                datos = self._obtener_activa(id_ejecucion).a_dict()
            except KeyError:
                pass
            resultados.append(_filtrar_estado_publico(cast(dict[str, object], datos)))
        return resultados

    @staticmethod
    def _resumen_historial(datos: dict[str, object]) -> dict[str, object]:
        hallazgos = datos.get("hallazgos")
        filas = hallazgos if isinstance(hallazgos, list) else []
        advertencias = sum(
            1
            for hallazgo in filas
            if isinstance(hallazgo, dict) and hallazgo.get("severidad") == "warning"
        )
        errores = sum(
            1
            for hallazgo in filas
            if isinstance(hallazgo, dict) and hallazgo.get("severidad") == "error"
        )
        outputs = datos.get("outputs")
        return {
            "id_ejecucion": datos.get("id_ejecucion"),
            "tipo": datos.get("tipo"),
            "archivo": datos.get("archivo"),
            "parametros": datos.get("parametros") or {},
            "estado": datos.get("estado"),
            "creada_en": datos.get("creada_en"),
            "actualizada_en": datos.get("actualizada_en"),
            "cancelacion_solicitada": bool(datos.get("cancelacion_solicitada")),
            "resumen": {
                "advertencias": advertencias,
                "errores": errores,
                "outputs": len(outputs) if isinstance(outputs, list) else 0,
            },
        }

    @staticmethod
    def _leer_reporte(ruta: Path) -> object:
        limite_bytes = 5 * 1024 * 1024
        try:
            tamano = ruta.stat().st_size
            if tamano > limite_bytes:
                return {"truncado": True, "bytes": tamano}
            contenido = ruta.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return {"no_disponible": True, "mensaje": "No se pudo leer este reporte."}
        if ruta.suffix.lower() == ".jsonl":
            filas: list[object] = []
            for linea in contenido.splitlines():
                if not linea.strip():
                    continue
                try:
                    filas.append(json.loads(linea))
                except (json.JSONDecodeError, TypeError):
                    return {
                        "no_disponible": True,
                        "mensaje": "El reporte contiene una línea malformada.",
                    }
            return filas
        try:
            return json.loads(contenido)
        except (json.JSONDecodeError, TypeError):
            return {"no_disponible": True, "mensaje": "El reporte está malformado."}

    @staticmethod
    def _fecha_manifest(datos: dict[str, object]) -> datetime | None:
        valor = str(datos.get("actualizada_en") or datos.get("creada_en") or "")
        if not valor:
            return None
        try:
            fecha = datetime.fromisoformat(valor)
        except ValueError:
            return None
        return fecha if fecha.tzinfo is not None else fecha.replace(tzinfo=UTC)

    @staticmethod
    def _escribir_migracion_atomica(ruta: Path, contenido: str) -> None:
        temporal = ruta.with_name(f".{ruta.name}.migracion.tmp")
        try:
            temporal.write_text(contenido, encoding="utf-8")
            temporal.replace(ruta)
        finally:
            try:
                temporal.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _actualizar_estado_migrado(manifest: dict[str, object]) -> None:
        estado = str(manifest.get("estado") or "")
        if estado not in _ESTADOS_SIN_ADVERTENCIAS:
            return

        def tiene_warning(valor: object) -> bool:
            if isinstance(valor, list):
                return any(tiene_warning(item) for item in valor)
            if isinstance(valor, dict):
                if valor.get("severidad") == "warning":
                    return True
                return any(tiene_warning(item) for item in valor.values())
            return False

        if not tiene_warning(manifest):
            manifest["estado"] = _ESTADOS_SIN_ADVERTENCIAS[estado]
