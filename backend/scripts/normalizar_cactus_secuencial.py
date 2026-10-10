"""Normaliza las 14 carreras mediante la API, una ejecución por carrera."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from getpass import getpass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agente.normalizador.silabos.entrada import CARRERAS_ULIMA, PATRON_PERIODO  # noqa: E402

ACTIVOS = {"recibido", "extrayendo", "validando", "limpiando", "normalizando"}
TERMINALES = {
    "limpiado",
    "limpiado_con_advertencias",
    "no_publicado",
    "rechazado",
    "error",
    "cancelado",
}


def solicitar(base: str, ruta: str, datos: dict[str, Any] | None = None) -> dict[str, Any]:
    cuerpo = json.dumps(datos).encode("utf-8") if datos is not None else None
    solicitud = Request(
        base.rstrip("/") + ruta, data=cuerpo, headers={"Content-Type": "application/json"}
    )
    try:
        with urlopen(solicitud, timeout=60) as respuesta:
            resultado = json.load(respuesta)
    except HTTPError as exc:
        # Una respuesta de validación podría incluir la solicitud con credenciales.
        raise RuntimeError(
            f"La API respondió HTTP {exc.code}; no se repetirá la solicitud."
        ) from None
    except (URLError, OSError) as exc:
        raise RuntimeError(f"Sin respuesta de la API ({type(exc).__name__}).") from None
    if not isinstance(resultado, dict):
        raise RuntimeError("La API no devolvió un objeto JSON.")
    return resultado


def guardar(ruta: Path, datos: Any) -> None:
    temporal = ruta.with_suffix(".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(ruta)


def ejecutar(
    base: str,
    periodo: str,
    usuario: str,
    contrasena: str,
    destino: Path,
    *,
    desde: int = 1,
    hitl: int = 0,
    intervalo: float = 5,
) -> int:
    destino.mkdir(parents=True, exist_ok=True)
    resumen: list[dict[str, Any]] = []
    fallos = 0
    for numero, carrera in enumerate(CARRERAS_ULIMA, start=1):
        if numero < desde:
            continue
        print(f"\n[{numero}/14] {carrera}: solicitando ejecución...", flush=True)
        # No reintentar POST: ante un timeout el servidor podría haber creado el trabajo.
        estado = solicitar(
            base,
            "/normalizador/silabos/cactus",
            {
                "carrera": carrera,
                "periodo": periodo,
                "usuario": usuario,
                "contrasena": contrasena,
                "hitl": hitl,
            },
        )
        identificador = str(estado.get("id_ejecucion") or "")
        if not identificador.startswith("NOR_"):
            raise RuntimeError("La API no devolvió un ID de ejecución; revisa el historial.")
        print(f"ID: {identificador}", flush=True)
        archivo = destino / f"{numero:02d}_{identificador}.json"
        fila = {"carrera": carrera, "id_ejecucion": identificador, "estado": estado.get("estado")}
        resumen.append(fila)
        guardar(destino / "resumen.json", resumen)
        try:
            while True:
                guardar(archivo, estado)
                actual = str(estado.get("estado") or "")
                fila["estado"] = actual
                guardar(destino / "resumen.json", resumen)
                fuente = estado.get("progreso_fuente") or {}
                llm = estado.get("progreso_llm") or {}
                print(
                    f"  {actual}: descargas={fuente.get('archivos_descargados', 0)}; "
                    f"sílabos LLM={llm.get('silabos_procesados', 0)}/"
                    f"{llm.get('silabos_totales', '?')}",
                    flush=True,
                )
                if actual in TERMINALES:
                    break
                if actual not in ACTIVOS:
                    raise RuntimeError(
                        f"Estado inesperado {actual!r}; no se iniciará otra carrera."
                    )
                time.sleep(intervalo)
                estado = solicitar(base, f"/normalizador/ejecuciones/{identificador}")
        except (KeyboardInterrupt, RuntimeError):
            print(
                f"\nSe detuvo el script. La ejecución {identificador} puede seguir en el backend."
                " No inicies otra corrida hasta revisar ese ID.",
                flush=True,
            )
            raise
        gate = estado.get("release_gate") or {}
        publicada = gate.get("decision") == "ALLOW_IMPORT"
        fila["publicada"] = publicada
        guardar(destino / "resumen.json", resumen)
        if not publicada:
            fallos += 1
            codigos = [h.get("codigo") for h in estado.get("hallazgos", [])]
            print(
                f"  Sin publicación. Hallazgos: {codigos}. Se continuará con la siguiente.",
                flush=True,
            )
        else:
            print("  Publicación permitida; los CSV están en la ejecución del backend.", flush=True)
    print(
        f"\nFinalizado: {len(resumen)} carreras; {fallos} sin publicación. Resumen: {destino}",
        flush=True,
    )
    return 1 if fallos else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://localhost:8001")
    parser.add_argument("--periodo", default="2026-2")
    parser.add_argument(
        "--desde",
        type=int,
        choices=range(1, 15),
        default=1,
        help="Número de carrera inicial, de Administración (1) a Psicología (14).",
    )
    parser.add_argument(
        "--hitl",
        type=int,
        choices=(0, 1),
        default=0,
        help="0: aprobación automática de propuestas válidas; 1: revisión humana.",
    )
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    if not PATRON_PERIODO.fullmatch(args.periodo):
        parser.error("El periodo debe tener formato 2026-2.")
    destino = args.salida or Path("resultados_cactus") / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    try:
        solicitar(args.api, "/health")
        print("API disponible. Mantén el backend abierto durante toda la corrida.")
        print("Se usará el catálogo vectorizado y la configuración LLM del backend.")
        usuario = input("Usuario ULima: ").strip()
        contrasena = getpass("Contraseña ULima (oculta): ")
        if not usuario or not contrasena or len(usuario) > 200 or len(contrasena) > 200:
            raise RuntimeError("Usuario y contraseña deben tener entre 1 y 200 caracteres.")
        return ejecutar(
            args.api, args.periodo, usuario, contrasena, destino, desde=args.desde, hitl=args.hitl
        )
    except KeyboardInterrupt:
        print("\nInterrumpido; no se solicitarán más carreras.")
        return 130
    except (RuntimeError, OSError, ValueError) as exc:
        print(
            f"\nError: {exc}. Revisa el resumen y el historial antes de volver a ejecutar.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
