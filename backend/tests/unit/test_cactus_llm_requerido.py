"""Una publicación vacía sin analista no demuestra normalización LLM."""

import json

import pytest
from fastapi.testclient import TestClient

from scripts import normalizar_cactus_secuencial as cli


@pytest.mark.parametrize("habilitado", [False, True])
def test_no_da_exito_a_csv_permitidos_sin_analista(monkeypatch, tmp_path, habilitado):
    pedidos = []

    def solicitar(_base, _ruta, datos=None):
        pedidos.append(datos)
        return {
            "id_ejecucion": "NOR_0000000000000001",
            "estado": "limpiado",
            "configuracion_curricular": {"usar_llm": habilitado},
            "release_gate": {"decision": "ALLOW_IMPORT"},
            "progreso_llm": {
                "fase": "completado",
                "silabos": [{"estado_analisis": "sin_propuesta", "latencia_modelo_ms": None}],
            }
            if habilitado
            else None,
        }

    monkeypatch.setattr(cli, "solicitar", solicitar)
    with pytest.raises(RuntimeError, match="LLM"):
        cli.ejecutar("http://localhost", "2026-2", "u", "p", tmp_path)
    assert len(pedidos) == 1  # No repetir el problema en las otras 13 carreras.
    resumen = json.loads((tmp_path / "resumen.json").read_text())
    assert resumen[0]["publicada"] is False


def test_llm_real_sin_coincidencias_es_valido_sin_forzar_habilidades(monkeypatch, tmp_path):
    def solicitar(_base, _ruta, datos=None):
        return {
            "id_ejecucion": "NOR_0000000000000001",
            "estado": "limpiado",
            "configuracion_curricular": {"usar_llm": True},
            "release_gate": {"decision": "ALLOW_IMPORT"},
            "progreso_llm": {
                "fase": "completado",
                "silabos": [
                    {
                        "estado_analisis": "sin_propuesta",
                        "latencia_modelo_ms": 0.0,
                        "propuestas_validas": 0,
                    }
                ],
            },
        }

    monkeypatch.setattr(cli, "solicitar", solicitar)
    assert cli.ejecutar("http://localhost", "2026-2", "u", "p", tmp_path, desde=14) == 0


def test_preflight_usa_config_real_del_backend_sin_descargar_o_pedir_secretos(monkeypatch):
    from api import servidor

    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))
    monkeypatch.setenv("NORMALIZADOR_CURRICULAR_LLM", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "secreto-no-mostrar")
    monkeypatch.setattr(cli.sys, "argv", ["script"])
    peticiones = []

    def solicitar(_base, ruta, datos=None):
        assert datos is None
        peticiones.append(ruta)
        respuesta = cliente.get(ruta)
        assert respuesta.status_code == 200
        assert "secreto-no-mostrar" not in respuesta.text
        return respuesta.json()

    monkeypatch.setattr(cli, "solicitar", solicitar)
    monkeypatch.setattr(cli, "getpass", lambda *_args: pytest.fail("No pedir secretos"))
    assert cli.main() == 1
    assert peticiones == ["/health", "/normalizador/configuracion/curricular"]


def test_diagnostico_consulta_ids_existentes_sin_post(monkeypatch, tmp_path, capsys):
    corrida = tmp_path / "corrida"
    corrida.mkdir()
    cli.guardar(
        corrida / "resumen.json",
        [{"carrera": "Administración", "id_ejecucion": "NOR_0000000000000001"}],
    )

    def solicitar(_base, ruta, datos=None):
        assert ruta == "/normalizador/ejecuciones/NOR_0000000000000001" and datos is None
        return {"estado": "limpiado", "configuracion_curricular": {"usar_llm": False}}

    monkeypatch.setattr(cli, "solicitar", solicitar)
    assert cli.diagnosticar("http://localhost", tmp_path) == 0
    datos = json.loads((corrida / "diagnostico.json").read_text())
    assert datos[0]["llm_habilitado"] is False and datos[0]["silabos_modelo"] == 0
    assert "Administración" in capsys.readouterr().out
