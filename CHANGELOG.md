# Changelog

All notable changes to the ORT Vimeo Scraper & RAG Knowledge Base project will be documented in this file.

## [Fixed] - 2026-05-07 (Extracción de config desde HTML embebido — Layer 1b + resiliencia general)

### Contexto
El 06/05/2026 el scraper encontró la nueva clase de Business Intelligence (video ID `1189866883`) pero no guardó la transcripción — reportado como `sin config` en la notificación de Telegram. La clase de Ecommerce del mismo día sí se guardó correctamente.

Investigación vía logs de GitHub Actions reveló la causa raíz: **Vimeo migró silenciosamente la arquitectura de su player**. Antes, el config del video (que contiene `text_tracks` con los subtítulos) se descargaba en un XHR separado a `player.vimeo.com/video/{id}/config`. Ahora ese config viene **embebido en el HTML de la página del player** (`player.vimeo.com/video/{id}?...`). El listener de respuestas miraba solo el endpoint viejo → nunca capturaba el config del nuevo video.

Por qué ecommerce funcionó y BI no: durante la carga del showcase de ecommerce, Vimeo auto-cargó el video nuevo como "featured" → el listener lo capturó antes del loop. En el showcase de BI, el video auto-cargado fue otro → `1189866883` no quedó en `player_configs`.

### Qué se implementó

**Layer 1b — Parseo de config desde HTML del player** (`vimeo_scraper.py`)

Nueva lógica en el handler `on_response`: cuando se captura `player.vimeo.com/video/{id}?...` (la página del player embed, no el endpoint `/config`), parsea el body HTML usando `json.JSONDecoder.raw_decode()` buscando el objeto JSON que contiene `text_tracks`. Usa marcadores `"cdn_url"`, `"player_url"`, `"request"` para localizar el inicio del objeto antes de llamar al decoder.

```
Layer 1  — response listener captura /config XHR (old-style, sigue soportado)
Layer 1b — response listener parsea config del HTML del player embed (new-style)
Layer 2  — cookie HTTP fetch directo al endpoint /config (works para videos viejos)
Layer 3  — click en thumbnail + wait_for_response determinístico (≤15s)
Layer 4  — navegación directa a showcase/video/{id} + wait_for_response (≤20s)
```

**Layer 2 — Retry con delay** (`vimeo_scraper.py`)

Reintenta el cookie fetch una vez con 4s de espera. Algunos videos nuevos tardan en propagarse por CDN. Si el primer intento retorna `empty_text_tracks`, espera 4s y reintenta. Si el segundo también falla, pasa a Layer 3.

**Layer 3 — Wait determinístico ampliado** (`vimeo_scraper.py`)

- `page.wait_for_response()` ahora matchea `player.vimeo.com/video/{id}` (embed URL) además del old `/config` XHR.
- Timeout subido de 6s fijo (sleep) a 15s determinístico — sale en cuanto llega la respuesta.

**Layer 4 — URL con contexto de showcase** (`vimeo_scraper.py`)

Cambiado de `vimeo.com/{vid_id}` (URL directa, no tiene el contexto de auth del showcase) a `vimeo.com/showcase/{showcase_id}/video/{vid_id}`. La cookie `{showcase_id}_albumpassword` aplica correctamente a esta URL.

**Workflow resiliente a concurrencia** (`scraper.yml`)

Agrega `git pull --rebase origin main` antes del `git push` en el step de commit. Previene errores si se hace un push manual al repo mientras el workflow está corriendo (como ocurrió durante el debugging de este mismo fix).

**Soporte para videos con hash-based privacy** (`vimeo_scraper.py`)

Extrae el hash del campo `link` de la respuesta de la API de Vimeo (formato `vimeo.com/{id}/{hash}`) y lo agrega como parámetro `?h={hash}` al cookie fetch del Layer 2. Para los videos actuales no hay hash, pero queda implementado para el futuro.

### Diagnóstico en logs

Mensaje `[PW] Config from player HTML (Layer 1b) for {vid_id}` indica cuándo se usa la nueva ruta. El nuevo handler también loggea todos los `player.vimeo.com` URLs capturados a nivel debug durante el desarrollo (luego limpiado).

### Resultado verificado

Run `25501304554` (07/05/2026):
- `business_intelligence.txt — 16 clases` ✓ (era 15 antes del fix)
- Telegram: `Nuevas: business_intelligence +1`
- Todas las demás materias sin cambios (15/16 clases previas, sin regresiones)

---

## [Feat] - 2026-05-01 (Observabilidad + silenciado automático de videos sin captions)

### Contexto
El 30/04/2026 el scraper encontró la clase de Economía y Gestión (video ID `1188206158`) pero no guardó la transcripción — el player config traía `text_tracks` vacío porque Vimeo todavía no había terminado de procesar los captions automáticos cuando el pipeline corrió a las 23:00 UTC. La notificación Telegram solo dijo "+1 contabilidad", lo cual era correcto pero sin diagnóstico.

En el re-run manual del 01/05, el sistema nuevo detectó además un segundo video sin captions: contabilidad_y_costos del 21/04 (día de evaluación — no hubo clase). Ese video aparecería como warning en **cada corrida futura**, generando ruido permanente.

### Qué se implementó

**1. Tracking de videos fallidos** (`vimeo_scraper.py`)

Nueva lista global `_run_warnings` que registra cada video encontrado pero no guardado:

| `reason` | Significado | Comportamiento |
|---|---|---|
| `no_player_config` | No se obtuvo el config del player (ninguna de las 3 capas funcionó) | Reintenta en el próximo run — puede ser transitorio |
| `empty_text_tracks` | Config obtenido pero sin subtítulos — video genuinamente sin captions | Crea stub file para silenciar runs futuros |
| `vtt_download_failed` | VTT existía pero falló la descarga (red o HTTP ≠ 200) | Reintenta en el próximo run |

Los warnings se incluyen en `run_summary.json` bajo la clave `warnings`.

**2. Notificación Telegram con diagnóstico** (`.github/workflows/scraper.yml`)

Cuando hay warnings, la notificación de éxito incluye un bloque detallado:
```
ORT Scraper - 01/05/2026
Nuevas: economia_y_gestion +1
⚠️ Videos sin transcripción:
  • contabilidad_y_costos [21-04-2026]: sin captions
```

**3. Stub automático para videos sin captions** (`vimeo_scraper.py`)

Cuando se confirma `empty_text_tracks` (el video genuinamente no tiene subtítulos en Vimeo — parciales, material administrativo, etc.), el scraper crea un archivo `.md` mínimo en la ruta correspondiente:
```
transcripts/semestre_5/{subject}/DD-MM-YYYY - {title}.md
# Sin captions
Video ID: {vid_id}
```
El check de "already exists" lo detecta en todas las corridas siguientes y lo salta silenciosamente, sin generar más warnings. El warning aparece **solo la primera vez**.

Esto generaliza automáticamente: si en el futuro hay otro parcial o video sin captions en cualquier materia, el mecanismo aplica sin intervención manual.

### Resultado verificado

- Re-run manual `25234727191` (01/05/2026): recuperó la clase de Economía del 30/04 exitosamente (captions disponibles a esa altura). Guardada + ingestada en Pinecone (20 vectores).
- Stub creado manualmente para contabilidad 21/04 (ID `1185395740`) — día de evaluación. No generará más warnings.

---

## [Fixed] - 2026-04-17 (Orden cronológico en UI + limpieza gitignore)

### Qué estaba roto
`generate_transcript_index()` en `vimeo_scraper.py` usaba `sorted(..., reverse=True)` sobre
nombres `DD-MM-YYYY`. El orden alfabético inverso ponía "26-03" como "más reciente" que "16-04"
— la UI mostraba clases de marzo antes que las de abril.

### Fix aplicado
Misma solución que `generate_raw_files.py`: key `(YYYY, MM, DD)` con `reverse=True` para
orden cronológico descendente (más reciente primero). `transcripts_index.json` regenerado y
commiteado para que Vercel lo aplique inmediatamente.

### También
`run_summary.json` agregado a `.gitignore` — este archivo es generado por el scraper en cada
run para la notificación Telegram y no debe commitearse al repo.

---

## [Feat] - 2026-04-17 (Confiabilidad y observabilidad del pipeline)

### Qué se agregó

**1. Retry automático en descargas HTTP** (`vimeo_scraper.py`)
Nueva función `_http_get_retry()`: si una descarga de subtítulos VTT, un fetch de config del
player, o una llamada a la API de Vimeo falla por red o error 5xx, reintenta hasta 3 veces
con espera exponencial (0s → 1s → 2s). Antes, un solo fallo de red descartaba la clase sin
reintentar.

**2. Resumen de run** (`vimeo_scraper.py`)
Al terminar cada ejecución, el scraper escribe `run_summary.json` con cuántas transcripciones
nuevas encontró por materia. Usado por el step de notificación de Telegram.

**3. Fallos explícitos en NotebookLM sync** (`notebooklm_sync.py`)
Antes, si las cookies de NotebookLM expiraban o algún notebook fallaba en sincronizar, el
script terminaba limpiamente y el workflow decía "success". Ahora llama `sys.exit(1)` en
esos casos, lo que dispara la notificación de Telegram de fallo. Efectos:
- Cookies vacías o ausentes → exit(1)
- Env vars faltantes en CI → exit(1)
- Uno o más notebooks fallaron → exit(1) con instrucciones de cómo renovar la auth

**4. Notificación Telegram en runs exitosos** (`scraper.yml`)
Nuevo step al final del pipeline (solo si todo salió bien) que manda un mensaje Telegram con
el resumen del run, ej:
```
ORT Scraper - 21/04/2026
Nuevas: contabilidad +1, economia +1
```
Antes solo llegaba Telegram cuando el workflow fallaba por completo.

### Pasos manuales requeridos (ver CHEATSHEET — sección Telegram)
Para que las notificaciones Telegram funcionen se necesita configurar un bot y agregar
`TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` como GitHub Secrets.

---

## [Fixed] - 2026-04-17 (Orden cronológico en raw files)

### Qué estaba roto
`generate_raw_files.py` usaba `sorted()` puro sobre los nombres de archivo con formato `DD-MM-YYYY`. El orden alfabético por día-primero mezclaba marzo y abril: `07-04` aparecía antes que `10-03`, `17-03`, etc.

### Fix aplicado
Se reemplazó el `sorted()` por una key que parsea la fecha y construye una tupla `(YYYY, MM, DD)` para ordenar cronológicamente:

```python
def _date_key(fname):
    m = re.match(r'(\d{2})-(\d{2})-(\d{4})', fname)
    if m:
        day, month, year = m.groups()
        return (year, month, day)
    return ('0000', '00', '00')

files = sorted([...], key=_date_key)
```

El efecto se aplica en el próximo run de Actions (lunes 20/04 a las 20:00 UYT), que regenera todos los raw files desde cero.

---

## [Fixed] - 2026-03-27 (Transcripts limpios — duplicados y fechas incorrectas eliminados)

### Estado final semestre 5 (27-03-2026)

| Materia | Clases | Fechas |
|---|---|---|
| Business Intelligence | 6 | 10,11,17,18,24,25/03 |
| Contabilidad y Costos | 6 | 10,12,17,19,24,26/03 |
| E-commerce y Servicios | 6 | 09,11,16,18,23,25/03 |
| Economía y Gestión | 6 | 10,12,17,19,24,26/03 |
| Project Management | 3 | 09,16,23/03 |

### Bugs resueltos

**1. Duplicados por encoding de ñ**: El scraper viejo guardaba `Caamao` (sin ñ) por sanitización agresiva. El scraper nuevo preserva ñ → nombres diferentes para el mismo video → skip-check no los detectaba → dos archivos por fecha.
- Fix: borrados los 4 archivos `Caamao` de ecommerce (09, 11, 16, 18/03).
- Fix estructural: `save_transcript()` ahora hace skip por prefijo de fecha (`startswith("DD-MM-YYYY - ")`) en vez de ruta exacta. Cambios futuros de encoding no generan duplicados.

**2. Archivos con fecha incorrecta (`27-03-2026`)**: Commits del bot en runs anteriores re-agregaron archivos `27-03-2026 - ... DD-MM-YYYY.md` que sobrevivieron nuestros deletes por race condition con GitHub Actions.
- Fix: borrados los 5 archivos restantes (uno por materia) via `git rm` + commit directo.

**3. Ecommerce 25-03 faltante**: El archivo correcto estaba en el `27-03-2026` erróneo que borramos. El siguiente run del scraper lo re-capturó con nombre correcto.

**4. Cosmético**: `23-03-2026` de ecommerce tenía `Caamao` en el nombre (único remanente del scraper viejo). Renombrado a `Caamaño` para consistencia.

---

## [Fixed] - 2026-03-27 (Playwright scraper — polling reemplazado por expect_response)

### Qué estaba roto y por qué
Vimeo migró sus showcases a renderizado client-side (Next.js + Cloudflare). El scraper HTTP (`requests`) recibía una shell HTML vacía — 0 videos encontrados. Playwright sí puede autenticar porque abre un browser real que ejecuta el JavaScript de Vimeo.

El flujo Playwright tiene dos partes:
1. **Lista de videos**: interceptando `api.vimeo.com/albums/{id}/videos` (funciona bien)
2. **Config del player** (contiene los subtítulos): requiere navegar a la URL de cada video dentro de la sesión autenticada para que Vimeo genere un token firmado y dispare el XHR a `player.vimeo.com/video/{id}/config`

**El problema específico**: la versión anterior esperaba esa respuesta con un loop manual de polling (12 iteraciones × 1 segundo = hasta 12s por video). En GitHub Actions (Ubuntu) ese tiempo no alcanzaba — el XHR llegaba después de los 12s → 0 subtítulos extraídos.

### Fix aplicado (2026-03-27)
Reemplazado el polling manual por `page.expect_response()`, la API nativa de Playwright para esperar respuestas HTTP. Se resuelve en cuanto llega el XHR — sin tiempo fijo:

```python
# Antes: polling de hasta 12s por video
for _ in range(12):
    config = player_configs.get(vid_id)
    if config: break
    page.wait_for_timeout(1000)

# Ahora: determinístico, termina cuando llega el XHR (~1-2s)
with page.expect_response(
    lambda r, v=vid_id: f'/video/{v}/config' in r.url and r.status == 200,
    timeout=30000,
) as resp_info:
    page.goto(video_url, wait_until='commit', timeout=30000)
config = resp_info.value.json()
```

Nota: `v=vid_id` como default arg en el lambda es necesario para capturar el valor por valor (no referencia) dentro del loop.

### Estado del run (2026-03-27 ~15:51 UTC)
Workflow `23655012904` en ejecución con el fix. Monitorear con:
```bash
gh run view --job=68909810643 --repo lorenzoscaldaferro/ort-classes
```

### Pendiente
- Configurar `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` como GitHub Secrets (el step de notificación de fallos ya está en `scraper.yml`, solo faltan los secrets).

## [Fixed] - 2026-04-14 (Vercel Migration — NotebookLM sync completamente funcional)

### Fixed
- **Vercel Migration**: Pipeline migrado de Netlify a Vercel. `VERCEL_URL` = `https://ort-classes.vercel.app`.
- **NotebookLM sync — 3 bugs encadenados resueltos**:
  1. `notebooklm-mcp>=2.0.0` en scraper.yml instalaba la v2.0.11 de PyPI, un proyecto completamente diferente al cliente local (v0.1.15) que tiene `NotebookLMClient`. El import fallaba silenciosamente → el sync nunca corría. Fix: vendorear `notebooklm_mcp/` (api_client.py, constants.py, __init__.py) directamente en el repo y reemplazar la dep por `httpx`.
  2. El cliente usaba `bl` (build label del frontend de NotebookLM) hardcodeado de enero 2026 → Google respondía 400 Bad Request. Fix: extraer `bl` dinámicamente de la página HTML al inicializar el cliente via regex en `_refresh_auth_tokens()`.
  3. El cliente usaba `csrf_token` y `session_id` del auth.json cacheado (de marzo 2026) → no hacía page fetch fresco → `bl` desactualizado nunca se corregía. Fix: inicializar `NotebookLMClient(cookies=cookies)` sin pasar csrf/session para forzar el page fetch que extrae los valores actuales.
- **notebooklm_sync.py — logging mejorado**: imprime fuentes encontradas (id, type, url, title) y advertencia explícita si ninguna matchea.

### Resultado verificado
Run `24402584005` — **5/5 notebooks sincronizados**:
```
[-] Borrando fuente antigua: url='https://ort-classes.netlify.app/raw/business_intelligence.txt'
[+] Agregando: https://ort-classes.vercel.app/raw/business_intelligence.txt  [✓]
[-] Borrando fuente antigua: url='https://ort-classes.netlify.app/raw/economia_y_gestion.txt'
... (repite para las 5 materias)
Completado — 5/5 notebooks sincronizados
```

---


## [Fixed] - 2026-04-12 (NotebookLM sync fix — notebooklm-mcp)

### Fixed
- **NotebookLM sync auth**: `pynotebooklm auth login` was blocked by Google's automated browser detection (Playwright Chromium triggers "No puedes acceder"). Replaced pynotebooklm entirely with `notebooklm-mcp`, which uses `notebooklm-mcp-auth` (real Chrome via CDP — not detected as a bot).
- **`notebooklm_sync.py`**: Rewrote to use `notebooklm_mcp.api_client.NotebookLMClient` directly. No asyncio, no Playwright. `NOTEBOOKLM_AUTH_JSON` format is now `~/.notebooklm-mcp/auth.json` (dict-style cookies + csrf_token).
- **`scraper.yml`**: Replaced `pynotebooklm` with `notebooklm-mcp` in `pip install`. Removed the conditional Playwright install step (saves ~2-3 min per CI run).

### Done
- `NOTEBOOKLM_AUTH_JSON` GitHub secret set with real Chrome cookies via `notebooklm-mcp-auth`.
- Tested locally: 5/5 ORT notebooks synced successfully (delete old source → re-add URL).
- All 7 GitHub secrets now configured: `PINECONE_API_KEY`, `PINECONE_HOST`, `OPENAI_API_KEY`, `SUBJECTS_JSON`, `NETLIFY_URL`, `NOTEBOOKLM_NOTEBOOK_IDS`, `NOTEBOOKLM_AUTH_JSON`.

### Auth renewal (when cookies expire ~2-4 weeks)
```bash
notebooklm-mcp-auth
cat ~/.notebooklm-mcp/auth.json | gh secret set NOTEBOOKLM_AUTH_JSON --repo lorenzoscaldaferro/ort-classes
```

---

## [Unreleased] - 2026-03-26 (NotebookLM Kortex-style + Scraper Fix)

### Added
- **`generate_raw_files.py`**: New script that concatenates all transcripts per subject into `.txt` files saved to `ui/public/raw/`. Netlify serves them as public static URLs — replaces the Google Drive approach entirely.
- **`notebooklm_sync.py`**: Async script using `pynotebooklm` (reverse-engineered Google batchexecute RPC) to delete and re-add URL sources in NotebookLM notebooks after each scrape. Requires `NOTEBOOKLM_AUTH_JSON`, `NOTEBOOKLM_NOTEBOOK_IDS`, and `NETLIFY_URL` GitHub Secrets. Exits cleanly if not configured.
- **`NOTEBOOKLM_SETUP.md`**: Rewritten with simplified 6-step setup (no Google Cloud, no service account needed).

### Changed
- **`scraper.yml`**: Replaced Google Drive sync step with `generate_raw_files.py` + `notebooklm_sync.py`. pip install now uses `pynotebooklm` instead of `google-auth/google-api-python-client`. Playwright browsers installed conditionally (only when `NOTEBOOKLM_AUTH_JSON` secret is set). Commit step now includes `ui/public/raw/`.
- **`vimeo_scraper.py`**: Fixed showcase authentication — Vimeo now renders password forms client-side (JavaScript), so the old HTML detection condition failed for all showcases. New approach: always attempt auth via known Vimeo showcase `/auth` endpoint with session cookies. Added Strategy B (Next.js `__NEXT_DATA__` JSON parsing) and Strategy C (regex fallback) for video discovery when `<a>` links aren't in the server-rendered HTML.

### Removed
- **`google_drive_sync.py`**: Deleted. Google Drive approach replaced by static Netlify URL sources.

### Bug diagnosed
- **Scraper found 0 videos (Mar 25 run)**: Root cause confirmed — "No password protection detected on this page." for all 5 showcases. Vimeo migrated showcases to client-side rendering; the conditions `"This showcase is private" in html` and `soup.find('input', {'name': 'password'})` both return False for the server-rendered shell. The fix attempts auth unconditionally and adds extra video discovery strategies. If this still fails, the fallback is Playwright-based scraping (node_modules already has playwright installed).

---

## [Unreleased] - 2026-03-24 (Phase 4 — Bug Fixes)

### Fixed
- **Transcript deep-link 404 (semester "N/A")**: `ingest.mjs` stored `semester: "N/A"` in Pinecone for any transcript whose header lacked a `**Semester:**` field — which is all files created by the Python scraper. Pinecone could return those vectors and the frontend constructed `/transcripts/N/A/...` URLs that always 404'd. Fixed in `TranscriptsView.tsx`: when the semester/subject from a deep-link don't exist in the loaded tree, `openFile` now searches the tree to resolve the correct path. Root cause also documented in `n8n_chat_workflow.json` (`Code Formatear ORT` now uses a subject→semester fallback map so future responses carry the correct `semestre_N` value).
- **Transcript filename URL encoding**: `fetch()` calls for transcript files used raw filenames containing spaces (e.g. `18-03-2026 - FACS-...`). Added `encodeURIComponent(file)` to ensure Netlify receives a properly encoded path.

### Added
- **Local sync cron job**: Created `sync-local.sh` (runs `git pull` + `rsync` from the production repo into the Mac's local `transcripts/` folder). Cron entry added at `20 23 * * 1-4` (23:20 UTC = 20:20 UYT), 20 minutes after GitHub Actions completes its nightly run.

---

## [Unreleased] - 2026-03-24 (Phase 4: Cloud Migration)

### Added
- **Production Isolation**: Created `cloud_production/` directory to separate the serverless production build from the local development codebase.
- **Serverless Scraper Pipeline**: Refactored `vimeo_scraper.py` into a pure Python/Requests script to remove Playwright/Node dependencies. Configured GitHub Action `.github/workflows/scraper.yml` to automate nightly scraping and Pinecone ingestion at 20:00 local time.
- **n8n AI Chat Agent**: Replaced the local Flask API with an industrial-grade n8n workflow (`ort-chat-agent`). Includes `n8n_chat_workflow.json` for one-shot deployment, handling Pinecone retrieval, context formatting, and GPT-4o-mini synthesis.
- **Static Frontend Architecture**: Migrated React UI to Netlify. Optimized the build process to bundle Markdown transcripts and a static `transcripts_index.json` directly into the `public/` directory for zero-latency loading.
- **CORS & Git Security**: Integrated `gh auth setup-git` protocols to bypass macOS Keychain credential conflicts. Implemented Repository Secrets for `PINECONE_API_KEY`, `OPENAI_API_KEY`, and `SUBJECTS_JSON`.

### Changed
- **Frontend Connectivity**: `ChatView.tsx` now POSTs directly to the n8n production webhook, eliminating the need for a persistent middleware server.
- **Scraper Persistence**: New GitHub Action commits new transcripts directly to the repository branch, ensuring the static frontend always has the latest data after each run.

## [Unreleased] - 2026-03-24 (UI Round 2)

### Fixed
- **Transcript deep-link 404**: `ingest_existing.py` stored `semester` as a bare number (`"5"`) but the filesystem uses `semestre_5`. `api_server.py` now converts it back before returning sources to the frontend (`semestre_{n}`).
- **Transcript deep-link filename mismatch**: `ingest_existing.py` stored `title` without the date prefix (e.g. `FACS-7990-...` instead of `18-03-2026 - FACS-7990-...`). `api_server.py` now reconstructs the full filename from `date` + `title` stored in metadata.
- **Chat history reset on view switch**: Messages state was local to `ChatView` and got destroyed when switching to Transcripciones. Lifted `messages` state to `Index.tsx` so it persists across view changes.

### Added
- **Copy button in transcript viewer**: Copy/Check button added to the file viewer header in `TranscriptsView.tsx`, mirroring the copy button available in the chat view.
- **Clickable source cards**: Each source citation card in the chat is now a clickable button. Clicking navigates to the Transcripciones view, auto-opens the referenced file, and scrolls to the cited excerpt with a subtle yellow highlight.
- **Transcript highlight on deep-link**: `TranscriptsView` accepts `initialOpen` prop with an optional `excerpt` field. The `HighlightedContent` component finds the excerpt in the full text and wraps it in a highlighted `<span>`, then scrolls it into view.
- **Semestre 5 shown first**: Transcript list now sorts semesters in reverse order so current subjects (semestre_5) appear at the top and Matemática Financiera (semestre_3) at the bottom.

### Changed
- **RAG context window**: Increased from 5 to 8 chunks passed to GPT-4o-mini for richer synthesis.
- **System prompt softened**: Replaced "Si la respuesta no está en los fragmentos, indicalo explícitamente" with "Si la información en los fragmentos es parcial, sintetizá lo que se pueda inferir y aclaralo" to avoid unnecessarily terse responses when partial information is available.
- **`ChatMessage` and `Source` interfaces exported** from `ChatView.tsx` so they can be reused by `Index.tsx` without duplication.

## [Unreleased] - 2026-03-24

### Added
- **Pinecone ingestion integrated into `vimeo_scraper.py`**: After saving each new transcript, the script now automatically chunks the text (~3000 chars with 300-char overlap), generates embeddings via OpenAI `text-embedding-3-small`, and upserts the vectors to the `ort-clases` Pinecone index. Uses the REST API directly with `requests` — no extra SDK dependencies.
- **`ingest_existing.py`**: One-shot utility script to bulk-ingest all previously downloaded transcripts (located in `transcripts/`) into Pinecone. Parses markdown headers to extract metadata (subject, semester, title, date) and stores the chunk text in vector metadata for retrieval.
- **macOS cron job**: Configured via `crontab` to run `vimeo_scraper.py` automatically Monday–Thursday at 20:00 local time (UYT). Logs output to `cron.log`.
- **Skip-existing logic**: `vimeo_scraper.py` now skips both file saving and Pinecone ingestion for transcripts that have already been processed.
- **Multi-subject loop**: `vimeo_scraper.py` now reads `config.json` and iterates over all 5 configured subjects instead of running a single hardcoded showcase.
- **API keys in `config.json`**: Added `pinecone_api_key`, `pinecone_host`, and `openai_api_key` fields.

## [Unreleased] - 2026-03-23

### Added
- **Phase 3 Pure RAG Retrieval (n8n)**: Designed and exported `ort-rag-workflow.json`, a highly optimized n8n workflow that operates entirely without a redundant LLM node. It functions as a pure semantic search API receiving a `query`, embedding it via OpenAI, scoring against Pinecone `ort-clases`, and outputting raw transcript chunks back to the calling LLM (Antigravity/Claude).
- **Phase 2 Vector Ingestion**: Engineered and successfully deployed `ingest.mjs`. This script iterates through `transcripts/`, parses markdown front-matter iteratively, chunks textual data via Langchain (`RecursiveCharacterTextSplitter`), and requests embeddings natively through OpenAI's `text-embedding-3-small`.
- **Pinecone RAG DB Mapping**: Integrated `@pinecone-database/pinecone` SDK (v3) within `ingest.mjs` to automatically stream, format, and batch-upsert over 50 embedded classes to the user's `ort-clases` serverless AWS index in real-time.
- **Semester Sorting Hierarchy**: Introduced a `semester` property to `config.json` and refactored `scraper.mjs` to dynamically organize VTT downloads into hierarchal nested folders (`transcripts/semestre_X/subject_name/`).
- **Targeted Extractions**: Programmed a CLI parser inside `scraper.mjs` (using `process.argv[2]`) to accept a single subject name. This allows scraping historic or one-off inactive classes (e.g. `matematica_financiera`) without spinning through the active `config.json` pipeline.
- **Multi-Subject Configuration**: `config.json` fully populated with 5 ORT subjects, showcase links, and passwords.
- **Dynamic File Naming**: `scraper.mjs` now extracts `document.title` and `h1` using Playwright, leveraging Regex to parse dates (e.g. `19-03-2026`) and saving the final Markdown transcripts as `DD-MM-YYYY - Title.md` instead of generic numeric IDs.
- **`test_scraper.mjs`**: Initial Playwright script to verify password bypass and VTT interception.
- **`config.json`**: Configuration file setup to manage subjects, showcase URLs, and passwords.
- **`scraper.js`**: Core loop script to process multiple showcases and extract subtitles using the `window._vimeoPlayerConfig` iframe injection technique.

### Changed
- **Architecture Shift**: Moved from programmatic `yt-dlp` / `requests` extraction to **Headless Playwright** extraction. This was necessary to bypass ORT's institutional Cloudflare and Next.js SSR session protections, which blocked pure HTTP requests from accessing Vimeo's video configurations.
- **RAG Architecture**: Decision made to build the RAG system using **n8n + MCP Server** and **Pinecone**, eliminating the need for Dockerized PostgreSQL or a custom Next.js chat frontend. This simplifies deployment and maximizes existing user capabilities.

### Fixed
- Fixed Vimeo iframe password bypass by capturing the Next.js rendered page, triggering a click on the video thumbnails, and intercepting the VTT URLs directly from the injected global JS state (`request.text_tracks`) instead of sniffing network packets, which were sometimes totally obfuscated.
