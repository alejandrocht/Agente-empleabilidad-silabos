"""Adapter de extracción curricular desde Cactus/ULima.

El repositorio original es un CLI orientado a una carpeta global y a un periodo
definido en ``.env``. Este módulo conserva su navegación robusta, pero expone una
interfaz por ejecución: carrera, periodo, credenciales y directorios se reciben
explícitamente y ningún secreto se persiste en el reporte.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from agente.normalizador.excepciones import CancelacionSolicitada

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
FORMATS_PROCESABLES = {".pdf", ".docx"}

ProgressCallback = Callable[[dict[str, object]], None]
CancelCallback = Callable[[], bool]


class CactusExtractorError(RuntimeError):
    """Error accionable de la fuente externa Cactus."""

    def __init__(self, codigo: str, mensaje: str) -> None:
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


class CactusAuthenticationError(CactusExtractorError):
    """La sesión de Cactus no pudo autenticarse."""

    def __init__(self, mensaje: str) -> None:
        super().__init__("CACTUS_AUTENTICACION_FALLIDA", mensaje)


class _SesionCaida(RuntimeError):
    """La sesión Domino volvió al formulario de login."""


class _RespuestaDemasiadoGrande(RuntimeError):
    """La fuente externa superó el límite de memoria de una respuesta."""


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


def strip_accents(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def normalize_text(value: object) -> str:
    """Normaliza texto para comparar nodos de la vista Domino."""

    return re.sub(r"\s+", " ", strip_accents(str(value or ""))).upper().strip()


def sanitize_filename(value: object, max_len: int = 120) -> str:
    """Convierte una etiqueta externa en una ruta de archivo segura."""

    text = strip_accents(str(value or "SIN_NOMBRE")).upper().strip()
    text = re.sub(r"[^\w\s\-]", "", text)
    text = re.sub(r"\s+", "_", text).strip("_")
    if not text:
        return "SIN_NOMBRE"
    return text[:max_len] if len(text) > max_len else text


def is_login_page(text: str) -> bool:
    return (
        "_CustomLoginform" in text
        or "names.nsf?Login" in text
        or "Acceso a los sistemas de informaci" in text
    )


def _silabo_url(html: str) -> tuple[str, str] | None:
    match = re.search(
        r'href="([^"]*\$FILE/[^" ]*\.(pdf|docx?)[^" ]*)"',
        html,
        re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1), match.group(2).lower()


def _leer_respuesta_limitada(respuesta: requests.Response, limite: int) -> bytes:
    """Lee una respuesta por chunks y evita materializar cuerpos ilimitados."""

    try:
        content_length = respuesta.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > limite:
                    raise _RespuestaDemasiadoGrande(
                        f"respuesta superior al límite de {limite} bytes"
                    )
            except ValueError:
                pass

        partes: list[bytes] = []
        total = 0
        for parte in respuesta.iter_content(chunk_size=64 * 1024):
            if not parte:
                continue
            total += len(parte)
            if total > limite:
                raise _RespuestaDemasiadoGrande(
                    f"respuesta superior al límite de {limite} bytes"
                )
            partes.append(parte)
        return b"".join(partes)
    finally:
        respuesta.close()


def empaquetar_archivos_cactus(raiz: Path, destino: Path) -> tuple[str, ...]:
    """Crea el ZIP interno que consume el validador curricular existente."""

    import zipfile

    raiz_resuelta = raiz.resolve()
    archivos = sorted(
        ruta
        for ruta in raiz.rglob("*")
        if ruta.is_file() and ruta.suffix.lower() in FORMATS_PROCESABLES
    )
    nombres: list[str] = []
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as paquete:
        for ruta in archivos:
            try:
                nombre = ruta.resolve().relative_to(raiz_resuelta).as_posix()
            except ValueError as exc:
                raise CactusExtractorError(
                    "CACTUS_RUTA_INVALIDA",
                    "La extracción produjo un archivo fuera de su directorio aislado.",
                ) from exc
            if not nombre or ".." in Path(nombre).parts:
                raise CactusExtractorError(
                    "CACTUS_RUTA_INVALIDA",
                    "La extracción produjo una ruta curricular no segura.",
                )
            paquete.write(ruta, nombre)
            nombres.append(nombre)
    return tuple(nombres)


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
        self._verificar_cancelacion(cancelada)
        try:
            if not is_login_page(pagina.content()):
                pagina.goto(self.login_probe, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            raise CactusAuthenticationError(
                f"No se pudo abrir la pantalla de autenticación de Cactus: {type(exc).__name__}."
            ) from exc

        if not is_login_page(pagina.content()):
            return
        if not usuario.strip() or not contrasena:
            raise CactusAuthenticationError(
                "Cactus solicitó autenticación y no se recibieron credenciales completas."
            )
        try:
            pagina.locator("input[name='Username']").fill(usuario.strip())
            pagina.locator("input[name='Password']").fill(contrasena)
            boton = pagina.locator("a:has(img[alt='aceptar'])")
            if boton.count() > 0:
                boton.first.click()
            else:
                pagina.locator("a[href*='javascript:Aceptar']").click()
            pagina.wait_for_load_state("networkidle", timeout=15000)
        except Exception as exc:
            raise CactusAuthenticationError(
                f"No se pudo completar el login de Cactus: {type(exc).__name__}."
            ) from exc
        if is_login_page(pagina.content()):
            raise CactusAuthenticationError(
                "Cactus rechazó las credenciales o la sesión no terminó correctamente."
            )

    def _procesar_carrera(
        self,
        pagina: Any,
        carrera: str,
        periodo: str,
        usuario: str,
        contrasena: str,
        cancelada: CancelCallback | None,
    ) -> list[dict[str, str]] | None:
        periodo_norm = normalize_text(periodo)
        for _intento in range(3):
            self._verificar_cancelacion(cancelada)
            try:
                pos_periodo = self._abrir_periodo(pagina, periodo_norm, cancelada)
                if not pos_periodo:
                    return None
                pos_carrera = self._buscar_carrera(
                    pagina,
                    pos_periodo,
                    normalize_text(carrera),
                    cancelada,
                )
                if not pos_carrera:
                    return None
                return self._cursos_de_carrera(pagina, pos_carrera, carrera, periodo, cancelada)
            except _SesionCaida:
                if _intento == 2:
                    raise CactusAuthenticationError(
                        "La sesión de Cactus cayó tres veces mientras se buscaba la carrera."
                    )
                self._esperar_login(pagina, usuario, contrasena, cancelada)
        return None

    def _abrir_periodo(
        self,
        pagina: Any,
        periodo_norm: str,
        cancelada: CancelCallback | None,
    ) -> str | None:
        pagina.goto(f"{self.view_url}?OpenView&CollapseView", wait_until="domcontentloaded")
        self._esperar_vista(pagina)
        self._comprobar_login(pagina)
        while True:
            self._verificar_cancelacion(cancelada)
            for link in pagina.locator("a[href*='Expand=']").all():
                href = link.get_attribute("href") or ""
                match = re.search(r"Expand=(\d+)(?:[#&]|$)", href)
                if match and periodo_norm in self._etiqueta(link):
                    posicion = match.group(1)
                    link.click()
                    self._esperar_vista(pagina)
                    self._comprobar_login(pagina)
                    return posicion
            if not self._clic_siguiente(pagina):
                return None
            self._comprobar_login(pagina)

    def _buscar_carrera(
        self,
        pagina: Any,
        pos_periodo: str,
        carrera_norm: str,
        cancelada: CancelCallback | None,
    ) -> str | None:
        patron = re.compile(rf"{re.escape(pos_periodo)}\.\d+$")
        prefijo = f"{pos_periodo}."
        while True:
            self._verificar_cancelacion(cancelada)
            for posicion, link in self._iter_posiciones(pagina):
                if patron.match(posicion) and self._etiqueta(link) == carrera_norm:
                    link.click()
                    self._esperar_vista(pagina)
                    self._comprobar_login(pagina)
                    return posicion
            if not self._clic_siguiente(pagina):
                return None
            self._comprobar_login(pagina)
            if not any(
                posicion.startswith(prefijo)
                for posicion, _ in self._iter_posiciones(pagina)
            ):
                return None

    def _cursos_de_carrera(
        self,
        pagina: Any,
        pos_carrera: str,
        carrera: str,
        periodo: str,
        cancelada: CancelCallback | None,
    ) -> list[dict[str, str]]:
        ciclos = self._leer_ciclos(pagina, pos_carrera, cancelada)
        cursos: list[dict[str, str]] = []
        for nivel, href in ciclos:
            self._verificar_cancelacion(cancelada)
            match = re.search(r"Expand=([\d.]+)", href)
            pos_ciclo = match.group(1) if match else None
            full_url = urljoin(f"{self.base_url}/", href)
            pagina.goto(full_url, wait_until="domcontentloaded")
            self._esperar_vista(pagina)
            self._comprobar_login(pagina)
            while True:
                self._verificar_cancelacion(cancelada)
                for unid, nombre in self._cursos_visibles(pagina):
                    if not any(item["unid"] == unid and item["nivel"] == nivel for item in cursos):
                        cursos.append(
                            {
                                "unid": unid,
                                "carrera": carrera,
                                "periodo": periodo,
                                "nivel": nivel,
                                "nombre_curso": nombre,
                            }
                        )
                if not pos_ciclo:
                    break
                if any(
                    self._posicion_mayor(posicion, pos_ciclo)
                    for posicion, _ in self._iter_posiciones(pagina)
                ):
                    break
                if not self._clic_siguiente(pagina):
                    break
                self._comprobar_login(pagina)
        return cursos

    def _leer_ciclos(
        self,
        pagina: Any,
        pos_carrera: str,
        cancelada: CancelCallback | None,
    ) -> list[tuple[str, str]]:
        patron = re.compile(rf"{re.escape(pos_carrera)}\.\d+$")
        prefijo = f"{pos_carrera}."
        ciclos: dict[str, tuple[str, str]] = {}
        while True:
            self._verificar_cancelacion(cancelada)
            hay_subarbol = False
            for posicion, link in self._iter_posiciones(pagina):
                if posicion.startswith(prefijo):
                    hay_subarbol = True
                if patron.match(posicion) and posicion not in ciclos:
                    match = re.search(r"(?<!\d)(\d{2})(?!\d)", self._etiqueta(link))
                    nivel = match.group(1) if match else posicion.split(".")[-1].zfill(2)
                    ciclos[posicion] = (nivel, link.get_attribute("href") or "")
            if not hay_subarbol or not self._clic_siguiente(pagina):
                break
            self._comprobar_login(pagina)
        return sorted(ciclos.values(), key=lambda item: item[0])

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
        url_doc = f"{self.base_url}/0/{info['unid']}?OpenDocument"
        try:
            pagina.goto(url_doc, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            return None
        if is_login_page(pagina.content()):
            return None
        enlaces = pagina.locator("a[href*='$FILE']")
        objetivo: Any = None
        extension_objetivo: str | None = None
        for indice in range(enlaces.count()):
            enlace = enlaces.nth(indice)
            href = enlace.get_attribute("href") or ""
            match = re.search(r"\.(pdf|docx?)(?:[?#]|$)", href, re.IGNORECASE)
            if not match:
                continue
            if not self._url_adjunto_segura(self._url_adjunto(href, info["unid"])):
                continue
            extension = match.group(1).lower()
            if extension != "pdf" or objetivo is None:
                objetivo = enlace
                extension_objetivo = extension
            if extension != "pdf":
                break
        if objetivo is None or extension_objetivo is None:
            return None
        directorio = directorio_salida / f"Ciclo_{sanitize_filename(info['nivel'])}"
        directorio.mkdir(parents=True, exist_ok=True)
        ruta = directorio / f"{info['nombre_curso']}.{extension_objetivo}"
        try:
            with pagina.expect_download(timeout=12000) as descarga_info:
                objetivo.click()
            descarga_info.value.save_as(str(ruta))
            if ruta.stat().st_size > MAX_ATTACHMENT_BYTES:
                ruta.unlink(missing_ok=True)
                return None
        except Exception:
            ruta.unlink(missing_ok=True)
            return None
        return extension_objetivo

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
            directorio = directorio_salida / f"Ciclo_{sanitize_filename(info['nivel'])}"
            directorio.mkdir(parents=True, exist_ok=True)
            ruta = directorio / f"{info['nombre_curso']}.{extension}"
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
        """Restrict attachments to the authenticated Cactus HTTPS origin."""

        base = urlparse(self.base_url)
        adjunto = urlparse(valor)
        return (
            base.scheme == "https"
            and adjunto.scheme == base.scheme
            and adjunto.hostname == base.hostname
            and adjunto.port == base.port
            and adjunto.username is None
            and adjunto.password is None
        )

    def _url_adjunto(self, valor: str, unid: str) -> str:
        if valor.startswith("/"):
            return urljoin(self.base_url, valor)
        if valor.startswith("http"):
            return valor
        if "$FILE/" in valor:
            return f"{self.base_url}/0/{unid}/$FILE/{valor.split('$FILE/')[-1]}"
        return f"{self.base_url}/{valor}"

    @staticmethod
    def _es_html(body: bytes) -> bool:
        return body[:20].lower().lstrip().startswith((b"<!doctype", b"<html"))

    @staticmethod
    def _clave_checkpoint(info: dict[str, str]) -> str:
        return f"Ciclo_{sanitize_filename(info['nivel'])}/{info['nombre_curso']}"

    @staticmethod
    def _existe_checkpoint(raiz: Path, clave: str) -> bool:
        ruta = raiz / clave
        return any(ruta.with_suffix(extension).is_file() for extension in (".pdf", ".docx"))

    @staticmethod
    def _cargar_checkpoint(raiz: Path) -> set[str]:
        ruta = raiz / ".checkpoint.json"
        if not ruta.is_file():
            return set()
        try:
            valor = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return set()
        if not isinstance(valor, list):
            return set()
        return {
            str(item)
            for item in valor
            if isinstance(item, str) and CactusExtractor._existe_checkpoint(raiz, item)
        }

    @staticmethod
    def _guardar_checkpoint(raiz: Path, done: set[str]) -> None:
        (raiz / ".checkpoint.json").write_text(
            json.dumps(sorted(done), ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _progreso(callback: ProgressCallback | None, **datos: object) -> None:
        if callback is not None:
            callback(dict(datos))

    @staticmethod
    def _verificar_cancelacion(cancelada: CancelCallback | None) -> None:
        if cancelada is not None and cancelada():
            raise CancelacionSolicitada()

    @staticmethod
    def _comprobar_login(pagina: Any) -> None:
        if is_login_page(pagina.content()):
            raise _SesionCaida()

    @staticmethod
    def _esperar_vista(pagina: Any) -> None:
        try:
            pagina.wait_for_load_state("domcontentloaded")
            pagina.wait_for_selector(
                "a[href*='Expand='], a[href*='OpenDocument']",
                timeout=8000,
            )
        except Exception:
            pass

    @staticmethod
    def _clic_siguiente(pagina: Any) -> bool:
        siguiente = pagina.get_by_role("link", name=re.compile(r"Next", re.IGNORECASE))
        if siguiente.count() == 0:
            return False
        siguiente.first.click()
        CactusExtractor._esperar_vista(pagina)
        return True

    @staticmethod
    def _etiqueta(link: Any) -> str:
        texto_link = normalize_text(link.inner_text())
        if texto_link:
            return texto_link
        fila = link.locator("xpath=ancestor::tr[1]")
        texto = normalize_text(fila.inner_text()) if fila.count() else ""
        return texto

    @staticmethod
    def _iter_posiciones(pagina: Any) -> list[tuple[str, Any]]:
        resultado: list[tuple[str, Any]] = []
        for link in pagina.locator("a[href*='Expand=']").all():
            href = link.get_attribute("href") or ""
            match = re.search(r"Expand=(\d+(?:\.\d+)*)(?:[#&]|$)", href)
            if match:
                resultado.append((match.group(1), link))
        return resultado

    @staticmethod
    def _cursos_visibles(pagina: Any) -> list[tuple[str, str]]:
        resultado: list[tuple[str, str]] = []
        for link in pagina.locator("a[href*='?OpenDocument']").all():
            href = link.get_attribute("href") or ""
            match = re.search(r"/([A-Fa-f0-9]{32})\?OpenDocument", href)
            if not match:
                continue
            unid = match.group(1)
            texto = link.inner_text().strip()
            resultado.append((unid, sanitize_filename(texto) if texto else unid[:8]))
        return resultado

    @staticmethod
    def _posicion_mayor(left: str, right: str) -> bool:
        try:
            return tuple(int(part) for part in left.split(".")) > tuple(
                int(part) for part in right.split(".")
            )
        except ValueError:
            return False
