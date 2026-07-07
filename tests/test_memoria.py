import unittest

from utils.memoria import (
    MAX_TURNOS_RECIENTES,
    actualizar_memoria,
    formatear_memoria,
    limpiar_memoria,
    obtener_memoria,
)
from nodos.devuelve_resultado import DevuelveResultado
from nodos.obtiene_pregunta import ObtienePregunta


class MemoriaSesionTest(unittest.TestCase):
    def setUp(self) -> None:
        limpiar_memoria("test-session")

    def tearDown(self) -> None:
        limpiar_memoria("test-session")

    def test_limita_ventana_y_resume_turnos_antiguos(self) -> None:
        for indice in range(MAX_TURNOS_RECIENTES + 2):
            actualizar_memoria(
                "test-session",
                {
                    "pregunta": f"Pregunta {indice}",
                    "respuesta": f"Respuesta {indice}",
                },
            )

        memoria = obtener_memoria("test-session")

        self.assertEqual(MAX_TURNOS_RECIENTES, len(memoria["turnos_recientes"]))
        self.assertGreaterEqual(len(memoria["resumen"]), 1)
        self.assertEqual("Pregunta 2", memoria["turnos_recientes"][0]["pregunta"])

        texto = formatear_memoria(memoria)
        self.assertIn("Resumen compacto", texto)
        self.assertIn("Ultimos turnos completos", texto)
        self.assertIn("Pregunta 5", texto)

    def test_deduplica_entidades_recientes_por_label_e_id(self) -> None:
        actualizar_memoria(
            "test-session",
            {
                "pregunta": "Cursos de sistemas",
                "respuesta": "Tiene varios cursos.",
                "entidades": [
                    {
                        "texto": "sistemas",
                        "label": "Carrera",
                        "nombre": "INGENIERIA DE SISTEMAS",
                        "id": "CAR_1",
                    }
                ],
            },
        )
        actualizar_memoria(
            "test-session",
            {
                "pregunta": "Habilidades de esa carrera",
                "respuesta": "Incluye analisis y programacion.",
                "entidades": [
                    {
                        "texto": "esa carrera",
                        "label": "Carrera",
                        "nombre": "INGENIERIA DE SISTEMAS",
                        "id": "CAR_1",
                    }
                ],
            },
        )

        memoria = obtener_memoria("test-session")

        self.assertEqual(1, len(memoria["entidades_recientes"]))
        self.assertEqual("Habilidades de esa carrera", memoria["entidades_recientes"][0]["origen_pregunta"])

    def test_nodos_guardan_y_cargan_memoria_de_sesion(self) -> None:
        cierre = DevuelveResultado()
        cambios_cierre = cierre(
            {
                "id_sesion": "test-session",
                "pregunta": "Que cursos tiene sistemas",
                "respuesta": "La carrera tiene cursos de programacion.",
                "cypher": "MATCH (c:Carrera)-[:CONTIENE]-(cu:Curso) RETURN cu.nombre",
                "schema_texto": "schema grande",
                "filas": [{"nombre": "Programacion"}],
                "entidades": [
                    {
                        "texto": "sistemas",
                        "label": "Carrera",
                        "nombre": "INGENIERIA DE SISTEMAS",
                        "id": "CAR_1",
                    }
                ],
            }
        )

        inicio = ObtienePregunta()
        cambios = inicio({"id_sesion": "test-session", "pregunta": "Y cuantas habilidades tiene esa carrera?"})

        self.assertIsNone(cambios_cierre["schema_texto"])
        self.assertEqual([], cambios_cierre["filas"])
        self.assertEqual([], cambios_cierre["entidades"])
        self.assertIn("INGENIERIA DE SISTEMAS", cambios["memoria_texto"])
        self.assertIn("Que cursos tiene sistemas", cambios["memoria_texto"])


if __name__ == "__main__":
    unittest.main()
