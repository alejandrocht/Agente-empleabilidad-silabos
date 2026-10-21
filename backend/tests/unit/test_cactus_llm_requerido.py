"""Una publicación vacía sin analista no demuestra normalización LLM."""

import json
from io import BytesIO
from urllib.error import HTTPError

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
    with pytest.raises(RuntimeError, match="LLM|habilidad"):
        cli.ejecutar("http://localhost", "2026-2", "u", "p", tmp_path)
    assert len(pedidos) == 1  # No repetir el problema en las otras 11 carreras.
    resumen = json.loads((tmp_path / "resumen.json").read_text())
    assert resumen[0]["publicada"] is False


def test_llm_real_sin_habilidades_no_publica(monkeypatch, tmp_path):
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
    with pytest.raises(RuntimeError, match="habilidad válida por sílabo"):
        cli.ejecutar("http://localhost", "2026-2", "u", "p", tmp_path, desde=12)


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


def test_sin_habilidad_exige_reintento_del_backend(monkeypatch, tmp_path):
    def solicitar(*_args):
        return {
            "id_ejecucion": "NOR_0000000000000001",
            "estado": "limpiado",
            "configuracion_curricular": {
                "usar_llm": True,
                "politica_habilidades": "catalogo_min_1_max_1",
            },
            "release_gate": {"decision": "ALLOW_IMPORT"},
            "progreso_llm": {
                "fase": "completado",
                "silabos_detectados": 1,
                "silabos": [
                    {
                        "estado_analisis": "sin_propuesta",
                        "latencia_modelo_ms": None,
                        "error_codigo": "HABILIDAD_NO_VALIDA_REINTENTO",
                    }
                ],
            },
        }

    monkeypatch.setattr(cli, "solicitar", solicitar)
    with pytest.raises(RuntimeError, match="habilidad"):
        cli.ejecutar("http://localhost", "2026-2", "u", "p", tmp_path, desde=12)


def test_no_basta_analizar_solo_un_silabo_de_la_carrera(monkeypatch, tmp_path):
    def solicitar(*_args):
        return {
            "id_ejecucion": "NOR_0000000000000001",
            "estado": "limpiado",
            "configuracion_curricular": {"usar_llm": True},
            "release_gate": {"decision": "ALLOW_IMPORT"},
            "progreso_llm": {
                "fase": "completado",
                "silabos_detectados": 2,
                "silabos": [
                    {"estado_analisis": "completado", "latencia_modelo_ms": 10},
                    {"estado_analisis": "sin_propuesta", "latencia_modelo_ms": None},
                ],
            },
        }

    monkeypatch.setattr(cli, "solicitar", solicitar)
    with pytest.raises(RuntimeError, match="habilidad"):
        cli.ejecutar("http://localhost", "2026-2", "u", "p", tmp_path, desde=12)


@pytest.mark.parametrize("correcta", [False, True])
def test_comprobacion_real_antes_de_credenciales_y_descargas(monkeypatch, correcta, capsys):
    monkeypatch.setattr(cli.sys, "argv", ["script", "--comprobar"])
    rutas = []

    def solicitar(_base, ruta, datos=None, *, timeout=60):
        rutas.append(ruta)
        if ruta == "/health":
            return {}
        if ruta == "/normalizador/configuracion/curricular":
            return {"usar_llm": True, "timeout_llm_seconds": 600, "max_reintentos_llm": 2}
        assert ruta == cli.RUTA_COMPROBACION
        assert datos == {"carreras": list(cli.CARRERAS_CATALOGO_ACTUAL)}
        assert timeout == 1980
        if not correcta:
            raise RuntimeError("El analista LLM no responde")
        return {
            "lista_para_normalizar": True,
            "catalogo": {
                "id_catalogo": cli.CATALOGO_OBJETIVO,
                "modelo_embedding": "modelo-vector",
            },
            "prueba_llm": {"latencia_modelo_ms": 5.0},
        }

    monkeypatch.setattr(cli, "solicitar", solicitar)
    monkeypatch.setattr(cli, "getpass", lambda *_args: pytest.fail("No pedir secretos"))
    monkeypatch.setattr("builtins.input", lambda *_args: pytest.fail("No pedir usuario"))
    assert cli.main() == (0 if correcta else 1)
    assert len(rutas) == 3
    salida = capsys.readouterr()
    assert "Comprobación OK" in salida.out if correcta else "LLM no responde" in salida.err


@pytest.mark.parametrize("causa", ["sin_catalogo", "hash_distinto", "faltan_carreras"])
def test_cli_muestra_causa_del_catalogo_sin_exponer_respuesta_cruda(monkeypatch, causa):
    detalle = {"codigo": "CATALOGO_NO_DISPONIBLE", "secreto": "no-mostrar"}
    if causa == "faltan_carreras":
        detalle["carreras_faltantes"] = ["Psicología"]
    else:
        detalle["motivo"] = {
            "sin_catalogo": "CATALOGO_NO_ENCONTRADO",
            "hash_distinto": "CATALOGO_HASH_DISTINTO",
        }[causa]

    def fallar(*_a, **_k):
        raise HTTPError(
            "http://localhost", 503, "", {}, BytesIO(json.dumps({"detail": detalle}).encode())
        )

    monkeypatch.setattr(cli, "urlopen", fallar)
    with pytest.raises(RuntimeError) as error:
        cli.solicitar("http://localhost", cli.RUTA_COMPROBACION, {})
    assert "no-mostrar" not in str(error.value)
    assert {
        "sin_catalogo": "NORMALIZADOR_HAB_TEC_DIR",
        "hash_distinto": "hash",
        "faltan_carreras": "Psicología",
    }[causa] in str(error.value)
