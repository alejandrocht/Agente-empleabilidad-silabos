"""Ejecuciones en segundo plano para la puerta de entrada del normalizador."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Lock
from typing import cast
from uuid import uuid4

from agente.config.settings import BASE_DIR, booleano, entero, texto
from agente.normalizador.empleabilidad.catalogo import (
    cargar_catalogo,
    cargar_catalogo_carrera,
)
from agente.normalizador.empleabilidad.entrada import validar_archivo
from agente.normalizador.empleabilidad.limpieza import limpiar_archivo
from agente.normalizador.empleabilidad.pipeline import normalizar_staging
from agente.normalizador.excepciones import CancelacionSolicitada
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
from agente.normalizador.silabos.entrada import validar_archivo as validar_silabos
from agente.normalizador.silabos.fuente_cactus import (
    CactusExtractor,
    CactusExtractorError,
    empaquetar_archivos_cactus,
)
from agente.normalizador.silabos.limpieza import limpiar_archivo as limpiar_silabos
from agente.observabilidad.langsmith import contexto_ejecucion, ejecutar_flujo


def _ahora() -> str:
    """Genera timestamps UTC comparables entre procesos y ejecuciones."""

    return datetime.now(UTC).isoformat()


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
_ESTADOS_CANCELABLES: frozenset[str] = frozenset(
    {"recibido", "extrayendo", "validando", "limpiando", "normalizando"}
)
_ID_EJECUCION = r"NOR_[0-9a-f]{16}"
_WARNING_MACOS_OBSOLETO = "METADATO_MACOS_IGNORADO"
_ESTADOS_SIN_ADVERTENCIAS = {
    "validado_con_advertencias": "validado",
    "limpiado_con_advertencias": "limpiado",
    "normalizado_con_advertencias": "normalizado",
}


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


class EjecucionNoCancelable(RuntimeError):
    """Indica que una ejecución no puede cambiar de estado a cancelado."""


class HistorialNoEliminable(RuntimeError):
    """Indica que una ejecución activa no puede eliminarse del historial."""


class Ejecucion:
    """Estado mutable mínimo de una ejecución de normalización."""

    def __init__(
        self,
        id_ejecucion: str,
        tipo: str,
        archivo: str,
        directorio: Path,
        parametros: dict[str, str] | None = None,
    ) -> None:
        self.id_ejecucion = id_ejecucion
        self.tipo = tipo
        self.archivo = archivo
        self.directorio = directorio
        self.parametros = parametros or {}
        self.estado: EstadoEjecucion = "recibido"
        self.creada_en = _ahora()
        self.actualizada_en = self.creada_en
        self.validacion: ResultadoValidacionEntrada | None = None
        self.validacion_silabos: ResultadoValidacionSilabos | None = None
        self.limpieza: ResultadoLimpieza | None = None
        self.limpieza_silabos: ResultadoLimpiezaSilabos | None = None
        self.normalizacion: ResultadoNormalizacion | None = None
        self.catalogo_chh: dict[str, object] | None = None
        self.hallazgos: list[Hallazgo] = []
        self.progreso_llm: ProgresoLimpiezaLLM | None = None
        self.fuente: dict[str, object] | None = None
        self.progreso_fuente: dict[str, object] | None = None
        self.outputs_fuente: list[dict[str, object]] = []
        self.cancelada = Event()
        self.cancelacion_solicitada = False
        self.cancelada_en: str | None = None

    def a_dict(self) -> dict[str, object]:
        """Expone el contrato público sin filtrar rutas internas del servidor."""

        release_gate = dict(self.limpieza_silabos.release_gate) if self.limpieza_silabos else None
        if self.tipo == "silabos":
            reporte_gate = self.directorio / "salidas" / "reportes" / "release_gate.json"
            try:
                contenido_gate = json.loads(reporte_gate.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                contenido_gate = None
            if isinstance(contenido_gate, dict):
                release_gate = contenido_gate

        outputs_procesamiento = (
            list(self.normalizacion.outputs)
            if self.normalizacion
            else list(self.limpieza.outputs)
            if self.limpieza
            else list(self.limpieza_silabos.outputs)
            if self.limpieza_silabos
            else []
        )
        outputs = [*self.outputs_fuente, *outputs_procesamiento]
        outputs = _actualizar_metadatos_outputs(self.directorio, outputs)
        aprobacion_curricular: dict[str, object] | None = None
        if self.tipo == "silabos":
            try:
                from agente.normalizador.silabos.aprobaciones import (
                    resumen_aprobacion_curricular,
                )

                aprobacion_curricular = resumen_aprobacion_curricular(self.directorio)
            except (OSError, ValueError, TypeError):
                aprobacion_curricular = None

        return {
            "id_ejecucion": self.id_ejecucion,
            "tipo": self.tipo,
            "archivo": self.archivo,
            "parametros": dict(self.parametros),
            "estado": self.estado,
            "creada_en": self.creada_en,
            "actualizada_en": self.actualizada_en,
            "cancelacion_solicitada": self.cancelacion_solicitada,
            "cancelada_en": self.cancelada_en,
            "validacion": self.validacion.a_dict() if self.validacion else None,
            "validacion_silabos": (
                self.validacion_silabos.a_dict() if self.validacion_silabos else None
            ),
            "limpieza": self.limpieza.a_dict() if self.limpieza else None,
            "limpieza_silabos": (self.limpieza_silabos.a_dict() if self.limpieza_silabos else None),
            "normalizacion": self.normalizacion.a_dict() if self.normalizacion else None,
            "release_gate": release_gate,
            "aprobacion_curricular": aprobacion_curricular,
            "catalogo_chh": self.catalogo_chh,
            "fuente": self.fuente,
            "progreso_fuente": self.progreso_fuente,
            "progreso_llm": self.progreso_llm.a_dict() if self.progreso_llm else None,
            "hallazgos": [hallazgo.a_dict() for hallazgo in self.hallazgos],
            "outputs": outputs,
        }


class GestorEjecuciones:
    """Coordina validaciones cortas y persiste un manifest por ejecución."""

    def __init__(self, base_dir: Path | None = None) -> None:
        configurado = texto("NORMALIZADOR_DATA_DIR")
        self.base_dir = base_dir or Path(configurado or BASE_DIR / ".normalizador")
        self._ejecuciones: dict[str, Ejecucion] = {}
        self._bloqueo = Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="normalizador")
        self.max_historial = max(1, entero("NORMALIZADOR_HISTORIAL_MAX_EJECUCIONES", 20))
        self.retencion_dias = max(1, entero("NORMALIZADOR_HISTORIAL_RETENCION_DIAS", 15))
        self._migrar_warning_macos_legacy()

    def crear(
        self,
        tipo: str,
        archivo: str,
        parametros: dict[str, str] | None = None,
    ) -> tuple[str, Path]:
        """Crea el directorio aislado de una ejecución antes de guardar la fuente."""

        id_ejecucion = f"NOR_{uuid4().hex[:16]}"
        directorio = self.base_dir / id_ejecucion
        (directorio / "entrada").mkdir(parents=True, exist_ok=False)
        ejecucion = Ejecucion(id_ejecucion, tipo, archivo, directorio, parametros)
        with self._bloqueo:
            self._ejecuciones[id_ejecucion] = ejecucion
        self._persistir(ejecucion)
        return id_ejecucion, directorio

    def iniciar_validacion(self, id_ejecucion: str, ruta_entrada: Path) -> None:
        """Programa la validación sin bloquear la petición HTTP."""

        ejecucion = self._obtener_objeto(id_ejecucion)
        ejecucion.estado = "validando"
        ejecucion.actualizada_en = _ahora()
        self._persistir(ejecucion)
        self._executor.submit(self._validar, ejecucion, ruta_entrada)

    def iniciar_validacion_silabos(
        self,
        id_ejecucion: str,
        ruta_entrada: Path,
        carrera: str,
        periodo: str,
    ) -> None:
        """Programa la validación y limpieza curricular en segundo plano."""

        ejecucion = self._obtener_objeto(id_ejecucion)
        ejecucion.estado = "validando"
        ejecucion.actualizada_en = _ahora()
        self._persistir(ejecucion)
        self._executor.submit(self._validar_silabos, ejecucion, ruta_entrada, carrera, periodo)

    def iniciar_extraccion_silabos(
        self,
        id_ejecucion: str,
        carrera: str,
        periodo: str,
        usuario: str,
        contrasena: str,
    ) -> None:
        """Programa Cactus y el pipeline curricular en una sola ejecución."""

        ejecucion = self._obtener_objeto(id_ejecucion)
        ejecucion.estado = "extrayendo"
        ejecucion.fuente = {
            "tipo": "cactus",
            "estado": "extrayendo",
            "carrera": carrera,
            "periodo": periodo,
        }
        ejecucion.progreso_fuente = {
            "fase": "preparando",
            "mensaje": "Preparando la extracción desde Cactus.",
            "cursos_encontrados": 0,
            "cursos_procesados": 0,
            "archivos_descargados": 0,
            "errores": 0,
        }
        ejecucion.actualizada_en = _ahora()
        self._persistir(ejecucion)
        self._executor.submit(
            self._extraer_y_validar_silabos,
            ejecucion,
            carrera,
            periodo,
            usuario,
            contrasena,
        )

    def marcar_rechazo(self, id_ejecucion: str, hallazgo: Hallazgo) -> None:
        """Marca un rechazo inmediato, por ejemplo por límite de carga."""

        ejecucion = self._obtener_objeto(id_ejecucion)
        ejecucion.estado = "rechazado"
        ejecucion.hallazgos = [hallazgo]
        self._finalizar(ejecucion)

    def cancelar(self, id_ejecucion: str) -> dict[str, object]:
        """Solicita una cancelación cooperativa y la persiste inmediatamente."""

        ejecucion = self._obtener_objeto(id_ejecucion)
        if ejecucion.estado == "cancelado":
            return ejecucion.a_dict()
        if ejecucion.estado not in _ESTADOS_CANCELABLES:
            raise EjecucionNoCancelable(
                f"La ejecución está en estado {ejecucion.estado} y ya no admite cancelación."
            )
        ejecucion.cancelada.set()
        ejecucion.cancelacion_solicitada = True
        ejecucion.cancelada_en = ejecucion.cancelada_en or _ahora()
        ejecucion.actualizada_en = _ahora()
        self._persistir(ejecucion)
        respuesta = ejecucion.a_dict()
        respuesta["mensaje"] = (
            "Cancelación solicitada. El lote que ya está en curso puede terminar; "
            "no se enviará otro lote al LLM."
        )
        return respuesta

    def listar_historial(self, limite: int = 20) -> dict[str, object]:
        """Lista ejecuciones recientes y aplica la política TTL/LRU."""

        self._aplicar_retencion()
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

    def obtener_reporte(self, id_ejecucion: str) -> dict[str, object]:
        """Construye un reporte JSON consolidado desde los artefactos auditables."""

        estado = self.obtener(id_ejecucion)
        reportes: dict[str, object] = {}
        directorio_reportes = self._directorio_seguro(id_ejecucion) / "salidas" / "reportes"
        if directorio_reportes.is_dir():
            for ruta in sorted(directorio_reportes.iterdir()):
                if not ruta.is_file() or ruta.suffix.lower() not in {".json", ".jsonl"}:
                    continue
                reportes[ruta.name] = self._leer_reporte(ruta)
        return {
            "id_ejecucion": id_ejecucion,
            "manifest": estado,
            "reportes": reportes,
        }

    def eliminar_historial(self, id_ejecucion: str) -> dict[str, object]:
        """Elimina una ejecución terminal, nunca una ejecución activa."""

        try:
            ejecucion = self._obtener_objeto(id_ejecucion)
        except KeyError:
            ejecucion = None
        if ejecucion is not None and ejecucion.estado not in _ESTADOS_TERMINALES:
            raise HistorialNoEliminable(
                "No se puede eliminar una ejecución mientras sigue en curso."
            )
        directorio = self._directorio_seguro(id_ejecucion)
        if not directorio.is_dir():
            raise KeyError(id_ejecucion)
        shutil.rmtree(directorio)
        with self._bloqueo:
            self._ejecuciones.pop(id_ejecucion, None)
        return {"id_ejecucion": id_ejecucion, "eliminado": True}

    def obtener(self, id_ejecucion: str) -> dict[str, object]:
        """Obtiene el estado serializable de una ejecución activa."""

        try:
            return self._obtener_objeto(id_ejecucion).a_dict()
        except KeyError:
            try:
                manifest = self._directorio_seguro(id_ejecucion) / "manifest.json"
            except KeyError:
                raise KeyError(id_ejecucion) from None
            if not manifest.exists():
                raise
            datos = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(datos, dict):
                raise ValueError("El manifest de la ejecución no tiene un objeto raíz.")
            return cast(dict[str, object], datos)

    def _obtener_objeto(self, id_ejecucion: str) -> Ejecucion:
        with self._bloqueo:
            ejecucion = self._ejecuciones.get(id_ejecucion)
        if ejecucion is None:
            raise KeyError(id_ejecucion)
        return ejecucion

    def _directorio_seguro(self, id_ejecucion: str) -> Path:
        if re.fullmatch(_ID_EJECUCION, id_ejecucion) is None:
            raise KeyError(id_ejecucion)
        raiz = self.base_dir.resolve()
        directorio = (raiz / id_ejecucion).resolve()
        if directorio.parent != raiz:
            raise KeyError(id_ejecucion)
        return directorio

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
                        and reporte.suffix
                        in {
                            ".json",
                            ".jsonl",
                        }
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
                datos = self._obtener_objeto(id_ejecucion).a_dict()
            except KeyError:
                pass
            resultados.append(cast(dict[str, object], datos))
        return resultados

    def _resumen_historial(self, datos: dict[str, object]) -> dict[str, object]:
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

    def _leer_reporte(self, ruta: Path) -> object:
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

    def _aplicar_retencion(self) -> None:
        """Elimina ejecuciones terminales por TTL o por exceso de antigüedad LRU."""

        ahora = datetime.now(UTC)
        limite_fecha = ahora - timedelta(days=self.retencion_dias)
        candidatos: list[tuple[Path, dict[str, object], datetime]] = []
        for datos in self._leer_manifests():
            id_ejecucion = str(datos.get("id_ejecucion") or "")
            if str(datos.get("estado") or "") not in _ESTADOS_TERMINALES:
                continue
            try:
                directorio = self._directorio_seguro(id_ejecucion)
            except KeyError:
                continue
            fecha = self._fecha_manifest(datos)
            if fecha is not None:
                candidatos.append((directorio, datos, fecha))
        candidatos.sort(key=lambda item: item[2], reverse=True)
        eliminar: set[Path] = {
            directorio for directorio, _datos, fecha in candidatos if fecha < limite_fecha
        }
        eliminar.update(
            directorio for directorio, _datos, _fecha in candidatos[self.max_historial :]
        )
        for directorio in eliminar:
            try:
                shutil.rmtree(directorio)
            except OSError:
                # La retención es mantenimiento best-effort; no debe tumbar la API.
                continue

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

    def _verificar_cancelacion(self, ejecucion: Ejecucion) -> None:
        if ejecucion.cancelada.is_set():
            raise CancelacionSolicitada()

    def _cancelar_si_solicitada(self, ejecucion: Ejecucion) -> bool:
        if not ejecucion.cancelada.is_set():
            return False
        self._marcar_cancelado(ejecucion)
        return True

    def _marcar_cancelado(self, ejecucion: Ejecucion) -> None:
        ejecucion.cancelacion_solicitada = True
        ejecucion.cancelada_en = ejecucion.cancelada_en or _ahora()
        ejecucion.estado = "cancelado"
        if not any(
            hallazgo.codigo == "PROCESAMIENTO_CANCELADO" for hallazgo in ejecucion.hallazgos
        ):
            ejecucion.hallazgos.append(
                Hallazgo(
                    codigo="PROCESAMIENTO_CANCELADO",
                    severidad="warning",
                    mensaje="El procesamiento fue cancelado por el usuario.",
                    detalle="No se enviarán nuevos lotes al LLM; el lote en curso pudo terminar.",
                )
            )
        if ejecucion.progreso_llm is not None:
            ejecucion.progreso_llm = replace(
                ejecucion.progreso_llm,
                fase="cancelado",
                reporte_final="cancelado",
            ).con_evento("Procesamiento cancelado; se conservaron los artefactos de auditoría.")
        self._asegurar_reportes_cancelacion(ejecucion)
        ejecucion.actualizada_en = _ahora()

    @staticmethod
    def _asegurar_reportes_cancelacion(ejecucion: Ejecucion) -> None:
        """Crea artefactos mínimos aunque la cancelación ocurra durante extracción."""

        reportes = ejecucion.directorio / "salidas" / "reportes"
        try:
            reportes.mkdir(parents=True, exist_ok=True)
            decisiones = reportes / "decisiones_llm.jsonl"
            if not decisiones.exists():
                decisiones.write_text(
                    json.dumps(
                        {
                            "tipo": "sistema",
                            "estado": "CANCELADO",
                            "detalle": (
                                "La ejecución se canceló antes de completar el análisis LLM."
                            ),
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            analisis = reportes / "analisis_llm.json"
            if not analisis.exists():
                analisis.write_text(
                    json.dumps(
                        {
                            "estado": "CANCELADO",
                            "decisiones_aceptadas": 0,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            cuarentena = reportes / "cuarentena.jsonl"
            if not cuarentena.exists():
                cuarentena.write_text("", encoding="utf-8")
        except OSError:
            # El estado cancelado debe persistir aunque el disco no permita el detalle.
            return

    def _finalizar(self, ejecucion: Ejecucion) -> None:
        """Cierra el manifest, purga temporales y aplica la retención."""

        if ejecucion.estado in _ESTADOS_TERMINALES:
            self._purgar_temporales(ejecucion)
        ejecucion.actualizada_en = _ahora()
        self._persistir(ejecucion)
        self._aplicar_retencion()

    def _purgar_temporales(self, ejecucion: Ejecucion) -> None:
        """Elimina fuentes binarias/staging, manteniendo CSV y reportes auditables."""

        raiz = ejecucion.directorio.resolve()
        for relativo in (
            "entrada",
            "fuentes_curriculares",
            "limpios",
            "cactus_chrome_profile",
        ):
            ruta = (raiz / relativo).resolve()
            if raiz not in ruta.parents or not ruta.is_dir():
                continue
            try:
                shutil.rmtree(ruta)
            except OSError:
                # La ejecución ya terminó; una falla de limpieza no invalida los CSV.
                continue

    def _validar(self, ejecucion: Ejecucion, ruta_entrada: Path) -> None:
        """Ejecuta el gate y genera staging solo cuando la fuente es estructuralmente válida."""

        try:
            self._verificar_cancelacion(ejecucion)
            resultado = validar_archivo(ruta_entrada, ejecucion.archivo)
        except CancelacionSolicitada:
            self._marcar_cancelado(ejecucion)
            self._finalizar(ejecucion)
            return
        except Exception as exc:
            ejecucion.estado = "error"
            ejecucion.hallazgos = [
                Hallazgo(
                    codigo="ERROR_INTERNO_VALIDACION",
                    severidad="error",
                    mensaje="La validación terminó con un error interno.",
                    detalle=f"{type(exc).__name__}: {str(exc)[:200]}",
                )
            ]
            ejecucion.actualizada_en = _ahora()
            self._finalizar(ejecucion)
            return

        ejecucion.validacion = resultado
        ejecucion.hallazgos = list(resultado.hallazgos)
        if self._cancelar_si_solicitada(ejecucion):
            self._finalizar(ejecucion)
            return
        if not resultado.valida:
            ejecucion.estado = "rechazado"
            self._finalizar(ejecucion)
            return

        try:
            ejecucion.catalogo_chh = cargar_catalogo().resumen()
        except Exception as exc:
            ejecucion.catalogo_chh = {
                "disponible": False,
                "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            }

        try:
            self._verificar_cancelacion(ejecucion)
            ejecucion.estado = "limpiando"
            ejecucion.actualizada_en = _ahora()
            self._persistir(ejecucion)
            limpieza = limpiar_archivo(ruta_entrada, ejecucion.directorio, resultado)
            self._verificar_cancelacion(ejecucion)
            ejecucion.limpieza = limpieza
            ejecucion.hallazgos = list(resultado.hallazgos) + list(limpieza.hallazgos)
            ejecucion.estado = (
                "limpiado_con_advertencias"
                if any(hallazgo.severidad == "warning" for hallazgo in ejecucion.hallazgos)
                else "limpiado"
            )
            ejecucion.actualizada_en = _ahora()
            self._persistir(ejecucion)

            ejecucion.estado = "normalizando"
            ejecucion.actualizada_en = _ahora()
            self._persistir(ejecucion)
            self._verificar_cancelacion(ejecucion)
            normalizacion = normalizar_staging(ejecucion.directorio, resultado)
            ejecucion.normalizacion = normalizacion
            ejecucion.hallazgos = ejecucion.hallazgos + list(normalizacion.hallazgos)
            hay_advertencias = any(
                hallazgo.severidad == "warning" for hallazgo in ejecucion.hallazgos
            )
            if not normalizacion.publicable:
                ejecucion.estado = "no_publicado"
            elif hay_advertencias:
                ejecucion.estado = "normalizado_con_advertencias"
            else:
                ejecucion.estado = "normalizado"
        except CancelacionSolicitada:
            self._marcar_cancelado(ejecucion)
        except Exception as exc:
            if ejecucion.cancelada.is_set():
                self._marcar_cancelado(ejecucion)
                return
            ejecucion.estado = "error"
            ejecucion.hallazgos.append(
                Hallazgo(
                    codigo="ERROR_INTERNO_LIMPIEZA",
                    severidad="error",
                    mensaje="La limpieza o normalización terminó con un error interno.",
                    detalle=f"{type(exc).__name__}: {str(exc)[:200]}",
                )
            )
        finally:
            self._finalizar(ejecucion)

    def _validar_silabos(
        self,
        ejecucion: Ejecucion,
        ruta_entrada: Path,
        carrera: str,
        periodo: str,
    ) -> None:
        """Valida y limpia un paquete curricular sin ejecutar aún la extracción CHH."""

        try:
            self._verificar_cancelacion(ejecucion)
            resultado = validar_silabos(ruta_entrada, carrera, periodo, ejecucion.archivo)
        except CancelacionSolicitada:
            self._marcar_cancelado(ejecucion)
            self._finalizar(ejecucion)
            return
        except Exception as exc:
            ejecucion.estado = "error"
            ejecucion.hallazgos = [
                Hallazgo(
                    codigo="ERROR_INTERNO_VALIDACION_SILABOS",
                    severidad="error",
                    mensaje="La validación curricular terminó con un error interno.",
                    detalle=f"{type(exc).__name__}: {str(exc)[:200]}",
                )
            ]
            ejecucion.actualizada_en = _ahora()
            self._finalizar(ejecucion)
            return

        ejecucion.validacion_silabos = resultado
        ejecucion.hallazgos = list(resultado.hallazgos)
        if self._cancelar_si_solicitada(ejecucion):
            self._finalizar(ejecucion)
            return
        if not resultado.valida:
            ejecucion.estado = "rechazado"
            self._finalizar(ejecucion)
            return

        try:
            catalogo_global = cargar_catalogo()
            catalogo_carrera = cargar_catalogo_carrera(
                resultado.carrera,
                resultado.periodo,
            )
            ejecucion.catalogo_chh = (catalogo_carrera or catalogo_global).resumen()
            ejecucion.catalogo_chh["alcance_curricular"] = (
                "carrera" if catalogo_carrera is not None else "perfil_del_silabo"
            )
            ejecucion.catalogo_chh["carrera"] = resultado.carrera
            ejecucion.catalogo_chh["periodo"] = resultado.periodo
        except Exception as exc:
            ejecucion.catalogo_chh = {
                "disponible": False,
                "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            }
        try:
            self._verificar_cancelacion(ejecucion)
            ejecucion.estado = "limpiando"
            ejecucion.actualizada_en = _ahora()
            usar_llm = booleano("NORMALIZADOR_CURRICULAR_LLM", True)
            if usar_llm:
                ejecucion.progreso_llm = ProgresoLimpiezaLLM(
                    fase="preparando",
                    chunks_completados=0,
                    chunks_totales=0,
                    logros_procesados=0,
                    logros_totales=0,
                    silabos_procesados=0,
                    silabos_totales=len(resultado.archivos),
                    decisiones_cacheadas=0,
                    reintentos=0,
                    silabos_detectados=0,
                    mensaje="Preparando la extracción de sílabos antes de iniciar el análisis LLM.",
                ).con_evento(
                    "Preparando la extracción de sílabos antes de iniciar el análisis LLM."
                )
            self._persistir(ejecucion)

            def actualizar_progreso_llm(progreso: ProgresoLimpiezaLLM) -> None:
                ejecucion.progreso_llm = progreso
                ejecucion.actualizada_en = _ahora()
                self._persistir(ejecucion)

            tags_traza, metadata_traza = contexto_ejecucion(
                ejecucion.id_ejecucion,
                resultado.carrera,
                resultado.periodo,
            )
            limpieza = ejecutar_flujo(
                lambda: limpiar_silabos(
                    ruta_entrada,
                    ejecucion.directorio,
                    resultado,
                    usar_llm=usar_llm,
                    inspeccionar_llm=booleano("NORMALIZADOR_CURRICULAR_INSPECTOR", True),
                    al_actualizar_progreso_llm=actualizar_progreso_llm if usar_llm else None,
                    progreso_inicial=ejecucion.progreso_llm if usar_llm else None,
                    id_ejecucion=ejecucion.id_ejecucion,
                    cancelada=ejecucion.cancelada.is_set,
                ),
                run_name="normalizador.curricular",
                inputs={
                    "execution_id": ejecucion.id_ejecucion,
                    "career": resultado.carrera,
                    "period": resultado.periodo,
                    "files_count": len(resultado.archivos),
                },
                tags=tags_traza,
                metadata={**metadata_traza, "flow": "curricular"},
            )
            limpieza = self._aplicar_gate_de_extraccion(ejecucion, limpieza)
            self._verificar_cancelacion(ejecucion)
            ejecucion.limpieza_silabos = limpieza
            ejecucion.hallazgos = ejecucion.hallazgos + list(limpieza.hallazgos)
            if not limpieza.publicable or any(
                hallazgo.severidad == "error" for hallazgo in ejecucion.hallazgos
            ):
                ejecucion.estado = "no_publicado"
            elif any(hallazgo.severidad == "warning" for hallazgo in ejecucion.hallazgos):
                ejecucion.estado = "limpiado_con_advertencias"
            else:
                ejecucion.estado = "limpiado"
        except CancelacionSolicitada:
            self._marcar_cancelado(ejecucion)
        except Exception as exc:
            if ejecucion.cancelada.is_set():
                self._marcar_cancelado(ejecucion)
                return
            ejecucion.estado = "error"
            if ejecucion.progreso_llm is not None:
                ejecucion.progreso_llm = replace(
                    ejecucion.progreso_llm,
                    fase="error",
                    reporte_final="error",
                ).con_evento(
                    "La ejecución terminó con error; se conservan los avances registrados."
                )
            ejecucion.hallazgos.append(
                Hallazgo(
                    codigo="ERROR_INTERNO_LIMPIEZA_SILABOS",
                    severidad="error",
                    mensaje="La limpieza curricular terminó con un error interno.",
                    detalle=f"{type(exc).__name__}: {str(exc)[:200]}",
                )
            )
        finally:
            self._finalizar(ejecucion)

    def _extraer_y_validar_silabos(
        self,
        ejecucion: Ejecucion,
        carrera: str,
        periodo: str,
        usuario: str,
        contrasena: str,
    ) -> None:
        """Descarga desde Cactus y entrega un ZIP interno al flujo curricular actual."""

        try:
            self._verificar_cancelacion(ejecucion)
            directorio_descarga = ejecucion.directorio / "fuentes_curriculares" / "cactus"
            extractor = CactusExtractor(
                headless=booleano("NORMALIZADOR_CACTUS_HEADLESS", False),
                download_workers=entero("NORMALIZADOR_CACTUS_DOWNLOAD_WORKERS", 3),
            )

            def actualizar_progreso(progreso: dict[str, object]) -> None:
                ejecucion.progreso_fuente = dict(progreso)
                ejecucion.actualizada_en = _ahora()
                self._persistir(ejecucion)

            resultado = extractor.extraer(
                carrera=carrera,
                periodo=periodo,
                usuario=usuario,
                contrasena=contrasena,
                directorio_salida=directorio_descarga,
                directorio_perfil=ejecucion.directorio / "cactus_chrome_profile",
                al_actualizar_progreso=actualizar_progreso,
                cancelada=ejecucion.cancelada.is_set,
            )
            # La contraseña solo es necesaria para la sesión Cactus. Liberar
            # ambas referencias antes de entrar al pipeline de normalización.
            usuario = ""
            contrasena = ""
            reporte = resultado.a_dict(directorio_descarga)
            ejecucion.fuente = reporte
            reporte_path = ejecucion.directorio / "salidas" / "reportes" / "extraccion_cactus.json"
            reporte_path.parent.mkdir(parents=True, exist_ok=True)
            reporte_path.write_text(
                json.dumps(reporte, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            ejecucion.outputs_fuente = _actualizar_metadatos_outputs(
                ejecucion.directorio,
                [
                    {
                        "tipo": "fuente_cactus",
                        "archivo": "salidas/reportes/extraccion_cactus.json",
                        "registros": 1,
                    }
                ],
            )
            ejecucion.actualizada_en = _ahora()
            self._persistir(ejecucion)

            if not resultado.archivos_procesables:
                ejecucion.estado = "rechazado"
                ejecucion.hallazgos.append(
                    Hallazgo(
                        codigo="CACTUS_SIN_SILABOS_PROCESABLES",
                        severidad="error",
                        mensaje="Cactus no produjo sílabos PDF o DOCX procesables.",
                        detalle=(
                            f"cursos={resultado.cursos_encontrados}; "
                            f"descargados={resultado.archivos_descargados}"
                        ),
                    )
                )
                self._finalizar(ejecucion)
                return

            ruta_entrada = ejecucion.directorio / "entrada" / ejecucion.archivo
            empaquetar_archivos_cactus(directorio_descarga, ruta_entrada)
            ejecucion.estado = "validando"
            ejecucion.actualizada_en = _ahora()
            self._persistir(ejecucion)
            self._validar_silabos(ejecucion, ruta_entrada, carrera, periodo)
        except CancelacionSolicitada:
            self._marcar_cancelado(ejecucion)
            self._finalizar(ejecucion)
        except CactusExtractorError as exc:
            self._registrar_error_fuente(ejecucion, exc.codigo, exc.mensaje)
        except Exception as exc:
            self._registrar_error_fuente(
                ejecucion,
                "ERROR_INTERNO_EXTRACCION_CACTUS",
                f"{type(exc).__name__}: {str(exc)[:200]}",
            )
        finally:
            # Evita conservar referencias innecesarias a la contraseña en el worker.
            usuario = ""
            contrasena = ""

    def _registrar_error_fuente(
        self,
        ejecucion: Ejecucion,
        codigo: str,
        detalle: str,
    ) -> None:
        if ejecucion.fuente is None:
            ejecucion.fuente = {"tipo": "cactus"}
        ejecucion.fuente = {
            **ejecucion.fuente,
            "estado": "error",
            "codigo": codigo,
            "detalle": detalle,
        }
        reportes = ejecucion.directorio / "salidas" / "reportes"
        reportes.mkdir(parents=True, exist_ok=True)
        reporte = reportes / "extraccion_cactus.json"
        reporte.write_text(
            json.dumps(ejecucion.fuente, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        ejecucion.outputs_fuente = _actualizar_metadatos_outputs(
            ejecucion.directorio,
            [
                {
                    "tipo": "fuente_cactus",
                    "archivo": "salidas/reportes/extraccion_cactus.json",
                    "registros": 1,
                }
            ],
        )
        ejecucion.estado = "error"
        ejecucion.hallazgos.append(
            Hallazgo(
                codigo=codigo,
                severidad="error",
                mensaje="La extracción desde Cactus no pudo completarse.",
                detalle=detalle,
            )
        )
        self._finalizar(ejecucion)

    def _aplicar_gate_de_extraccion(
        self,
        ejecucion: Ejecucion,
        limpieza: ResultadoLimpiezaSilabos,
    ) -> ResultadoLimpiezaSilabos:
        """Bloquea la publicación cuando Cactus entregó una fuente incompleta."""

        fuente = ejecucion.fuente
        if not isinstance(fuente, dict) or fuente.get("completa") is not False:
            return limpieza

        gate = dict(limpieza.release_gate)
        blockers_value = gate.get("blockers")
        blockers_items: list[object] = blockers_value if isinstance(blockers_value, list) else []
        blockers = {str(item) for item in blockers_items if item}
        blockers.add("EXTRACTION_COVERAGE_INCOMPLETE")
        checks_value = gate.get("checks")
        checks = dict(checks_value) if isinstance(checks_value, dict) else {}
        checks["source_extraction"] = {
            "ok": False,
            "cursos_encontrados": fuente.get("cursos_encontrados", 0),
            "archivos_descargados": fuente.get("archivos_descargados", 0),
            "archivos_procesables": fuente.get("archivos_procesables", 0),
            "sin_silabo": fuente.get("sin_silabo", 0),
            "fetch_fallidos": fuente.get("fetch_fallidos", 0),
            "sesiones_fallidas": fuente.get("sesiones_fallidas", 0),
            "archivos_no_soportados": fuente.get("archivos_no_soportados", 0),
        }
        gate["checks"] = checks
        gate["blockers"] = sorted(blockers)
        gate["decision"] = "BLOCK_IMPORT"
        reporte = ejecucion.directorio / "salidas" / "reportes" / "release_gate.json"
        reporte.parent.mkdir(parents=True, exist_ok=True)
        reporte.write_text(
            json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        hallazgo = Hallazgo(
            codigo="EXTRACCION_CACTUS_INCOMPLETA",
            severidad="warning",
            mensaje="La extracción desde Cactus fue parcial; la publicación quedó bloqueada.",
            detalle=(
                f"{fuente.get('archivos_procesables', 0)}/"
                f"{fuente.get('cursos_encontrados', 0)} sílabos procesables."
            ),
        )
        return replace(
            limpieza,
            publicable=False,
            release_gate=gate,
            hallazgos=(*limpieza.hallazgos, hallazgo),
        )

    def _persistir(self, ejecucion: Ejecucion) -> None:
        """Escribe el manifest para conservar evidencia aunque el proceso reinicie."""

        manifest = ejecucion.directorio / "manifest.json"
        temporal = manifest.with_suffix(".json.tmp")
        temporal.write_text(
            json.dumps(ejecucion.a_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporal.replace(manifest)


gestor_ejecuciones = GestorEjecuciones()
