"""CLI secuencial: frontera HTTP real y trabajos sin solapamiento."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError

import pytest

from scripts import normalizar_cactus_secuencial as cli


def test_catorce_carreras_por_http_esperan_llm_y_continuan_tras_error(tmp_path: Path):
    pedidos = []
    activo = None
    consultas = 0

    class API(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def responder(self, datos, codigo=200):
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(datos).encode())

        def do_POST(self):
            nonlocal activo, consultas
            assert self.path == "/normalizador/silabos/cactus"
            if activo is not None:
                self.responder({}, 409)
                return
            datos = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert datos["usuario"] == "usuario-prueba"
            assert datos["contrasena"] == "secreto-prueba"
            assert datos["hitl"] == 0 and datos["periodo"] == "2026-2"
            pedidos.append(datos["carrera"])
            activo = f"NOR_{len(pedidos):016x}"
            consultas = 0
            self.responder({"id_ejecucion": activo, "estado": "extrayendo"}, 202)

        def do_GET(self):
            nonlocal activo, consultas
            assert self.path == f"/normalizador/ejecuciones/{activo}"
            consultas += 1
            if consultas == 1:
                self.responder(
                    {
                        "id_ejecucion": activo,
                        "estado": "limpiando",
                        "progreso_llm": {"silabos_totales": 2, "silabos_procesados": 1},
                    }
                )
                return
            falla = len(pedidos) == 2
            datos = {
                "id_ejecucion": activo,
                "estado": "error" if falla else "limpiado_con_advertencias",
                "release_gate": None if falla else {"decision": "ALLOW_IMPORT"},
                "hallazgos": [{"codigo": "CACTUS_AUTENTICACION_FALLIDA"}] if falla else [],
            }
            activo = None
            self.responder(datos)

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), API)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        codigo = cli.ejecutar(
            f"http://127.0.0.1:{servidor.server_port}",
            "2026-2",
            "usuario-prueba",
            "secreto-prueba",
            tmp_path,
            intervalo=0,
        )
    finally:
        servidor.shutdown()
        servidor.server_close()
        hilo.join()
    assert codigo == 1
    assert pedidos == list(cli.CARRERAS_ULIMA)
    resumen = json.loads((tmp_path / "resumen.json").read_text())
    assert len(resumen) == 14
    assert sum(r["publicada"] for r in resumen) == 13
    assert resumen[1]["estado"] == "error"
    assert len(list(tmp_path.glob("*_NOR_*.json"))) == 14
    for archivo in tmp_path.glob("*.json"):
        assert "secreto-prueba" not in archivo.read_text()
        assert "usuario-prueba" not in archivo.read_text()


def test_desde_psicologia_solicita_solo_ultima_carrera(monkeypatch, tmp_path):
    pedidos = []

    def solicitar(_base, _ruta, datos=None):
        pedidos.append(datos)
        return {
            "id_ejecucion": "NOR_0000000000000001",
            "estado": "no_publicado",
            "release_gate": {"decision": "BLOCK_IMPORT"},
        }

    monkeypatch.setattr(cli, "solicitar", solicitar)
    assert cli.ejecutar("http://localhost", "2026-2", "u", "p", tmp_path, desde=14) == 1
    assert [p["carrera"] for p in pedidos] == ["Psicología"]


@pytest.mark.parametrize("motivo", ["estado_desconocido", "sin_conexion", "interrumpido"])
def test_no_inicia_siguiente_si_no_confirma_fin(monkeypatch, tmp_path, motivo):
    pedidos = []

    def solicitar(_base, _ruta, datos=None):
        if datos is not None:
            pedidos.append(datos)
            return {"id_ejecucion": "NOR_0000000000000001", "estado": "extrayendo"}
        if motivo == "sin_conexion":
            raise RuntimeError("Sin respuesta")
        if motivo == "interrumpido":
            raise KeyboardInterrupt
        return {"estado": "desconocido"}

    monkeypatch.setattr(cli, "solicitar", solicitar)
    esperado = KeyboardInterrupt if motivo == "interrumpido" else RuntimeError
    with pytest.raises(esperado):
        cli.ejecutar("http://localhost", "2026-2", "u", "p", tmp_path, intervalo=0)
    assert len(pedidos) == 1
    assert json.loads((tmp_path / "resumen.json").read_text())[0]["id_ejecucion"]


def test_post_sin_respuesta_no_se_reintenta(monkeypatch, tmp_path):
    intentos = []

    def fallar(*_args, **_kwargs):
        intentos.append(1)
        raise URLError("No registrar credenciales ni repetir")

    monkeypatch.setattr(cli, "urlopen", fallar)
    with pytest.raises(RuntimeError, match="Sin respuesta"):
        cli.ejecutar("http://localhost", "2026-2", "u", "p", tmp_path)
    assert len(intentos) == 1


def test_cli_comprueba_backend_antes_de_pedir_credenciales(monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "argv", ["normalizar_cactus_secuencial.py"])

    def sin_backend(*_args):
        raise RuntimeError("Sin respuesta de la API")

    def no_pedir(*_args):
        pytest.fail("No pedir secretos sin backend")

    monkeypatch.setattr(cli, "solicitar", sin_backend)
    monkeypatch.setattr(cli, "getpass", no_pedir)
    assert cli.main() == 1
    assert "Sin respuesta" in capsys.readouterr().err
