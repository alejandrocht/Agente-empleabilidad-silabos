-- 1. Resumen de competencias genéricas y específicas
MATCH (co:Competencia)
RETURN co.tipo_competencia AS tipo,
       count(co) AS registros,
       count(DISTINCT co.nombre_competencia) AS nombres_unicos
ORDER BY tipo
LIMIT 20;

-- 2. Competencias genéricas usadas en la currícula
MATCH (c:Carrera)-[:ENSENIA]->(cu:Curso)-[:TIENE]->(s:Silabo)
      -[:DECLARA]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia)
WHERE co.tipo_competencia = 'generica'
RETURN co.codigo_competencia AS codigo,
       co.nombre_competencia AS competencia,
       count(DISTINCT c) AS carreras,
       count(DISTINCT cu) AS cursos,
       count(DISTINCT s) AS silabos,
       count(DISTINCT cc) AS coberturas
ORDER BY silabos DESC, coberturas DESC, competencia
LIMIT 100;

-- 3. Competencias específicas usadas en la currícula
MATCH (c:Carrera)-[:ENSENIA]->(cu:Curso)-[:TIENE]->(s:Silabo)
      -[:DECLARA]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia)
WHERE co.tipo_competencia = 'especifica'
RETURN co.codigo_competencia AS codigo,
       co.nombre_competencia AS competencia,
       count(DISTINCT c) AS carreras,
       count(DISTINCT cu) AS cursos,
       count(DISTINCT s) AS silabos,
       count(DISTINCT cc) AS coberturas
ORDER BY silabos DESC, coberturas DESC, competencia
LIMIT 100;

-- 4. Competencias por curso y tipo
MATCH (c:Carrera)-[:ENSENIA]->(cu:Curso)-[:TIENE]->(s:Silabo)
      -[:DECLARA]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia)
RETURN c.nombre_carrera AS carrera,
       cu.codigo_curso AS codigo_curso,
       cu.nombre_curso AS curso,
       co.tipo_competencia AS tipo,
       count(DISTINCT co) AS competencias,
       count(DISTINCT s) AS silabos,
       count(DISTINCT cc) AS coberturas
ORDER BY carrera, curso, tipo
LIMIT 100;

-- 5. Detalle de cada sílabo y sus competencias
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

-- 6. Sílabos con competencias genéricas
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

-- 7. Sílabos con competencias específicas
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

-- 8. Resumen de competencias por carrera
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

-- 9. Competencias más recurrentes en los sílabos
MATCH (s:Silabo)-[:DECLARA]->(cc:Cobertura_Curricular)
      -[:CUBRE]->(co:Competencia)
RETURN co.codigo_competencia AS codigo,
       co.nombre_competencia AS competencia,
       co.tipo_competencia AS tipo,
       count(DISTINCT s) AS silabos,
       count(DISTINCT cc) AS coberturas
ORDER BY silabos DESC, coberturas DESC, competencia
LIMIT 20;

-- 10. Sílabos sin competencias asociadas
MATCH (cu:Curso)-[:TIENE]->(s:Silabo)
OPTIONAL MATCH (s)-[:DECLARA]->(:Cobertura_Curricular)
      -[:CUBRE]->(co:Competencia)
WITH cu, s, count(DISTINCT co) AS competencias
WHERE competencias = 0
RETURN cu.codigo_curso AS codigo_curso,
       cu.nombre_curso AS curso,
       s.codigo_silabo AS silabo,
       s.periodo_academico AS periodo
ORDER BY curso
LIMIT 100;