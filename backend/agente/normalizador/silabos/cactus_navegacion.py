"""Navegación Playwright para la fuente curricular Cactus."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from agente.normalizador.silabos.cactus_archivos import (
    CactusExtractorError,
    is_login_page,
    normalize_text,
    ruta_curso,
    sanitize_filename,
)

CancelCallback = Callable[[], bool]
VerificarCancelacion = Callable[[CancelCallback | None], None]
EsperarLogin = Callable[[Any, str, str, CancelCallback | None], None]
EsperarVista = Callable[[Any], None]
ComprobarLogin = Callable[[Any], None]
ClicSiguiente = Callable[[Any], bool]
UrlAdjunto = Callable[[str, str], str]
UrlAdjuntoSegura = Callable[[str], bool]


class CactusAuthenticationError(CactusExtractorError):
    """La sesión de Cactus no pudo autenticarse."""

    def __init__(self, mensaje: str) -> None:
        super().__init__("CACTUS_AUTENTICACION_FALLIDA", mensaje)


class _SesionCaida(RuntimeError):
    """La sesión Domino volvió al formulario de login."""


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)


class NavegadorCactus:
    """Encapsula autenticación, DOM y fallback de descarga de Playwright."""

    def __init__(
        self,
        *,
        base_url: str,
        view_url: str,
        login_probe: str,
        max_attachment_bytes: int,
    ) -> None:
        self.base_url = base_url
        self.view_url = view_url
        self.login_probe = login_probe
        self.max_attachment_bytes = max_attachment_bytes

    def esperar_login(
        self,
        pagina: Any,
        usuario: str,
        contrasena: str,
        cancelada: CancelCallback | None,
        verificar_cancelacion: VerificarCancelacion,
    ) -> None:
        verificar_cancelacion(cancelada)
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

    def procesar_carrera(
        self,
        pagina: Any,
        carrera: str,
        periodo: str,
        usuario: str,
        contrasena: str,
        cancelada: CancelCallback | None,
        *,
        verificar_cancelacion: VerificarCancelacion,
        esperar_login: EsperarLogin,
        esperar_vista: EsperarVista,
        comprobar_login: ComprobarLogin,
        clic_siguiente: ClicSiguiente,
    ) -> list[dict[str, str]] | None:
        periodo_norm = normalize_text(periodo)
        for intento in range(3):
            verificar_cancelacion(cancelada)
            try:
                pos_periodo = self.abrir_periodo(
                    pagina,
                    periodo_norm,
                    cancelada,
                    verificar_cancelacion=verificar_cancelacion,
                    esperar_vista=esperar_vista,
                    comprobar_login=comprobar_login,
                    clic_siguiente=clic_siguiente,
                )
                if not pos_periodo:
                    return None
                pos_carrera = self.buscar_carrera(
                    pagina,
                    pos_periodo,
                    normalize_text(carrera),
                    cancelada,
                    verificar_cancelacion=verificar_cancelacion,
                    esperar_vista=esperar_vista,
                    comprobar_login=comprobar_login,
                    clic_siguiente=clic_siguiente,
                )
                if not pos_carrera:
                    return None
                return self.cursos_de_carrera(
                    pagina,
                    pos_carrera,
                    carrera,
                    periodo,
                    cancelada,
                    verificar_cancelacion=verificar_cancelacion,
                    esperar_vista=esperar_vista,
                    comprobar_login=comprobar_login,
                    clic_siguiente=clic_siguiente,
                )
            except _SesionCaida:
                if intento == 2:
                    raise CactusAuthenticationError(
                        "La sesión de Cactus cayó tres veces mientras se buscaba la carrera."
                    )
                esperar_login(pagina, usuario, contrasena, cancelada)
        return None

    def abrir_periodo(
        self,
        pagina: Any,
        periodo_norm: str,
        cancelada: CancelCallback | None,
        *,
        verificar_cancelacion: VerificarCancelacion,
        esperar_vista: EsperarVista,
        comprobar_login: ComprobarLogin,
        clic_siguiente: ClicSiguiente,
    ) -> str | None:
        pagina.goto(f"{self.view_url}?OpenView&CollapseView", wait_until="domcontentloaded")
        esperar_vista(pagina)
        comprobar_login(pagina)
        while True:
            verificar_cancelacion(cancelada)
            for link in pagina.locator("a[href*='Expand=']").all():
                href = link.get_attribute("href") or ""
                match = re.search(r"Expand=(\d+)(?:[#&]|$)", href)
                if match and periodo_norm in self.etiqueta(link):
                    posicion = match.group(1)
                    link.click()
                    esperar_vista(pagina)
                    comprobar_login(pagina)
                    return posicion
            if not clic_siguiente(pagina):
                return None
            comprobar_login(pagina)

    def buscar_carrera(
        self,
        pagina: Any,
        pos_periodo: str,
        carrera_norm: str,
        cancelada: CancelCallback | None,
        *,
        verificar_cancelacion: VerificarCancelacion,
        esperar_vista: EsperarVista,
        comprobar_login: ComprobarLogin,
        clic_siguiente: ClicSiguiente,
    ) -> str | None:
        patron = re.compile(rf"{re.escape(pos_periodo)}\.\d+$")
        prefijo = f"{pos_periodo}."
        while True:
            verificar_cancelacion(cancelada)
            for posicion, link in self.iter_posiciones(pagina):
                if patron.match(posicion) and self.etiqueta(link) == carrera_norm:
                    link.click()
                    esperar_vista(pagina)
                    comprobar_login(pagina)
                    return posicion
            if not clic_siguiente(pagina):
                return None
            comprobar_login(pagina)
            if not any(
                posicion.startswith(prefijo) for posicion, _ in self.iter_posiciones(pagina)
            ):
                return None

    def cursos_de_carrera(
        self,
        pagina: Any,
        pos_carrera: str,
        carrera: str,
        periodo: str,
        cancelada: CancelCallback | None,
        *,
        verificar_cancelacion: VerificarCancelacion,
        esperar_vista: EsperarVista,
        comprobar_login: ComprobarLogin,
        clic_siguiente: ClicSiguiente,
    ) -> list[dict[str, str]]:
        ciclos = self.leer_ciclos(
            pagina,
            pos_carrera,
            cancelada,
            verificar_cancelacion=verificar_cancelacion,
            comprobar_login=comprobar_login,
            clic_siguiente=clic_siguiente,
        )
        cursos: list[dict[str, str]] = []
        for nivel, href in ciclos:
            verificar_cancelacion(cancelada)
            match = re.search(r"Expand=([\d.]+)", href)
            pos_ciclo = match.group(1) if match else None
            full_url = urljoin(f"{self.base_url}/", href)
            pagina.goto(full_url, wait_until="domcontentloaded")
            esperar_vista(pagina)
            comprobar_login(pagina)
            while True:
                verificar_cancelacion(cancelada)
                for unid, nombre in self.cursos_visibles(pagina):
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
                    self.posicion_mayor(posicion, pos_ciclo)
                    for posicion, _ in self.iter_posiciones(pagina)
                ):
                    break
                if not clic_siguiente(pagina):
                    break
                comprobar_login(pagina)
        return cursos

    def leer_ciclos(
        self,
        pagina: Any,
        pos_carrera: str,
        cancelada: CancelCallback | None,
        *,
        verificar_cancelacion: VerificarCancelacion,
        comprobar_login: ComprobarLogin,
        clic_siguiente: ClicSiguiente,
    ) -> list[tuple[str, str]]:
        patron = re.compile(rf"{re.escape(pos_carrera)}\.\d+$")
        prefijo = f"{pos_carrera}."
        ciclos: dict[str, tuple[str, str]] = {}
        while True:
            verificar_cancelacion(cancelada)
            hay_subarbol = False
            for posicion, link in self.iter_posiciones(pagina):
                if posicion.startswith(prefijo):
                    hay_subarbol = True
                if patron.match(posicion) and posicion not in ciclos:
                    match = re.search(r"(?<!\d)(\d{2})(?!\d)", self.etiqueta(link))
                    nivel = match.group(1) if match else posicion.split(".")[-1].zfill(2)
                    ciclos[posicion] = (nivel, link.get_attribute("href") or "")
            if not hay_subarbol or not clic_siguiente(pagina):
                break
            comprobar_login(pagina)
        return sorted(ciclos.values(), key=lambda item: item[0])

    def descargar_por_navegador(
        self,
        pagina: Any,
        info: dict[str, str],
        directorio_salida: Path,
        *,
        url_adjunto: UrlAdjunto,
        url_adjunto_segura: UrlAdjuntoSegura,
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
            if not url_adjunto_segura(url_adjunto(href, info["unid"])):
                continue
            extension = match.group(1).lower()
            if extension != "pdf" or objetivo is None:
                objetivo = enlace
                extension_objetivo = extension
            if extension != "pdf":
                break
        if objetivo is None or extension_objetivo is None:
            return None
        ruta = ruta_curso(directorio_salida, info, extension_objetivo)
        try:
            with pagina.expect_download(timeout=12000) as descarga_info:
                objetivo.click()
            descarga_info.value.save_as(str(ruta))
            if ruta.stat().st_size > self.max_attachment_bytes:
                ruta.unlink(missing_ok=True)
                return None
        except Exception:
            ruta.unlink(missing_ok=True)
            return None
        return extension_objetivo

    @staticmethod
    def comprobar_login(pagina: Any) -> None:
        if is_login_page(pagina.content()):
            raise _SesionCaida()

    @staticmethod
    def esperar_vista(pagina: Any) -> None:
        try:
            pagina.wait_for_load_state("domcontentloaded")
            pagina.wait_for_selector(
                "a[href*='Expand='], a[href*='OpenDocument']",
                timeout=8000,
            )
        except Exception:
            pass

    @staticmethod
    def etiqueta(link: Any) -> str:
        texto_link = normalize_text(link.inner_text())
        if texto_link:
            return texto_link
        fila = link.locator("xpath=ancestor::tr[1]")
        return normalize_text(fila.inner_text()) if fila.count() else ""

    @staticmethod
    def iter_posiciones(pagina: Any) -> list[tuple[str, Any]]:
        resultado: list[tuple[str, Any]] = []
        for link in pagina.locator("a[href*='Expand=']").all():
            href = link.get_attribute("href") or ""
            match = re.search(r"Expand=(\d+(?:\.\d+)*)(?:[#&]|$)", href)
            if match:
                resultado.append((match.group(1), link))
        return resultado

    @staticmethod
    def cursos_visibles(pagina: Any) -> list[tuple[str, str]]:
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
    def posicion_mayor(left: str, right: str) -> bool:
        try:
            return tuple(int(part) for part in left.split(".")) > tuple(
                int(part) for part in right.split(".")
            )
        except ValueError:
            return False

    @staticmethod
    def clic_siguiente(pagina: Any, esperar_vista: EsperarVista) -> bool:
        siguiente = pagina.get_by_role("link", name=re.compile(r"Next", re.IGNORECASE))
        if siguiente.count() == 0:
            return False
        siguiente.first.click()
        esperar_vista(pagina)
        return True

    def _abrir_contexto(self: Any, playwright: Any, directorio_perfil: Path) -> Any:
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
        self: Any,
        pagina: Any,
        usuario: str,
        contrasena: str,
        cancelada: CancelCallback | None,
    ) -> None:
        NavegadorCactus.esperar_login(
            self, pagina, usuario, contrasena, cancelada, self._verificar_cancelacion
        )

    def _procesar_carrera(
        self: Any,
        pagina: Any,
        carrera: str,
        periodo: str,
        usuario: str,
        contrasena: str,
        cancelada: CancelCallback | None,
    ) -> list[dict[str, str]] | None:
        return NavegadorCactus.procesar_carrera(
            self,
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
        self: Any,
        pagina: Any,
        periodo_norm: str,
        cancelada: CancelCallback | None,
    ) -> str | None:
        return NavegadorCactus.abrir_periodo(
            self,
            pagina,
            periodo_norm,
            cancelada,
            verificar_cancelacion=self._verificar_cancelacion,
            esperar_vista=self._esperar_vista,
            comprobar_login=self._comprobar_login,
            clic_siguiente=self._clic_siguiente,
        )

    def _buscar_carrera(
        self: Any,
        pagina: Any,
        pos_periodo: str,
        carrera_norm: str,
        cancelada: CancelCallback | None,
    ) -> str | None:
        return NavegadorCactus.buscar_carrera(
            self,
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
        self: Any,
        pagina: Any,
        pos_carrera: str,
        carrera: str,
        periodo: str,
        cancelada: CancelCallback | None,
    ) -> list[dict[str, str]]:
        return NavegadorCactus.cursos_de_carrera(
            self,
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
        self: Any,
        pagina: Any,
        pos_carrera: str,
        cancelada: CancelCallback | None,
    ) -> list[tuple[str, str]]:
        return NavegadorCactus.leer_ciclos(
            self,
            pagina,
            pos_carrera,
            cancelada,
            verificar_cancelacion=self._verificar_cancelacion,
            comprobar_login=self._comprobar_login,
            clic_siguiente=self._clic_siguiente,
        )

    def _descargar_por_navegador(
        self: Any,
        pagina: Any,
        info: dict[str, str],
        directorio_salida: Path,
    ) -> str | None:
        return NavegadorCactus.descargar_por_navegador(
            self,
            pagina,
            info,
            directorio_salida,
            url_adjunto=self._url_adjunto,
            url_adjunto_segura=self._url_adjunto_segura,
        )

    def _clic_siguiente(self: Any, pagina: Any) -> bool:
        return NavegadorCactus.clic_siguiente(pagina, self._esperar_vista)
