"""Catálogo de veinte consultas frecuentes alineadas con el schema Neo4j vivo de CIAR."""

from __future__ import annotations

from typing import TypedDict


class Plantilla(TypedDict):
    """Describe el reconocimiento, Cypher y parámetros necesarios de una intención."""

    id: str
    descripcion: str
    patrones: list[str]
    cypher: str
    params: dict[str, str]
    prioridad: int


# Las consultas académicas usan los nombres exactos ``nombre_carrera`` y ``nombre_curso``.
PLANTILLAS: list[Plantilla] = [
    {
        "id": "contar_carreras",
        "descripcion": "Total de carreras registradas",
        "patrones": ["cuantas carreras", "total de carreras", "numero de carreras"],
        "cypher": "MATCH (c:Carrera) RETURN count(c) AS total",
        "params": {},
        "prioridad": 20,
    },
    {
        "id": "listar_carreras",
        "descripcion": "Lista de carreras registradas",
        "patrones": ["que carreras hay", "listar carreras", "lista de carreras"],
        "cypher": (
            "MATCH (c:Carrera) RETURN c.nombre_carrera AS carrera ORDER BY carrera LIMIT 25"
        ),
        "params": {},
        "prioridad": 20,
    },
    {
        "id": "cursos_de_carrera",
        "descripcion": "Cursos asociados a una carrera",
        "patrones": ["cursos de", "cursos tiene", "que cursos"],
        "cypher": (
            "MATCH (c:Carrera {id_carrera: '{id_carrera}'})-[:ENSENIA]-(cu:Curso) "
            "RETURN DISTINCT cu.nombre_curso AS curso ORDER BY curso LIMIT 25"
        ),
        "params": {"id_carrera": "entidad.Carrera.id"},
        "prioridad": 30,
    },
    {
        "id": "contar_cursos_de_carrera",
        "descripcion": "Cantidad de cursos asociados a una carrera",
        "patrones": ["cuantos cursos", "total de cursos"],
        "cypher": (
            "MATCH (c:Carrera {id_carrera: '{id_carrera}'})-[:ENSENIA]-(cu:Curso) "
            "RETURN count(DISTINCT cu) AS total"
        ),
        "params": {"id_carrera": "entidad.Carrera.id"},
        "prioridad": 40,
    },
    {
        "id": "facultad_de_carrera",
        "descripcion": "Facultad que ofrece una carrera",
        "patrones": [
            "facultad pertenece",
            "a que facultad pertenece",
            "que facultad ofrece la carrera",
        ],
        "cypher": (
            "MATCH (f:Facultad)-[:OFRECE]-(c:Carrera {id_carrera: '{id_carrera}'}) "
            "RETURN DISTINCT f.nombre_facultad AS facultad LIMIT 25"
        ),
        "params": {"id_carrera": "entidad.Carrera.id"},
        "prioridad": 35,
    },
    # Las consultas laborales recorren Empresa-PUBLICA-Oferta_Laboral con nombres del schema.
    {
        "id": "top_empresas_ofertas",
        "descripcion": "Empresas con más ofertas laborales",
        "patrones": ["top empresas", "empresas con mas ofertas", "empresas publican mas"],
        "cypher": (
            "MATCH (e:Empresa)-[:PUBLICA]-(o:Oferta_Laboral) "
            "RETURN e.nombre AS empresa, count(DISTINCT o) AS ofertas "
            "ORDER BY ofertas DESC LIMIT 25"
        ),
        "params": {},
        "prioridad": 30,
    },
    {
        "id": "ofertas_de_empresa",
        "descripcion": "Cantidad de ofertas publicadas por una empresa",
        "patrones": [
            "ofertas publico",
            "ofertas laborales publico",
            "ofertas de la empresa",
        ],
        "cypher": (
            "MATCH (e:Empresa {id_empresa: '{id_empresa}'})-[:PUBLICA]-(o:Oferta_Laboral) "
            "RETURN count(DISTINCT o) AS ofertas"
        ),
        "params": {"id_empresa": "entidad.Empresa.id"},
        "prioridad": 40,
    },
    {
        "id": "puestos_de_empresa",
        "descripcion": "Puestos publicados por una empresa",
        "patrones": ["puestos ofrece", "puestos de", "cargos de la empresa"],
        "cypher": (
            "MATCH (e:Empresa {id_empresa: '{id_empresa}'})-[:PUBLICA]-(o:Oferta_Laboral)"
            "-[:OFRECE]-(p:Puesto) WHERE p.nombre IS NOT NULL "
            "RETURN DISTINCT p.nombre AS puesto "
            "ORDER BY puesto LIMIT 25"
        ),
        "params": {"id_empresa": "entidad.Empresa.id"},
        "prioridad": 35,
    },
    {
        "id": "listar_empresas",
        "descripcion": "Lista de empresas registradas",
        "patrones": ["que empresas hay", "listar empresas", "lista de empresas"],
        "cypher": "MATCH (e:Empresa) RETURN e.nombre AS empresa ORDER BY empresa LIMIT 25",
        "params": {},
        "prioridad": 20,
    },
    # Competencias, habilidades y herramientas se conectan mediante requerimientos laborales.
    {
        "id": "competencias_demandadas_carrera",
        "descripcion": "Competencias pedidas en ofertas dirigidas a una carrera",
        "patrones": ["competencias para", "competencias demandadas", "competencias de"],
        "cypher": (
            "MATCH (c:Carrera {id_carrera: '{id_carrera}'})-[:DIRIGE_A]-(o:Oferta_Laboral)"
            "-[:TIENE]-(r:Requerimiento_Laboral)-[:REQUIERE]-(co:Competencia) "
            "RETURN co.nombre_competencia AS competencia, count(DISTINCT o) AS ofertas "
            "ORDER BY ofertas DESC LIMIT 25"
        ),
        "params": {"id_carrera": "entidad.Carrera.id"},
        "prioridad": 35,
    },
    {
        "id": "top_competencias_ofertas",
        "descripcion": "Competencias más demandadas por las ofertas",
        "patrones": ["competencias mas demandadas", "top competencias", "competencias requeridas"],
        "cypher": (
            "MATCH (o:Oferta_Laboral)-[:TIENE]-(r:Requerimiento_Laboral)"
            "-[:REQUIERE]-(c:Competencia) "
            "RETURN c.nombre_competencia AS competencia, count(DISTINCT o) AS ofertas "
            "ORDER BY ofertas DESC LIMIT 25"
        ),
        "params": {},
        "prioridad": 45,
    },
    {
        "id": "habilidades_para_puesto",
        "descripcion": "Habilidades requeridas para un puesto",
        "patrones": ["habilidades para", "habilidades de un puesto", "habilidades del puesto"],
        "cypher": (
            "MATCH (p:Puesto {id_puesto: '{id_puesto}'})-[:DEFIINE]-(r:Requerimiento_Laboral)"
            "-[:REQUIERE]-(h:Habilidad) RETURN DISTINCT h.nombre_habilidad AS habilidad "
            "ORDER BY habilidad LIMIT 25"
        ),
        "params": {"id_puesto": "entidad.Puesto.id"},
        "prioridad": 35,
    },
    {
        "id": "herramientas_mas_requeridas",
        "descripcion": "Herramientas más requeridas en ofertas",
        "patrones": ["herramientas mas requeridas", "top herramientas", "herramientas demandadas"],
        "cypher": (
            "MATCH (o:Oferta_Laboral)-[:TIENE]-(r:Requerimiento_Laboral)"
            "-[:REQUIERE]-(h:Herramienta) "
            "RETURN h.nombre_herramienta AS herramienta, count(DISTINCT o) AS ofertas "
            "ORDER BY ofertas DESC LIMIT 25"
        ),
        "params": {},
        "prioridad": 45,
    },
    {
        "id": "herramientas_de_carrera",
        "descripcion": "Herramientas enseñadas por una carrera",
        "patrones": [
            "herramientas ensena",
            "herramientas se ensenan",
            "herramientas de la carrera",
        ],
        "cypher": (
            "MATCH (c:Carrera {id_carrera: '{id_carrera}'})-[:ENSENIA]-(cu:Curso)"
            "-[:TIENE]-(cc:Cobertura_Curricular)-[:ENSENIA]-(h:Herramienta) "
            "RETURN DISTINCT h.nombre_herramienta AS herramienta ORDER BY herramienta LIMIT 25"
        ),
        "params": {"id_carrera": "entidad.Carrera.id"},
        "prioridad": 35,
    },
    {
        "id": "puestos_mas_demandados",
        "descripcion": "Puestos presentes en más ofertas",
        "patrones": ["puestos mas demandados", "top puestos", "puestos con mas ofertas"],
        "cypher": (
            "MATCH (o:Oferta_Laboral)-[:OFRECE]-(p:Puesto) "
            "WHERE p.nombre IS NOT NULL "
            "RETURN p.nombre AS puesto, count(DISTINCT o) AS ofertas "
            "ORDER BY ofertas DESC LIMIT 25"
        ),
        "params": {},
        "prioridad": 40,
    },
    # Industria, sílabos y cobertura curricular completan las consultas frecuentes.
    {
        "id": "industrias_con_mas_ofertas",
        "descripcion": "Industrias agrupadas por cantidad de ofertas",
        "patrones": ["industrias con mas ofertas", "top industrias", "sectores con mas ofertas"],
        "cypher": (
            "MATCH (i:Industria)-[:AGRUPA]-(e:Empresa)-[:PUBLICA]-(o:Oferta_Laboral) "
            "RETURN i.nombre AS industria, count(DISTINCT o) AS ofertas "
            "ORDER BY ofertas DESC LIMIT 25"
        ),
        "params": {},
        "prioridad": 40,
    },
    {
        "id": "empresas_de_industria",
        "descripcion": "Empresas agrupadas en una industria",
        "patrones": ["empresas del sector", "empresas de la industria", "empresas de"],
        "cypher": (
            "MATCH (i:Industria {id_industria: '{id_industria}'})-[:AGRUPA]-(e:Empresa) "
            "RETURN DISTINCT e.nombre AS empresa ORDER BY empresa LIMIT 25"
        ),
        "params": {"id_industria": "entidad.Industria.id"},
        "prioridad": 35,
    },
    {
        "id": "silabo_de_curso",
        "descripcion": "Sílabo asociado a un curso",
        "patrones": ["silabo de", "silabo del curso", "sumilla de"],
        "cypher": (
            "MATCH (c:Curso {id_curso: '{id_curso}'})-[:TIENE]-(s:Silabo) "
            "RETURN s.codigo_silabo AS codigo, s.sumilla AS sumilla LIMIT 25"
        ),
        "params": {"id_curso": "entidad.Curso.id"},
        "prioridad": 35,
    },
    {
        "id": "carreras_que_tienen_curso",
        "descripcion": "Carreras que enseñan un curso",
        "patrones": ["carreras tienen", "carreras que tienen", "carreras ensenan"],
        "cypher": (
            "MATCH (c:Carrera)-[:ENSENIA]-(cu:Curso {id_curso: '{id_curso}'}) "
            "RETURN DISTINCT c.nombre_carrera AS carrera ORDER BY carrera LIMIT 25"
        ),
        "params": {"id_curso": "entidad.Curso.id"},
        "prioridad": 35,
    },
    {
        "id": "cursos_para_competencia",
        "descripcion": "Cursos cuya cobertura desarrolla una competencia",
        "patrones": ["cursos que desarrollan", "cursos para", "cursos de competencia"],
        "cypher": (
            "MATCH (cu:Curso)-[:TIENE]-(cc:Cobertura_Curricular)-[:CUBRE]-"
            "(co:Competencia {id_competencia: '{id_competencia}'}) "
            "RETURN DISTINCT cu.nombre_curso AS curso ORDER BY curso LIMIT 25"
        ),
        "params": {"id_competencia": "entidad.Competencia.id"},
        "prioridad": 35,
    },
]
