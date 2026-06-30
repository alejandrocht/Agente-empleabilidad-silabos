# Preguntas de ejemplo para el agente

Preguntas armadas con la data **real** del grafo (introspección en vivo). Dos niveles:
**sencillo** (1 entidad, 1 salto o conteo) y **complicado** (varios saltos, agregación
o cruce currícula ↔ mercado laboral).

## Qué hay en el grafo (resumen)

| Label | Cantidad | Label | Cantidad |
|---|---|---|---|
| Carrera | 14 | OfertaLaboral | 44 401 |
| Facultad | 7 | Puesto | 44 401 |
| Curso | 73 | Empresa | 9 483 |
| Silabo | 73 | Industria | 314 |
| Competencia | 54 | RequerimientoLaboral | 120 817 |
| Habilidad | 117 | EvalDesempeno | 36 909 |
| Herramienta | 121 | CoberturaCurricular | 455 |

**Relaciones principales:**
- Currícula: `(Facultad)-[:OFRECE]->(Carrera)-[:CONTIENE]->(Curso)-[:TIENE]->(Silabo)`
- Cobertura: `(Curso)-[:TIENE_COBERTURA]->(CoberturaCurricular)-[:ENSEÑA_HERRAMIENTA / ENSEÑA_HABILIDAD / CUBRE_COMPETENCIA]->(...)`
- Mercado: `(Empresa)-[:PUBLICA]->(OfertaLaboral)-[:DIRIGE_A]->(Carrera)`, `(OfertaLaboral)-[:OFRECE_PUESTO]->(Puesto)`
- Requerimientos: `(OfertaLaboral / Puesto / Empresa)-[:..._REQUERIMIENTO]->(RequerimientoLaboral)-[:REQUIERE_HERRAMIENTA / REQUIERE_HABILIDAD / REQUIERE_COMPETENCIA]->(...)`
- Industria: `(Industria)-[:AGRUPA]->(Empresa)`
- Desempeño: `(Empresa)-[:REALIZA]->(EvalDesempeno)-[:EVALUA_CARRERA]->(Carrera)`, `(EvalDesempeno)-[:MIDE]->(Competencia / Habilidad / Herramienta)`

**Nombres reales útiles:**
- Carreras: Ingeniería de Sistemas, Ingeniería Industrial, Administración, Derecho, Economía, Marketing, Psicología, Arquitectura, Comunicación, Contabilidad y Finanzas, Negocios Internacionales, Ingeniería Civil, Ingeniería Ambiental, Ingeniería Mecatrónica.
- Facultades: Ingeniería, Ciencias Empresariales, Derecho, Economía, Comunicación, Psicología, Arquitectura.
- Herramientas frecuentes: SQL, Python, Power BI, Microsoft Excel, Git, Docker, SAP, Unity, Arduino.
- Empresas con muchas ofertas: EVENTIVA S.A.C., SUNAT, EY, KROWDY PERU SAC, ADECCO CONSULTING S.A.

---

## Nivel sencillo

1. ¿Cuántas carreras hay?
2. ¿Qué facultades existen?
3. ¿Cuántos cursos tiene Ingeniería de Sistemas?
4. ¿Qué cursos tiene la carrera de Administración?
5. ¿Qué carreras ofrece la Facultad de Ingeniería?
6. ¿Cuántas empresas hay registradas?
7. ¿Cuántas ofertas laborales publicó EVENTIVA S.A.C.?
8. ¿A qué industria pertenece SUNAT?
9. ¿Qué competencias desarrolla la carrera de Economía?
10. ¿Qué herramientas se enseñan en Ingeniería Industrial?
11. ¿Cuántas ofertas están dirigidas a Derecho?
12. ¿Qué facultad ofrece la carrera de Psicología?

---

## Nivel complicado

1. ¿Qué carrera tiene más cursos?
2. ¿Cuántas ofertas laborales están dirigidas a cada carrera? (ranking)
3. Top 10 herramientas más solicitadas en ofertas dirigidas a Ingeniería de Sistemas.
4. ¿Qué competencias blandas requieren las ofertas de la industria de Publicidad?
5. ¿Qué herramientas se enseñan en Ingeniería de Sistemas **y además** las piden las ofertas dirigidas a esa carrera? (alineación currícula ↔ mercado)
6. ¿Qué herramientas piden las ofertas de Ingeniería Industrial que **no** se enseñan en su currícula? (brecha)
7. Top 10 empresas con más ofertas dirigidas a Derecho.
8. ¿Qué competencias mide la evaluación de desempeño de la carrera de Administración?
9. Promedio del puntaje general de las evaluaciones de desempeño por carrera.
10. ¿Qué industrias publican más ofertas para Marketing?
11. ¿Qué habilidades comparten las ofertas de Economía y las de Contabilidad y Finanzas?
12. ¿Cuántos sílabos declaran la competencia "Análisis de datos"?
