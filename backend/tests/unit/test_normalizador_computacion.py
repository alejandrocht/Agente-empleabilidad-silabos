"""Pure normalization and fixed pre-refactor output contracts."""

from __future__ import annotations

import builtins
import copy
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pytest
from test_normalizador_salida_contract import (
    _catalogo,
    _catalogo_sin_habilidad,
    _registro,
    _validacion,
)

from agente.normalizador.silabos import salida


@pytest.mark.parametrize("pending", [False, True])
def test_normalization_is_pure_repeatable_and_preserves_inputs(monkeypatch, pending):
    records = [_registro()]
    catalog = _catalogo_sin_habilidad() if pending else _catalogo()
    proposals = {}
    before = copy.deepcopy((records, vars(catalog), proposals))

    def no_io(*args, **kwargs):
        pytest.fail("Pure normalization attempted disk I/O")

    with monkeypatch.context() as guarded:
        guarded.setattr(builtins, "open", no_io)
        for method in ("open", "write_text", "write_bytes", "mkdir", "unlink", "read_text"):
            guarded.setattr(Path, method, no_io)
        first = salida.normalizar_registros_curriculares(
            records,
            _validacion(),
            "NOR_TEST",
            catalog,
            propuestas_llm=proposals,
        )
        second = salida.normalizar_registros_curriculares(
            records,
            _validacion(),
            "NOR_TEST",
            catalog,
            propuestas_llm=proposals,
        )
    assert first == second
    assert (records, vars(catalog), proposals) == before
    assert bool(first.pendientes_curriculares) is pending
    assert len(first.cobertura_fuente_lineage) == 2


def output_fingerprints(directory):
    result = {}
    for path in sorted((directory / "salidas").rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            if path.suffix == ".json":
                data = json.dumps(json.loads(data), ensure_ascii=False, sort_keys=True).encode()
            elif path.suffix == ".jsonl":
                data = json.dumps(
                    [json.loads(line) for line in data.splitlines()],
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode()
            result[str(path.relative_to(directory))] = hashlib.sha256(data).hexdigest()
    return result


@pytest.mark.parametrize("pending", [False, True])
def test_public_outputs_match_pre_refactor_bytes_and_json(tmp_path, pending):
    catalog = _catalogo_sin_habilidad() if pending else _catalogo()
    directory = tmp_path / "NOR_TEST"
    result = salida.construir_salidas_curriculares([_registro()], _validacion(), directory, catalog)
    golden = json.loads(
        (Path(__file__).parents[1] / "fixtures" / "normalizador_output_baseline.json").read_text()
    )[str(pending)]
    assert output_fingerprints(directory) == golden["files"]
    assert json.loads(json.dumps(asdict(result))) == golden["result"]
    # Reusing the same execution must remove stale canonical files when it becomes pending.
    salida.construir_salidas_curriculares(
        [_registro()],
        _validacion(),
        directory,
        _catalogo_sin_habilidad(),
    )
    assert not any((directory / "salidas" / name).exists() for name, _ in salida.ARCHIVOS_SALIDA)


def test_disk_validation_reads_materialized_csv_and_blocks_corruption(tmp_path, monkeypatch):
    import io

    original_open = Path.open
    reads = []

    def corrupted_read(path, mode="r", *args, **kwargs):
        if path.name == "curso.csv" and mode == "r":
            # The file must have been written before the disk-based validator runs.
            assert path.is_file()
            reads.append(path)
            return io.StringIO("incorrect_header\ninvalid\n")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", corrupted_read)
    result = salida.construir_salidas_curriculares(
        [_registro()],
        _validacion(),
        tmp_path / "NOR_TEST",
        _catalogo(),
    )
    assert reads
    assert not result.publicable
    assert any(finding.codigo == "CSV_ESQUEMA_INVALIDO" for finding in result.hallazgos)
    assert result.release_gate["decision"] == "BLOCK_IMPORT"


def test_persistence_errors_propagate_instead_of_reporting_success(tmp_path, monkeypatch):
    original_open = Path.open

    def disk_full(path, mode="r", *args, **kwargs):
        if path.name == "curso.csv" and "w" in mode:
            raise OSError("disk full")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", disk_full)
    with pytest.raises(OSError, match="disk full"):
        salida.construir_salidas_curriculares(
            [_registro()],
            _validacion(),
            tmp_path / "NOR_TEST",
            _catalogo(),
        )
