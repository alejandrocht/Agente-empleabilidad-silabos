# Memoria durable asíncrona

Después de que el inspector acepta una respuesta, CIAR actualiza primero la memoria corta
acotada y aislada por usuario y conversación. Esa memoria es la fuente inmediata de verdad para
la siguiente pregunta, incluso si la escritura durable todavía no terminó.

La extracción de memoria larga se copia a un `DurableMemoryJob` inmutable y se entrega a una cola
en proceso acotada. Un único worker supervisado procesa los jobs con reintentos y backoff
limitados; la cola se inicia de forma perezosa, rechaza duplicados por `turn_key`, y registra
éxitos, fallos y drops por saturación o agotamiento de reintentos. El payload se redacciona y
limita antes de salir del hilo de la petición, y no se expone en la API ni en logs.

El modelo es **at-least-once** y de consistencia eventual: un job puede reintentarse, y una caída
del proceso o una cola llena puede descartar la escritura durable después de que el usuario haya
recibido una respuesta válida. La idempotencia durable por `turn_key` evita duplicar una extracción
aceptada. Una falla durable nunca sustituye la respuesta pública.

Los tests pueden inyectar `MemoryWriter` o `DurableMemoryQueue` y llamar `drain()` para esperar de
forma determinista. No se requiere Redis ni otro servicio para este slice.

## Shutdown and retry policy

Shutdown first transitions the queue to `closing`, cancels queued jobs, and waits only
for the configured bounded timeout. If an active writer is still running, shutdown
returns an explicit deferred state and the shared repository remains open. A later
shutdown call must observe worker termination before the repository/driver is closed;
the queue cannot accept new jobs while deferred and a completed queue is not reused.

Retries are limited to explicitly classified Neo4j transport or transient transaction
errors (`ServiceUnavailable`, `SessionExpired`, and `TransientError`). Authentication
and authorization failures are terminal, as are unclassified exceptions. Backoff is
bounded and exponential within the configured attempt limit.
