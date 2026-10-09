"""Evidencia recuperable de una descarga Cactus que aborta antes del análisis."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from agente.normalizador import ejecuciones
from agente.normalizador.ejecuciones import GestorEjecuciones
from agente.normalizador.silabos.cactus_navegacion import CactusAuthenticationError


def test_fallo_en_segunda_carrera_conserva_conteos_y_zip_parcial_sin_credenciales(
    monkeypatch, tmp_path: Path
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    id_ejecucion, directorio = gestor.crear(
        "silabos",
        "cactus.zip",
        {"carrera": "TODAS", "periodo": "2026-2", "fuente": "cactus"},
    )

    class ExtractorFalso:
        def __init__(self, **_kwargs):
            pass

        def extraer(self, **kwargs):
            destino = kwargs["directorio_salida"] / "ADMINISTRACION/2026-2/Ciclo_01"
            destino.mkdir(parents=True)
            for i in range(86):
                (destino / f"curso_{i}.docx").write_bytes(b"documento")
            perfil = kwargs["directorio_perfil"]
            perfil.mkdir()
            (perfil / "cookies").write_text("secreto-no-persistir")
            kwargs["al_actualizar_progreso"](
                {
                    "fase": "navegando",
                    "carrera_actual": "Arquitectura",
                    "carreras_procesadas": 1,
                    "carreras_totales": 14,
                    "cursos_encontrados": 86,
                    "archivos_descargados": 86,
                    "cursos_procesados": 86,
                }
            )
            raise CactusAuthenticationError("La sesión no terminó correctamente.")

    def no_normalizar(*_args):
        pytest.fail("Una extracción fallida no debe iniciar el análisis LLM")

    monkeypatch.setattr(ejecuciones, "CactusExtractor", ExtractorFalso)
    monkeypatch.setattr(gestor, "_validar_silabos", no_normalizar)
    gestor._extraer_y_validar_silabos(
        gestor._obtener_objeto(id_ejecucion),
        "TODAS",
        "2026-2",
        "usuario@ulima.edu.pe",
        "secreto-no-persistir",
    )
    estado = gestor.obtener(id_ejecucion)
    assert estado["estado"] == "error"
    assert estado["progreso_llm"] is None
    fuente = estado["fuente"]
    assert fuente["completa"] is False
    assert fuente["carrera_actual"] == "Arquitectura"
    assert fuente["carreras_procesadas"] == 1
    assert fuente["archivos_descargados"] == fuente["archivos_procesables"] == 86
    assert fuente["archivo_parcial"] == "entrada/cactus.zip"
    assert estado["outputs"] == []
    with ZipFile(directorio / fuente["archivo_parcial"]) as paquete:
        assert len(paquete.namelist()) == 86
        assert all(n.startswith("ADMINISTRACION/2026-2/") for n in paquete.namelist())
    manifest = (directorio / "manifest.json").read_text(encoding="utf-8")
    reporte = (directorio / "salidas/reportes/extraccion_cactus.json").read_text(encoding="utf-8")
    assert "secreto-no-persistir" not in manifest + reporte
    assert "usuario@ulima.edu.pe" not in manifest + reporte
    assert not (directorio / "cactus_chrome_profile").exists()


def test_respaldo_fallido_no_oculta_error_original(monkeypatch, tmp_path: Path) -> None:
    from agente.normalizador import ejecuciones_curriculares

    gestor = GestorEjecuciones(tmp_path)
    id_ejecucion, directorio = gestor.crear("silabos", "cactus.zip")
    (directorio / "fuentes_curriculares/cactus").mkdir(parents=True)

    def fallar(*_args):
        raise OSError("Fallo de disco de prueba")

    monkeypatch.setattr(ejecuciones_curriculares, "empaquetar_archivos_cactus", fallar)
    gestor._registrar_error_fuente(
        gestor._obtener_objeto(id_ejecucion), "CACTUS_AUTENTICACION_FALLIDA", "Sesión rechazada"
    )
    estado = gestor.obtener(id_ejecucion)
    assert estado["estado"] == "error"
    assert estado["fuente"]["codigo"] == "CACTUS_AUTENTICACION_FALLIDA"
    assert estado["fuente"]["respaldo_parcial_error"] == "OSError"
    assert "archivo_parcial" not in estado["fuente"]
