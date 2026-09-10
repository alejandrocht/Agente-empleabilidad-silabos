"""Generate a natural-language answer from Neo4j results."""

from __future__ import annotations

import asyncio
import math
import os
from typing import Protocol, cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from agente.grafo.estado import Estado, pregunta_para_procesar
from agente.utils.llm import ANALYST_CHAT_PROFILE, build_chat_openai
from agente.utils.logger import log_error, log_event
from agente.utils.prompt import build_qa_prompt, build_qa_user_prompt

DEFAULT_ANALYST_TIMEOUT_SECONDS = 30.0


class AnalystRunnable(Protocol):
    """Minimal async interface for the QA answer chain."""

    async def ainvoke(self, input: list[BaseMessage]) -> object: ...


def build_analyst_runnable() -> AnalystRunnable:
    """Build the QA chain that converts Neo4j context into a natural answer."""
    model = build_chat_openai(ANALYST_CHAT_PROFILE, constructor=ChatOpenAI)
    return cast(AnalystRunnable, model | StrOutputParser())


def _analyst_timeout_seconds() -> float:
    raw_value = os.getenv("CIAR_ANALYST_TIMEOUT_SECONDS")
    if raw_value is None:
        return DEFAULT_ANALYST_TIMEOUT_SECONDS
    try:
        value = float(raw_value)
    except ValueError:
        return DEFAULT_ANALYST_TIMEOUT_SECONDS
    return value if math.isfinite(value) and value > 0 else DEFAULT_ANALYST_TIMEOUT_SECONDS


async def redacta_respuesta(
    estado: Estado,
    *,
    analyst_runnable: AnalystRunnable | None = None,
) -> Estado:
    """Answer the question using only the rows returned by Neo4j."""
    if estado.get("error"):
        return {}

    question = pregunta_para_procesar(estado)
    rows = estado.get("filas")
    if (
        not isinstance(question, str)
        or not question.strip()
        or not isinstance(rows, list)
        or not all(isinstance(row, dict) for row in rows)
    ):
        return {}

    messages = [
        SystemMessage(content=build_qa_prompt()),
        HumanMessage(content=build_qa_user_prompt(question, rows)),
    ]
    try:
        runnable = analyst_runnable or build_analyst_runnable()
        raw_result = await asyncio.wait_for(
            runnable.ainvoke(messages),
            timeout=_analyst_timeout_seconds(),
        )
        answer = raw_result.content if isinstance(raw_result, BaseMessage) else raw_result
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("El analista QA devolvió una respuesta vacía")
    except TimeoutError as exc:
        log_error("analyst", "timeout", exc)
        return {"error": "analyst_timeout", "warning": "analyst_timeout"}
    except Exception as exc:
        log_error("analyst", "failed", exc)
        return {"error": "analyst_failed", "warning": "analyst_failed"}

    answer = answer.strip()
    log_event(
        "analyst",
        "completed",
        rows_count=len(rows),
        length=len(answer),
        model_driven=True,
    )
    return {"respuesta": answer}
