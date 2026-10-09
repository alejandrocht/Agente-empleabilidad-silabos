# Consultas de competencias y sílabos

Consultas Cypher de solo lectura para analizar competencias genéricas y específicas
en la currícula universitaria.

## Relación vigente en Neo4j

La ruta curricular comprobada en el grafo es:

```text
Carrera -[:ENSENIA]-> Curso -[:TIENE]-> Silabo
Silabo -[:DECLARA]-> Cobertura_Curricular -[:CUBRE]-> Competencia
```

No se debe invertir la dirección de `CUBRE` al consultar competencias.

## 1. Carreras que tienen una competencia

Ejemplo: competencias genéricas relacionadas con “Pensamiento crítico”.

```cypher
MATCH (c:Carrera)-[:ENSENIA]->(cu:Curso)-[:TIENE]->(s:Silabo)
      -[:DECLARA]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia)
WHERE co.tipo_competencia = $tipo
  AND toLower(co.nombre_competencia) CONTAINS toLower($competencia)
RETURN c.nombre_carrera AS carrera,
       co.codigo_competencia AS codigo,
       co.nombre_competencia AS competencia,
       count(DISTINCT cu) AS cursos,
       count(DISTINCT s) AS silabos,
       count(DISTINCT cc) AS coberturas
ORDER BY carrera, codigo
LIMIT 100;
```

Parámetros:

En Neo4j Browser, el bloque JSON no se ejecuta como una consulta. Primero ejecuta
estas dos líneas, una por una, en el editor:

```cypher
:param tipo => 'generica'
```

```cypher
:param competencia => 'Pensamiento crítico'
```

Después ejecuta la consulta Cypher anterior, que usa `$tipo` y `$competencia`.

También puedes probarla sin parámetros usando valores literales:

```cypher
MATCH (c:Carrera)-[:ENSENIA]->(cu:Curso)-[:TIENE]->(s:Silabo)
      -[:DECLARA]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia)
WHERE co.tipo_competencia = 'generica'
  AND toLower(co.nombre_competencia) CONTAINS toLower('Pensamiento crítico')
RETURN c.nombre_carrera AS carrera,
       co.codigo_competencia AS codigo,
       co.nombre_competencia AS competencia,
       count(DISTINCT cu) AS cursos,
       count(DISTINCT s) AS silabos,
       count(DISTINCT cc) AS coberturas
ORDER BY carrera, codigo
LIMIT 100;
```

Si ejecutas las consultas desde Python mediante el gateway del backend, los
parámetros sí se envían como un diccionario:

```python
parametros = {
    "tipo": "generica",
    "competencia": "Pensamiento crítico",
}
filas = await gateway.run(consulta, parametros)
```

## 2. Cursos y sílabos que trabajan una competencia

```cypher
MATCH (c:Carrera)-[:ENSENIA]->(cu:Curso)-[:TIENE]->(s:Silabo)
      -[:DECLARA]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia)
WHERE co.tipo_competencia = $tipo
  AND toLower(co.nombre_competencia) CONTAINS toLower($competencia)
RETURN c.nombre_carrera AS carrera,
       cu.codigo_curso AS codigo_curso,
       cu.nombre_curso AS curso,
       s.codigo_silabo AS silabo,
       s.periodo_academico AS periodo,
       co.codigo_competencia AS codigo_competencia,
       co.nombre_competencia AS competencia,
       count(DISTINCT cc) AS coberturas
ORDER BY carrera, curso, silabo
LIMIT 100;
```

## 3. Competencias genéricas por carrera

```cypher
MATCH (c:Carrera)-[:ENSENIA]->(:Curso)-[:TIENE]->(s:Silabo)
      -[:DECLARA]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia)
WHERE co.tipo_competencia = 'generica'
RETURN c.nombre_carrera AS carrera,
       co.nombre_competencia AS competencia,
       co.codigo_competencia AS codigo,
       count(DISTINCT s) AS silabos,
       count(DISTINCT cc) AS coberturas
ORDER BY carrera, competencia
LIMIT 100;
```

## 4. Competencias específicas por carrera

```cypher
MATCH (c:Carrera)-[:ENSENIA]->(:Curso)-[:TIENE]->(s:Silabo)
      -[:DECLARA]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia)
WHERE co.tipo_competencia = 'especifica'
RETURN c.nombre_carrera AS carrera,
       co.nombre_competencia AS competencia,
       co.codigo_competencia AS codigo,
       count(DISTINCT s) AS silabos,
       count(DISTINCT cc) AS coberturas
ORDER BY carrera, competencia
LIMIT 100;
```

## 5. Detalle de cada sílabo y sus competencias

```cypher
MATCH (c:Carrera)-[:ENSENIA]->(cu:Curso)-[:TIENE]->(s:Silabo)
OPTIONAL MATCH (s)-[:DECLARA]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia)
RETURN c.nombre_carrera AS carrera,
       cu.codigo_curso AS codigo_curso,
       cu.nombre_curso AS curso,
       s.codigo_silabo AS codigo_silabo,
       s.periodo_academico AS periodo,
       count(DISTINCT co) AS competencias_total,
       count(DISTINCT CASE
           WHEN co.tipo_competencia = 'generica' THEN co
       END) AS genericas,
       count(DISTINCT CASE
           WHEN co.tipo_competencia = 'especifica' THEN co
       END) AS especificas,
       count(DISTINCT cc) AS coberturas
ORDER BY carrera, curso
LIMIT 100;
```

## 6. Sílabos con competencias genéricas

```cypher
MATCH (c:Carrera)-[:ENSENIA]->(cu:Curso)-[:TIENE]->(s:Silabo)
      -[:DECLARA]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia)
WHERE co.tipo_competencia = 'generica'
RETURN c.nombre_carrera AS carrera,
       cu.codigo_curso AS codigo_curso,
       cu.nombre_curso AS curso,
       s.codigo_silabo AS silabo,
       count(DISTINCT co) AS competencias_genericas,
       count(DISTINCT cc) AS coberturas
ORDER BY competencias_genericas DESC, curso
LIMIT 100;
```

## 7. Sílabos con competencias específicas

```cypher
MATCH (c:Carrera)-[:ENSENIA]->(cu:Curso)-[:TIENE]->(s:Silabo)
      -[:DECLARA]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia)
WHERE co.tipo_competencia = 'especifica'
RETURN c.nombre_carrera AS carrera,
       cu.codigo_curso AS codigo_curso,
       cu.nombre_curso AS curso,
       s.codigo_silabo AS silabo,
       count(DISTINCT co) AS competencias_especificas,
       count(DISTINCT cc) AS coberturas
ORDER BY competencias_especificas DESC, curso
LIMIT 100;
```

## 8. Resumen de competencias por carrera y tipo

```cypher
MATCH (c:Carrera)-[:ENSENIA]->(cu:Curso)-[:TIENE]->(s:Silabo)
      -[:DECLARA]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia)
RETURN c.nombre_carrera AS carrera,
       co.tipo_competencia AS tipo,
       count(DISTINCT co) AS competencias,
       count(DISTINCT cu) AS cursos,
       count(DISTINCT s) AS silabos,
       count(DISTINCT cc) AS coberturas
ORDER BY carrera, tipo
LIMIT 100;
```

## 9. Competencias más recurrentes en los sílabos

```cypher
MATCH (s:Silabo)-[:DECLARA]->(cc:Cobertura_Curricular)
      -[:CUBRE]->(co:Competencia)
RETURN co.codigo_competencia AS codigo,
       co.nombre_competencia AS competencia,
       co.tipo_competencia AS tipo,
       count(DISTINCT s) AS silabos,
       count(DISTINCT cc) AS coberturas
ORDER BY silabos DESC, coberturas DESC, competencia
LIMIT 20;
```

## 10. Sílabos sin competencias asociadas

```cypher
MATCH (cu:Curso)-[:TIENE]->(s:Silabo)
OPTIONAL MATCH (s)-[:DECLARA]->(:Cobertura_Curricular)-[:CUBRE]->(co:Competencia)
WITH cu, s, count(DISTINCT co) AS competencias
WHERE competencias = 0
RETURN cu.codigo_curso AS codigo_curso,
       cu.nombre_curso AS curso,
       s.codigo_silabo AS silabo,
       s.periodo_academico AS periodo
ORDER BY curso
LIMIT 100;
```

## Verificación contra Neo4j

Las consultas fueron ejecutadas con el gateway de lectura del backend, que aplica
validación, `EXPLAIN` y routing `READ`.

## Ejecución desde Python

El script genera la consulta, imprime la pregunta conversacional que resuelve,
muestra los parámetros y ejecuta las consultas contra Neo4j:

```powershell
cd backend
python scripts/consultas_competencias.py --codigo G6 --tipo generica
```

Para generar las consultas sin conectarse a Neo4j:

```powershell
cd backend
python scripts/consultas_competencias.py --codigo G6 --tipo generica --solo-generar
```

El script está en
[`backend/scripts/consultas_competencias.py`](../backend/scripts/consultas_competencias.py).

También acepta un filtro opcional por nombre:

```powershell
cd backend
python scripts/consultas_competencias.py --codigo G7 --tipo generica --competencia "Pensamiento crítico"
```

Resultados observados:

- El catálogo contiene 27 registros genéricos y 13 específicos.
- Hay 17 registros genéricos y 9 específicos conectados a coberturas curriculares.
- Se encontraron 74 sílabos.
- 55 sílabos tienen competencias genéricas.
- 36 sílabos tienen competencias específicas.
- “Pensamiento crítico” aparece en Ingeniería de Sistemas, con los registros `G7`
  y `C7`, en 8 sílabos y 29 coberturas.
- `G6` aparece en 7 cursos y 7 sílabos de Ingeniería de Sistemas, pero está
  asociado tanto a “Autogestión del aprendizaje” como a “Monitoreo del aprendizaje”.
- El sílabo `650069`, “Proyecto Integrador de Sistemas”, no tiene una competencia
  asociada.

## Observaciones de calidad de datos

Los códigos y nombres de competencias no son completamente únicos. Por ejemplo,
“Pensamiento crítico” aparece con códigos `G7` y `C7`, y algunos nombres se repiten
con diferencias de mayúsculas o códigos. Para reportes institucionales definitivos
conviene normalizar primero el catálogo de competencias.
