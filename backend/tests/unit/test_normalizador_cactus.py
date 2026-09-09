"""Pruebas del adapter de extracción curricular desde Cactus."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from agente.normalizador import ejecuciones
from agente.normalizador.ejecuciones import GestorEjecuciones
from agente.normalizador.modelos import ResultadoLimpiezaSilabos
from agente.normalizador.silabos.cactus_navegacion import (
    CactusAuthenticationError,
    NavegadorCactus,
)
from agente.normalizador.silabos.fuente_cactus import (
    CactusExtractor,
    ResultadoExtraccionCactus,
    empaquetar_archivos_cactus,
    sanitize_filename,
)


def test_empaqueta_solo_formatos_curriculares_procesables(tmp_path: Path) -> None:
    raiz = tmp_path / "descargas"
    (raiz / "Ciclo_01").mkdir(parents=True)
    (raiz / "Ciclo_01" / "BASES.pdf").write_bytes(b"pdf")
    (raiz / "Ciclo_01" / "BASES.docx").write_bytes(b"docx")
    (raiz / "Ciclo_01" / "BASES.doc").write_bytes(b"legacy")
    destino = tmp_path / "entrada" / "cactus.zip"

    archivos = empaquetar_archivos_cactus(raiz, destino)

    assert archivos == ("Ciclo_01/BASES.docx", "Ciclo_01/BASES.pdf")
    with ZipFile(destino) as paquete:
        assert paquete.namelist() == ["Ciclo_01/BASES.docx", "Ciclo_01/BASES.pdf"]


def test_resuelve_adjuntos_en_la_raiz_del_mismo_host_y_nombres_vacios() -> None:
    extractor = CactusExtractor(base_url="https://cactus.example.test/ac/base.nsf")

    assert extractor._url_adjunto("/ac/base.nsf/0/ABC/$FILE/a.pdf", "ABC") == (
        "https://cactus.example.test/ac/base.nsf/0/ABC/$FILE/a.pdf"
    )
    assert extractor._url_adjunto("$FILE/a.pdf", "ABC") == (
        "https://cactus.example.test/ac/base.nsf/0/ABC/$FILE/a.pdf"
    )
    assert sanitize_filename("***") == "SIN_NOMBRE"


def test_restringe_adjuntos_al_origen_https_autenticado() -> None:
    extractor = CactusExtractor(base_url="https://cactus.example.test/ac/base.nsf")

    assert extractor._url_adjunto_segura(
        "https://cactus.example.test/ac/base.nsf/0/ABC/$FILE/a.pdf"
    )
    assert not extractor._url_adjunto_segura(
        "http://cactus.example.test/ac/base.nsf/0/ABC/$FILE/a.pdf"
    )
    assert not extractor._url_adjunto_segura(
        "https://attacker.example.test/ac/base.nsf/0/ABC/$FILE/a.pdf"
    )
    assert not extractor._url_adjunto_segura(
        "https://user:pass@cactus.example.test/ac/base.nsf/0/ABC/$FILE/a.pdf"
    )


def test_checkpoint_corrupto_se_descarta_y_recupera_solo_archivos_existentes(
    tmp_path: Path,
) -> None:
    info = {"nivel": "1", "nombre_curso": "BASES"}
    clave = CactusExtractor._clave_checkpoint(info)
    (tmp_path / ".checkpoint.json").write_text("{corrupto", encoding="utf-8")

    assert CactusExtractor._cargar_checkpoint(tmp_path) == set()

    ruta = tmp_path / "Ciclo_1" / "BASES.pdf"
    ruta.parent.mkdir()
    ruta.write_bytes(b"pdf")
    CactusExtractor._guardar_checkpoint(tmp_path, {"Ciclo_1/FALTANTE", clave})

    assert json.loads((tmp_path / ".checkpoint.json").read_text(encoding="utf-8")) == [
        "Ciclo_1/BASES",
        "Ciclo_1/FALTANTE",
    ]
    assert CactusExtractor._cargar_checkpoint(tmp_path) == {clave}


def test_fallback_navegador_registra_exito_y_fallo_http(monkeypatch, tmp_path: Path) -> None:
    extractor = CactusExtractor(base_url="https://cactus.example.test/ac/base.nsf")
    info = {"nivel": "1", "nombre_curso": "BASES", "unid": "ABC"}
    resultado_http = {"info": info, "status": "doc_error", "detalle": "HTML-no-login"}

    monkeypatch.setattr(extractor, "_ronda_descarga", lambda *_args, **_kwargs: [resultado_http])
    monkeypatch.setattr(extractor, "_capturar_cookies", lambda _contexto: {})
    monkeypatch.setattr(extractor, "_descargar_por_navegador", lambda *_args: "pdf")

    exito = extractor._descargar_cursos(
        object(), object(), [info], tmp_path, set(), "usuario", "secreto", None, None
    )

    assert exito["archivos_descargados"] == 1
    assert exito["fetch_fallidos"] == 0
    assert json.loads((tmp_path / ".checkpoint.json").read_text(encoding="utf-8")) == [
        "Ciclo_1/BASES"
    ]

    monkeypatch.setattr(extractor, "_descargar_por_navegador", lambda *_args: None)
    fallo = extractor._descargar_cursos(
        object(), object(), [info], tmp_path, set(), "usuario", "secreto", None, None
    )

    assert fallo["archivos_descargados"] == 0
    assert fallo["fetch_fallidos"] == 1
    assert fallo["errores"] == [
        {
            "codigo": "CACTUS_ADJUNTO_NO_DESCARGABLE",
            "curso": "BASES",
            "mensaje": "El curso figura en Cactus, pero el adjunto no pudo descargarse.",
        }
    ]


def test_prefiere_texto_del_enlace_para_no_confundir_columnas_de_la_fila() -> None:
    class FilaFalsa:
        def count(self) -> int:
            return 1

        def inner_text(self) -> str:
            return "1.32 Marketing"

    class EnlaceFalso:
        def inner_text(self) -> str:
            return "Marketing"

        def locator(self, _selector: str) -> FilaFalsa:
            return FilaFalsa()

    assert CactusExtractor._etiqueta(EnlaceFalso()) == "MARKETING"


class _LocatorFalso:
    def __init__(self, enlaces: list[_EnlaceFalso] | None = None) -> None:
        self.enlaces = enlaces or []

    @property
    def first(self) -> _EnlaceFalso:
        return self.enlaces[0]

    def all(self) -> list[_EnlaceFalso]:
        return self.enlaces

    def count(self) -> int:
        return len(self.enlaces)

    def nth(self, indice: int) -> _EnlaceFalso:
        return self.enlaces[indice]


class _EnlaceFalso:
    def __init__(self, pagina: _PaginaFalsa, href: str, texto: str, accion: str = "") -> None:
        self.pagina = pagina
        self.href = href
        self.texto = texto
        self.accion = accion

    def click(self) -> None:
        if self.accion == "siguiente":
            self.pagina.avanzar()
        elif self.accion:
            self.pagina.estado = self.accion

    def get_attribute(self, nombre: str) -> str:
        assert nombre == "href"
        return self.href

    def inner_text(self) -> str:
        return self.texto

    def locator(self, _selector: str) -> _LocatorFalso:
        return _LocatorFalso()


class _PaginaFalsa:
    def __init__(self) -> None:
        self.estado = "inicio"
        self.pagina_periodos = 0
        self.urls: list[str] = []

    def content(self) -> str:
        return "<html>contenido</html>"

    def goto(self, url: str, **_kwargs: object) -> None:
        self.urls.append(url)
        if "CollapseView" in url:
            self.estado = "periodos"
        elif "Expand=1.2.3" in url:
            self.estado = "curso"

    def locator(self, selector: str) -> _LocatorFalso:
        if selector == "a[href*='Expand=']":
            if self.estado == "periodos":
                if self.pagina_periodos == 0:
                    return _LocatorFalso([_EnlaceFalso(self, "?Expand=9", "2025-2")])
                return _LocatorFalso([_EnlaceFalso(self, "?Expand=1", "2026-1", "carrera")])
            if self.estado == "carrera":
                return _LocatorFalso(
                    [_EnlaceFalso(self, "?Expand=1.2", "Marketing", "ciclos")]
                )
            if self.estado == "ciclos":
                return _LocatorFalso([_EnlaceFalso(self, "?Expand=1.2.3", "Ciclo 03")])
            return _LocatorFalso()
        if selector == "a[href*='?OpenDocument']" and self.estado == "curso":
            return _LocatorFalso(
                [
                    _EnlaceFalso(
                        self,
                        "/0123456789ABCDEF0123456789ABCDEF?OpenDocument",
                        "Bases de datos",
                    )
                ]
            )
        return _LocatorFalso()

    def get_by_role(self, role: str, *, name: object) -> _LocatorFalso:
        assert role == "link"
        if self.estado == "periodos" and self.pagina_periodos == 0:
            return _LocatorFalso([_EnlaceFalso(self, "", "Next", "siguiente")])
        return _LocatorFalso()

    def wait_for_load_state(self, *_args: object, **_kwargs: object) -> None:
        pass

    def wait_for_selector(self, *_args: object, **_kwargs: object) -> None:
        pass

    def avanzar(self) -> bool:
        if self.estado != "periodos" or self.pagina_periodos:
            return False
        self.pagina_periodos = 1
        return True


def test_navega_periodo_carrera_paginacion_expand_y_open_document(monkeypatch) -> None:
    extractor = CactusExtractor(base_url="https://cactus.example.test/ac/base.nsf")
    pagina = _PaginaFalsa()
    esperas: list[str] = []

    monkeypatch.setattr(extractor, "_esperar_vista", lambda _pagina: esperas.append("vista"))

    cursos = extractor._procesar_carrera(
        pagina, "Marketing", "2026-1", "usuario", "secreto", None
    )

    assert cursos == [
        {
            "unid": "0123456789ABCDEF0123456789ABCDEF",
            "carrera": "Marketing",
            "periodo": "2026-1",
            "nivel": "03",
            "nombre_curso": "BASES_DE_DATOS",
        }
    ]
    assert any("CollapseView" in url for url in pagina.urls)
    assert any("Expand=1.2.3" in url for url in pagina.urls)
    assert esperas


class _CampoFalso:
    def __init__(self) -> None:
        self.valor = ""

    def fill(self, valor: str) -> None:
        self.valor = valor


class _DescargaFalsa:
    def __init__(self, contenido: bytes) -> None:
        self.contenido = contenido

    def save_as(self, ruta: str) -> None:
        Path(ruta).write_bytes(self.contenido)


class _ContextoDescargaFalso:
    def __init__(self, contenido: bytes) -> None:
        self.value = _DescargaFalsa(contenido)

    def __enter__(self) -> _ContextoDescargaFalso:
        return self

    def __exit__(self, *_args: object) -> None:
        pass


class _PaginaLoginYDescargaFalsa:
    def __init__(self, contenido: bytes) -> None:
        self.login = True
        self.usuario = _CampoFalso()
        self.contrasena = _CampoFalso()
        self.boton = _EnlaceFalso(self, "", "", "autenticado")
        self.contenido = contenido

    @property
    def estado(self) -> str:
        return ""

    @estado.setter
    def estado(self, valor: str) -> None:
        if valor == "autenticado":
            self.login = False

    def content(self) -> str:
        return "_CustomLoginform" if self.login else "<html>documento</html>"

    def goto(self, _url: str, **_kwargs: object) -> None:
        pass

    def locator(self, selector: str) -> _CampoFalso | _LocatorFalso:
        if selector == "input[name='Username']":
            return self.usuario
        if selector == "input[name='Password']":
            return self.contrasena
        if selector == "a:has(img[alt='aceptar'])":
            return _LocatorFalso([self.boton])
        if selector == "a[href*='$FILE']":
            return _LocatorFalso([_EnlaceFalso(self, "$FILE/silabo.pdf", "Sílabo")])
        return _LocatorFalso()

    def wait_for_load_state(self, *_args: object, **_kwargs: object) -> None:
        pass

    def expect_download(self, **_kwargs: object) -> _ContextoDescargaFalso:
        return _ContextoDescargaFalso(self.contenido)


def test_login_y_fallback_playwright_rechazan_credenciales_incompletas_y_archivos_grandes(
    tmp_path: Path,
) -> None:
    navegador = NavegadorCactus(
        base_url="https://cactus.example.test/ac/base.nsf",
        view_url="https://cactus.example.test/ac/base.nsf/VCursosXCiclAcdXEspc",
        login_probe="https://cactus.example.test/login",
        max_attachment_bytes=3,
    )
    pagina = _PaginaLoginYDescargaFalsa(b"1234")

    with pytest.raises(CactusAuthenticationError):
        navegador.esperar_login(pagina, "", "", None, lambda _cancelada: None)

    navegador.esperar_login(pagina, "usuario", "secreto", None, lambda _cancelada: None)
    assert pagina.usuario.valor == "usuario"
    assert pagina.contrasena.valor == "secreto"
    assert (
        navegador.descargar_por_navegador(
            pagina,
            {"unid": "ABC", "nivel": "1", "nombre_curso": "BASES"},
            tmp_path,
            url_adjunto=lambda href, _unid: f"https://cactus.example.test/{href}",
            url_adjunto_segura=lambda _url: True,
        )
        is None
    )
    assert not list(tmp_path.rglob("*.pdf"))


def test_el_worker_entrega_el_paquete_cactus_al_pipeline_sin_persistir_secretos(
    monkeypatch, tmp_path: Path
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    id_ejecucion, directorio = gestor.crear(
        "silabos",
        "cactus.zip",
        {"carrera": "Marketing", "periodo": "2026-1", "fuente": "cactus"},
    )
    captura: dict[str, object] = {}

    class ExtractorFalso:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def extraer(self, **kwargs: object) -> ResultadoExtraccionCactus:
            salida = kwargs["directorio_salida"]
            perfil = kwargs["directorio_perfil"]
            assert isinstance(salida, Path)
            assert isinstance(perfil, Path)
            (salida / "Ciclo_01").mkdir(parents=True)
            (salida / "Ciclo_01" / "MARKETING.pdf").write_bytes(b"pdf")
            perfil.mkdir(parents=True)
            callback = kwargs["al_actualizar_progreso"]
            assert callable(callback)
            callback({"fase": "completado", "cursos_encontrados": 1, "cursos_procesados": 1})
            return ResultadoExtraccionCactus(
                carrera="Marketing",
                periodo="2026-1",
                cursos_encontrados=1,
                archivos_descargados=1,
                archivos_procesables=1,
                sin_silabo=0,
                fetch_fallidos=0,
                sesiones_fallidas=0,
                archivos_no_soportados=0,
                archivos=(salida / "Ciclo_01" / "MARKETING.pdf",),
                errores=(),
            )

    def validar_falso(ejecucion, ruta, carrera, periodo) -> None:
        captura.update(ruta=ruta, carrera=carrera, periodo=periodo)
        captura["estado_antes_de_validar"] = ejecucion.estado
        ejecucion.estado = "limpiado"

    monkeypatch.setattr(ejecuciones, "CactusExtractor", ExtractorFalso)
    monkeypatch.setattr(gestor, "_validar_silabos", validar_falso)

    gestor._extraer_y_validar_silabos(
        gestor._obtener_objeto(id_ejecucion),
        "Marketing",
        "2026-1",
        "usuario@ulima.edu.pe",
        "secreto-no-persistir",
    )

    ruta_entrada = captura["ruta"]
    assert ruta_entrada == directorio / "entrada" / "cactus.zip"
    assert isinstance(ruta_entrada, Path)
    assert captura["estado_antes_de_validar"] == "validando"
    with ZipFile(ruta_entrada) as paquete:
        assert paquete.namelist() == ["Ciclo_01/MARKETING.pdf"]
    manifest = (directorio / "manifest.json").read_text(encoding="utf-8")
    assert "secreto-no-persistir" not in manifest
    assert "usuario@ulima.edu.pe" not in manifest
    assert gestor.obtener(id_ejecucion)["fuente"]["tipo"] == "cactus"


def test_bloquea_release_gate_si_cactus_entrega_cobertura_incompleta(tmp_path: Path) -> None:
    gestor = GestorEjecuciones(tmp_path)
    id_ejecucion, directorio = gestor.crear("silabos", "cactus.zip")
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    ejecucion.fuente = {
        "tipo": "cactus",
        "completa": False,
        "cursos_encontrados": 2,
        "archivos_descargados": 1,
        "archivos_procesables": 1,
    }
    limpieza = ResultadoLimpiezaSilabos(
        registros=1,
        outputs=(),
        hallazgos=(),
        publicable=True,
        release_gate={"decision": "ALLOW_IMPORT", "blockers": [], "checks": {}},
    )

    resultado = gestor._aplicar_gate_de_extraccion(ejecucion, limpieza)

    assert resultado.publicable is False
    assert resultado.release_gate["decision"] == "BLOCK_IMPORT"
    assert "EXTRACTION_COVERAGE_INCOMPLETE" in resultado.release_gate["blockers"]
    assert resultado.release_gate["checks"]["source_extraction"]["ok"] is False
    assert (directorio / "salidas" / "reportes" / "release_gate.json").is_file()


def test_rechaza_extraccion_sin_archivos_y_purga_sesion_del_navegador(
    monkeypatch, tmp_path: Path
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    id_ejecucion, directorio = gestor.crear("silabos", "cactus.zip")

    class ExtractorVacio:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def extraer(self, **kwargs: object) -> ResultadoExtraccionCactus:
            salida = kwargs["directorio_salida"]
            perfil = kwargs["directorio_perfil"]
            assert isinstance(salida, Path)
            assert isinstance(perfil, Path)
            (salida / "Ciclo_01").mkdir(parents=True)
            perfil.mkdir(parents=True)
            return ResultadoExtraccionCactus(
                carrera="Marketing",
                periodo="2026-1",
                cursos_encontrados=1,
                archivos_descargados=0,
                archivos_procesables=0,
                sin_silabo=1,
                fetch_fallidos=0,
                sesiones_fallidas=0,
                archivos_no_soportados=0,
                archivos=(),
                errores=({"codigo": "CACTUS_SIN_SILABO", "mensaje": "sin adjunto"},),
            )

    monkeypatch.setattr(ejecuciones, "CactusExtractor", ExtractorVacio)

    gestor._extraer_y_validar_silabos(
        gestor._obtener_objeto(id_ejecucion),
        "Marketing",
        "2026-1",
        "usuario@ulima.edu.pe",
        "secreto-no-persistir",
    )

    assert gestor.obtener(id_ejecucion)["estado"] == "rechazado"
    assert any(
        hallazgo["codigo"] == "CACTUS_SIN_SILABOS_PROCESABLES"
        for hallazgo in gestor.obtener(id_ejecucion)["hallazgos"]
    )
    assert not (directorio / "fuentes_curriculares").exists()
    assert not (directorio / "cactus_chrome_profile").exists()
    assert (directorio / "salidas" / "reportes" / "extraccion_cactus.json").is_file()
