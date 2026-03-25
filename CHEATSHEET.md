# ORT Vimeo RAG — Cheatsheet

Referencia rápida de toda la infraestructura. Diseñado para ser leído por un humano o por un LLM sin contexto previo.

---

## Qué hace este sistema

1. **Descarga** las transcripciones de clases desde showcases privados de Vimeo (protegidos con contraseña)
2. **Guarda** cada transcripción como archivo Markdown en carpetas organizadas por semestre y materia
3. **Ingesta** el texto en Pinecone (base vectorial) para búsqueda semántica
4. **Expone** una API Flask local que recibe preguntas, busca chunks relevantes vía n8n/Pinecone, y sintetiza respuestas con GPT-4o-mini
5. **Sirve** una UI React local (localhost:5174) con chat semántico, visor de transcripciones y navegación desde fuentes citadas

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

### Correr el scraper manualmente (todas las materias)
```bash
python3 /Users/lolescaldaferro/Antigravity/Vimeo/vimeo_scraper.py
```
- Loopea las 5 materias de `config.json`
- Skipea archivos ya existentes (no re-descarga)
- Ingesta en Pinecone solo los nuevos

### Ingestar transcripciones existentes en Pinecone (una sola vez)
```bash
python3 /Users/lolescaldaferro/Antigravity/Vimeo/ingest_existing.py
```

### Ver el log del cron
```bash
tail -f /Users/lolescaldaferro/Antigravity/Vimeo/cron.log
```

### Ver el cron configurado
```bash
crontab -l
```
Salida esperada:
```
0 20 * * 1-4 /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Users/lolescaldaferro/Antigravity/Vimeo/vimeo_scraper.py >> /Users/lolescaldaferro/Antigravity/Vimeo/cron.log 2>&1
```

### Correr la UI local
```bash
# Terminal 1 — API backend
cd /Users/lolescaldaferro/Antigravity/Vimeo
python3 api_server.py
# Escucha en http://localhost:5001

# Terminal 2 — Frontend
cd /Users/lolescaldaferro/Antigravity/Vimeo/ui
npm run dev
# Abre http://localhost:5174
```

### Instalar dependencias Python
```bash
pip install requests beautifulsoup4 flask flask-cors openai
```
No hay dependencias extra para Pinecone: se llama vía `requests` directamente.

### Instalar dependencias UI
```bash
cd /Users/lolescaldaferro/Antigravity/Vimeo/ui
npm install
```

---

## Cron (ejecución automática)

- **Horario**: lunes a jueves a las **20:00 hora local** (UYT, UTC-3)
- **Requisito**: el Mac debe estar **encendido y despierto** a esa hora
- **Logs**: se acumulan en `cron.log`
- Para que no falle por suspensión: Preferencias del Sistema → Batería → desactivar suspensión automática en noches de semana

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

## Arquitectura completa

```
┌─────────────────────────────────────────────────────┐
│  INGESTA (automática, lun-jue 20:00)                │
│                                                     │
│  Mac cron                                           │
│    → vimeo_scraper.py                               │
│       → Autentica en Vimeo (password)               │
│       → Descarga VTT (subtítulos)                   │
│       → Convierte VTT → texto plano                 │
│       → Guarda .md en transcripts/                  │
│       → Divide en chunks de ~3000 chars             │
│       → OpenAI text-embedding-3-small               │
│       → Upsert a Pinecone (índice: ort-clases)      │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  UI LOCAL (localhost:5174)                          │
│                                                     │
│  React + Vite (npm run dev)                         │
│    → Chat: pregunta → POST /api/chat                │
│    → Transcripciones: GET /api/transcripts          │
│    → Fuente citada → abre transcript con highlight  │
│                                                     │
│  Flask API (python3 api_server.py, puerto 5001)     │
│    → /api/chat                                      │
│       → POST n8n webhook (RAG search)               │
│       → Recibe top 8 chunks de Pinecone             │
│       → GPT-4o-mini sintetiza la respuesta          │
│       → Devuelve { answer, sources[] }              │
│    → /api/transcripts                               │
│       → Lee filesystem transcripts/                 │
│       → Devuelve árbol semestre/materia/archivos    │
│    → /api/transcripts/<path>                        │
│       → Devuelve contenido de un .md               │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  BÚSQUEDA RAG (on-demand, vía n8n)                  │
│                                                     │
│  Flask api_server.py                                │
│    → POST https://n8n.flowai.it.com/               │
│             webhook/ort-rag-search                  │
│       body: { "query": "tu pregunta" }              │
│    → n8n: OpenAI embedding de la query              │
│    → n8n: Pinecone "Get Many" (top chunks)          │
│    → Devuelve chunks con metadata                   │
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

**Importante**: `semester` viene como número (`"5"`), no como nombre de directorio (`semestre_5`). `api_server.py` lo convierte antes de enviarlo al frontend.

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
| `ui/src/components/dashboard/ChatView.tsx` | Vista de chat: input, mensajes, source cards clicables |
| `ui/src/components/dashboard/TranscriptsView.tsx` | Vista de transcripciones: árbol semestre/materia, visor con highlight |
| `ui/src/components/dashboard/DashboardSidebar.tsx` | Navegación lateral: Chat con mis clases / Transcripciones |
| `ui/vite.config.ts` | Proxy `/api` → `http://localhost:5001` |

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
