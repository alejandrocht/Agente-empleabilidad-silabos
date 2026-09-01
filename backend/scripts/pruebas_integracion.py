"""Run 5 integration probes against the CIAR agent and report timing.

Usage from the repository root:

    cd backend
    python -m scripts.pruebas_integracion

The script uses the configured .env credentials. It prints:
- total request time
- per-stage latency when available in logs
- final answer

Probes:
1. Direct greeting (responder_directo)
2. Curriculum fact (generar_cypher)
3. Labor-market ranking (generar_cypher)
4. Independent entity query
5. Independent graph query
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Sequence

from dotenv import load_dotenv

from agente import responder

load_dotenv()


PROBES: Sequence[tuple[str, str | None]] = [
    ("Hola, ¿cómo estás?", None),
    ("¿Cuántas carreras hay?", None),
    ("Top 10 empresas con más ofertas dirigidas a Derecho.", None),
    ("¿Y para Ingeniería de Sistemas?", "Top 10 empresas con más ofertas dirigidas a Derecho."),
    (
        "¿Cuáles son las herramientas más solicitadas para esa carrera?",
        "¿Y para Ingeniería de Sistemas?",
    ),
]


def _print_separator() -> None:
    print("=" * 80)


async def _run_probe(
    question: str,
    previous_question: str | None,
    thread_id: str,
) -> dict[str, object]:
    started_at = time.perf_counter()
    answer = await responder(question, thread_id=thread_id)
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    return {
        "question": question,
        "previous_question": previous_question,
        "answer": answer,
        "duration_ms": duration_ms,
    }


async def main() -> None:
    thread_id = f"thread-{int(time.time())}"

    print(f"Thread ID: {thread_id}")
    def _eff_bool(name: str, default: str) -> bool:
        value = os.getenv(name, default)
        return value.strip().lower() in {"1", "true", "yes", "on"}

    print(f"Orchestrator model: {os.getenv('OPENAI_MODEL_ORQUESTADOR', 'NOT SET')}")
    print(f"Generator model: {os.getenv('OPENAI_MODEL_GENERADOR_CYPHER', 'NOT SET')}")
    print(f"Analyst model: {os.getenv('OPENAI_MODEL_ANALISTA', 'NOT SET')}")
    print(
        "Responses API generator (effective): "
        f"{_eff_bool('OPENAI_USE_RESPONSES_API_GENERADOR_CYPHER', 'true')}"
    )
    print(
        "Responses API analyst (effective): "
        f"{_eff_bool('OPENAI_USE_RESPONSES_API_ANALISTA', 'true')}"
    )
    print()

    results: list[dict[str, object]] = []
    for index, (question, previous) in enumerate(PROBES, start=1):
        _print_separator()
        print(f"Probe {index}/{len(PROBES)}")
        if previous:
            print(f"Previous: {previous}")
        print(f"Question: {question}")
        result = await _run_probe(question, previous, thread_id)
        results.append(result)
        print(f"Duration: {result['duration_ms']} ms")
        print(f"Answer: {result['answer']}")
        print()
        # Small pause between requests to avoid rate limits.
        await asyncio.sleep(0.5)

    _print_separator()
    print("SUMMARY")
    _print_separator()
    total_ms = sum(float(r["duration_ms"]) for r in results)
    print(f"Total time: {total_ms} ms")
    for index, result in enumerate(results, start=1):
        print(
            f"{index}. {result['question'][:50]:<50} "
            f"{result['duration_ms']} ms"
        )

    summary_path = "scripts/pruebas_integracion_resultados.json"
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print(f"\nResults written to {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
