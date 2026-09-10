# Ejecución en producción del extractor Cactus/ULima en una VPS

> **Recomendación:** empezar con **Playwright + Chromium headless dentro de un contenedor Docker en la VPS**. Es la opción con menor cambio funcional porque conserva el flujo actual de login, navegación, cookies y descargas, mantiene las credenciales dentro de la infraestructura propia y evita añadir un proveedor remoto. Después, probar **Browserless** solo si operar el navegador en la VPS se convierte en el problema principal. **Apify** tiene sentido si se quiere externalizar el ciclo completo de trabajos y outputs. **Bright Data** debe quedar como escalamiento condicionado a bloqueos anti-bot comprobados. **HTTP-only** debe ser un experimento de paridad, no un reemplazo asumido.

No se ejecutó una prueba real contra Cactus/ULima ni se usaron credenciales. Por tanto, ninguna opción queda declarada compatible con Cactus sin una prueba controlada.

## 1. Qué ocurre hoy

**Evidencia local revisada:** `backend/agente/normalizador/silabos/fuente_cactus.py`, `backend/agente/normalizador/ejecuciones.py`, `backend/README.md` y `backend/pyproject.toml`.

- `CactusExtractor` define `headless=False` y el backend conserva ese valor por defecto mediante `NORMALIZADOR_CACTUS_HEADLESS=false`. Por eso aparece una ventana: el código está solicitando una sesión visible; no es una exigencia inherente de Cactus. El [código de Cactus](../backend/agente/normalizador/silabos/fuente_cactus.py) intenta primero `channel="chrome"` y luego un navegador de Playwright como fallback.
- El extractor usa un perfil persistente por ejecución, inicia sesión con Playwright, navega el DOM y acepta descargas. Luego captura cookies simples y las entrega a `requests.Session` para descargar páginas y adjuntos; conserva un fallback de descarga mediante el navegador y limita los workers HTTP a tres.
- El backend recibe usuario y contraseña para esa ejecución, no los incorpora al manifiesto ni a los reportes, limpia las referencias en memoria y purga el perfil temporal al finalizar. Esto reduce exposición, pero logs, trazas y archivos temporales deben seguir tratándose como sensibles. Véanse [ejecuciones.py](../backend/agente/normalizador/ejecuciones.py) y la [documentación operativa](../backend/README.md).
- El proyecto ya declara `playwright` y `requests`, pero no `httpx`; la base es Python 3.11 o superior. Véase [pyproject.toml](../backend/pyproject.toml).

La documentación oficial de [Playwright para Python](https://playwright.dev/python/docs/library) indica que el navegador se ejecuta headless por defecto y que `headless=False` muestra la interfaz. La guía de [navegadores](https://playwright.dev/docs/browsers) distingue el Chromium distribuido por Playwright de los canales de Chrome instalados localmente. Aquí la visibilidad se explica, concretamente, por la combinación de `headless=False` y `channel="chrome"`.

## 2. Comparación ejecutiva

| Opción | Encaje con el código actual | Credenciales y trabajos/outputs | Límites y precio observado | Cambio estimado |
|---|---|---|---|---|
| **Playwright/Chromium headless + Docker** | **Alto; primera opción.** Mantiene el flujo actual y solo cambia el modo de ejecución. | Credenciales, cookies, perfil, ZIP e informes permanecen en la VPS. Se conserva el pipeline existente. | Sin tarifa BaaS; coste de VPS, RAM/CPU, almacenamiento y operación. La tarifa depende del proveedor de VPS y no se cotiza aquí. | **Código XS/S; infraestructura M.** Imagen, secretos, volumen temporal, health checks, logs y capacidad. |
| **Browserless BaaS** | Medio; segunda opción si la operación del navegador local es el cuello de botella. Requiere adaptar la creación/cierre del contexto persistente a una conexión WebSocket remota. | Credenciales de Cactus viajan a un navegador administrado por un tercero; el backend sigue guardando outputs. Browserless entrega sesiones, no reemplaza automáticamente el manifiesto/ZIP del backend. | [Precios](https://www.browserless.io/pricing), observados **2026-08-28** con facturación anual: Free $0/1.000 unidades, 2 concurrentes, 2 min; Prototyping $25/mes, 20.000 unidades, 15 min; Starter $140/mes, 180.000, 30 min; Scale $350/mes, 500.000, 60 min. Una unidad equivale a hasta 30 s de conexión; hay sobrecostos por uso. | **Código M; infraestructura S/M.** |
| **Apify Actor + Playwright** | Medio; útil si se quiere externalizar ejecución, programación, reintentos, observabilidad y almacenamiento. No es un cambio pequeño del backend actual. | Actor remoto con estados de ejecución; Dataset para datos tabulares y Key-value store para archivos/outputs. Las credenciales deben ser inputs secretos y nunca logs/datasets. | [Precios](https://apify.com/pricing), observados **2026-08-28**: Free $0 con $5 de consumo; Starter $29/mes + uso; Scale $199/mes + uso; Business $999/mes + uso. La unidad de cómputo es 1 GB-hora; almacenamiento, proxy y transferencia se cobran aparte. Memoria, timeout y concurrencia dependen del plan. | **Código L/XL; infraestructura M/L.** Actor, build versionado, API de ejecución, polling/webhook, descarga de outputs y rehidratación del pipeline. |
| **Bright Data Browser API** (antes Scraping Browser) | Bajo como primera opción; solo si aparecen bloqueos anti-bot reales. | Chrome remoto por WebSocket; no hay conexión REST para este producto. La FAQ dice que por defecto bloquea introducir contraseñas; el acceso a login privado requiere revisión/KYC y aprobación. Eso es especialmente importante porque Cactus requiere usuario y contraseña. El cliente debe conservar la sesión, descargar los adjuntos y producir el manifest/ZIP del backend; no es un orquestador de jobs/outputs equivalente a Apify. | [Producto y precios](https://brightdata.com/products/scraping-browser?hs_signup=1), observados **2026-08-28**: PAYG $8/GB; $499/mes incluye 71 GB a $7/GB; $999/mes incluye 166 GB a $6/GB; $1.999/mes incluye 399 GB a $5/GB. Una sesión solo puede navegar múltiples URLs del mismo dominio. | **Código M/L; infraestructura S/M.** |
| **HTTP-only: Requests/HTTPX + parser** | Bajo hoy; candidato a experimento posterior. El extractor ya usa Requests después del login, pero Playwright aún descubre/navega y conserva un fallback. | Todo queda en la VPS y no hay coste de navegador remoto. Los trabajos/outputs actuales pueden conservarse, pero hay que reimplementar y demostrar login, navegación, paginación, sesión y parsing. | [Requests](https://requests.readthedocs.io/en/stable/user/advanced/) ofrece sesiones/cookies/streaming; [HTTPX](https://www.python-httpx.org/) ofrece API sync/async, cookies, streaming y timeouts. No hay límites de navegador, pero sí los del sitio y del servidor. | **Código M/L; runtime S.** El parser y la paridad funcional son el riesgo, no el consumo. |

Los límites de Browserless están documentados en sus [buenas prácticas](https://docs.browserless.io/baas/best-practices); sus sesiones remotas tienen duración máxima, concurrencia y coste por unidades. Apify documenta que cada run vive en un contenedor con recursos y storages propios en [runs y builds](https://docs.apify.com/actors/running/runs-and-builds), y que input, timeout y outputs se gestionan en [input/output](https://docs.apify.com/actors/running/input-and-output). Los precios son una fotografía del **2026-08-28**, no una promesa de tarifa futura.

## 3. Evaluación por opción

### A. Playwright/Chromium headless en Docker — opción recomendada

La ruta de menor riesgo es activar `NORMALIZADOR_CACTUS_HEADLESS=true` y empaquetar una versión fijada de Playwright y Chromium. La [guía oficial de Docker de Playwright](https://playwright.dev/python/docs/docker) recomienda, para crawling de sitios no confiables, usuario no root y un perfil seccomp; también recomienda `--init` para evitar procesos zombie y `--ipc=host` para reducir fallos de memoria de Chromium. Ejecutar Chromium como root desactiva su sandbox. La imagen y el paquete deben estar alineados por versión; no conviene depender de `latest`.

**Diseño inicial:** un worker por ejecución, perfil aislado por ejecución, volumen temporal con permisos restrictivos, secretos inyectados por el mecanismo de secretos de la VPS, sin puerto de depuración expuesto y con red/egress controlados. La [API de contexto persistente](https://playwright.dev/python/docs/api/class-browsertype) confirma que cookies y almacenamiento local viven en el `user_data_dir`; no se debe reutilizar simultáneamente el mismo perfil.

**Riesgo principal:** la imagen puede no tener exactamente el Chrome/canal esperado o Cactus puede comportarse distinto sin UI. Se resuelve con una prueba real, no con una inferencia de la documentación.

### B. Browserless BaaS — segundo escalón

Browserless permite conectar Playwright a navegadores administrados por WebSocket y cambiar la infraestructura local por una URL remota; véanse [BaaS](https://docs.browserless.io/baas/start), [conexión Playwright](https://docs.browserless.io/examples/playwright-connection) y [patrones de URL](https://docs.browserless.io/baas/connection-url-patterns). Es atractivo si no se quiere parchear Chromium, dimensionar RAM o mantener un pool.

La adaptación no es solo cambiar una URL: el código actual crea un contexto persistente local y obtiene su página. En remoto hay que definir qué contexto/browser devuelve el proveedor, cómo se cierra, qué ocurre si se corta el WebSocket y dónde se guardan los archivos. Browserless recomienda cerrar siempre la sesión y advierte que cada espera de Playwright es un round-trip; usar una región cercana importa. El [manejo de sesiones](https://docs.browserless.io/baas/session-management) también permite conservar cookies/estado, lo que puede ampliar el riesgo de retención.

El token va en la URL de conexión; la [documentación de API keys](https://docs.browserless.io/overview/api-keys) exige mantenerlo fuera del código, logs y cliente. Además, con un BaaS las credenciales de Cactus se introducen en infraestructura de terceros: debe existir aprobación de seguridad y una política explícita de retención.

### C. Apify Actors — cuando el problema es el trabajo completo

Apify es más que un navegador remoto: un Actor se construye en una imagen Docker, cada run tiene estado, logs y storages, y puede ejecutarse de forma síncrona o asíncrona mediante API; véanse el [SDK Python](https://docs.apify.com/sdk/python/docs/overview), [API](https://docs.apify.com/integrations/api) y [runs/builds](https://docs.apify.com/actors/running/runs-and-builds). Esto encaja si el producto necesita agenda, reintentos, monitoreo y retención de outputs fuera de la VPS.

La integración tendría que empaquetar el extractor, declarar un input, publicar una build fijada, mapear el run a la ejecución local y recuperar ZIP/reportes. Para datos estructurados usaría Dataset y para archivos Key-value store. Las credenciales deben declararse como `isSecret: true`, según la [documentación de secret input](https://docs.apify.com/actors/development/actor-definition/input-schema/secret-input); aun así, no deben aparecer en logs, outputs ni errores.

### D. Bright Data — únicamente ante anti-bot demostrado

La [FAQ oficial](https://docs.brightdata.com/scraping-automation/scraping-browser/faqs) llama actualmente al producto **Browser API** y documenta conexión Playwright por WebSocket, rotación de IP/fingerprint y manejo de CAPTCHA como capacidades del proveedor. También documenta dos límites decisivos: no hay método REST de conexión y, por defecto, se impide introducir contraseñas; el uso de login privado requiere aprobación de cumplimiento. Por eso no debe seleccionarse para Cactus solo porque “desbloquea” sitios: primero hay que observar un bloqueo reproducible en el navegador propio y confirmar por escrito que el flujo autenticado es permitido.

La página del producto enumera HTML crudo y capturas como formatos de salida, no un contrato de ejecución/almacenamiento que reemplace el manifest, el ZIP y los reportes de este backend. La integración tendría que descargar los PDF/DOCX y conservar el pipeline local.

### E. HTTP-only — experimento con criterio de salida

La evidencia local es prometedora pero insuficiente: Requests ya reutiliza las cookies del navegador para pedir el HTML de cursos y descargar adjuntos. Eso demuestra que **parte** del flujo es HTTP, no que todo el login y la navegación lo sean.

Antes de retirar Playwright, ejecutar una prueba shadow con datos reales y sin exponer credenciales:

1. Reproducir el login HTTP, incluidos campos ocultos, cookies, redirecciones y expiración de sesión.
2. Confirmar que las respuestas contienen carrera, periodo, cursos, identificadores y paginación/expansión sin ejecutar JavaScript.
3. Para cada identificador, reproducir `/0/{unid}?OpenDocument`, resolver `$FILE`, verificar tipo PDF/DOCX, bytes, tamaño, hash y ausencia de HTML de login.
4. Comparar contra Playwright cobertura, cantidad de cursos, adjuntos, errores, duración y reintentos en varias carreras y periodos.
5. Probar sesión vencida, relogin, respuestas parciales, concurrencia de 1–3 workers, rate limits, CAPTCHA y cualquier token/estado generado por JavaScript.
6. Mantener Playwright como fallback y exigir varias ejecuciones equivalentes antes de cambiar producción.

Si falla cualquier paso de login, descubrimiento, paginación o cobertura, HTTP-only queda como optimización parcial —por ejemplo, solo para descargas— y no como reemplazo.

## 4. Plan de implementación recomendado

1. **Definir baseline:** registrar, sin guardar secretos, cobertura, cantidad de archivos, hashes, duración, errores y estado final del pipeline actual.
2. **Construir la primera prueba en Docker local/VPS:** Chromium fijado, usuario no root, seccomp, `--init`, `--ipc=host`, perfil por ejecución y `NORMALIZADOR_CACTUS_HEADLESS=true`.
3. **Validar Cactus de extremo a extremo:** login, carreras/periodos, paginación, PDFs/DOCX, sesión vencida, cancelación, limpieza y generación de reportes/ZIP. Esta es la prueba que falta; no se ejecutó en esta investigación.
4. **Operar con límites conservadores:** un worker de navegador por ejecución y hasta los tres workers HTTP existentes; añadir métricas de RAM, CPU, tiempos, cobertura y causa de fallo, con redacción de credenciales.
5. **Reevaluar proveedor remoto con el baseline:** probar Browserless si el coste operativo de la VPS supera su coste y riesgo; probar Apify si se necesita orquestación/outputs administrados; probar Bright Data solo después de un bloqueo anti-bot verificable y aprobación de login autenticado.
6. **Probar HTTP-only en shadow:** exigir paridad de cobertura y rollback antes de retirar Playwright.

## 5. Decisión de seguridad

- **Local Docker:** es el límite de confianza más pequeño. Secretos en el secret manager de la VPS; nunca en imagen, manifiesto, ZIP, query string o logs. El perfil temporal debe ser único, restringido y eliminado al terminar.
- **Browserless:** proteger el token de URL y evitar logs de la URL completa; cerrar sesiones y no activar persistencia/replay salvo necesidad. Las [sesiones persistentes](https://docs.browserless.io/baas/session-management/persisting-state) pueden conservar cookies y almacenamiento local.
- **Apify:** usar input secreto y token de API en el header `Authorization`; la API recomienda no reutilizar tokens entre servicios y rotarlos. No copiar usuario/contraseña a Dataset, KVS, logs ni mensajes de error.
- **Bright Data:** tratar usuario/contraseña de zona y el endpoint WebSocket como secretos; además, resolver antes la restricción de password/KYC. No enviar credenciales de Cactus hasta tener autorización explícita.
- **HTTP-only:** reduce superficie de navegador remoto, pero un parser incorrecto puede producir una extracción silenciosamente incompleta; la cobertura es un requisito de seguridad e integridad, no solo de rendimiento.

## Límites de esta investigación

- No se modificó código ni configuración, no se ejecutaron tests, builds ni instalaciones y no se leyó `backend/.env`.
- Solo se revisaron los cuatro archivos locales indicados.
- Las recomendaciones son inferencias basadas en esa evidencia local y documentación oficial; no sustituyen una prueba credential-safe contra Cactus/ULima.
- Los precios se observaron el **2026-08-28** y pueden cambiar; el precio real también depende de consumo, almacenamiento, proxy, transferencia y operación.

## Fuentes oficiales consultadas

- **Playwright:** [Python library](https://playwright.dev/python/docs/library), [Docker](https://playwright.dev/python/docs/docker), [browsers/channels](https://playwright.dev/docs/browsers), [persistent context](https://playwright.dev/python/docs/api/class-browsertype).
- **Browserless:** [BaaS](https://docs.browserless.io/baas/start), [Playwright connection](https://docs.browserless.io/examples/playwright-connection), [connection URLs](https://docs.browserless.io/overview/connection-urls), [best practices](https://docs.browserless.io/baas/best-practices), [session management](https://docs.browserless.io/baas/session-management), [API keys](https://docs.browserless.io/overview/api-keys), [pricing](https://www.browserless.io/pricing).
- **Apify:** [Python SDK](https://docs.apify.com/sdk/python/docs/overview), [Crawlee/Playwright](https://docs.apify.com/sdk/python/docs/guides/crawlee), [input/output](https://docs.apify.com/actors/running/input-and-output), [runs/builds](https://docs.apify.com/actors/running/runs-and-builds), [secret input](https://docs.apify.com/actors/development/actor-definition/input-schema/secret-input), [API](https://docs.apify.com/integrations/api), [pricing](https://apify.com/pricing).
- **Bright Data:** [FAQ de Browser API](https://docs.brightdata.com/scraping-automation/scraping-browser/faqs), [producto/precios](https://brightdata.com/products/scraping-browser?hs_signup=1), [pricing](https://brightdata.com/pricing).
- **HTTP y parsing:** [Requests](https://requests.readthedocs.io/en/stable/user/advanced/), [HTTPX](https://www.python-httpx.org/), [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/), [Crawlee crawlers](https://docs.apify.com/sdk/python/docs/guides/crawlee).

## Lecciones del topic GitHub scraper

**Fecha de revisión: 2026-08-28.**

### Conclusión ejecutiva

La evidencia oficial no justifica migrar CIAR/Cactus completo a otro framework. La estrategia de menor consumo es **HTTP-first con Playwright acotado**: conservar Playwright para login, navegación, estado de sesión y cualquier tramo cuya paridad HTTP no esté demostrada; usar HTTP para las descargas y rutas repetitivas que ya funcionan con las cookies capturadas; y mantener límites estrictos, checkpoints y un worker aislado. Crawlee, Scrapy, `scrapy-playwright` y Colly aportan patrones reutilizables, no una razón suficiente para reescribir el adaptador actual. Firecrawl y Maxun tienen un alcance de plataforma mayor que el problema de una extracción autenticada de Cactus, pero la evidencia revisada no permite convertir esa observación en un benchmark de CPU/RAM.

### Tabla comparativa: qué aprovechar y qué no copiar

| Proyecto | Patrón aprovechable | No copiar para CIAR en esta etapa |
|---|---|---|
| [apify/crawlee-python](https://github.com/apify/crawlee-python) | Sus [crawlers HTTP](https://crawlee.dev/python/docs/guides/http-crawlers) evitan navegador cuando el servidor no requiere JavaScript; [PlaywrightCrawler](https://crawlee.dev/python/docs/guides/playwright-crawler) queda para páginas dinámicas. La API de [concurrencia](https://crawlee.dev/python/api/class/ConcurrencySettings), los [reintentos](https://crawlee.dev/python/docs/guides/error-handling), el [SessionPool](https://crawlee.dev/python/docs/guides/session-management), las cookies y el [almacenamiento](https://crawlee.dev/python/docs/guides/storage-clients) ofrecen modelos claros para límites, estado y reanudación. | No adoptar todo Crawlee ni sus defaults amplios: su API contempla concurrencia, rotación de sesiones, colas y storages para crawls generales. En Cactus conviene copiar la separación HTTP/navegador, un pool de una sesión y checkpoints locales, manteniendo el pipeline Python existente. |
| [scrapy/scrapy](https://github.com/scrapy/scrapy) + [scrapy-playwright](https://github.com/scrapy-plugins/scrapy-playwright) | El [scheduler](https://docs.scrapy.org/en/latest/topics/scheduler.html) y [`JOBDIR`](https://docs.scrapy.org/en/master/topics/jobs.html) materializan cola, deduplicación y reanudación. El handler HTTP normal procesa las requests salvo que se marque `playwright=True`; los [settings de concurrencia](https://docs.scrapy.org/en/master/topics/settings.html) permiten fijar límites por dominio. El plugin expone `PLAYWRIGHT_MAX_CONTEXTS`, `PLAYWRIGHT_MAX_PAGES_PER_CONTEXT` y `PLAYWRIGHT_ABORT_REQUEST`; el último sirve para descartar imágenes, fuentes u otros recursos solo después de comprobar que no son necesarios. | No introducir una migración a spiders/Scrapy solo para obtener una cola. El scheduler, `JOBDIR` y el cierre explícito de páginas son patrones; la plataforma completa añadiría una refactorización al adaptador y otro modelo operativo. Su [`RetryMiddleware`](https://docs.scrapy.org/en/latest/topics/downloader-middleware.html) tampoco sustituye por sí solo una política de backoff específica de CIAR. |
| [gocolly/colly](https://github.com/gocolly/colly) | Colly es un framework HTTP de Go; su [límite por dominio](https://go-colly.org/docs/examples/parallel/) permite fijar paralelismo pequeño y su documentación cubre [cookies/URLs persistentes y almacenamiento](https://go-colly.org/docs/best_practices/crawling/). Es una buena referencia para HTTP-only, cookie jar, cola/cache y límites por origen. | No reescribir Cactus en Go como optimización prematura. El backend actual, el contrato de ejecución y la validación están en Python, y la cobertura de login/DOM de Cactus no está probada como HTTP-only. El coste de mantener otro runtime y demostrar paridad supera la evidencia disponible sobre ahorro para este caso. |
| [firecrawl/firecrawl](https://github.com/firecrawl/firecrawl) | La idea general de separar API, jobs y workers puede inspirar un worker de extracción desacoplado. | No copiar la plataforma. Su [README oficial](https://raw.githubusercontent.com/firecrawl/firecrawl/main/README.md) cubre búsqueda, scrape, crawl, map, batch, acciones de navegador, agentes y extracción de medios; su [self-host oficial](https://raw.githubusercontent.com/firecrawl/firecrawl/main/SELF_HOST.md) y [Compose](https://raw.githubusercontent.com/firecrawl/firecrawl/main/docker-compose.yaml) muestran API/workers, Playwright, Redis, RabbitMQ y NuQ PostgreSQL, con FoundationDB opcional. Es un alcance operativo mayor que una ejecución Cactus en la VPS; los límites de recursos del Compose son del despliegue de Firecrawl, no benchmarks de CIAR. |
| [getmaxun/maxun](https://github.com/getmaxun/maxun) | Separar definición de extracción, ejecución y programación es un patrón conceptual útil si CIAR necesita más adelante una cola administrada. | No adoptar la plataforma no-code completa. El [README oficial](https://raw.githubusercontent.com/getmaxun/maxun/develop/README.md) incluye recorder con IA, scraping, crawling, búsqueda, SDK, CLI, schedules, integraciones, MCP y self-hosting. La evidencia confirma mayor alcance funcional y operativo, no un consumo mínimo ni un benchmark que justifique usarlo como backend de Cactus. |

**Señales visibles de mantenimiento.** En la página oficial del topic se observaron actualizaciones visibles el 2026-08-28 para Crawlee y Firecrawl, el 2026-08-27 para Maxun y el 2026-08-14 para Colly. Las páginas oficiales también muestran historial de commits/automatizaciones; la documentación de Crawlee mostraba la versión 1.9 y páginas actualizadas el 2026-08-25, mientras Scrapy exponía documentación 2.18.0. Son señales de actividad observada en esa fecha, no una evaluación de calidad o de idoneidad. Las estrellas se trataron solo como contexto del topic y no como criterio de decisión.

### Comparación enfocada para una VPS

- **Crawlee:** distingue explícitamente crawler HTTP y navegador. Su `ConcurrencySettings` permite fijar `min_concurrency`, `max_concurrency` y `max_tasks_per_minute`; la API documenta valores generales como `max_concurrency=100` y `desired_concurrency=10`, demasiado amplios como guardrail inicial para una VPS pequeña. La gestión de sesiones/cookies y el storage persistente son patrones útiles, pero la persistencia de cookies autenticadas debe seguir siendo temporal y secreta.
- **Scrapy + scrapy-playwright:** es el modelo más claro de scheduler HTTP-first: la request común usa el handler HTTP y solo la request marcada usa Playwright. Scrapy documenta `CONCURRENT_REQUESTS=16` como default general; `PLAYWRIGHT_MAX_CONTEXTS` sin configurar puede quedar ilimitado y `PLAYWRIGHT_MAX_PAGES_PER_CONTEXT` se relaciona con `CONCURRENT_REQUESTS`; por eso ambos deben declararse, no heredarse. `playwright_include_page=True` exige cerrar la página en callbacks/errbacks para no agotar el límite. `JOBDIR` es una buena referencia para checkpoints, con la salvedad oficial de que la reanudación requiere un cierre limpio y un directorio por job.
- **Colly:** muestra el patrón HTTP-only más pequeño de los comparados: `LimitRule` por dominio, cookies/URLs visitadas y backend de storage configurable. La propia documentación advierte que cookies y URLs se guardan en memoria por defecto y que keep-alive puede elevar la presión sobre descriptores en trabajos largos; son recordatorios útiles para definir límites y ciclo de vida. El ahorro potencial no compensa por sí solo una reescritura Go sin una prueba de paridad Cactus.

### Qué ya hace el código actual

- `fuente_cactus.py` ya usa un contexto persistente de Playwright por ejecución, la página activa observada para login/DOM, fallback de canal Chrome a Chromium, y captura cookies del navegador para crear sesiones `requests` independientes en los workers HTTP. El código/README dejan `headless=False` como default configurable, no como requisito de producción. El límite actual de descargas es de hasta 3 workers; también existen hasta 4 intentos de descarga, timeouts diferenciados, rondas acotadas de recuperación de sesión, límites de bytes para documentos/adjuntos y un `.checkpoint.json` que evita reutilizar archivos ausentes.
- `ejecuciones.py` ya mantiene un único job de extracción/normalización activo por proceso mediante un `ThreadPoolExecutor` con `max_workers=1`; dentro del extractor, las descargas HTTP independientes tienen su propio techo. También purga el perfil y temporales al terminar, conserva los artefactos de auditoría y bloquea la publicación si la cobertura queda incompleta.
- Esto confirma que no hace falta añadir un framework para obtener los primeros ahorros. También muestra límites futuros: el backoff actual es incremental, no exponencial; el checkpoint se escribe como una lista y no como una transacción por curso; y el filtrado de recursos del navegador no está establecido como política general. Esas observaciones son oportunidades futuras, no cambios aplicados en esta investigación.

### Recomendación específica para CIAR

Mantener la implementación Python actual y explicitar una frontera de transporte:

1. **Playwright para autenticación y cobertura:** login, selección de periodo/carrera/ciclos, navegación DOM y fallback de descarga. No retirar Playwright hasta comparar, en modo shadow, cantidad de cursos, archivos, tipos, errores y cobertura completa contra ejecuciones reales de Cactus.
2. **HTTP-first para lo comprobado:** descargar PDF/DOCX y endpoints repetitivos con las cookies de la sesión, sin trasladar objetos Playwright a hilos. Si una ruta HTTP no conserva cobertura, vuelve al navegador y queda registrada como excepción.
3. **Worker aislado:** conservar un único job de normalización activo por proceso y límites de CPU/RAM del contenedor/VPS; aumentar throughput con una cola de jobs, no creando más contextos o páginas por curso.
4. **No adoptar Crawlee, Scrapy, Colly, Firecrawl ni Maxun como dependencia inmediata.** Reconsiderar Crawlee/Scrapy si CIAR pasa a múltiples dominios, muchas colas o spiders reutilizables; reconsiderar Colly solo si existe una decisión independiente de operar un backend Go. Esa es una inferencia arquitectónica para CIAR, no una propiedad afirmada por los proyectos.

### Plan de bajo consumo (guardrails de diseño, no benchmarks)

Estos valores son límites conservadores para probar y ajustar; no representan mediciones de rendimiento:

1. **Navegador:** un contexto/sesión Playwright persistente por ejecución y una sola página activa; cero paralelismo Playwright por curso. Reutilizar el perfil temporal solo durante la ejecución y eliminarlo al cerrar.
2. **HTTP:** empezar con concurrencia 1 por origen Cactus y permitir como máximo 3 en el adaptador actual. No aumentar ese techo sin evidencia de cobertura, estabilidad y capacidad de la VPS.
3. **Reintentos:** futuro objetivo de hasta 3 reintentos además del intento inicial, solo para timeout, conexión, 429, 5xx o sesión recuperable; backoff exponencial acotado de 1/2/4 segundos, con tope de 8 segundos. No reintentar errores deterministas de parseo o formato; hacer como máximo una reloginación por ronda de sesión. El código actual usa hasta cuatro intentos con espera incremental, así que este punto es recomendación futura.
4. **Timeouts:** mantener como guardrail 30 s para login/navegación y documento, 60 s para adjunto, y fallar cerrado si se exceden. Completar los `goto`/esperas que todavía no tienen un timeout explícito; no asumir que un default del framework es adecuado.
5. **Checkpoints:** guardar después de cada curso exitoso el identificador, URL, extensión, tamaño, hash y estado; escribir mediante archivo temporal + reemplazo atómico. Al reanudar, validar existencia y metadatos antes de saltar el curso. El checkpoint actual prueba existencia de archivos, pero no ofrece todavía este nivel de atomicidad/metadatos.
6. **Recursos:** solicitar y conservar solo PDF/DOCX en la fase de descarga. En Playwright, abortar imágenes, fuentes, media y analítica únicamente después de comprobar que login y navegación no las necesitan; nunca bloquear a ciegas CSS/JS, redirects o respuestas de autenticación.
7. **Estado y seguridad:** una sesión autenticada por ejecución, sin persistir cookies en Dataset/KVS/logs; métricas sin credenciales (conteos, status, tamaño, duración, causa de reintento) y limpieza aun cuando el job falle o se cancele.

### Evidencia, inferencia y límites

- **Evidencia oficial:** los proyectos documentan HTTP sin navegador, scheduler/cola, límites de concurrencia, reintentos, sesiones/cookies, storage, descarte de recursos y contextos/páginas Playwright; Firecrawl y Maxun documentan además un alcance de plataforma significativamente más amplio.
- **Inferencia para CIAR:** por tratarse de un flujo autenticado, de un origen conocido, con pipeline Python existente y Playwright ya integrado, copiar esos patrones dentro del adaptador reduce riesgo y consumo sin pagar una migración de framework.
- **Unknowns:** no se ejecutaron Cactus, pruebas, builds, instalaciones ni mediciones en VPS; no está demostrada la paridad HTTP de login, paginación, ciclos, sesión vencida ni cobertura de archivos; tampoco está validado qué recursos puede abortar el navegador. Por tanto, ningún límite anterior es un benchmark ni autoriza retirar Playwright.

### Fuentes oficiales consultadas en esta ampliación

- [GitHub topic: scraper](https://github.com/topics/scraper).
- [Crawlee Python](https://github.com/apify/crawlee-python), [HTTP crawlers](https://crawlee.dev/python/docs/guides/http-crawlers), [Playwright crawler](https://crawlee.dev/python/docs/guides/playwright-crawler), [concurrency](https://crawlee.dev/python/api/class/ConcurrencySettings), [sessions](https://crawlee.dev/python/docs/guides/session-management), [cookies](https://crawlee.dev/python/docs/guides/cookie-management), [storage](https://crawlee.dev/python/docs/guides/storage-clients) y [error handling](https://crawlee.dev/python/docs/guides/error-handling).
- [Scrapy](https://github.com/scrapy/scrapy), [scheduler](https://docs.scrapy.org/en/latest/topics/scheduler.html), [jobs](https://docs.scrapy.org/en/master/topics/jobs.html), [settings](https://docs.scrapy.org/en/master/topics/settings.html), [retries](https://docs.scrapy.org/en/latest/topics/downloader-middleware.html) y [scrapy-playwright README oficial](https://raw.githubusercontent.com/scrapy-plugins/scrapy-playwright/main/README.md).
- [Colly](https://github.com/gocolly/colly), [documentación oficial](https://go-colly.org/docs/), [paralelismo](https://go-colly.org/docs/examples/parallel/) y [configuración/ciclo de vida](https://go-colly.org/docs/best_practices/crawling/).
- [Firecrawl README](https://raw.githubusercontent.com/firecrawl/firecrawl/main/README.md), [self-host](https://raw.githubusercontent.com/firecrawl/firecrawl/main/SELF_HOST.md) y [Compose oficial](https://raw.githubusercontent.com/firecrawl/firecrawl/main/docker-compose.yaml).
- [Maxun README](https://raw.githubusercontent.com/getmaxun/maxun/develop/README.md) y [repositorio oficial](https://github.com/getmaxun/maxun).
