# Guía práctica para crear consultas Cypher correctamente

Esta guía explica cómo diseñar consultas Cypher claras, parametrizadas y seguras para el grafo de empleabilidad. Los ejemplos se basan en el esquema real compartido.

## 1. Esquema de referencia

```text
(Industria)-[:AGRUPA]->(Empresa)-[:PUBLICA]->(Oferta_Laboral)
(Oferta_Laboral)-[:DIRIGE_A]->(Carrera)
(Oferta_Laboral)-[:TIENE]->(Requerimiento_Laboral)
(Oferta_Laboral)-[:OFRECE]->(Puesto)
(Puesto)-[:DEFIINE]->(Requerimiento_Laboral)
(Requerimiento_Laboral)-[:REQUIERE]->(Habilidad)
(Requerimiento_Laboral)-[:REQUIERE]->(Herramienta)
(Requerimiento_Laboral)-[:REQUIERE]->(Competencia)
```

> **Importante:** la relación `DEFIINE` está escrita con doble `I` en la base de datos. Cypher exige usar el nombre exacto.

### Propiedades principales

| Nodo | Identificador | Propiedades útiles |
|---|---|---|
| `Oferta_Laboral` | `id_ofe_laboral` | `cargo`, `area`, `area_especifica`, `descripcion_breve`, `fecha_publicacion`, `fecha_finalizacion` |
| `Empresa` | `id_empresa` | `nombre`, `razon_social`, `tipo`, `ruc`, `descripcion_breve` |
| `Industria` | `id_industria` | `nombre`, `ciiu`, `sector_macro`, `descripcion_breve` |
| `Carrera` | `id_carrera` | `nombre_carrera`, `codigo_carrera`, `coordinador` |
| `Puesto` | `id_puesto` | `nombre`, `ciclo_requerido` |
| `Requerimiento_Laboral` | `id_req_laboral` | `tipo` |
| `Habilidad` | `id_habilidad` | `nombre_habilidad`, `descripcion_breve` |
| `Herramienta` | `id_herramienta` | `nombre_herramienta`, `descripcion_breve_herramienta` |
| `Competencia` | `id_competencia` | `nombre_competencia`, `tipo_competencia` |

## 2. Estructura recomendada de una consulta

Una consulta analítica suele construirse en este orden:

```cypher
// 1. Definir el patrón principal
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)

// 2. Aplicar los filtros lo antes posible
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)

// 3. Añadir información que puede no existir
OPTIONAL MATCH (o)-[:DIRIGE_A]->(c:Carrera)

// 4. Proyectar solo los datos necesarios
RETURN
  o.id_ofe_laboral AS oferta_id,
  o.cargo AS cargo,
  coalesce(e.nombre, e.razon_social) AS empresa,
  c.nombre_carrera AS carrera

// 5. Ordenar y limitar la salida
ORDER BY o.fecha_publicacion DESC
LIMIT $limite
```

## 3. Reglas fundamentales

### 3.1 Usar etiquetas y direcciones reales

Consulta correcta:

```cypher
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
RETURN e.nombre, o.cargo
LIMIT 10
```

Evita inventar etiquetas, propiedades o relaciones como `Oferta`, `titulo` o `id_oferta`, porque no existen en el esquema compartido.

### 3.2 Parametrizar los valores externos

Correcto:

```cypher
MATCH (o:Oferta_Laboral)-[:DIRIGE_A]->(c:Carrera)
WHERE c.id_carrera = $carrera_id
RETURN o.id_ofe_laboral, o.cargo
```

Parámetros:

```json
{
  "carrera_id": 4
}
```

No se recomienda insertar directamente el valor dentro del texto de la consulta. Los parámetros facilitan la reutilización, mejoran el aprovechamiento del plan de ejecución y evitan problemas de escapado.

### 3.3 Respetar el contrato entre parámetros, propiedades y operadores

Los parámetros canónicos de entidades representan identificadores, no texto de búsqueda:

- `$industria_id` se compara con `i.id_industria = $industria_id`.
- `$herramienta_id` se compara con `h.id_herramienta = $herramienta_id`.
- `$carrera_ids` se compara con `c.id_carrera IN $carrera_ids`.

Nunca uses `CONTAINS`, `toLower()` ni propiedades de nombre con parámetros terminados en `_id` o `_ids`. Si la intención es buscar texto, usa un parámetro textual explícito, por ejemplo `$industria_texto`, contra `i.nombre`.

El nombre del parámetro también es parte del contrato: `id_industria` exige `$industria_id`, `id_herramienta` exige `$herramienta_id` e `id_carrera` exige `$carrera_id`. No uses aliases genéricos como `$entidad_id`.

### 3.4 Elegir el grano de salida antes de escribir el patrón

- Para un puesto o cargo formal, usa `(o:Oferta_Laboral)-[:OFRECE]->(p:Puesto)` y `p.nombre`. Usa `o.cargo` sólo cuando la pregunta pida el texto crudo publicado en la oferta.
- Para listar combinaciones únicas, proyecta las dimensiones pedidas con `RETURN DISTINCT`.
- Para rankings de ofertas, agrupa por todas las dimensiones retornadas y usa `count(DISTINCT o)` para no inflar el conteo.
- Para analizar la relación entre puestos y herramientas, el grano es el par puesto-herramienta; devuelve ambas dimensiones y ordénalas por `count(DISTINCT o)`.
- Si una agregación determina el orden, proyéctala en `RETURN` con un alias y usa ese alias en `ORDER BY`. No introduzcas una agregación nueva únicamente dentro de `ORDER BY`.

### 3.5 Usar intervalos de fecha semiabiertos

```cypher
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
```

Con este criterio se incluye `$desde` y se excluye `$hasta`. Para analizar agosto de 2026:

```json
{
  "desde": "2026-08-01",
  "hasta": "2026-09-01"
}
```

Este patrón evita problemas con horas, minutos y segundos del último día del mes.

### 3.6 Elegir entre `MATCH` y `OPTIONAL MATCH`

- Usa `MATCH` cuando la relación es obligatoria para responder la pregunta.
- Usa `OPTIONAL MATCH` cuando el registro principal debe conservarse aunque el dato relacionado no exista.

Ejemplo: conservar una oferta aunque no tenga carrera asociada.

```cypher
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
OPTIONAL MATCH (o)-[:DIRIGE_A]->(c:Carrera)
RETURN o.id_ofe_laboral, o.cargo, c.nombre_carrera
```

### 3.7 Evitar conteos inflados

Una oferta puede conectarse con varias carreras o requerimientos. Después de recorrer esas relaciones, `count(o)` puede contar la misma oferta varias veces.

Usa:

```cypher
count(DISTINCT o) AS total_ofertas
```

en lugar de:

```cypher
count(o) AS total_ofertas
```

### 3.8 Controlar valores nulos

```cypher
coalesce(e.nombre, e.razon_social, toString(e.id_empresa)) AS empresa
```

`coalesce()` devuelve el primer valor no nulo. Es útil cuando una empresa puede tener `nombre`, `razon_social` o solo identificador.

## 4. Ejemplos progresivos

## Ejemplo 1. Obtener una muestra de ofertas

**Objetivo:** inspeccionar los campos disponibles antes de construir una consulta más compleja.

```cypher
MATCH (o:Oferta_Laboral)
RETURN
  o.id_ofe_laboral AS oferta_id,
  o.cargo AS cargo,
  o.area AS area,
  o.fecha_publicacion AS fecha_publicacion
ORDER BY fecha_publicacion DESC
LIMIT 10
```

## Ejemplo 2. Filtrar ofertas por periodo

```cypher
MATCH (o:Oferta_Laboral)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
RETURN
  o.id_ofe_laboral AS oferta_id,
  o.cargo AS cargo,
  o.fecha_publicacion AS fecha_publicacion
ORDER BY fecha_publicacion DESC
```

Parámetros:

```json
{
  "desde": "2026-01-01",
  "hasta": "2026-09-01"
}
```

## Ejemplo 3. Buscar una oferta por texto

```cypher
MATCH (o:Oferta_Laboral)
WHERE toLower(coalesce(o.cargo, '')) CONTAINS toLower($texto)
   OR toLower(coalesce(o.area, '')) CONTAINS toLower($texto)
   OR toLower(coalesce(o.descripcion_breve, '')) CONTAINS toLower($texto)
RETURN
  o.id_ofe_laboral AS oferta_id,
  o.cargo AS cargo,
  o.area AS area,
  o.descripcion_breve AS descripcion
LIMIT $limite
```

Parámetros:

```json
{
  "texto": "datos",
  "limite": 20
}
```

> Para búsquedas frecuentes sobre grandes volúmenes, conviene crear y utilizar un índice de texto completo en vez de depender únicamente de `CONTAINS`.

## Ejemplo 4. Relacionar ofertas con empresas

```cypher
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
RETURN
  o.id_ofe_laboral AS oferta_id,
  o.cargo AS cargo,
  e.id_empresa AS empresa_id,
  coalesce(e.nombre, e.razon_social) AS empresa
ORDER BY o.fecha_publicacion DESC
LIMIT $limite
```

## Ejemplo 5. Obtener las empresas con más ofertas

```cypher
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
RETURN
  e.id_empresa AS empresa_id,
  coalesce(e.nombre, e.razon_social, toString(e.id_empresa)) AS empresa,
  count(DISTINCT o) AS total_ofertas
ORDER BY total_ofertas DESC, empresa ASC
LIMIT $limite
```

## Ejemplo 6. Incluir una relación opcional

**Objetivo:** listar ofertas y mostrar la industria si la empresa está asociada a una.

```cypher
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
OPTIONAL MATCH (i:Industria)-[:AGRUPA]->(e)
RETURN
  o.id_ofe_laboral AS oferta_id,
  o.cargo AS cargo,
  coalesce(e.nombre, e.razon_social) AS empresa,
  i.nombre AS industria
ORDER BY o.fecha_publicacion DESC
LIMIT $limite
```

Si se reemplaza `OPTIONAL MATCH` por `MATCH`, desaparecerán del resultado las ofertas de empresas sin industria asociada.

## Ejemplo 7. Agrupar relaciones múltiples en una lista

**Objetivo:** devolver una sola fila por oferta, aunque esté dirigida a varias carreras.

```cypher
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
OPTIONAL MATCH (o)-[:DIRIGE_A]->(c:Carrera)
WITH e, o,
     [carrera IN collect(DISTINCT c)
      WHERE carrera IS NOT NULL |
      {
        carrera_id: carrera.id_carrera,
        nombre: carrera.nombre_carrera
      }
     ] AS carreras
RETURN
  o.id_ofe_laboral AS oferta_id,
  o.cargo AS cargo,
  coalesce(e.nombre, e.razon_social) AS empresa,
  carreras
ORDER BY o.fecha_publicacion DESC
LIMIT $limite
```

## Ejemplo 8. Crear una serie mensual

```cypher
MATCH (:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
WITH
  date.truncate('month', date(o.fecha_publicacion)) AS periodo,
  count(DISTINCT o) AS total_ofertas
RETURN periodo, total_ofertas
ORDER BY periodo ASC
```

Esta consulta devuelve únicamente meses con ofertas. Si el gráfico debe mostrar meses con valor cero, primero se debe generar el calendario de meses y después usar `OPTIONAL MATCH`.

## Ejemplo 9. Ranking de herramientas demandadas

```cypher
MATCH (o:Oferta_Laboral)-[:TIENE]->(:Requerimiento_Laboral)
      -[:REQUIERE]->(h:Herramienta)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
RETURN
  h.id_herramienta AS herramienta_id,
  h.nombre_herramienta AS herramienta,
  count(DISTINCT o) AS total_ofertas
ORDER BY total_ofertas DESC, herramienta ASC
LIMIT $limite
```

## Ejemplo 10. Comparar demanda por carrera e industria

```cypher
MATCH (i:Industria)-[:AGRUPA]->(e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
MATCH (o)-[:DIRIGE_A]->(c:Carrera)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
RETURN
  c.id_carrera AS carrera_id,
  c.nombre_carrera AS carrera,
  i.id_industria AS industria_id,
  i.nombre AS industria,
  count(DISTINCT o) AS total_ofertas,
  count(DISTINCT e) AS total_empresas
ORDER BY total_ofertas DESC, carrera ASC, industria ASC
LIMIT $limite
```

## Ejemplo 11. Paginar resultados

```cypher
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
WHERE o.fecha_publicacion IS NOT NULL
RETURN
  o.id_ofe_laboral AS oferta_id,
  o.cargo AS cargo,
  coalesce(e.nombre, e.razon_social) AS empresa,
  o.fecha_publicacion AS fecha_publicacion
ORDER BY fecha_publicacion DESC, oferta_id ASC
SKIP $offset
LIMIT $limite
```

Primera página:

```json
{
  "offset": 0,
  "limite": 20
}
```

Segunda página:

```json
{
  "offset": 20,
  "limite": 20
}
```

El segundo criterio de ordenamiento, `oferta_id`, hace más estable la paginación cuando varias ofertas tienen la misma fecha.

## Ejemplo 12. Usar `WITH` para separar etapas

**Objetivo:** calcular el promedio de ofertas por empresa sin mezclar niveles de agregación.

```cypher
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
WITH e, count(DISTINCT o) AS ofertas_por_empresa
RETURN
  count(e) AS empresas,
  round(avg(ofertas_por_empresa), 2) AS promedio_ofertas_por_empresa,
  min(ofertas_por_empresa) AS minimo,
  max(ofertas_por_empresa) AS maximo
```

## 5. Errores frecuentes y correcciones

### Error 1. Usar propiedades que no existen

Incorrecto:

```cypher
RETURN o.id_oferta, o.titulo, o.descripcion
```

Correcto:

```cypher
RETURN o.id_ofe_laboral, o.cargo, o.descripcion_breve
```

### Error 2. Colocar un filtro opcional en `WHERE` sin considerar los nulos

Esta consulta convierte de hecho la industria en obligatoria:

```cypher
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
OPTIONAL MATCH (i:Industria)-[:AGRUPA]->(e)
WHERE i.sector_macro = $sector
RETURN o, e, i
```

Si solo se quieren ofertas del sector, se puede usar un `MATCH` normal:

```cypher
MATCH (i:Industria)-[:AGRUPA]->(e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
WHERE i.sector_macro = $sector
RETURN o, e, i
```

Si se necesita conservar todas las ofertas y marcar la coincidencia:

```cypher
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
OPTIONAL MATCH (i:Industria)-[:AGRUPA]->(e)
RETURN
  o.id_ofe_laboral AS oferta_id,
  i.nombre AS industria,
  i.sector_macro = $sector AS coincide_sector
```

### Error 3. Multiplicar filas con varios `OPTIONAL MATCH`

Evita combinar en una misma etapa listas independientes de habilidades, herramientas y competencias. Si un requerimiento tiene varios elementos de cada clase, se generan combinaciones intermedias.

Una alternativa es recorrer todos los elementos una sola vez:

```cypher
MATCH (o:Oferta_Laboral)-[:TIENE]->(r:Requerimiento_Laboral)
      -[:REQUIERE]->(elemento)
WHERE any(etiqueta IN labels(elemento)
          WHERE etiqueta IN ['Habilidad', 'Herramienta', 'Competencia'])
WITH
  CASE
    WHEN elemento:Habilidad THEN 'habilidad'
    WHEN elemento:Herramienta THEN 'herramienta'
    WHEN elemento:Competencia THEN 'competencia'
  END AS categoria,
  elemento,
  count(DISTINCT o) AS total_ofertas
RETURN categoria, elemento, total_ofertas
ORDER BY total_ofertas DESC
```

### Error 4. Devolver nodos completos sin necesidad

Para una herramienta de agente, normalmente es preferible devolver campos explícitos:

```cypher
RETURN
  o.id_ofe_laboral AS oferta_id,
  o.cargo AS cargo,
  o.fecha_publicacion AS fecha_publicacion
```

en lugar de:

```cypher
RETURN o
```

Esto reduce el tamaño de la respuesta y estabiliza el contrato de salida.

### Error 5. Usar `DISTINCT` como solución automática

`RETURN DISTINCT` puede ocultar duplicaciones, pero no corrige un patrón mal diseñado. Primero identifica qué relación multiplica las filas y decide si debes:

- agrupar con `collect(DISTINCT ...)`;
- contar con `count(DISTINCT ...)`;
- separar etapas mediante `WITH`;
- o cambiar un patrón obligatorio por uno opcional.

## 6. Plantilla reutilizable para una herramienta del agente

Cada herramienta debería documentar su finalidad, parámetros, salida y consulta.

````markdown
### Nombre de la herramienta

**Objetivo:** explicar qué pregunta responde.

**Parámetros:**

- `desde`: fecha inicial inclusiva, formato `YYYY-MM-DD`.
- `hasta`: fecha final exclusiva, formato `YYYY-MM-DD`.
- `limite`: cantidad máxima de filas.

**Consulta:**

```cypher
MATCH ...
WHERE ...
RETURN ...
ORDER BY ...
LIMIT $limite
```

**Salida:** describir cada campo retornado.

**Consideraciones:** indicar qué nodos sin relación quedan excluidos.
````

## 7. Lista de verificación antes de aprobar una consulta

- [ ] Las etiquetas coinciden exactamente con el esquema.
- [ ] Las relaciones usan el nombre y la dirección correctos.
- [ ] Las propiedades existen en los nodos correspondientes.
- [ ] Los valores externos se envían como parámetros.
- [ ] El filtro de fechas define claramente si los límites son inclusivos o exclusivos.
- [ ] Se decidió conscientemente entre `MATCH` y `OPTIONAL MATCH`.
- [ ] Las relaciones múltiples no inflan los conteos.
- [ ] Los campos nulos se manejan con `coalesce()` cuando corresponde.
- [ ] La salida devuelve propiedades explícitas y nombres estables.
- [ ] La consulta tiene `ORDER BY` antes de paginar.
- [ ] El límite máximo está controlado por la aplicación.
- [ ] La consulta fue probada con parámetros representativos y casos sin relaciones opcionales.

## 8. Validación técnica

Antes de integrar una consulta como herramienta, se recomienda revisar su plan:

```cypher
EXPLAIN
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
RETURN count(DISTINCT o) AS total_ofertas
```

Después, medir la ejecución real en un entorno de prueba:

```cypher
PROFILE
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
RETURN count(DISTINCT o) AS total_ofertas
```

- `EXPLAIN` muestra el plan sin ejecutar la consulta.
- `PROFILE` ejecuta la consulta y muestra filas, accesos y operadores utilizados.
- No uses `PROFILE` de forma indiscriminada sobre consultas costosas en producción.

## 9. Parámetros generales de ejemplo

```json
{
  "desde": "2026-01-01",
  "hasta": "2026-09-01",
  "carrera_id": "CAR_ejemplo",
  "industria_id": "INDU_ejemplo",
  "sector": "Servicios",
  "texto": "analista de datos",
  "offset": 0,
  "limite": 20
}
```

> La aplicación debe validar que `offset` sea igual o mayor que cero y establecer un máximo razonable para `limite` antes de enviar los parámetros a Neo4j.
