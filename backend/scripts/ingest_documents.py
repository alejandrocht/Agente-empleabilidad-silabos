#!/usr/bin/env python3
"""Offline/admin CIAR document ingestion with dry-run preview by default."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence

from agente.ingestion.service import (
    IngestionLimits,
    Neo4jGraphWriter,
    build_llm_graph_transformer,
    load_source_documents,
    transform_documents,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract an allow-listed CIAR graph preview from local documents."
    )
    parser.add_argument(
        "paths", nargs="+", help="Local .txt, .md, .markdown, or shaped .json files"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the reviewed normalized graph using NEO4J_INGEST_* credentials",
    )
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-documents", type=int, default=32)
    parser.add_argument("--max-document-chars", type=int, default=12_000)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL_INGESTION", "gpt-4o-mini"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    limits = IngestionLimits(
        max_documents=args.max_documents,
        max_document_chars=args.max_document_chars,
        batch_size=args.batch_size,
    )
    sources = load_source_documents(args.paths, limits=limits)

    from langchain_openai import ChatOpenAI

    transformer = build_llm_graph_transformer(
        ChatOpenAI(model=args.model, temperature=0, max_retries=0)
    )
    writer = Neo4jGraphWriter.from_env(os.environ) if args.write else None
    try:
        result = transform_documents(
            sources,
            transformer=transformer,
            writer=writer,
            credentials=writer.credentials if writer is not None else None,
            write=args.write,
            authorize_write=args.write,
            limits=limits,
        )
        print(json.dumps(result.preview(), ensure_ascii=True, indent=2, sort_keys=True))
    finally:
        if writer is not None:
            writer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
