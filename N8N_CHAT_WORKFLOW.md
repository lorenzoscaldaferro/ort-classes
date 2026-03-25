# n8n Chat Workflow — ORT Chat Agent

## Objetivo

Crear un nuevo workflow en n8n que reemplace a Flask como intermediario del chat.
El workflow recibe la pregunta del usuario, busca en Pinecone, sintetiza con GPT-4o-mini
y devuelve `{ answer, sources }` exactamente como lo hacía Flask.

## URL del nuevo webhook

`https://n8n.flowai.it.com/webhook/ort-chat-agent`

---

## Estructura del workflow (5 nodos)

```
[Webhook] → [HTTP Request: RAG] → [Code: Formatear] → [OpenAI: Sintetizar] → [Code: Respuesta] → [Respond to Webhook]
```

---

## Nodo 1 — Webhook

- **Tipo**: Webhook
- **HTTP Method**: POST
- **Path**: `ort-chat-agent`
- **Response Mode**: Using 'Respond to Webhook' Node
- **CORS**: Habilitar, Allow All Origins

---

## Nodo 2 — HTTP Request (llamar al RAG existente)

- **Tipo**: HTTP Request
- **Method**: POST
- **URL**: `https://n8n.flowai.it.com/webhook/ort-rag-search`
- **Body Parameters** (JSON):
  ```json
  { "query": "{{ $json.body.query }}" }
  ```
- **Response Format**: JSON

---

## Nodo 3 — Code (formatear sources + contexto)

- **Tipo**: Code
- **Language**: JavaScript

```javascript
const results = Array.isArray($input.first().json)
  ? $input.first().json
  : [$input.first().json];

const query = $('Webhook').first().json.body.query;

const SUBJECT_LABELS = {
  'economia_y_gestion':    'Economía y Gestión',
  'business_intelligence': 'Business Intelligence',
  'contabilidad_y_costos': 'Contabilidad y Costos',
  'project_management':    'Project Management',
  'ecommerce_y_servicios': 'E-commerce y Servicios',
  'matematica_financiera':  'Matemática Financiera',
};

const sources = [];
const contextChunks = [];

for (const r of results) {
  const doc = r.document || {};
  const text = (doc.pageContent || '').trim();
  const meta = doc.metadata || {};
  if (!text) continue;

  contextChunks.push(text);

  const titleRaw = meta.title || meta.source_file || '';
  const dateStr = meta.date || (titleRaw.match(/^(\d{2}-\d{2}-\d{4})/) || [])[1] || '';
  const fullTitle = (dateStr && titleRaw && !titleRaw.startsWith(dateStr))
    ? `${dateStr} - ${titleRaw}`
    : titleRaw;

  const semesterRaw = String(meta.semester || '');
  const semesterDir = /^\d+$/.test(semesterRaw) ? `semestre_${semesterRaw}` : semesterRaw;

  const subject = meta.subject || '';
  sources.push({
    subject,
    subjectLabel: SUBJECT_LABELS[subject] || subject.replace(/_/g, ' '),
    semester: semesterDir,
    title: fullTitle,
    date: dateStr,
    excerpt: text.length > 220 ? text.slice(0, 220) + '…' : text,
    score: Math.round((r.score || 0) * 1000) / 1000,
  });
}

const context = contextChunks.slice(0, 8).join('\n\n---\n\n');

return [{ json: { query, context, sources, hasContext: contextChunks.length > 0 } }];
```

---

## Nodo 4 — OpenAI Chat Model (sintetizar respuesta)

- **Tipo**: OpenAI (Chat Completion)
- **Credential**: tu OpenAI API Key
- **Model**: `gpt-4o-mini`
- **Temperature**: 0.2
- **System Message**:
  ```
  Sos un asistente académico personal. Respondé preguntas del estudiante basándote ÚNICAMENTE en los fragmentos de transcripciones de clases universitarias que se te proveen a continuación. Respondé en español rioplatense, de forma clara, directa y concisa. Si la información en los fragmentos es parcial, sintetizá lo que se pueda inferir y aclaralo. No inventes información que no esté respaldada por los fragmentos.
  ```
- **User Message**:
  ```
  Fragmentos de las clases:

  {{ $json.context }}

  ---

  Pregunta: {{ $json.query }}
  ```

Si no hay contexto (`hasContext === false`), el nodo puede retornar un mensaje fijo. Opcionalmente, agregar un nodo IF antes del OpenAI para manejar este caso.

---

## Nodo 5 — Code (ensamblar respuesta final)

- **Tipo**: Code
- **Language**: JavaScript

```javascript
const answer = $input.first().json.message?.content || $input.first().json.text || '';
const sources = $('Code: Formatear').first().json.sources || [];

return [{ json: { answer, sources } }];
```

---

## Nodo 6 — Respond to Webhook

- **Tipo**: Respond to Webhook
- **Response Body**: `{{ JSON.stringify($json) }}`
- **Response Headers**: `Content-Type: application/json`

---

## Verificacion rapida

```bash
curl -X POST https://n8n.flowai.it.com/webhook/ort-chat-agent \
  -H 'Content-Type: application/json' \
  -d '{"query":"que es la elasticidad precio"}'
```

Debe retornar: `{ "answer": "...", "sources": [...] }`

---

## Nota sobre CORS

El workflow de n8n necesita manejar el preflight OPTIONS.
En el nodo Webhook, activar la opcion de CORS o agregar un segundo
Webhook con metodo OPTIONS que devuelva headers de CORS manualmente.
Alternativamente: en Netlify, agregar un archivo `ui/public/_headers`:

```
/*
  Access-Control-Allow-Origin: *
```

Esto resuelve CORS desde el lado del cliente si n8n lo permite.
