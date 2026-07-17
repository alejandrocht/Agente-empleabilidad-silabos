# Plan — Dashboard de tendencias: currículo CIAR y mercado laboral

## Propósito

Construir un dashboard para comparar, con evidencia de Neo4j, **lo que las carreras enseñan** frente a **lo que las ofertas laborales solicitan**. Debe permitir descubrir tendencias temporales de la demanda y priorizar elementos curriculares que vale la pena revisar.

El dashboard no es un explorador genérico del grafo ni un panel de salud de la base. Se excluyen métricas como número total de nodos, densidad del grafo, empresas con más registros o relaciones por etiqueta, salvo que aporten contexto directo a una comparación currículo--mercado.

## Fuente de verdad y alcance de la ontología

La imagen adjunta organiza el dominio en cuatro grupos:

| Dominio | Entidades que intervienen | Papel en el dashboard |
| --- | --- | --- |
| Académico | **Facultad**, **Carrera**, **Curso**, **Silabo**, **Cobertura_Curricular** | Define qué cursos y coberturas componen una carrera. |
| Competencias | **Competencia**, **Habilidad**, **Herramienta** | Es el vocabulario común que permite contrastar oferta formativa y demanda. |
| Mercado laboral | **Industria**, **Empresa**, **Oferta_Laboral**, **Requerimiento_Laboral**, **Puesto** | Aporta las ofertas publicadas, sus requerimientos y el contexto laboral. |
| Evaluación | **Evaluacion_Desempenio** | Puede servir para validar resultados más adelante; no es una métrica principal de la primera versión. |

La cabecera de la imagen indica 16 entidades y 27 relaciones. Sin embargo, el schema vivo consultado por el backend actual expone 14 etiquetas y 21 tipos de relación. Las 14 entidades con nombre que se distinguen en la imagen coinciden con esas etiquetas. También hay diferencias de nomenclatura: por ejemplo, el schema vivo usa **ENSENIA** entre **Carrera** y **Curso** y **DEFIINE** entre **Puesto** y **Requerimiento_Laboral**.

**Decisión:** la imagen se toma como modelo conceptual y guía del producto; el schema vivo de Neo4j y las relaciones validadas por el guard son la fuente ejecutable. Antes de implementar cada plantilla se ejecutará una auditoría de topología y propiedades. No se inventarán las dos entidades ni las seis relaciones que no estén presentes en el schema vivo.

### Recorridos que sí sustentan la comparación

~~~text
Carrera --ENSENIA--> Curso --TIENE--> Cobertura_Curricular
                                      |--CUBRE--> Competencia
                                      |--ENSENIA--> Habilidad / Herramienta

Oferta_Laboral --TIENE--> Requerimiento_Laboral --REQUIERE-->
                                      Competencia / Habilidad / Herramienta
Oferta_Laboral --DIRIGE_A--> Carrera
Oferta_Laboral --PUBLICA--> Empresa --AGRUPA--> Industria
~~~

La comparación principal se hará por separado para competencias, habilidades y herramientas. No se mezclarán sus conteos en una sola lista: son entidades con semánticas y relaciones curriculares distintas.

### Hallazgo de disponibilidad en los datos actuales

La auditoría de la instancia actual encontró 14 carreras, pero solo **Ingeniería de Sistemas** tiene cursos enlazados mediante **Carrera-ENSENIA-Curso**: 73 cursos, 455 coberturas curriculares y 52 competencias con cobertura. Las otras 13 carreras devuelven cero cursos por ese recorrido.

Esto no prueba que esas carreras no enseñen cursos; prueba que la relación necesaria para medir su cobertura no está cargada o no está conectada en el grafo actual. Por ello:

- La tendencia y los rankings de **demanda laboral** pueden mostrarse para cualquier carrera que tenga ofertas dirigidas.
- La comparación currículo--mercado y sus brechas solo se habilitan cuando la carrera tiene al menos un curso conectado y la consulta devuelve un denominador curricular válido.
- Para las carreras sin esa relación, la interfaz mostrará “cobertura curricular no disponible en el grafo” y enlazará a la auditoría de datos. Nunca pintará cobertura 0 % ni una brecha como si fuese una conclusión.

## Preguntas que el dashboard debe responder

1. ¿Cómo evoluciona, mes a mes, la cantidad de ofertas en el período elegido?
2. Para una carrera, ¿qué competencias, habilidades y herramientas aparecen con más frecuencia en sus ofertas dirigidas?
3. ¿En cuántos cursos de esa carrera existe una cobertura que declara cada elemento?
4. ¿Qué elementos tienen alta presencia en las ofertas y baja presencia en los cursos de la carrera? Esas son **señales de revisión curricular**, no una afirmación de que la carrera sea insuficiente.
5. ¿Qué elementos reciben mucha cobertura y tienen poca demanda registrada? Son candidatos a revisión por vigencia o a análisis cualitativo, no a una eliminación automática.

No se mostrará una conclusión causal del tipo “el curso X causa empleabilidad”: la ontología contiene asociaciones y cobertura declarada, no resultados longitudinales de inserción laboral atribuibles a un curso.

### Exploración ampliada: trayectorias, pertinencia y mercado

La interfaz se organiza como un **observatorio de correspondencias**, no como un formulario de preguntas. Sus filtros de facultad, carrera, industria, empresa de referencia, empresa comparada y función cambian el contexto de las visualizaciones. Así permite explorar de forma indirecta estas decisiones:

| Decisión que se quiere explorar | Vista indirecta | Qué representa realmente |
| --- | --- | --- |
| Orientación por sector | Afinidad por industria y pulso de oportunidades | Ofertas vinculadas a una carrera, no el empleo efectivo de sus egresados. |
| Priorización de cursos para una empresa y función | Cursos para priorizar | Correspondencia entre requerimientos del mercado y cobertura declarada por curso. |
| Preparación comparada | Índice de preparación por carrera | Cobertura relativa frente a señales de una industria; no un ranking absoluto de calidad. |
| Brechas y diseño curricular | Cobertura/demanda, vigencia y mapa de espacios de diseño | Señales para investigar actualización o creación de experiencias formativas; no recomendaciones automáticas. |
| Reclutamiento desde la academia | Densidad formativa y cursos con correspondencia | Evidencia de oferta curricular identificable, nunca datos de personas, candidatos o dominio individual. |
| Competencia y evolución del mercado | Perfil comparativo de empresas, núcleo de función y matriz por estructura organizacional | Patrones de requerimientos por empresa, función y tipo de organización. |

#### Límite semántico obligatorio

El schema actual no contiene una entidad de **Persona**, **Estudiante**, **Egresado**, contrato, postulación ni relación de empleo. Por tanto, no es válido afirmar con esta base:

- en qué industrias trabajan los graduados;
- de qué carrera egresan personas con conocimientos exactos;
- qué curso causó una contratación, desempeño o empleabilidad.

Para soportar esas afirmaciones haría falta incorporar datos de trayectoria laboral y consentimiento/controles de privacidad apropiados. Hasta entonces, los nombres de las vistas deben conservar “oportunidades vinculadas”, “afinidad”, “cobertura declarada” y “señales”, en vez de “empleabilidad comprobada”, “talento disponible” o “colocación de egresados”.

La versión actual del frontend usa datos simulados y los identifica como **Modo demostración**. Las consultas reales deberán replicar estas unidades de medida y no sustituirlas por inferencias personales.

## Métricas y gráficos seleccionados

Los gráficos se ordenan por valor analítico. Todos incluyen filtros de período y de carrera cuando el recorrido lo permite. La medida de demanda es siempre **count(DISTINCT oferta)** para no inflar valores cuando una oferta tiene varios requerimientos iguales o relacionados.

| Prioridad | Métrica | Gráfico recomendado | Motivo de la elección | Interacción |
| --- | --- | --- | --- | --- |
| 1 | Ofertas publicadas por mes | Línea | Es la lectura más clara para tendencia, picos y variación mensual. Un área rellenada ocultaría comparaciones si se agregan series. | Período; carrera e industria opcionales; tooltip con mes y ofertas. |
| 1 | Demanda de competencias, habilidades o herramientas para una carrera | Barras horizontales ordenadas | Las etiquetas suelen ser largas y se requiere comparar un ranking exacto. Es más legible que un donut. | Pestañas por dimensión; Top 10/20; clic filtra la tabla de detalle. |
| 1 | Cobertura curricular declarada de la misma dimensión | Barras horizontales ordenadas | Expone en cuántos cursos se declara cada elemento sin sugerir una equivalencia de calidad u horas. | Misma carrera; tooltip con cursos y porcentaje de cursos. |
| 1 | Brecha currículo--mercado por elemento | Barras agrupadas horizontales con índices porcentuales | Muestra lado a lado demanda y cobertura sobre una escala común de 0 a 100. Evita comparar directamente conteos de ofertas y cursos, que no comparten denominador. | Ordenar por prioridad; seleccionar elemento; enlace a cursos y ofertas de soporte. |
| 2 | Mapa de priorización de brechas | Dispersión | Ubica cada elemento por demanda relativa (Y) y cobertura relativa (X). El cuadrante superior izquierdo identifica demanda alta con cobertura baja. | Filtros por carrera/dimensión; etiquetar solo puntos seleccionados para no saturar. |
| 2 | Composición de demanda por industria | Barras horizontales apiladas, solo para el elemento seleccionado | Permite saber en qué industrias aparece una brecha concreta. No se muestra como ranking general de empresas. | Visible al seleccionar una competencia, habilidad o herramienta. |

### Métrica de brecha normalizada

Para una carrera y un período determinados, cada elemento tendrá:

~~~text
índice_demanda   = ofertas dirigidas a la carrera que lo requieren
                   / total de ofertas dirigidas a la carrera

índice_cobertura = cursos de la carrera que lo cubren o enseñan
                   / total de cursos de la carrera

brecha           = índice_demanda - índice_cobertura
~~~

Los gráficos usarán ambos índices expresados como porcentajes. La tabla mostrará además los numeradores y denominadores para que la comparación sea auditable. No se clasificará una brecha como prioritaria si hay muy pocas ofertas: el umbral mínimo se definirá con usuarios funcionales tras medir la distribución real de datos, y se mostrará como filtro explícito.

**Cobertura_Curricular** representa presencia declarada en un curso, no profundidad, créditos, calidad pedagógica ni dominio alcanzado por estudiantes. Por esa razón el dashboard denominará el eje “cobertura declarada”, no “competencia adquirida”.

## Plantillas Cypher de solo lectura

Las consultas se implementarán como plantillas con nombre en un módulo separado del catálogo conversacional. El frontend nunca enviará Cypher; enviará filtros tipados y el backend elegirá una plantilla permitida. Todas pasan por el guard de solo lectura y se ejecutan con parámetros, sin interpolar valores de usuario.

| Id de plantilla | Uso | Recorrido validado | Parámetros |
| --- | --- | --- | --- |
| **dashboard_ofertas_por_mes** | Tendencia global de ofertas | **Oferta_Laboral.fecha_publicacion** | **desde**, **hasta** |
| **dashboard_ofertas_por_mes_carrera** | Tendencia para una carrera | **Carrera-DIRIGE_A-Oferta_Laboral** | **carrera_id**, **desde**, **hasta** |
| **dashboard_demanda_competencias_carrera** | Ranking de competencias demandadas | **Carrera-DIRIGE_A-Oferta-TIENE-Requerimiento-REQUIERE-Competencia** | **carrera_id**, **desde**, **hasta**, **limite** |
| **dashboard_cobertura_competencias_carrera** | Ranking de cobertura de competencias | **Carrera-ENSENIA-Curso-TIENE-Cobertura-CUBRE-Competencia** | **carrera_id**, **limite** |
| **dashboard_brechas_competencias_carrera** | Índices comparables y brecha | Unión de los dos recorridos anteriores | **carrera_id**, **desde**, **hasta**, **limite** |
| **dashboard_demanda_habilidades_carrera**, **dashboard_cobertura_habilidades_carrera**, **dashboard_brechas_habilidades_carrera** | Misma lectura para habilidades | En currículo usa **Cobertura_Curricular-ENSENIA-Habilidad** | mismos parámetros |
| **dashboard_demanda_herramientas_carrera**, **dashboard_cobertura_herramientas_carrera**, **dashboard_brechas_herramientas_carrera** | Misma lectura para herramientas | En currículo usa **Cobertura_Curricular-ENSENIA-Herramienta** | mismos parámetros |
| **dashboard_industrias_elemento** | Contexto laboral de un elemento seleccionado | **Industria-AGRUPA-Empresa-PUBLICA-Oferta-TIENE-Requerimiento-REQUIERE-elemento** | **tipo**, **elemento_id**, **desde**, **hasta**, **limite** |
| **dashboard_catalogo_filtros** | Selectores de carreras e industrias | etiquetas correspondientes | sin filtros o búsqueda limitada |

### Consulta de tendencia mensual

**fecha_publicacion** está almacenada como DateTime en el schema vivo. Se agrupará por sus componentes temporales y el backend entregará **anio** y **mes** para que la interfaz los formatee según el locale.

~~~cypher
MATCH (o:Oferta_Laboral)
WHERE o.fecha_publicacion >= datetime($desde)
  AND o.fecha_publicacion < datetime($hasta)
RETURN o.fecha_publicacion.year AS anio,
       o.fecha_publicacion.month AS mes,
       count(DISTINCT o) AS ofertas
ORDER BY anio, mes
~~~

La variante por carrera añade el patrón **(:Carrera {id_carrera: $carrera_id})-[:DIRIGE_A]-(o)** al MATCH. Se mantiene como plantilla distinta para no obligar al recorrido global a depender de esa relación.

### Consulta de brecha de competencias por carrera

Esta plantilla es la referencia para las tres dimensiones. Para habilidades y herramientas se cambia exclusivamente la etiqueta, la propiedad de nombre y la relación curricular según el schema vivo.

~~~cypher
MATCH (ca:Carrera {id_carrera: $carrera_id})
OPTIONAL MATCH (ca)-[:DIRIGE_A]-(o_total:Oferta_Laboral)
WHERE o_total.fecha_publicacion >= datetime($desde)
  AND o_total.fecha_publicacion < datetime($hasta)
WITH ca, count(DISTINCT o_total) AS total_ofertas
OPTIONAL MATCH (ca)-[:ENSENIA]-(cu_total:Curso)
WITH ca, total_ofertas, count(DISTINCT cu_total) AS total_cursos
MATCH (co:Competencia)
OPTIONAL MATCH (ca)-[:ENSENIA]-(cu_cobertura:Curso)-[:TIENE]
               -(cc:Cobertura_Curricular)-[:CUBRE]-(co)
WITH ca, co, total_cursos, total_ofertas,
     count(DISTINCT cu_cobertura) AS cursos_con_cobertura
OPTIONAL MATCH (ca)-[:DIRIGE_A]-(o_requerida:Oferta_Laboral)-[:TIENE]
               -(r:Requerimiento_Laboral)-[:REQUIERE]-(co)
WHERE o_requerida.fecha_publicacion >= datetime($desde)
  AND o_requerida.fecha_publicacion < datetime($hasta)
WITH co, total_cursos, total_ofertas, cursos_con_cobertura,
     count(DISTINCT o_requerida) AS ofertas_que_requieren
WHERE cursos_con_cobertura > 0 OR ofertas_que_requieren > 0
WITH co, total_cursos, total_ofertas, cursos_con_cobertura,
     ofertas_que_requieren,
     CASE WHEN total_cursos = 0 THEN 0.0
          ELSE toFloat(cursos_con_cobertura) / total_cursos END AS cobertura,
     CASE WHEN total_ofertas = 0 THEN 0.0
          ELSE toFloat(ofertas_que_requieren) / total_ofertas END AS demanda
RETURN co.id_competencia AS id,
       co.nombre_competencia AS elemento,
       cursos_con_cobertura,
       total_cursos,
       ofertas_que_requieren,
       total_ofertas,
       cobertura,
       demanda,
       demanda - cobertura AS brecha
ORDER BY brecha DESC, ofertas_que_requieren DESC
LIMIT $limite
~~~

La secuencia de OPTIONAL MATCH y WITH agrega cada lado antes de recorrer el siguiente: así evita multiplicar cursos por ofertas. La enumeración de Competencia es intencional y pequeña; las agregaciones DISTINCT conservan una unidad clara: cursos únicos y ofertas únicas. Esta forma no usa CALL, que la guarda actual reserva para procedimientos de metadatos de lectura. Antes de usarla en producción se verifican el plan de ejecución, índices sobre IDs y la cardinalidad real.

## Diseño del dashboard

### Filtros persistentes

- Carrera: obligatorio para cualquier comparación currículo--mercado.
- Período: obligatorio para demanda; valor inicial sugerido: últimos 12 meses con datos disponibles, no la fecha de navegador si no hay datos recientes.
- Dimensión: **Competencias**, **Habilidades** o **Herramientas**.
- Industria: filtro opcional que restringe el lado de mercado; nunca modifica artificialmente la cobertura curricular.
- Mínimo de ofertas: opcional y visible para evitar interpretar muestras pequeñas.

El selector indicará qué carreras tienen cobertura curricular disponible. Si no la tienen, conservará las vistas puramente laborales y deshabilitará las de cobertura y brecha con una explicación del dato faltante.

### Orden de contenido

1. Encabezado de filtros y la definición visible de “cobertura declarada”.
2. Línea de evolución de ofertas para el contexto temporal.
3. Dos rankings paralelos: demanda laboral y cobertura curricular.
4. Gráfico de barras agrupadas de brechas y tabla accesible con valores exactos.
5. Dispersión de priorización y desglose por industria solo al seleccionar un elemento.

En estados sin datos se mostrará por qué falta información: “no hay ofertas dirigidas a la carrera en este período”, “no hay cobertura declarada” o “el elemento no pertenece al vocabulario de esta dimensión”. No se representará un cero ambiguo como si fuera una observación confirmada.

## Implementación con shadcn/ui Charts

La implementación usará [shadcn/ui Charts](https://ui.shadcn.com/charts), que ofrece componentes que se copian al proyecto y están construidos sobre Recharts. Su **ChartContainer**, configuración de etiquetas y colores (**ChartConfig**), tooltips y leyendas permiten reutilizar el sistema visual existente sin adoptar la paleta de otro producto. La documentación también permite activar **accessibilityLayer** para interacción por teclado y lectores de pantalla.

El frontend actual usa Next 16, React 19 y Tailwind 3, y todavía no declara shadcn/ui ni Recharts. La fase de preparación debe:

1. Inicializar shadcn/ui dentro de **frontend** sin reemplazar los tokens, tipografías ni colores ya definidos en **tailwind.config.js** y los estilos globales.
2. Añadir el componente chart con **npx shadcn@latest add chart**; este provee el archivo local de composición de gráficos y su dependencia Recharts.
3. Definir los colores de cada serie mediante variables CSS de la marca en **ChartConfig**. No se usarán los colores de ejemplo de la documentación.
4. Definir una altura o clase **min-h-*** en cada **ChartContainer**, requisito para que el contenedor responsive mida correctamente en el primer render.
5. Activar **accessibilityLayer**, tooltips con valores y denominadores, y una tabla alternativa para cada gráfico.

Propuesta de componentes reutilizables:

~~~text
frontend/src/components/dashboard/
  FiltrosTendencias.jsx           # carrera, período, industria y dimensión
  TarjetaGrafico.jsx              # título, definición, carga, error y tabla alternativa
  TendenciaOfertasChart.jsx       # LineChart
  RankingDimensionChart.jsx       # BarChart horizontal
  BrechaCurriculoMercadoChart.jsx # BarChart agrupado horizontal
  MapaPriorizacionChart.jsx       # ScatterChart
  TablaBrechas.jsx                # valores y navegación accesible
  dashboard-api.js                # cliente de endpoints del backend
~~~

Cada componente de visualización recibe datos ya agregados, un ChartConfig y callbacks de selección; no contiene Cypher ni reglas de negocio.

## Diseño del backend y seguridad

1. Crear un módulo **agente/dashboard/consultas.py** con las plantillas anteriores y una lista cerrada de dimensiones permitidas. No reutilizar el LLM ni el flujo de LangGraph para responder al dashboard.
2. Crear un servicio que valide IDs, fechas, límite máximo y rango temporal; después ejecuta solamente las plantillas permitidas mediante el driver Neo4j.
3. Aplicar el validador de solo lectura y de schema ya existente a cada consulta durante pruebas. No habilitar APOC, escrituras ni Cypher suministrado por el cliente.
4. Exponer endpoints de lectura con contratos estables, por ejemplo:

~~~text
GET /dashboard/filtros/carreras
GET /dashboard/ofertas/tendencia?desde&hasta&carrera_id?
GET /dashboard/dimensiones/{tipo}/demanda?carrera_id&desde&hasta&limite
GET /dashboard/dimensiones/{tipo}/cobertura?carrera_id&limite
GET /dashboard/dimensiones/{tipo}/brechas?carrera_id&desde&hasta&limite
GET /dashboard/dimensiones/{tipo}/industrias?elemento_id&desde&hasta
~~~

5. Aplicar timeout, límite de resultados, caché breve por combinación de filtros y logs estructurados con plantilla, filtros no sensibles, duración y número de filas. No registrar texto completo de ofertas ni datos personales.

## Fases de entrega y criterios de aceptación

### Fase 0 — Auditoría de datos

- Ejecutar **introspeccionar_schema()** y un EXPLAIN por plantilla.
- Confirmar que **fecha_publicacion**, los IDs, nombres y todas las relaciones de los recorridos existan en el entorno objetivo.
- Documentar divergencias entre la imagen y el schema; posponer todo elemento no verificable.

**Aceptación:** cada consulta pasa la guarda de solo lectura, no produce escrituras y devuelve una unidad de medida definida.

### Fase 1 — Núcleo analítico

- Implementar catálogo de filtros, tendencia mensual y las tres familias de demanda/cobertura/brecha por carrera.
- Añadir pruebas unitarias para parámetros, denominadores en cero, ausencia de datos y prevención de duplicados por múltiples requerimientos.
- Contrastar al menos una carrera real contra resultados de Cypher ejecutados en Neo4j.

**Aceptación:** para una carrera y período seleccionados, el gráfico y la tabla reportan exactamente los mismos numeradores, denominadores y porcentajes.

### Fase 2 — Interfaz shadcn/ui

- Integrar los componentes de charts sin alterar la identidad visual existente.
- Construir filtros, estados de carga/vacío/error, tooltips y tabla alternativa.
- Verificar responsive, teclado, lector de pantalla y contraste con los tokens de marca definidos.

**Aceptación:** la selección de filtros actualiza continuamente los cuatro gráficos principales; ningún gráfico queda sin texto alternativo o acceso a los valores tabulares.

### Fase 3 — Priorización y validación funcional

- Añadir dispersión de priorización y desglose por industria bajo demanda.
- Acordar el mínimo de ofertas y el período por defecto con responsables académicos y de empleabilidad.
- Validar una muestra de resultados con usuarios antes de rotular una señal como prioridad de revisión.

**Aceptación:** cada señal de brecha permite navegar a sus cursos de cobertura y a la cantidad de ofertas que la sustentan; el dashboard no presenta inferencias causales ni recomendaciones automáticas.

## Elementos deliberadamente pospuestos

- Métricas de **Evaluacion_Desempenio**: solo se consideran si la auditoría confirma sus relaciones y propiedades para las tres dimensiones. No se mezclarán con cobertura o demanda sin una definición estadística validada.
- Predicciones, recomendaciones automáticas y uso de LLM: no son necesarios para responder las preguntas del dashboard y añadirían interpretaciones no sustentadas por la ontología.
- Visualización completa de la red y KPIs de volumen de la base: son útiles para administración técnica, no para detectar la alineación entre enseñanza y mercado laboral.
