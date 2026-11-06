# Research — harden-normalizer-reliability

## Research status

- Selected classes: official documentation and open web
- Completion: complete
- Retrieved at: 2026-09-14T23:00:29Z
- External runtime calls: documentation/search tools only; no live LLM application call, Neo4j connection, LangSmith call, browser session, or paid project API was used
- Repository versions considered: Python >=3.11, FastAPI lock 0.141.1, Starlette lock 1.6.0, Neo4j Python driver lock 6.2.0, langchain-openai lock 1.6.0

## Tool-call record

| ID | Tool | Exact research operation | Result |
| --- | --- | --- | --- |
| T1 | `web_search` | Three queries for FastAPI router/request boundaries, Starlette upload/body limits, and Neo4j transaction/idempotency guidance; `includeContent=true` | response `mu1ugwji2s9wz2` |
| T2 | `web_search` | Three queries for OpenAI structured output/prompt injection, instruction hierarchy, and Python atomic file replacement | response `mu1uhcdsidvbe1` |
| T3 | `source_check` | Compound FastAPI router/client-host/TrustedHost claim | `unclear`, response `mu1uhp059lknrk` |
| T4 | `source_check` | Compound Starlette UploadFile/body-limit claim | `unclear`, response `mu1uhp952m0x2r` |
| T5 | `source_check` | Compound Neo4j transaction/local-history claim | `unclear`, response `mu1uhs31arjq6r` |
| T6 | `fetch_content` | FastAPI APIRouter, FastAPI direct Request, Starlette Requests, Neo4j transactions, OpenAI prompt injection, Python `os` docs | response `mu1uhzntarmv88`; Starlette DNS and OpenAI 403 prevented direct fetch for those two URLs |
| T7 | `source_check` | Narrow FastAPI router dependency claim | `unclear`, response `mu1uimdykqojh7` |
| T8 | `source_check` | Narrow FastAPI `request.client.host` claim | `unclear`, response `mu1uikqkcvboqs` |
| T9 | `source_check` | Narrow Neo4j managed-transaction retry/idempotency claim | `unclear`, response `mu1uikfy7isjm6` |
| T10 | `source_check` | Narrow OpenAI prompt-injection/untrusted-content claim | `unclear`, response `mu1uimih49bgxp` |
| T11 | `get_search_content` | Exact-passage retrieval for FastAPI dependencies/client host, Starlette body limits, Neo4j retries, Python replace/fsync, and OpenAI instruction hierarchy | passages recorded below |
| T12 | `fetch_content` | Original Starlette `docs/requests.md` from the publisher-owned GitHub repository and OpenAI's official agent-safety guide | response `mu1uln21a3zauy` |
| T13 | `get_search_content` | Exact passages from the two original documents fetched by T12 | passages recorded in S4 and S9 |

The `source_check` status is retained exactly. Direct official-documentation excerpts below support narrower facts; cross-system conclusions are labeled as design inferences rather than source claims.

## Sources and excerpts

### S1 — FastAPI APIRouter reference

- Publisher: FastAPI
- URL: <https://fastapi.tiangolo.com/reference/apirouter/>
- Version context: current documentation; repository locks FastAPI 0.141.1
- Retrieved through: T1, T6, T11
- Exact excerpt: “A list of dependencies (using `Depends()`) to be applied to all the path operations in this router.”

### S2 — FastAPI direct Request access

- Publisher: FastAPI
- URL: <https://fastapi.tiangolo.com/advanced/using-request-directly/>
- Version context: current documentation; repository locks FastAPI 0.141.1
- Retrieved through: T1, T6, T11
- Exact excerpt: “For that you need to access the request directly.” The example assigns `client_host = request.client.host`.

### S3 — FastAPI/Starlette TrustedHost middleware

- Publisher: FastAPI, documenting Starlette middleware
- URL: <https://fastapi.tiangolo.com/advanced/middleware/>
- Version context: current documentation
- Retrieved through: T1
- Exact excerpt: “Enforces that all incoming requests have a correctly set `Host` header, in order to guard against HTTP Host Header attacks.”
- Design implication: TrustedHost is not a substitute for checking the peer address in `request.client.host` when the selected contract is loopback-only.

### S4 — Starlette Requests and upload limits

- Publisher: Starlette
- URLs:
  - <https://www.starlette.io/requests/>
  - <https://raw.githubusercontent.com/Kludex/starlette/master/docs/requests.md>
- Version context: current publisher-owned documentation source; repository locks Starlette 1.6.0
- Retrieved through: T1, T11, T12, and T13; the rendered documentation host failed DNS resolution, so the original documentation source was fetched from Starlette's official repository
- Exact excerpt: “uploaded files are spooled to temporary storage and are not limited by `max_part_size`.”
- Exact excerpt: “To limit the complete request body, including uploaded files and multipart encoding overhead, configure `max_body_size` on the application, router, mount, or route, or use `RequestBodyLimitMiddleware`.”

### S5 — FastAPI UploadFile reference/tutorial

- Publisher: FastAPI
- URLs:
  - <https://fastapi.tiangolo.com/reference/uploadfile/>
  - <https://fastapi.tiangolo.com/tutorial/request-files/>
- Version context: current documentation; repository locks FastAPI 0.141.1
- Retrieved through: T1, T4
- Exact excerpt: UploadFile uses “a spooled file” stored in memory up to a limit and then on disk, and exposes a `SpooledTemporaryFile` through `.file`.

### S6 — Neo4j Python driver transactions

- Publisher: Neo4j
- URL: <https://neo4j.com/docs/python-manual/current/transactions/>
- Version context: current Python driver manual; repository locks Neo4j driver 6.2.0
- Retrieved through: T1, T5, T6, T9, T11
- Exact excerpt: “A transaction is a unit of work that is either committed in its entirety or rolled back on failure.”
- Exact excerpt: “The driver automatically retries to run a failed transaction if the failure is deemed to be transient.”
- Exact excerpt: “Because the transaction might be re-run, transaction functions must be idempotent.”
- Exact excerpt: “you cannot have multiple queries and interleave some client-logic in between them.”

### S7 — Python atomic replacement and durability primitives

- Publisher: Python Software Foundation
- URL: <https://docs.python.org/3.11/library/os.html>
- Version context: Python 3.11 documentation; project requires Python >=3.11
- Retrieved through: T2, T6, T11
- Exact excerpt for `os.replace`: “If successful, the renaming will be an atomic operation.”
- Exact excerpt for `os.fsync`: “Force write of file with filedescriptor fd to disk.”
- Exact excerpt: for a buffered file, call `flush()` and then `os.fsync(f.fileno())` to ensure internal buffers are written.

### S8 — OpenAI instruction hierarchy

- Publisher: OpenAI
- URL: <https://openai.com/index/the-instruction-hierarchy/>
- Version context: first-party research article; no application model call was made
- Retrieved through: T2, T10, T11
- Exact excerpt: models can treat system prompts “the same priority as text from untrusted users and third parties”; the proposed hierarchy teaches models to “selectively ignore lower-privileged instructions.”

### S9 — OpenAI agent-safety guidance

- Publisher: OpenAI
- URL: <https://developers.openai.com/api/docs/guides/agent-builder-safety>
- Version context: current official OpenAI API documentation
- Retrieved through: T12 and T13
- Exact excerpt: “A prompt injection happens when untrusted text or data enters an AI system, and malicious contents in that text or data attempt to override instructions to the AI.”
- Exact excerpt: “injecting untrusted input directly into developer messages gives attackers the highest degree of control.”
- Exact excerpt: structured outputs “eliminate freeform channels that attackers can exploit to smuggle instructions or data.”
- Exact excerpt: structured outputs and isolation “greatly reduce, but don’t fully remove, this risk.”

## Claim-to-source map

| Claim ID | Bounded claim | Evidence | Admission |
| --- | --- | --- | --- |
| C1 | A reusable FastAPI router dependency is the native seam for applying one guard to every route in `/normalizador` and `/neo4j`. | S1 | Supported |
| C2 | `request.client.host` is the native request-level peer-host value available to a FastAPI dependency. | S2 | Supported |
| C3 | TrustedHost validates the HTTP Host header and therefore does not implement the selected peer-loopback contract. | S2 + S3 | Supported as a direct comparison of documented semantics |
| C4 | Multipart parsing alone does not bound uploaded file bytes through `max_part_size`; complete-body or streaming enforcement is required. | S4 + S5 | Supported for the repository's locked current stack; implementation must confirm installed API shape in tests |
| C5 | Neo4j managed transaction callbacks must remain idempotent because the driver can retry them. | S6 | Supported |
| C6 | Neo4j commit and local JSON persistence are two durability domains; one Neo4j transaction cannot make the later local file replacement atomic. | S6 + repository architecture | Design inference, not directly asserted by Neo4j docs |
| C7 | A local history file can be atomically replaced with `os.replace`, and stronger crash durability requires flushing/fsync before replacement. | S7 | Supported |
| C8 | Syllabus/profile text must be explicitly treated as untrusted data in the analyst prompt; prompt wording is defense-in-depth, not the sole control. | S8 + S9 | Supported recommendation; OpenAI states prompt injection remains an open problem |
| C9 | Python-side validation, release blocking, least-privilege routing, and constrained write sinks remain necessary even with a stronger system prompt. | S8 + S9 + repository architecture | Design inference |

## Design consequences for the proposal

1. Implement the local-only boundary as one replaceable APIRouter dependency that checks the direct peer host against parsed loopback addresses. Do not use Host-header validation as authorization.
2. Document that reverse proxies and multi-host deployment are unsupported until real authentication replaces the loopback guard. Do not trust forwarded headers in this change.
3. Reject oversized requests before execution creation when the framework exposes a reliable full-body limit; retain a bounded-copy cleanup guard as defense in depth at the UploadFile seam.
4. Keep Neo4j transaction callbacks idempotent and put local durable intent/history around the graph transaction. Add reconciliation for ambiguous `en_progreso` history rather than claiming cross-system atomicity.
5. Use atomic local JSON replacement and explicit recovery states; do not rely on a successful Python return as durable evidence.
6. Add an untrusted-content instruction to the curricular analyst prompt only in a future prompt-specific scope; for the current read-only assessment, keep enforcement in Python and block publication on invocation/grounding failures.

## Research limitations

- All four required tool classes were used (`web_search`, `source_check`, `fetch_content`, `get_search_content`).
- Every `source_check` returned `unclear`; those statuses are preserved and are not treated as approval.
- Initial direct fetches failed for the rendered Starlette site (DNS) and an OpenAI article (HTTP 403); T12/T13 replaced both with successfully fetched original publisher-owned documentation.
- No runtime behavior of FastAPI 0.141.1/Starlette 1.6.0 was inferred solely from docs; implementation tasks must lock behavior with local tests.
- No live Neo4j or OpenAI acceptance was performed or is authorized.
