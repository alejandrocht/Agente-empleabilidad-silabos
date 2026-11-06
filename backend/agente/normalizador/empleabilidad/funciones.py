"""Retira cláusulas laborales vacías sin inferir funciones a partir del cargo."""

from __future__ import annotations

import re
import unicodedata

_SEPARADOR = re.compile(r"[\n\r;•●▪]+|(?<=[.!?])\s+|\s+(?=\(\d+\))")
_ENUMERACION = re.compile(r"^\s*(?:[-–—*]+|\(?\d+\)?[.):-])\s*")
_GENERICA = re.compile(
    r"(?:las?\s+)?(?:(?:funcion(?:es)?|labor(?:es)?|tareas?|actividad(?:es)?|"
    r"responsabilidad(?:es)?)[\s:]+)?"
    r"inherentes?\s+(?:al|a\s+su|a\s+la|a\s+las)\s+"
    r"(?:puesto|puetso|cargo|posicion|funcion|funciones|ambito\s+de\s+su\s+competencia)"
    r"(?:\s+.*)?$"
    r"|(?:realizar|cumplir|ejecutar|desempenar|apoyar\s+en)?\s*"
    r"(?:con\s+)?(?:las\s+)?otras?\s+(?:funcion(?:es)?|labor(?:es)?|tareas?|"
    r"actividad(?:es)?|responsabilidad(?:es)?)"
    r"(?:\s+(?:inherentes?|propias?|asignadas?|que\s+(?:le\s+)?(?:sean|asigne|encomiende)|"
    r"segun|indicadas?|solicitadas?|afines|relacionadas?)(?:\s+.*)?)?$"
)


def _clave(texto: str) -> str:
    valor = unicodedata.normalize("NFKD", texto.casefold())
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", valor).strip(" \t.,:!?-–—")


def funciones_concretas(valor: object) -> str:
    """Devuelve contenido funcional conservado; vacío significa sin evidencia.

    Solo elimina segmentos que coinciden enteramente con fórmulas genéricas.
    Una función como «analizar los riesgos inherentes al proyecto» se conserva.
    El original permanece en staging/cuarentena para su auditoría.
    """
    texto = str(valor or "").strip()
    conservadas = []
    for fragmento in _SEPARADOR.split(texto):
        limpio = _ENUMERACION.sub("", fragmento).strip()
        clave = _clave(limpio)
        if not clave or not re.search(r"[a-z0-9]", clave):
            continue
        if _GENERICA.fullmatch(clave) and not re.search(
            r"\b(?:incluyendo|incluye|tales como|por ejemplo|consistente en)\b", clave
        ):
            continue
        conservadas.append(re.sub(r"\s+", " ", limpio))
    return " ".join(conservadas)
