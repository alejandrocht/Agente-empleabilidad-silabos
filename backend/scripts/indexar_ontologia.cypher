// CIAR - Indexación idempotente de la ontología vigente.
// Ejecutar en la base de datos neo4j de la instancia activa.

// -----------------------------------------------------------------------------
// Restricciones únicas para impedir IDs repetidos.
// Cada restricción crea también su índice RANGE de respaldo.
// -----------------------------------------------------------------------------

CREATE CONSTRAINT ciar_facultad_id_unique IF NOT EXISTS
FOR (n:Facultad) REQUIRE n.id_facultad IS UNIQUE;

CREATE CONSTRAINT ciar_carrera_id_unique IF NOT EXISTS
FOR (n:Carrera) REQUIRE n.id_carrera IS UNIQUE;

CREATE CONSTRAINT ciar_curso_id_unique IF NOT EXISTS
FOR (n:Curso) REQUIRE n.id_curso IS UNIQUE;

CREATE CONSTRAINT ciar_silabo_id_unique IF NOT EXISTS
FOR (n:Silabo) REQUIRE n.id_silabo IS UNIQUE;

CREATE CONSTRAINT ciar_competencia_id_unique IF NOT EXISTS
FOR (n:Competencia) REQUIRE n.id_competencia IS UNIQUE;

CREATE CONSTRAINT ciar_habilidad_id_unique IF NOT EXISTS
FOR (n:Habilidad) REQUIRE n.id_habilidad IS UNIQUE;

CREATE CONSTRAINT ciar_logros_id_unique IF NOT EXISTS
FOR (n:Logros) REQUIRE n.id_logros IS UNIQUE;

CREATE CONSTRAINT ciar_cobertura_id_unique IF NOT EXISTS
FOR (n:Cobertura_Curricular) REQUIRE n.id_cob_curricular IS UNIQUE;

CREATE CONSTRAINT ciar_industria_id_unique IF NOT EXISTS
FOR (n:Industria) REQUIRE n.id_industria IS UNIQUE;

CREATE CONSTRAINT ciar_empresa_id_unique IF NOT EXISTS
FOR (n:Empresa) REQUIRE n.id_empresa IS UNIQUE;

CREATE CONSTRAINT ciar_oferta_laboral_id_unique IF NOT EXISTS
FOR (n:Oferta_Laboral) REQUIRE n.id_ofe_laboral IS UNIQUE;

CREATE CONSTRAINT ciar_puesto_id_unique IF NOT EXISTS
FOR (n:Puesto) REQUIRE n.id_puesto IS UNIQUE;

CREATE CONSTRAINT ciar_requerimiento_laboral_id_unique IF NOT EXISTS
FOR (n:Requerimiento_Laboral) REQUIRE n.id_req_laboral IS UNIQUE;

// -----------------------------------------------------------------------------
// Índices full-text usados por resolución de entidades y búsquedas textuales.
// -----------------------------------------------------------------------------

CREATE FULLTEXT INDEX ciar_facultad_text_ft IF NOT EXISTS
FOR (n:Facultad) ON EACH [n.nombre_facultad];

CREATE FULLTEXT INDEX ciar_carrera_text_ft IF NOT EXISTS
FOR (n:Carrera) ON EACH [n.nombre_carrera];

CREATE FULLTEXT INDEX ciar_curso_text_ft IF NOT EXISTS
FOR (n:Curso) ON EACH [n.nombre_curso, n.coordinador];

CREATE FULLTEXT INDEX ciar_competencia_text_ft IF NOT EXISTS
FOR (n:Competencia) ON EACH [n.nombre_competencia];

CREATE FULLTEXT INDEX ciar_habilidad_text_ft IF NOT EXISTS
FOR (n:Habilidad) ON EACH [n.nombre_habilidad];

CREATE FULLTEXT INDEX ciar_logros_text_ft IF NOT EXISTS
FOR (n:Logros) ON EACH [n.logro];

CREATE FULLTEXT INDEX ciar_empresa_text_ft IF NOT EXISTS
FOR (n:Empresa) ON EACH [n.nombre, n.razon_social];

CREATE FULLTEXT INDEX ciar_industria_text_ft IF NOT EXISTS
FOR (n:Industria) ON EACH [n.nombre];

CREATE FULLTEXT INDEX ciar_puesto_text_ft IF NOT EXISTS
FOR (n:Puesto) ON EACH [n.nombre];

// -----------------------------------------------------------------------------
// Verificación posterior.
// -----------------------------------------------------------------------------

SHOW CONSTRAINTS;

SHOW FULLTEXT INDEXES;
