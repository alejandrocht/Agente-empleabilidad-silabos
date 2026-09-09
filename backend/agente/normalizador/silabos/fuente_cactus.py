"""Adapter de extracción curricular desde Cactus/ULima.

El repositorio original es un CLI orientado a una carpeta global y a un periodo
definido en ``.env``. Este módulo conserva su navegación robusta, pero expone una
interfaz por ejecución: carrera, periodo, credenciales y directorios se reciben
explícitamente y ningún secreto se persiste en el reporte.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from agente.normalizador.excepciones import CancelacionSolicitada
from agente.normalizador.silabos.cactus_archivos import (
    FORMATS_PROCESABLES,
    CactusExtractorError,
    _cargar_checkpoint,
    _clave_checkpoint,
    _es_html,
    _existe_checkpoint,
    _guardar_checkpoint,
    _leer_respuesta_limitada,
    _RespuestaDemasiadoGrande,
    _silabo_url,
    _url_adjunto,
    _url_adjunto_segura,
    empaquetar_archivos_cactus,
    is_login_page,
    normalize_text,
    ruta_curso,
    sanitize_filename,
    strip_accents,
)
from agente.normalizador.silabos.cactus_navegacion import (
    CactusAuthenticationError,
    NavegadorCactus,
    _SesionCaida,  # noqa: F401
)

__all__ = (
    "CactusAuthenticationError",
    "CactusExtractor",
    "CactusExtractorError",
    "FORMATS_PROCESABLES",
    "ResultadoExtraccionCactus",
    "empaquetar_archivos_cactus",
    "is_login_page",
    "normalize_text",
    "ruta_curso",
    "sanitize_filename",
    "strip_accents",
)

BASE_URL = "https://cactus.ulima.edu.pe/ac/ac_bd001.nsf"
VIEW_CURSOS = "VCursosXCiclAcdXEspc"
LOGIN_PROBE = f"{BASE_URL}/{VIEW_CURSOS}?OpenView"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)
DOWNLOAD_WORKERS = 3
MAX_REINTENTOS = 4
MAX_RONDAS_SESION = 8
BACKOFF_BASE = 0.8
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024

ProgressCallback = Callable[[dict[str, object]], None]
CancelCallback = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class ResultadoExtraccionCactus:
    """Resultado auditable de una extracción aislada."""

    carrera: str
    periodo: str
    cursos_encontrados: int
    archivos_descargados: int
    archivos_procesables: int
    sin_silabo: int
    fetch_fallidos: int
    sesiones_fallidas: int
    archivos_no_soportados: int
    archivos: tuple[Path, ...]
    errores: tuple[dict[str, str], ...]

    @property
    def completa(self) -> bool:
        """Indica si cada curso descubierto produjo un archivo procesable."""

        return (
            self.cursos_encontrados > 0
            and self.archivos_descargados == self.cursos_encontrados
            and self.archivos_procesables == self.cursos_encontrados
            and self.sin_silabo == 0
            and self.fetch_fallidos == 0
            and self.sesiones_fallidas == 0
            and self.archivos_no_soportados == 0
        )

    def a_dict(self, raiz: Path) -> dict[str, object]:
        """Serializa el resultado sin credenciales ni rutas absolutas."""

        archivos = []
        for ruta in self.archivos:
            try:
                archivos.append(ruta.resolve().relative_to(raiz.resolve()).as_posix())
            except ValueError:
                archivos.append(ruta.name)
        return {
            "tipo": "cactus",
            "fuente": "cactus",
            "carrera": self.carrera,
            "periodo": self.periodo,
            "estado": "completado" if self.completa else "parcial",
            "completa": self.completa,
            "cursos_encontrados": self.cursos_encontrados,
            "archivos_descargados": self.archivos_descargados,
            "archivos_procesables": self.archivos_procesables,
            "sin_silabo": self.sin_silabo,
            "fetch_fallidos": self.fetch_fallidos,
            "sesiones_fallidas": self.sesiones_fallidas,
            "archivos_no_soportados": self.archivos_no_soportados,
            "archivos": archivos,
            "errores": list(self.errores),
        }


class CactusExtractor:
    """Módulo profundo para navegar Cactus y descargar una carrera/periodo."""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        headless: bool = False,
        download_workers: int = DOWNLOAD_WORKERS,
        max_session_rounds: int = MAX_RONDAS_SESION,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.view_url = f"{self.base_url}/{VIEW_CURSOS}"
        self.login_probe = f"{self.view_url}?OpenView"
        self.headless = headless
        self.download_workers = max(1, min(int(download_workers), 3))
        self.max_session_rounds = max(1, int(max_session_rounds))

    def extraer(
        self,
        *,
        carrera: str,
        periodo: str,
        usuario: str,
        contrasena: str,
        directorio_salida: Path,
        directorio_perfil: Path,
        al_actualizar_progreso: ProgressCallback | None = None,
        cancelada: CancelCallback | None = None,
    ) -> ResultadoExtraccionCactus:
        """Descarga sílabos de una carrera y ciclo sin persistir credenciales."""

        carrera_limpia = str(carrera or "").strip()
        periodo_limpio = re.sub(r"\s+", "", str(periodo or ""))
        if not carrera_limpia:
            raise CactusExtractorError("CACTUS_CARRERA_REQUERIDA", "La carrera es obligatoria.")
        if re.fullmatch(r"\d{4}-\d+", periodo_limpio) is None:
            raise CactusExtractorError(
                "CACTUS_PERIODO_INVALIDO",
                "El periodo debe tener formato año-secuencia, por ejemplo 2026-1.",
            )

        directorio_salida.mkdir(parents=True, exist_ok=True)
        directorio_perfil.mkdir(parents=True, exist_ok=True)
        done = self._cargar_checkpoint(directorio_salida)
        self._progreso(
            al_actualizar_progreso,
            fase="autenticando",
            mensaje="Abriendo una sesión autenticada en Cactus.",
            cursos_encontrados=0,
            cursos_procesados=0,
            archivos_descargados=0,
        )

        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as exc:
            raise CactusExtractorError(
                "CACTUS_PLAYWRIGHT_NO_DISPONIBLE",
                "Playwright no está instalado en el backend.",
            ) from exc

        errores: list[dict[str, str]] = []
        cursos: list[dict[str, str]] = []
        with sync_playwright() as playwright:
            contexto = self._abrir_contexto(playwright, directorio_perfil)
            try:
                pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
                self._esperar_login(pagina, usuario, contrasena, cancelada)
                self._verificar_cancelacion(cancelada)
                self._progreso(
                    al_actualizar_progreso,
                    fase="navegando",
                    mensaje=f"Buscando {carrera_limpia} en el periodo {periodo_limpio}.",
                    cursos_encontrados=0,
                    cursos_procesados=0,
                    archivos_descargados=0,
                )
                cursos = self._procesar_carrera(
                    pagina,
                    carrera_limpia,
                    periodo_limpio,
                    usuario,
                    contrasena,
                    cancelada,
                ) or []
                if not cursos:
                    errores.append(
                        {
                            "codigo": "CACTUS_CARRERA_SIN_CURSOS",
                            "mensaje": (
                                f"No se encontraron cursos para {carrera_limpia} "
                                f"en {periodo_limpio}."
                            ),
                        }
                    )
                self._progreso(
                    al_actualizar_progreso,
                    fase="descargando",
                    mensaje=f"Se encontraron {len(cursos)} cursos; iniciando descargas.",
                    cursos_encontrados=len(cursos),
                    cursos_procesados=0,
                    archivos_descargados=0,
                )
                estadisticas = self._descargar_cursos(
                    contexto,
                    pagina,
                    cursos,
                    directorio_salida,
                    done,
                    usuario,
                    contrasena,
                    cancelada,
                    al_actualizar_progreso,
                )
                errores.extend(estadisticas.pop("errores"))
            finally:
                contexto.close()

        archivos = tuple(
            sorted(
                ruta
                for ruta in directorio_salida.rglob("*")
                if ruta.is_file() and ruta.suffix.lower() in FORMATS_PROCESABLES
            )
        )
        resultado = ResultadoExtraccionCactus(
            carrera=carrera_limpia,
            periodo=periodo_limpio,
            cursos_encontrados=len(cursos),
            archivos_descargados=int(estadisticas.get("archivos_descargados", 0)),
            archivos_procesables=len(archivos),
            sin_silabo=int(estadisticas.get("sin_silabo", 0)),
            fetch_fallidos=int(estadisticas.get("fetch_fallidos", 0)),
            sesiones_fallidas=int(estadisticas.get("sesiones_fallidas", 0)),
            archivos_no_soportados=int(estadisticas.get("archivos_no_soportados", 0)),
            archivos=archivos,
            errores=tuple(errores),
        )
        self._guardar_checkpoint(directorio_salida, done)
        self._progreso(
            al_actualizar_progreso,
            fase="completado" if resultado.completa else "parcial",
            mensaje=(
                f"Extracción finalizada: {resultado.archivos_procesables}/"
                f"{resultado.cursos_encontrados} sílabos procesables."
            ),
            cursos_encontrados=resultado.cursos_encontrados,
            cursos_procesados=resultado.archivos_descargados,
            archivos_descargados=resultado.archivos_descargados,
            errores=len(resultado.errores),
        )
        return resultado

    def _abrir_contexto(self, playwright: Any, directorio_perfil: Path) -> Any:
        try:
            return playwright.chromium.launch_persistent_context(
                str(directorio_perfil),
                headless=self.headless,
                channel="chrome",
                user_agent=USER_AGENT,
                accept_downloads=True,
            )
        except Exception as primer_error:
            try:
                return playwright.chromium.launch_persistent_context(
                    str(directorio_perfil),
                    headless=self.headless,
                    user_agent=USER_AGENT,
                    accept_downloads=True,
                )
            except Exception as segundo_error:
                raise CactusExtractorError(
                    "CACTUS_NAVEGADOR_NO_DISPONIBLE",
                    (
                        "No se pudo abrir Chromium/Chrome para Cactus: "
                        f"{type(segundo_error).__name__}: {str(segundo_error)[:200]}"
                    ),
                ) from primer_error

    def _esperar_login(
        self,
        pagina: Any,
        usuario: str,
        contrasena: str,
        cancelada: CancelCallback | None,
    ) -> None:
        NavegadorCactus(
            base_url=self.base_url,
            view_url=self.view_url,
            login_probe=self.login_probe,
            max_attachment_bytes=MAX_ATTACHMENT_BYTES,
        ).esperar_login(pagina, usuario, contrasena, cancelada, self._verificar_cancelacion)

    def _procesar_carrera(
        self,
        pagina: Any,
        carrera: str,
        periodo: str,
        usuario: str,
        contrasena: str,
        cancelada: CancelCallback | None,
    ) -> list[dict[str, str]] | None:
        return NavegadorCactus(
            base_url=self.base_url,
            view_url=self.view_url,
            login_probe=self.login_probe,
            max_attachment_bytes=MAX_ATTACHMENT_BYTES,
        ).procesar_carrera(
            pagina,
            carrera,
            periodo,
            usuario,
            contrasena,
            cancelada,
            verificar_cancelacion=self._verificar_cancelacion,
            esperar_login=self._esperar_login,
            esperar_vista=self._esperar_vista,
            comprobar_login=self._comprobar_login,
            clic_siguiente=self._clic_siguiente,
        )

    def _abrir_periodo(
        self,
        pagina: Any,
        periodo_norm: str,
        cancelada: CancelCallback | None,
    ) -> str | None:
        return NavegadorCactus(
            base_url=self.base_url,
            view_url=self.view_url,
            login_probe=self.login_probe,
            max_attachment_bytes=MAX_ATTACHMENT_BYTES,
        ).abrir_periodo(
            pagina,
            periodo_norm,
            cancelada,
            verificar_cancelacion=self._verificar_cancelacion,
            esperar_vista=self._esperar_vista,
            comprobar_login=self._comprobar_login,
            clic_siguiente=self._clic_siguiente,
        )

    def _buscar_carrera(
        self,
        pagina: Any,
        pos_periodo: str,
        carrera_norm: str,
        cancelada: CancelCallback | None,
    ) -> str | None:
        return NavegadorCactus(
            base_url=self.base_url,
            view_url=self.view_url,
            login_probe=self.login_probe,
            max_attachment_bytes=MAX_ATTACHMENT_BYTES,
        ).buscar_carrera(
            pagina,
            pos_periodo,
            carrera_norm,
            cancelada,
            verificar_cancelacion=self._verificar_cancelacion,
            esperar_vista=self._esperar_vista,
            comprobar_login=self._comprobar_login,
            clic_siguiente=self._clic_siguiente,
        )

    def _cursos_de_carrera(
        self,
        pagina: Any,
        pos_carrera: str,
        carrera: str,
        periodo: str,
        cancelada: CancelCallback | None,
    ) -> list[dict[str, str]]:
        return NavegadorCactus(
            base_url=self.base_url,
            view_url=self.view_url,
            login_probe=self.login_probe,
            max_attachment_bytes=MAX_ATTACHMENT_BYTES,
        ).cursos_de_carrera(
            pagina,
            pos_carrera,
            carrera,
            periodo,
            cancelada,
            verificar_cancelacion=self._verificar_cancelacion,
            esperar_vista=self._esperar_vista,
            comprobar_login=self._comprobar_login,
            clic_siguiente=self._clic_siguiente,
        )

    def _leer_ciclos(
        self,
        pagina: Any,
        pos_carrera: str,
        cancelada: CancelCallback | None,
    ) -> list[tuple[str, str]]:
        return NavegadorCactus(
            base_url=self.base_url,
            view_url=self.view_url,
            login_probe=self.login_probe,
            max_attachment_bytes=MAX_ATTACHMENT_BYTES,
        ).leer_ciclos(
            pagina,
            pos_carrera,
            cancelada,
            verificar_cancelacion=self._verificar_cancelacion,
            comprobar_login=self._comprobar_login,
            clic_siguiente=self._clic_siguiente,
        )

    def _descargar_cursos(
        self,
        contexto: Any,
        pagina: Any,
        cursos: list[dict[str, str]],
        directorio_salida: Path,
        done: set[str],
        usuario: str,
        contrasena: str,
        cancelada: CancelCallback | None,
        progreso: ProgressCallback | None,
    ) -> dict[str, Any]:
        tareas: list[dict[str, str]] = []
        for info in cursos:
            clave = self._clave_checkpoint(info)
            if clave in done or self._existe_checkpoint(directorio_salida, clave):
                done.add(clave)
            else:
                tareas.append(info)

        estado: dict[str, Any] = {
            "archivos_descargados": len(cursos) - len(tareas),
            "sin_silabo": 0,
            "fetch_fallidos": 0,
            "sesiones_fallidas": 0,
            "archivos_no_soportados": 0,
            "errores": [],
        }
        caidos: list[dict[str, str]] = []
        errores_doc: list[dict[str, str]] = []
        if tareas:
            # Playwright Sync API objects are thread-affine. Capture the plain
            # cookie values while still on the browser-owning thread, then
            # keep worker threads limited to independent HTTP sessions.
            cookies = self._capturar_cookies(contexto)
            for resultado in self._ronda_descarga(
                cookies,
                tareas,
                cancelada,
                self.download_workers,
            ):
                self._aplicar_resultado(
                    resultado,
                    directorio_salida,
                    done,
                    estado,
                    caidos,
                    errores_doc,
                    cancelada,
                    progreso,
                    len(cursos),
                )

        ronda = 0
        while caidos and ronda < self.max_session_rounds:
            self._verificar_cancelacion(cancelada)
            ronda += 1
            # Reabrir login con las credenciales recibidas. Nunca se guardan en el manifest.
            self._esperar_login(pagina, usuario, contrasena, cancelada)
            pendientes = caidos
            caidos = []
            cookies = self._capturar_cookies(contexto)
            for resultado in self._ronda_descarga(cookies, pendientes, cancelada, workers=1):
                self._aplicar_resultado(
                    resultado,
                    directorio_salida,
                    done,
                    estado,
                    caidos,
                    errores_doc,
                    cancelada,
                    progreso,
                    len(cursos),
                )
            if len(caidos) == len(pendientes):
                break

        for info in caidos:
            estado["sesiones_fallidas"] += 1
            estado["errores"].append(
                {
                    "codigo": "CACTUS_ERROR_SESION",
                    "curso": info["nombre_curso"],
                    "mensaje": "La sesión no permitió descargar el sílabo.",
                }
            )
        for info in errores_doc:
            self._verificar_cancelacion(cancelada)
            extension = self._descargar_por_navegador(pagina, info, directorio_salida)
            if extension:
                done.add(self._clave_checkpoint(info))
                estado["archivos_descargados"] += 1
                self._emitir_descarga(progreso, estado, len(cursos), info)
            else:
                estado["fetch_fallidos"] += 1
                estado["errores"].append(
                    {
                        "codigo": "CACTUS_ADJUNTO_NO_DESCARGABLE",
                        "curso": info["nombre_curso"],
                        "mensaje": (
                            "El curso figura en Cactus, pero el adjunto no pudo "
                            "descargarse."
                        ),
                    }
                )
        self._guardar_checkpoint(directorio_salida, done)
        return estado

    def _ronda_descarga(
        self,
        cookies: tuple[dict[str, Any], ...],
        cursos: list[dict[str, str]],
        cancelada: CancelCallback | None,
        workers: int,
    ) -> list[dict[str, Any]]:
        if workers == 1:
            return [self._descargar_con_sesion(cookies, info, cancelada) for info in cursos]
        resultados: list[dict[str, Any]] = []
        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="cactus-download",
        ) as executor:
            futuros = {
                executor.submit(self._descargar_con_sesion, cookies, info, cancelada): info
                for info in cursos
            }
            for futuro in as_completed(futuros):
                self._verificar_cancelacion(cancelada)
                try:
                    resultados.append(futuro.result())
                except CancelacionSolicitada:
                    raise
                except Exception as exc:
                    info = futuros[futuro]
                    resultados.append(
                        {
                            "info": info,
                            "status": "fetch_err",
                            "detalle": f"{type(exc).__name__}: {str(exc)[:200]}",
                        }
                    )
        return resultados

    def _descargar_con_sesion(
        self,
        cookies: tuple[dict[str, Any], ...],
        info: dict[str, str],
        cancelada: CancelCallback | None,
    ) -> dict[str, Any]:
        """Descarga con una sesión HTTP propia para evitar compartir estado entre hilos."""

        sesion = self._build_session(cookies)
        try:
            return self._descargar_uno(sesion, info, cancelada)
        finally:
            sesion.close()

    def _descargar_uno(
        self,
        sesion: requests.Session,
        info: dict[str, str],
        cancelada: CancelCallback | None,
    ) -> dict[str, Any]:
        unid = info["unid"]
        silabo: tuple[str, str] | None = None
        ultimo_detalle = "desconocido"
        for intento in range(MAX_REINTENTOS):
            self._verificar_cancelacion(cancelada)
            try:
                respuesta = sesion.get(
                    f"{self.base_url}/0/{unid}?OpenDocument",
                    timeout=30,
                    allow_redirects=False,
                    stream=True,
                )
                if respuesta.is_redirect or respuesta.is_permanent_redirect:
                    respuesta.close()
                    ultimo_detalle = "redirección de documento no permitida"
                    return {"info": info, "status": "fetch_err", "detalle": ultimo_detalle}
                encoding = respuesta.encoding or "utf-8"
                cuerpo = _leer_respuesta_limitada(respuesta, MAX_DOCUMENT_BYTES)
                html = cuerpo.decode(encoding, errors="replace")
            except Exception as exc:
                if isinstance(exc, _RespuestaDemasiadoGrande):
                    return {"info": info, "status": "fetch_err", "detalle": str(exc)}
                ultimo_detalle = f"excepción documento: {type(exc).__name__}"
                time.sleep(BACKOFF_BASE * (intento + 1))
                continue
            if is_login_page(html):
                ultimo_detalle = f"login en documento HTTP {respuesta.status_code}"
                time.sleep(BACKOFF_BASE * (intento + 1))
                continue
            if not html.strip():
                ultimo_detalle = f"documento vacío HTTP {respuesta.status_code}"
                time.sleep(BACKOFF_BASE * (intento + 1))
                continue
            silabo = _silabo_url(html)
            break
        if silabo is None:
            return {
                "info": info,
                "status": "sesion" if "login" in ultimo_detalle else "sin_silabo",
                "detalle": ultimo_detalle,
            }

        silabo_url, extension = silabo
        full_url = self._url_adjunto(silabo_url, unid)
        if not self._url_adjunto_segura(full_url):
            return {
                "info": info,
                "status": "fetch_err",
                "detalle": "origen o esquema del adjunto no permitido",
            }

        for intento in range(MAX_REINTENTOS):
            self._verificar_cancelacion(cancelada)
            try:
                respuesta_archivo = sesion.get(
                    full_url,
                    timeout=60,
                    allow_redirects=False,
                    stream=True,
                )
                if (
                    respuesta_archivo.is_redirect
                    or respuesta_archivo.is_permanent_redirect
                ):
                    respuesta_archivo.close()
                    return {
                        "info": info,
                        "status": "fetch_err",
                        "detalle": "redirección de adjunto no permitida",
                    }
                body = _leer_respuesta_limitada(respuesta_archivo, MAX_ATTACHMENT_BYTES)
            except Exception as exc:
                if isinstance(exc, _RespuestaDemasiadoGrande):
                    return {"info": info, "status": "fetch_err", "detalle": str(exc)}
                ultimo_detalle = f"excepción archivo: {type(exc).__name__}"
                time.sleep(BACKOFF_BASE * (intento + 1))
                continue
            if body and not self._es_html(body):
                return {"info": info, "status": "ok", "extension": extension, "body": body}
            texto = body.decode("latin-1", errors="replace")
            es_login = is_login_page(texto)
            ultimo_detalle = f"{'login' if es_login else 'HTML-no-login'} en archivo"
            if es_login:
                time.sleep(BACKOFF_BASE * (intento + 1))
                continue
            return {"info": info, "status": "doc_error", "detalle": ultimo_detalle}
        return {"info": info, "status": "sesion", "detalle": ultimo_detalle}

    def _descargar_por_navegador(
        self,
        pagina: Any,
        info: dict[str, str],
        directorio_salida: Path,
    ) -> str | None:
        return NavegadorCactus(
            base_url=self.base_url,
            view_url=self.view_url,
            login_probe=self.login_probe,
            max_attachment_bytes=MAX_ATTACHMENT_BYTES,
        ).descargar_por_navegador(
            pagina,
            info,
            directorio_salida,
            url_adjunto=self._url_adjunto,
            url_adjunto_segura=self._url_adjunto_segura,
        )

    def _aplicar_resultado(
        self,
        resultado: dict[str, Any],
        directorio_salida: Path,
        done: set[str],
        estado: dict[str, Any],
        caidos: list[dict[str, str]],
        errores_doc: list[dict[str, str]],
        cancelada: CancelCallback | None,
        progreso: ProgressCallback | None,
        total: int,
    ) -> None:
        self._verificar_cancelacion(cancelada)
        info = resultado["info"]
        status = resultado.get("status")
        if status == "ok":
            extension = str(resultado.get("extension") or "").lower()
            ruta = ruta_curso(directorio_salida, info, extension)
            ruta.write_bytes(resultado["body"])
            done.add(self._clave_checkpoint(info))
            estado["archivos_descargados"] += 1
            if extension not in {"pdf", "docx"}:
                estado["archivos_no_soportados"] += 1
                estado["errores"].append(
                    {
                        "codigo": "CACTUS_FORMATO_NO_SOPORTADO",
                        "curso": info["nombre_curso"],
                        "mensaje": f"El extractor descargó .{extension}, formato no procesable.",
                    }
                )
            self._emitir_descarga(progreso, estado, total, info)
        elif status == "sin_silabo":
            estado["sin_silabo"] += 1
            estado["errores"].append(
                {
                    "codigo": "CACTUS_SIN_SILABO",
                    "curso": info["nombre_curso"],
                    "mensaje": "El curso no tiene sílabo descargable en Cactus.",
                }
            )
        elif status == "sesion":
            caidos.append(info)
        elif status == "doc_error":
            errores_doc.append(info)
        else:
            estado["fetch_fallidos"] += 1
            estado["errores"].append(
                {
                    "codigo": "CACTUS_ERROR_DESCARGA",
                    "curso": info["nombre_curso"],
                    "mensaje": str(resultado.get("detalle") or "Falló la descarga del sílabo."),
                }
            )

    def _emitir_descarga(
        self,
        progreso: ProgressCallback | None,
        estado: dict[str, Any],
        total: int,
        info: dict[str, str],
    ) -> None:
        self._progreso(
            progreso,
            fase="descargando",
            mensaje=f"Descarga procesada: {info['nombre_curso']}.",
            cursos_encontrados=total,
            cursos_procesados=estado["archivos_descargados"],
            archivos_descargados=estado["archivos_descargados"],
            errores=(
                len(estado["errores"])
                + len(estado.get("caidos", []))
                + len(estado.get("doc_errors", []))
            ),
        )

    @staticmethod
    def _capturar_cookies(contexto: Any) -> tuple[dict[str, Any], ...]:
        """Read browser cookies before handing work to non-Playwright threads."""

        return tuple(dict(cookie) for cookie in contexto.cookies())

    def _build_session(self, cookies: tuple[dict[str, Any], ...]) -> requests.Session:
        sesion = requests.Session()
        for cookie in cookies:
            sesion.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
                secure=bool(cookie.get("secure")),
            )
        sesion.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": self.login_probe,
            }
        )
        return sesion

    def _url_adjunto_segura(self, valor: str) -> bool:
        return _url_adjunto_segura(self.base_url, valor)

    def _url_adjunto(self, valor: str, unid: str) -> str:
        return _url_adjunto(self.base_url, valor, unid)

    @staticmethod
    def _es_html(body: bytes) -> bool:
        return _es_html(body)

    @staticmethod
    def _clave_checkpoint(info: dict[str, str]) -> str:
        return _clave_checkpoint(info)

    @staticmethod
    def _existe_checkpoint(raiz: Path, clave: str) -> bool:
        return _existe_checkpoint(raiz, clave)

    @staticmethod
    def _cargar_checkpoint(raiz: Path) -> set[str]:
        return _cargar_checkpoint(raiz)

    @staticmethod
    def _guardar_checkpoint(raiz: Path, done: set[str]) -> None:
        _guardar_checkpoint(raiz, done)

    @staticmethod
    def _progreso(callback: ProgressCallback | None, **datos: object) -> None:
        if callback is not None:
            callback(dict(datos))

    @staticmethod
    def _verificar_cancelacion(cancelada: CancelCallback | None) -> None:
        if cancelada is not None and cancelada():
            raise CancelacionSolicitada()

    _comprobar_login = staticmethod(NavegadorCactus.comprobar_login)
    _esperar_vista = staticmethod(NavegadorCactus.esperar_vista)
    _etiqueta = staticmethod(NavegadorCactus.etiqueta)
    _iter_posiciones = staticmethod(NavegadorCactus.iter_posiciones)
    _cursos_visibles = staticmethod(NavegadorCactus.cursos_visibles)
    _posicion_mayor = staticmethod(NavegadorCactus.posicion_mayor)

    @staticmethod
    def _clic_siguiente(pagina: Any) -> bool:
        return NavegadorCactus.clic_siguiente(pagina, CactusExtractor._esperar_vista)
