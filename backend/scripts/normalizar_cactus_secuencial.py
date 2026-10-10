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


def resumen_analisis(estado: dict[str, Any]) -> dict[str, Any]:
    config = estado.get("configuracion_curricular") or {}
    progreso = estado.get("progreso_llm") or {}
    silabos = progreso.get("silabos") or []
    return {
        "llm_habilitado": config.get("usar_llm"),
        "modelo": config.get("modelo_analista"),
        "proveedor": config.get("proveedor_llm"),
        "fase_llm": progreso.get("fase"),
        "logros_detectados": progreso.get("logros_detectados", 0),
        "silabos_detectados": progreso.get("silabos_detectados", 0),
        "silabos_modelo": sum(
            s.get("latencia_modelo_ms") is not None
            and s.get("estado_analisis") in {"completado", "sin_propuesta"}
            for s in silabos
        ),
        "silabos_omitidos": sum(
            s.get("latencia_modelo_ms") is None
            and s.get("estado_analisis") in {"sin_propuesta", "omitido"}
            for s in silabos
        ),
        "propuestas_validas": sum(s.get("propuestas_validas", 0) for s in silabos),
    }


def diagnosticar(base: str, raiz: Path) -> int:
    resumenes = list(raiz.rglob("resumen.json"))
    if not resumenes:
        raise RuntimeError(f"No hay resúmenes guardados en {raiz}")
    ultimo = max(resumenes, key=lambda p: p.stat().st_mtime_ns)
    filas = json.loads(ultimo.read_text(encoding="utf-8"))
    diagnostico = []
    for fila in filas:
        identificador = fila["id_ejecucion"]
        estado = solicitar(base, f"/normalizador/ejecuciones/{identificador}")
        analisis = resumen_analisis(estado)
        datos = {
            "carrera": fila["carrera"],
            "id_ejecucion": identificador,
            "estado": estado.get("estado"),
            **analisis,
            "hallazgos": estado.get("hallazgos"),
            "release_gate": estado.get("release_gate"),
        }
        diagnostico.append(datos)
        print(json.dumps(datos, ensure_ascii=False, indent=2), flush=True)
        guardar(ultimo.parent / "diagnostico.json", diagnostico)
    print(f"Diagnóstico guardado: {ultimo.parent / 'diagnostico.json'}")
    return 0


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
                analisis = resumen_analisis(estado)
                fila.update(analisis)
                fila["publicada"] = False
                guardar(destino / "resumen.json", resumen)
                fuente = estado.get("progreso_fuente") or {}
                llm = estado.get("progreso_llm") or {}
                print(
                    f"  {actual}: descargas={fuente.get('archivos_descargados', 0)}; "
                    f"sílabos LLM={llm.get('silabos_procesados', 0)}/"
                    f"{llm.get('silabos_totales', '?')}; "
                    f"con modelo={analisis['silabos_modelo']}; "
                    f"omitidos={analisis['silabos_omitidos']}; "
                    f"propuestas={analisis['propuestas_validas']}",
                    flush=True,
                )
                if analisis["llm_habilitado"] is False:
                    raise RuntimeError("LLM desactivado en el backend; no se continuará la corrida")
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
        if publicada and (
            analisis["llm_habilitado"] is not True
            or not analisis["silabos_modelo"]
            or analisis["fase_llm"] != "completado"
        ):
            raise RuntimeError(
                f"La ejecución {identificador} permitió CSV sin análisis LLM comprobado. "
                "Revisa los logros, candidatos vectorizados y el reporte del analista"
            )
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
    parser.add_argument(
        "--diagnosticar",
        action="store_true",
        help="Consulta los IDs de la última corrida, sin descargar ni pedir claves.",
    )
    args = parser.parse_args()
    if not PATRON_PERIODO.fullmatch(args.periodo):
        parser.error("El periodo debe tener formato 2026-2.")
    destino = args.salida or Path("resultados_cactus") / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    try:
        solicitar(args.api, "/health")
        if args.diagnosticar:
            return diagnosticar(args.api, args.salida or Path("resultados_cactus"))
        config = solicitar(args.api, "/normalizador/configuracion/curricular")
        if config.get("usar_llm") is not True:
            raise RuntimeError(
                "LLM desactivado: inicia el backend con NORMALIZADOR_CURRICULAR_LLM=true"
            )
        print("API disponible. Mantén el backend abierto durante toda la corrida.")
        print(f"LLM habilitado: {config.get('proveedor_llm')} / {config.get('modelo_analista')}")
        print("Se usará el catálogo vectorizado del backend.")
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
