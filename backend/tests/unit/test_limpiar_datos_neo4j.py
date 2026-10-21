from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


def _cargar_script() -> Any:
    ruta = Path(__file__).parents[2] / "scripts" / "limpiar_datos_neo4j.py"
    especificacion = importlib.util.spec_from_file_location("limpiar_datos_neo4j", ruta)
    assert especificacion and especificacion.loader
    modulo = importlib.util.module_from_spec(especificacion)
    sys.modules[especificacion.name] = modulo
    especificacion.loader.exec_module(modulo)
    return modulo


class _Resultado:
    def __init__(self, campo: str, cantidad: int) -> None:
        self._campo = campo
        self._cantidad = cantidad

    def single(self) -> dict[str, int]:
        return {self._campo: self._cantidad}


class _Transaccion:
    def __init__(self, campo: str, cantidades: list[int]) -> None:
        self.campo = campo
        self.cantidades = cantidades
        self.consultas: list[str] = []

    def run(self, cypher: str, **_: object) -> _Resultado:
        self.consultas.append(cypher)
        return _Resultado(self.campo, self.cantidades.pop(0))


class _Sesion:
    def __init__(self, transaccion: _Transaccion) -> None:
        self.transaccion = transaccion

    def execute_write(self, funcion: Any) -> Any:
        return funcion(self.transaccion)


def test_limpieza_elimina_relaciones_y_conserva_carreras() -> None:
    script = _cargar_script()
    transaccion_relaciones = _Transaccion("eliminadas", [3, 0])
    assert script.eliminar_relaciones_por_lotes(_Sesion(transaccion_relaciones), 2) == 3
    assert all("DELETE r" in consulta for consulta in transaccion_relaciones.consultas)

    transaccion_nodos = _Transaccion("eliminados", [5, 0])
    assert script.eliminar_por_lotes(_Sesion(transaccion_nodos), 2) == 5
    assert all("WHERE NOT n:Carrera" in consulta for consulta in transaccion_nodos.consultas)
    assert all("DETACH DELETE n" in consulta for consulta in transaccion_nodos.consultas)
