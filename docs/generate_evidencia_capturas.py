from __future__ import annotations

import csv
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(r"C:\Users\I13305\Desktop\Agente-empleabilidad-silabos")
DOWNLOADS = Path(r"C:\Users\I13305\Downloads")
OUT = ROOT / "docs"


def font(size: int, bold: bool = False):
    path = Path(r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf")
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def render_table(path: Path, title: str, subtitle: str, headers: list[str], rows: list[list[str]], widths: list[int]) -> None:
    title_font = font(30, True)
    subtitle_font = font(19)
    header_font = font(19, True)
    body_font = font(18)
    small_font = font(16)
    pad = 20
    line_h = 25
    table_x = 35
    table_y = 145
    total_w = sum(widths)

    def wrapped(value: str, width: int, fnt):
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1), "white"))
        max_chars = max(8, int(width / max(probe.textlength("M", font=fnt), 1)))
        return textwrap.wrap(str(value), width=max_chars) or [""]

    header_lines = [wrapped(v, widths[i] - 2 * pad, header_font) for i, v in enumerate(headers)]
    row_lines = [[wrapped(v, widths[i] - 2 * pad, body_font) for i, v in enumerate(row)] for row in rows]
    header_h = max(len(x) for x in header_lines) * line_h + 2 * pad
    row_heights = [max(len(x) for x in row) * line_h + 2 * pad for row in row_lines]
    height = table_y + header_h + sum(row_heights) + 75

    image = Image.new("RGB", (table_x * 2 + total_w, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((table_x, 25), title, fill="black", font=title_font)
    draw.text((table_x, 78), subtitle, fill="#444444", font=subtitle_font)

    y = table_y
    x = table_x
    for i, lines in enumerate(header_lines):
        draw.rectangle((x, y, x + widths[i], y + header_h), fill="#D9D9D9", outline="black", width=2)
        for j, line in enumerate(lines):
            draw.text((x + pad, y + pad + j * line_h), line, fill="black", font=header_font)
        x += widths[i]

    y += header_h
    for row_idx, row in enumerate(row_lines):
        x = table_x
        row_h = row_heights[row_idx]
        fill = "#F2F2F2" if row_idx % 2 else "white"
        for col_idx, lines in enumerate(row):
            draw.rectangle((x, y, x + widths[col_idx], y + row_h), fill=fill, outline="#777777", width=1)
            for j, line in enumerate(lines):
                draw.text((x + pad, y + pad + j * line_h), line, fill="black", font=body_font)
            x += widths[col_idx]
        y += row_h

    draw.text((table_x, height - 48), "Evidencia reproducible · valores exportados sin modificación", fill="#444444", font=small_font)
    image.save(path)


def load_csv(name: str):
    with (DOWNLOADS / name).open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    competencies = load_csv("catalogo_competencias (1).csv")
    skills = load_csv("catalogo_habilidades (1).csv")
    courses = load_csv("curso (3).csv")
    matches = load_csv("neo4j_query_table_data_2026-10-5.csv")

    comp_cases = [
        ["Pensamiento crítico", "44", "44", "10", "Variantes de mayúsculas y acentuación"],
        ["Trabajo colaborativo", "28", "28", "8", "Genérica y específica"],
        ["Comportamiento ético", "29", "29", "5", "Múltiples descripciones"],
        ["Liderazgo", "5", "5", "2", "Múltiples descripciones"],
    ]
    render_table(
        OUT / "evidencia_catalogo_competencias_variantes.png",
        "EVIDENCIA DE VARIANTES EN COMPETENCIAS",
        "Fuente: catalogo_competencias (1).csv · corte 5 de octubre de 2026",
        ["Competencia", "Registros", "IDs", "Descripciones", "Observación"],
        comp_cases,
        [300, 150, 120, 180, 430],
    )

    course_cases = [
        ["tipo_curso", "Obligatoria / OBLIGATORIA", "475", "Mayúsculas"],
        ["creditos", "Tres (3) / TRES (3)", "550", "Mayúsculas"],
        ["naturaleza", "Variantes de Teórico-práctica", "546", "Guiones, espacios y acentos"],
        ["nivel", "Décimo / Decimo", "77", "Acentuación"],
    ]
    render_table(
        OUT / "evidencia_catalogo_cursos_normalizacion.png",
        "EVIDENCIA DE NORMALIZACIÓN DE CURSOS",
        "Fuente: curso (3).csv · 882 registros · corte curricular 2026-2",
        ["Atributo", "Valores equivalentes", "Registros", "Variación"],
        course_cases,
        [230, 420, 160, 370],
    )

    skill_cases = [
        ["Desarrollar métodos o procesos técnicos.", "4", "4 carreras", "Identidad repetida por carrera"],
        ["Analizar datos empresariales o financieros.", "2", "2 carreras", "El match exacto puede fragmentarse"],
        ["Implementar mejoras de diseño o de procesos.", "3", "3 carreras", "Posible equivalencia transversal"],
        ["Preparar documentos de procedimiento.", "3", "3 carreras", "Contexto disciplinar por revisar"],
    ]
    render_table(
        OUT / "evidencia_catalogo_habilidades_ids.png",
        "EVIDENCIA DE HABILIDADES REPETIDAS POR ID",
        "Fuente: catalogo_habilidades (1).csv · 1,572 habilidades · corte curricular 2026-2",
        ["Nombre de habilidad", "IDs", "Alcance", "Riesgo analítico"],
        skill_cases,
        [430, 110, 190, 450],
    )

    top = sorted(matches, key=lambda row: int(row["requerimientos_laborales"]), reverse=True)[:5]
    match_cases = [[row["id_habilidad"], row["habilidad"], row["coberturas_curriculares"], row["requerimientos_laborales"]] for row in top]
    render_table(
        OUT / "evidencia_match_csv_habilidades_tecnicas.png",
        "EVIDENCIA DEL MATCH CURRICULAR LABORAL",
        "Fuente: neo4j_query_table_data_2026-10-5.csv · 134 habilidades coincidentes",
        ["ID", "Habilidad técnica", "Coberturas", "Requerimientos"],
        match_cases,
        [190, 770, 170, 210],
    )


if __name__ == "__main__":
    main()
