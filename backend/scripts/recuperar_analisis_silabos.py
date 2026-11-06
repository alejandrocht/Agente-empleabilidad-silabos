"""Recupera análisis desde sílabos descargados y guarda avance por sílabo."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agente.config.settings import configuracion_normalizador_curricular  # noqa: E402
from agente.normalizador.escritura_atomica import escribir_texto_atomico  # noqa: E402
from agente.normalizador.silabos import analista_tecnico  # noqa: E402
from agente.normalizador.silabos.salida_catalogos import construir_salidas_tecnicas  # noqa: E402


def leer_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def recuperar(origen: Path, destino: Path) -> dict:
    """Conserva propuestas anteriores; analiza únicamente sílabos sin resultados guardados."""
    staging = origen / "limpios/silabos.jsonl"
    propuestas_path = origen / "salidas/reportes/propuestas_tecnicas.jsonl"
    manifest = json.loads((origen / "manifest.json").read_text(encoding="utf-8"))
    if str(manifest.get("parametros", {}).get("hitl")) != "0":
        raise ValueError("La recuperación automática requiere una ejecución con hitl=0")
    registros = leer_jsonl(staging)
    alcances = {(r["carrera"], r["periodo"]) for r in registros}
    if len(alcances) != 1:
        raise ValueError("La recuperación requiere una sola carrera y período")
    ids = {r["id_silabo"] for r in registros}
    if len(ids) != len(registros):
        raise ValueError("Hay sílabos duplicados en la fuente")
    config = configuracion_normalizador_curricular()
    if not config.usar_llm:
        raise ValueError("La recuperación requiere LLM habilitado")
    catalogo = analista_tecnico.cargar_catalogo_hab_tec("HABTEC_38b1f27240cb401a")
    huella = hashlib.sha256(
        staging.read_bytes() + propuestas_path.read_bytes()
        + catalogo.sha256.encode() + json.dumps(config.a_dict(), sort_keys=True).encode()
    ).hexdigest()
    destino.mkdir(parents=True, exist_ok=True)
    checkpoint = destino / "checkpoint.json"
    if checkpoint.exists():
        estado = json.loads(checkpoint.read_text(encoding="utf-8"))
        if estado["huella"] != huella:
            raise ValueError("La fuente, catálogo o configuración cambiaron desde el checkpoint")
    else:
        anteriores = leer_jsonl(propuestas_path)
        if any(p.get("id_silabo") not in ids for p in anteriores):
            raise ValueError("Las propuestas anteriores no corresponden a los sílabos")
        estado = {
            "huella": huella,
            "origen": str(origen),
            "configuracion": config.a_dict(),
            "propuestas": anteriores,
            "completados": sorted({p["id_silabo"] for p in anteriores}),
            "auditoria": [],
        }

    def guardar() -> None:
        escribir_texto_atomico(checkpoint, json.dumps(estado, ensure_ascii=False, indent=2))

    guardar()
    completados = set(estado["completados"])
    print(f"{origen.name}: {len(completados)}/{len(registros)} sílabos conservados", flush=True)
    for indice, registro in enumerate(registros, 1):
        if registro["id_silabo"] in completados:
            continue
        print(f"{origen.name}: analizando sílabo {indice}/{len(registros)}", flush=True)
        auditoria: list[dict] = []
        propuestas = analista_tecnico.inferir_competencias_tecnicas(
            [registro], config, catalogo, auditoria=auditoria
        )
        estado["propuestas"].extend(propuestas)
        estado["auditoria"].extend(auditoria)
        estado["completados"].append(registro["id_silabo"])
        guardar()
        print(f"{origen.name}: sílabo {indice} guardado; habilidades={len(propuestas)}", flush=True)

    carrera, periodo = next(iter(alcances))
    analisis = {
        "estado": "COMPLETADO_CON_ADVERTENCIAS" if estado["auditoria"] else "COMPLETADO",
        "politica_habilidades": "catalogo_min_1",
        "advertencias": estado["auditoria"],
        "ejecucion_origen": origen.name,
    }
    resultado = construir_salidas_tecnicas(
        registros, destino / "salidas", carrera=carrera, periodo_academico=periodo,
        propuestas_aprobadas=estado["propuestas"], analisis_tecnico=analisis,
    )
    analista_tecnico.escribir_propuestas_tecnicas(
        destino / "propuestas_tecnicas.jsonl", estado["propuestas"]
    )
    resumen = {
        "ejecucion_origen": origen.name, "carrera": carrera, "silabos": len(registros),
        "asignaciones": len(estado["propuestas"]), "publicable": resultado.publicable,
        "release_gate": resultado.release_gate,
    }
    escribir_texto_atomico(
        destino / "resumen.json", json.dumps(resumen, ensure_ascii=False, indent=2)
    )
    return resumen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=Path(".normalizador"))
    fuentes = parser.add_mutually_exclusive_group(required=True)
    fuentes.add_argument("--ejecucion", action="append")
    fuentes.add_argument("--resumen-secuenciador", type=Path)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--esperar-archivo", type=Path)
    args = parser.parse_args()
    if args.esperar_archivo:
        print("Esperando que termine el secuenciador actual; no se iniciará otra llamada LLM.",
              flush=True)
        while not args.esperar_archivo.exists():
            time.sleep(30)
    ejecuciones = args.ejecucion
    if args.resumen_secuenciador:
        filas = json.loads(args.resumen_secuenciador.read_text(encoding="utf-8"))
        ejecuciones = [f["id_ejecucion"] for f in filas
                       if f.get("estado") not in {"limpiado", "limpiado_con_advertencias"}]
    if any(not re.fullmatch(r"NOR_[0-9a-f]{16}", s) for s in ejecuciones):
        parser.error("ID de ejecución inválido")
    for identificador in ejecuciones:
        resumen = recuperar(args.base / identificador, args.salida / identificador)
        print(json.dumps(resumen, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
