"""Regression tests for the single deterministic identity implementation.

The golden identifiers below were taken from generated catalogs under
Desktop/CATALOGOS, so they lock the contract against real data rather than
against a previous version of this code.
"""

from __future__ import annotations

import pytest

from agente.normalizador.identidad import DIGEST_LENGTH, hashed, normalize


class TestNormalizeFoldsForComparison:
    def test_strips_accents_case_and_surrounding_space(self) -> None:
        assert normalize("  Análisis   de Datos  ") == "analisis de datos"

    def test_folds_every_accented_variant_to_one_key(self) -> None:
        keys = {normalize(value) for value in ("MS Excel", "ms  excel", "MS Éxcel", "MS EXCEL")}
        assert keys == {"ms excel"}

    def test_dashes_and_newlines_become_single_spaces(self) -> None:
        assert normalize("Diseño—curricular") == "diseno curricular"
        assert normalize("Línea\ndividida") == "linea dividida"
        assert normalize("uno\tdos") == "uno dos"

    def test_punctuation_is_dropped_but_spacing_stays_separated(self) -> None:
        assert normalize("Programación, orientada; a objetos!") == (
            "programacion orientada a objetos"
        )

    def test_tool_significant_characters_survive(self) -> None:
        assert normalize("C++") == "c++"
        assert normalize("C#") == "c#"
        assert normalize("ASP.NET") == "asp.net"

    def test_tool_significant_characters_stay_distinct(self) -> None:
        assert normalize("C++") != normalize("C#")
        assert normalize("C") != normalize("C++")

    def test_empty_and_falsy_values_fold_to_the_empty_string(self) -> None:
        assert normalize("") == ""
        assert normalize("   ") == ""
        assert normalize(None) == ""

    def test_normalization_is_idempotent(self) -> None:
        once = normalize("  Análisis   de Datos—v2  ")
        assert normalize(once) == once


class TestHashedIsDeterministic:
    def test_same_parts_always_produce_the_same_identifier(self) -> None:
        assert hashed("COMP", "generica", "G2") == hashed("COMP", "generica", "G2")

    def test_unaccented_and_acc_ented_spellings_agree(self) -> None:
        assert hashed("LOGRO", "Diseño curricular") == hashed("LOGRO", "diseno  CURRICULAR")

    def test_digest_is_sixteen_lowercase_hex_characters(self) -> None:
        _, _, digest = hashed("CUR", "510007").partition("_")
        assert len(digest) == DIGEST_LENGTH
        assert digest == digest.lower()
        assert all(character in "0123456789abcdef" for character in digest)

    def test_part_order_changes_the_identifier(self) -> None:
        assert hashed("COB_CUR", "a", "b") != hashed("COB_CUR", "b", "a")

    def test_prefix_labels_the_identifier_without_joining_the_digest(self) -> None:
        # A course and its syllabus share one code, so they share one digest
        # and differ only by prefix.
        curso = hashed("CUR", "510007")
        silabo = hashed("SIL", "510007")
        assert curso.split("_", 1)[1] == silabo.split("_", 1)[1]

    def test_a_different_prefix_alone_does_not_change_the_digest(self) -> None:
        assert hashed("A", "x").split("_", 1)[1] == hashed("B", "x").split("_", 1)[1]

    def test_changing_any_single_part_changes_the_identifier(self) -> None:
        base = hashed("COMP", "tecnica", "Ingeniería de software")
        assert hashed("COMP", "tecnica", "Ingeniería industrial") != base
        assert hashed("COMP", "generica", "Ingeniería de software") != base

    def test_no_parts_still_produces_a_stable_identifier(self) -> None:
        assert hashed("X") == hashed("X")
        assert hashed("X") == "X_" + hashed("Y").split("_", 1)[1]


class TestGoldenIdentifiersFromGeneratedCatalogs:
    """Locks the contract against real catalog rows, not against this code."""

    @pytest.mark.parametrize(
        ("parts", "expected"),
        [
            (("CUR", "510007"), "CUR_8859b55d5be6aa91"),
            (("SIL", "510007"), "SIL_8859b55d5be6aa91"),
            (("CUR", "510005"), "CUR_34903c6b28f2332c"),
            (
                ("COMP", "generica", "G2", "Solución de problemas"),
                "COMP_a8d9977c133ff943",
            ),
            (
                (
                    "LOGRO",
                    "Analizar principios y valores éticos esenciales para la "
                    "convivencia en sociedades contemporáneas",
                ),
                "LOGRO_352e43baa73298e4",
            ),
        ],
    )
    def test_matches_the_generated_catalog(self, parts: tuple[str, ...], expected: str) -> None:
        assert hashed(*parts) == expected

    def test_coverage_identifier_matches_the_generated_catalog(self) -> None:
        assert (
            hashed(
                "COB_CUR",
                "CUR_8859b55d5be6aa91",
                "SIL_8859b55d5be6aa91",
                "COMP_a8d9977c133ff943",
                "",
                "",
            )
            == "COB_CUR_dc2c55befe069ac8"
        )


class TestDuplicateCourseCodes:
    """Duplicate codes are disambiguated by the caller adding the name."""

    def test_first_occurrence_hashes_on_the_code_alone(self) -> None:
        assert hashed("CUR", "510007") == "CUR_8859b55d5be6aa91"

    def test_later_occurrence_hashes_on_code_and_name(self) -> None:
        plain = hashed("CUR", "510007")
        disambiguated = hashed("CUR", "510007", "Cálculo II")
        assert disambiguated != plain
        assert disambiguated.startswith("CUR_")

    def test_disambiguation_is_stable_regardless_of_visit_order(self) -> None:
        first = hashed("CUR", "510007", "Cálculo II")
        later = hashed("CUR", "510007", "Cálculo II")
        assert first == later
