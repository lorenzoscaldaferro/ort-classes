# ORT Vimeo RAG — Cheatsheet

Referencia rápida de toda la infraestructura. Diseñado para ser leído por un humano o por un LLM sin contexto previo.

---

## Qué hace este sistema

1. **Descarga** las transcripciones de clases desde showcases privados de Vimeo (protegidos con contraseña)
2. **Guarda** cada transcripción como archivo Markdown en carpetas organizadas por semestre y materia
3. **Genera raw files** — un `.txt` por materia con todas sus transcripciones concatenadas, para usar como fuentes en NotebookLM
4. **Sincroniza** esos raw files con NotebookLM automáticamente
5. **Sirve** una UI React estática en Vercel con visor de transcripciones
6. **Sintetiza** respuestas vía n8n (workflow `ORT Chat Agent`): recibe la query, busca en Pinecone, genera respuesta con GPT-4 y devuelve `{ answer, sources[] }` al frontend

> **Cloud vs Local**: `cloud_production/` es el build serverless. El scraper corre en GitHub Actions (nightly). El frontend está en Vercel. El chat API es n8n. No se requiere Mac encendida para que el sistema funcione.

---

## Flujo completo: de la clase al NotebookLM

Este es el recorrido completo desde que termina una clase hasta que aparece en el raw file y en NotebookLM:

```
[Profesor sube la grabación a Vimeo]
         │
         ▼
[GitHub Actions — lun-jue 23:00 UTC / 20:00 UYT]
         │
         ├─ 1. vimeo_scraper.py (Playwright)
         │       → Abre Chrome real, autentica con contraseña
         │       → Intercepta XHR con lista de videos del showcase
         │       → Por cada video nuevo: navega a la URL, espera el
         │         XHR de config del player, extrae los subtítulos VTT
         │       → Convierte VTT → texto plano
         │       → Guarda como .md en transcripts/semestre_5/{materia}/
         │
         ├─ 2. generate_raw_files.py
         │       → Lee todos los .md de transcripts/
         │       → Concatena por materia, en orden cronológico (YYYY-MM-DD)
         │       → Escribe ui/public/raw/{materia}.txt
         │
         ├─ 3. git commit + git push → rama main de GitHub
         │       → Vercel detecta el push automáticamente
         │       → Redespliega la UI estática (incluye los raw files)
         │       → En ~30s los raw files están disponibles en:
         │         https://ort-classes.vercel.app/raw/{materia}.txt
         │
         └─ 4. notebooklm_sync.py
                 → Le dice a cada notebook de NotebookLM que recargue
                   su fuente URL (apunta al raw file en Vercel)
                 → NotebookLM descarga el txt actualizado y reindexea
```

**Por qué raw files y no archivos individuales**: NotebookLM acepta fuentes URL. Un solo `.txt` por materia es más fácil de mantener que actualizar 10+ fuentes individuales por notebook.

**Frecuencia**: una vez por noche, de lunes a jueves. Los viernes no corre — si una clase del jueves no aparece, esperá al día siguiente o triggeá manualmente.

**Trigger manual**: GitHub → repo `ort-classes` → Actions → "Vimeo Scraper" → Run workflow.

---

## Archivos clave

| Archivo | Propósito |
|---|---|
| `vimeo_scraper.py` | Scraper principal con Playwright: autentica, descarga VTT, guarda .md |
| `generate_raw_files.py` | Concatena transcripts por materia → `ui/public/raw/*.txt` (orden cronológico) |
| `notebooklm_sync.py` | Refresca las fuentes URL en los notebooks de NotebookLM |
| `.github/workflows/scraper.yml` | Pipeline de GitHub Actions: cron lun-jue 23:00 UTC |
| `ui/public/raw/` | Raw files estáticos servidos por Vercel (una fuente por materia) |
| `transcripts/semestre_5/` | Archivos .md de cada clase, organizados por materia |
| `transcripts_index.json` | Índice de todos los transcripts (usado por la UI) |
| `api_server.py` | Flask API (legacy, no usada en producción cloud) |

---

## Estructura de carpetas de transcripciones

```
transcripts/
  semestre_3/
    matematica_financiera/
      DD-MM-YYYY - {titulo-del-video}.md
      ...
  semestre_5/
    economia_y_gestion/
    business_intelligence/
    contabilidad_y_costos/
    project_management/
    ecommerce_y_servicios/
```

Cada archivo `.md` tiene este formato:
```markdown
# DD-MM-YYYY - {titulo}

**Subject:** {nombre_materia}
**Video ID:** {id_vimeo}

---

{texto completo de la transcripción VTT convertido a texto plano}
```

---

## Comandos

### Correr el scraper manualmente (desde cloud_production/)
```bash
cd /Users/lolescaldaferro/Antigravity/Vimeo/cloud_production
python3 vimeo_scraper.py
```
- Lee API keys de `config.json` (local) o de variables de entorno (GitHub Actions)
- Loopea todas las materias configuradas, skipea archivos ya existentes
- Ingesta en Pinecone solo los nuevos, regenera `transcripts_index.json`

### Triggerear el scraper en GitHub Actions manualmente
En GitHub → repo `ort-classes` → Actions → "Vimeo Scraper" → Run workflow.

### Ver el log del cron
```bash
tail -f /Users/lolescaldaferro/Antigravity/Vimeo/cron.log
```

### Ver el cron configurado
```bash
crontab -l
```
Salida esperada (dos entradas):
```
# Legacy local scraper (requiere Mac encendida)
0 20 * * 1-4 /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Users/lolescaldaferro/Antigravity/Vimeo/vimeo_scraper.py >> /Users/lolescaldaferro/Antigravity/Vimeo/cron.log 2>&1

# Sync local desde GitHub después de que Actions termina
20 23 * * 1-4 /bin/bash /Users/lolescaldaferro/Antigravity/Vimeo/cloud_production/sync-local.sh
```

### Sync local manual (bajar transcripts nuevos desde GitHub)
```bash
cd /Users/lolescaldaferro/Antigravity/Vimeo/cloud_production
git pull
rsync -a transcripts/ /Users/lolescaldaferro/Antigravity/Vimeo/transcripts/
```

### Instalar dependencias Python (cloud scraper)
```bash
pip install requests beautifulsoup4 openai notebooklm-mcp
```
Sin Flask, sin Playwright. Pinecone se llama vía `requests` directamente.

### Renovar auth de NotebookLM (cuando las cookies expiran ~2-4 semanas)
```bash
notebooklm-mcp-auth   # abre Chrome real → login normal con Google
cat ~/.notebooklm-mcp/auth.json | gh secret set NOTEBOOKLM_AUTH_JSON --repo lorenzoscaldaferro/ort-classes
```

### Build de la UI (Netlify lo corre automáticamente en cada push)
```bash
cd /Users/lolescaldaferro/Antigravity/Vimeo/cloud_production/ui
npm install
npm run build  # copia transcripts/ a public/ y compila con Vite
```

---

## Cron / Automatización

| Qué | Cuándo | Dónde corre |
|---|---|---|
| GitHub Actions scraper | Lun-Jue 23:00 UTC (20:00 UYT) | GitHub (nube, siempre activo) |
| `sync-local.sh` | Lun-Jue 23:20 UTC (20:20 UYT) | Mac (solo si está encendida) |

- **GitHub Actions**: corre `vimeo_scraper.py`, `generate_raw_files.py`, commitea, luego `notebooklm_sync.py` refresca las fuentes en los 5 notebooks de NotebookLM
- **sync-local.sh**: hace `git pull` + `rsync` para que la Mac tenga los transcripts nuevos en local
- **Logs**: se acumulan en `/Users/lolescaldaferro/Antigravity/Vimeo/cron.log`

---

## config.json — estructura

```json
{
  "pinecone_api_key": "pcsk_...",
  "pinecone_host":    "https://ort-clases-xxxx.svc.aped-xxxx.pinecone.io",
  "openai_api_key":   "sk-proj-...",
  "subjects": [
    {
      "name":         "economia_y_gestion",
      "semester":     5,
      "showcase_url": "https://vimeo.com/showcase/XXXXXXX",
      "password":     "..."
    },
    ...
  ]
}
```

**Importante**: este archivo contiene contraseñas y API keys. No commitear a repositorios públicos.

---

## Arquitectura completa (Cloud Production)

```
┌─────────────────────────────────────────────────────┐
│  INGESTA (automática, lun-jue 23:00 UTC)            │
│                                                     │
│  GitHub Actions (Ubuntu runner)                     │
│    → vimeo_scraper.py  (Playwright + Chromium)      │
│       → Autentica en Vimeo con contraseña           │
│       → Intercepta XHR lista de videos              │
│       → Por cada video: espera config del player    │
│       → Extrae VTT → convierte a texto plano        │
│       → Guarda .md en transcripts/semestre_5/{mat}/ │
│       → Embeddings OpenAI → upsert Pinecone         │
│    → generate_raw_files.py                          │
│       → Concatena .md por materia → ui/public/raw/  │
│    → git commit + push → main                       │
│       → Vercel auto-redespliega (~30s)              │
│    → notebooklm_sync.py                             │
│       → Refresca fuentes URL en los 5 notebooks     │
│                                                     │
│  Mac cron 23:20 UTC (solo si Mac está encendida)    │
│    → sync-local.sh: git pull + rsync al local       │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  UI PRODUCCIÓN (Vercel CDN)                         │
│                                                     │
│  React + Vite (build estático)                      │
│    → Transcripciones: fetch /transcripts_index.json │
│    → Archivo: fetch /transcripts/{sem}/{sub}/{file} │
│    → Raw files: /raw/{materia}.txt (fuentes NbLM)   │
│    → Chat: POST n8n webhook/ort-chat-agent          │
│    → Fuente citada → abre transcript con highlight  │
│                                                     │
│  URL: https://ort-classes.vercel.app                │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  CHAT RAG (on-demand, vía n8n)                      │
│                                                     │
│  n8n workflow "ORT Chat Agent"                      │
│    → POST webhook/ort-chat-agent  { query }         │
│    → n8n: OpenAI embedding + Pinecone top-8 chunks  │
│    → Code: formatea sources[] con semester/subject  │
│    → OpenAI GPT-4: sintetiza respuesta              │
│    → Devuelve { answer, sources[] }                 │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  NOTEBOOKLM (5 notebooks, uno por materia)          │
│                                                     │
│  Cada notebook tiene como fuente la URL:            │
│    https://ort-classes.vercel.app/raw/{materia}.txt │
│  notebooklm_sync.py la refresca tras cada run       │
│  → NotebookLM descarga el txt y reindexea           │
└─────────────────────────────────────────────────────┘
```

---

## n8n — workflow "ORT Transcripts RAG Tool"

**URL**: `https://n8n.flowai.it.com/webhook/ort-rag-search`
**Método**: POST
**Cuerpo esperado**:
```json
{ "query": "¿qué es la elasticidad precio?" }
```

**Cómo funciona internamente** (n8n, siempre activo en el servidor):
1. Webhook recibe el `query`
2. OpenAI genera el embedding del query
3. Pinecone busca los chunks más similares en `ort-clases`
4. Devuelve los resultados con metadata (materia, fecha, título, texto del chunk)

**Metadata devuelta por chunk**:
```json
{
  "document": {
    "pageContent": "texto del chunk...",
    "metadata": {
      "subject": "business_intelligence",
      "semester": "5",
      "title": "FACS-7990-Business intelligence-...",
      "date": "18-03-2026",
      "chunk_index": 2
    }
  },
  "score": 0.847
}
```

**Importante — problema conocido de datos**: `ingest.mjs` (el script Node.js original) guardó `semester: "N/A"` en Pinecone para todos los archivos cuyos headers no tenían `**Semester:**` (todos los generados por el scraper Python). `Code Formatear ORT` incluye un fallback de subject→semester para corregirlo. `TranscriptsView.tsx` también resuelve el path buscando en el árbol si el semester es inválido.

**Para qué sirve**: es la "memoria de clases" que le pasás al LLM. El LLM llama este endpoint, recibe los fragmentos relevantes, y los usa como contexto para responder. Sin esto, el LLM respondería de memoria general; con esto, responde basado en lo que se dijo en tus clases de ORT.

---

## Pinecone

- **Índice**: `ort-clases`
- **Modelo de embedding**: `text-embedding-3-small` (OpenAI, 1536 dimensiones)
- **Chunk size**: ~3000 chars con 300 chars de overlap
- **Metadata por vector**: `subject`, `semester`, `title`, `date`, `text` (el chunk), `chunk_index`
- **ID de vector**: `{video_id}_{chunk_index}` — permite re-ingestar sin duplicados

---

## UI — stack y componentes clave

**Stack**: React + TypeScript + Vite + Tailwind + Radix UI + Framer Motion

| Archivo UI | Propósito |
|---|---|
| `ui/src/pages/Index.tsx` | Raíz: maneja `activeView`, `chatMessages` (persistente) y `transcriptDeepLink` |
| `ui/src/components/dashboard/ChatView.tsx` | Vista de chat: input, mensajes, source cards clicables, POST a n8n |
| `ui/src/components/dashboard/TranscriptsView.tsx` | Vista de transcripciones: árbol semestre/materia, visor con highlight, fallback de path |
| `ui/src/components/dashboard/DashboardSidebar.tsx` | Navegación lateral: Chat con mis clases / Transcripciones |
| `ui/vite.config.ts` | Sin proxy — todos los requests van directo (Netlify CDN o n8n) |
| `ui/public/_headers` | CORS headers para Netlify (`Access-Control-Allow-Origin: *`) |

**Flujo de deep-link** (clic en fuente citada):
1. `ChatView` llama `onOpenTranscript(semester, subject, file, excerpt)`
2. `Index.tsx` setea `transcriptDeepLink` y cambia `activeView` a `"transcripts"`
3. `TranscriptsView` recibe `initialOpen`, hace `fetch` del archivo y ejecuta `scrollIntoView` al fragmento

**Persistencia del chat**: `messages` vive en `Index.tsx`, no en `ChatView`. Navegar a Transcripciones y volver no borra el historial.

---

## Flujo de scraping de Vimeo (vimeo_scraper.py)

El scraper usa **Playwright** (browser real Chromium) porque Vimeo migró a renderizado client-side (Next.js + Cloudflare) — el viejo approach HTTP con `requests` recibía HTML vacío.

**Dos etapas con Playwright**:

1. **Lista de videos**: intercepta el XHR `api.vimeo.com/albums/{id}/videos` mientras navega al showcase autenticado. Devuelve todos los videos del showcase.

2. **Config del player (subtítulos)**: por cada video, navega a su URL dentro de la sesión autenticada. Usa `page.expect_response()` para esperar el XHR `player.vimeo.com/video/{id}/config` de forma determinística (termina cuando llega, no con timeout fijo). Extrae `request.text_tracks[].url` del JSON.

**Skip de videos ya descargados**: verifica si existe algún archivo cuyo nombre empiece con `DD-MM-YYYY - ` antes de scrapear. Evita re-descargar clases ya guardadas.

**Nota**: Si Vimeo cambia su estructura, revisar la intercepción de XHRs en `vimeo_scraper.py`. El síntoma sería 0 videos encontrados o 0 subtítulos extraídos.
