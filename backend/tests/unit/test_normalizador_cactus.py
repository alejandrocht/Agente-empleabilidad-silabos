"""Pruebas del adapter de extracción curricular desde Cactus."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from agente.normalizador import ejecuciones
from agente.normalizador.ejecuciones import GestorEjecuciones
from agente.normalizador.modelos import ResultadoLimpiezaSilabos
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
