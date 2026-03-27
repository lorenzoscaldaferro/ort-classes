# ORT Vimeo RAG — Cheatsheet

Referencia rápida de toda la infraestructura. Diseñado para ser leído por un humano o por un LLM sin contexto previo.

---

## Qué hace este sistema

1. **Descarga** las transcripciones de clases desde showcases privados de Vimeo (protegidos con contraseña)
2. **Guarda** cada transcripción como archivo Markdown en carpetas organizadas por semestre y materia
3. **Ingesta** el texto en Pinecone (base vectorial) para búsqueda semántica
4. **Sirve** una UI React estática en Netlify con chat semántico, visor de transcripciones y navegación desde fuentes citadas
5. **Sintetiza** respuestas vía n8n (workflow `ORT Chat Agent`): recibe la query, busca en Pinecone, genera respuesta con GPT-4 y devuelve `{ answer, sources[] }` al frontend

> **Cloud vs Local**: `cloud_production/` es el build serverless. El scraper corre en GitHub Actions (nightly). El frontend está en Netlify. El chat API es n8n. No se requiere Mac encendida para que el sistema funcione.

---

## Archivos clave

| Archivo | Propósito |
|---|---|
| `vimeo_scraper.py` | Script principal: scraping + guardado + ingesta Pinecone |
| `ingest_existing.py` | Ingesta en Pinecone todos los `.md` ya descargados (correr una sola vez) |
| `api_server.py` | Flask API en puerto 5001: `/api/chat` y `/api/transcripts` |
| `config.json` | Configuración: API keys, materias, URLs y contraseñas de Vimeo |
| `cron.log` | Log de todas las ejecuciones automáticas del cron |
| `ui/` | Frontend React + Vite (localhost:5174) |
| `vimeo_dump.py` | Debug: vuelca el HTML crudo de un showcase |
| `vimeo_check_auth.py` | Debug: chequea headers HTTP de respuesta |
| `test_config.py` | Debug: prueba la API del player para un video específico |

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
│  GitHub Actions (Ubuntu)                            │
│    → vimeo_scraper.py                               │
│       → Autentica en Vimeo (password)               │
│       → Descarga VTT (subtítulos)                   │
│       → Convierte VTT → texto plano                 │
│       → Guarda .md en cloud_production/transcripts/ │
│       → Divide en chunks de ~3000 chars             │
│       → OpenAI text-embedding-3-small               │
│       → Upsert a Pinecone (índice: ort-clases)      │
│       → Regenera transcripts_index.json             │
│    → git commit + push → Netlify rebuilds           │
│                                                     │
│  Mac cron 23:20 UTC (si está encendida)             │
│    → sync-local.sh: git pull + rsync al local       │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  UI PRODUCCIÓN (Netlify CDN)                        │
│                                                     │
│  React + Vite (build estático)                      │
│    → Transcripciones: fetch /transcripts_index.json │
│    → Archivo: fetch /transcripts/{sem}/{sub}/{file} │
│    → Chat: POST n8n webhook/ort-chat-agent          │
│    → Fuente citada → abre transcript con highlight  │
│                                                     │
│  (sin Flask, sin servidor Node, sin cron local)     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  CHAT RAG (on-demand, vía n8n)                      │
│                                                     │
│  n8n workflow "ORT Chat Agent"                      │
│    → POST webhook/ort-chat-agent  { query }         │
│    → HTTP request → webhook/ort-rag-search          │
│    → n8n: OpenAI embedding + Pinecone top-8 chunks  │
│    → Code: formatea sources[] con semester/subject  │
│    → OpenAI GPT-4: sintetiza respuesta              │
│    → Devuelve { answer, sources[] }                 │
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

El scraper intenta tres estrategias en orden para obtener el player config JSON que contiene los text tracks:

1. `window.vimeo.clip_page_config` en la página del video → `config_url` externo
2. `var config = {...}` embebido directamente en el HTML
3. `<iframe src="player.vimeo.com/...">` → `window.playerConfig` en el HTML del iframe

Una vez obtenido el player config, extrae `request.text_tracks[].url` para descargar el VTT.

**Nota**: Si Vimeo cambia su estructura de página, revisar estas tres estrategias en `extract_vtt_from_showcase()`.
