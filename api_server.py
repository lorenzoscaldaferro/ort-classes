"""
ORT Knowledge Base — API server
Proxies chat queries: n8n RAG search → OpenAI synthesis → JSON response
Also serves the transcripts filesystem as JSON.
"""
import json
import os
import re

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from openai import OpenAI

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
TRANSCRIPTS_PATH = os.path.join(BASE_DIR, 'transcripts')
N8N_WEBHOOK = "https://n8n.flowai.it.com/webhook/ort-rag-search"

app = Flask(__name__)
CORS(app)


def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_date(text):
    m = re.match(r'(\d{2}-\d{2}-\d{4})', str(text))
    return m.group(1) if m else ''


def subject_label(slug):
    labels = {
        'economia_y_gestion':   'Economía y Gestión',
        'business_intelligence': 'Business Intelligence',
        'contabilidad_y_costos': 'Contabilidad y Costos',
        'project_management':   'Project Management',
        'ecommerce_y_servicios': 'E-commerce y Servicios',
        'matematica_financiera': 'Matemática Financiera',
    }
    return labels.get(slug, slug.replace('_', ' ').title())


# ---------------------------------------------------------------------------
# /api/chat
# ---------------------------------------------------------------------------

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json(silent=True) or {}
    query = (data.get('query') or '').strip()
    if not query:
        return jsonify({'error': 'No query provided'}), 400

    config = load_config()

    # 1. Retrieve relevant chunks from Pinecone via n8n
    try:
        n8n_resp = requests.post(
            N8N_WEBHOOK,
            json={'query': query},
            timeout=30,
        )
        n8n_resp.raise_for_status()
        raw = n8n_resp.json()
    except Exception as e:
        return jsonify({'error': f'RAG search failed: {e}'}), 502

    # n8n may return a single object or a list
    results = raw if isinstance(raw, list) else [raw]

    sources = []
    context_chunks = []
    for r in results:
        doc = r.get('document', {})
        text = (doc.get('pageContent') or '').strip()
        meta = doc.get('metadata', {})
        if not text:
            continue
        context_chunks.append(text)
        title_raw = meta.get('title') or meta.get('source_file') or ''
        date_from_meta = meta.get('date', '') or extract_date(title_raw)
        # Reconstruct full filename: ingest stored title without date prefix
        if date_from_meta and title_raw and not title_raw.startswith(date_from_meta):
            full_title = f"{date_from_meta} - {title_raw}"
        else:
            full_title = title_raw
        # Semester stored as bare number ("5"), filesystem uses "semestre_5"
        semester_raw = str(meta.get('semester', ''))
        semester_dir = f"semestre_{semester_raw}" if semester_raw.isdigit() else semester_raw
        sources.append({
            'subject':      meta.get('subject', ''),
            'subjectLabel': subject_label(meta.get('subject', '')),
            'semester':     semester_dir,
            'title':        full_title,
            'date':         date_from_meta,
            'excerpt':      text[:220] + '…' if len(text) > 220 else text,
            'score':        round(r.get('score', 0), 3),
        })

    if not context_chunks:
        return jsonify({
            'answer': 'No encontré información relevante en tus transcripciones para esa pregunta. Intentá reformular o usá términos que aparezcan en las clases.',
            'sources': [],
        })

    # 2. Synthesize with OpenAI
    client = OpenAI(api_key=config['openai_api_key'])
    context = '\n\n---\n\n'.join(context_chunks[:8])

    try:
        completion = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'Sos un asistente académico personal. '
                        'Respondé preguntas del estudiante basándote ÚNICAMENTE en los fragmentos '
                        'de transcripciones de clases universitarias que se te proveen a continuación. '
                        'Respondé en español rioplatense, de forma clara, directa y concisa. '
                        'Si la información en los fragmentos es parcial, sintetizá lo que se pueda inferir y aclaralo. '
                        'No inventes información que no esté respaldada por los fragmentos.'
                    ),
                },
                {
                    'role': 'user',
                    'content': f'Fragmentos de las clases:\n\n{context}\n\n---\n\nPregunta: {query}',
                },
            ],
            temperature=0.2,
        )
        answer = completion.choices[0].message.content
    except Exception as e:
        return jsonify({'error': f'LLM synthesis failed: {e}'}), 502

    return jsonify({'answer': answer, 'sources': sources})


# ---------------------------------------------------------------------------
# /api/transcripts
# ---------------------------------------------------------------------------

@app.route('/api/transcripts', methods=['GET'])
def transcripts_list():
    result = {}
    if not os.path.isdir(TRANSCRIPTS_PATH):
        return jsonify(result)
    for semester_dir in sorted(os.listdir(TRANSCRIPTS_PATH)):
        s_path = os.path.join(TRANSCRIPTS_PATH, semester_dir)
        if not os.path.isdir(s_path):
            continue
        result[semester_dir] = {}
        for subject_dir in sorted(os.listdir(s_path)):
            sub_path = os.path.join(s_path, subject_dir)
            if not os.path.isdir(sub_path):
                continue
            files = sorted(
                [f for f in os.listdir(sub_path) if f.endswith('.md')],
                reverse=True,
            )
            result[semester_dir][subject_dir] = {
                'label': subject_label(subject_dir),
                'files': files,
            }
    return jsonify(result)


@app.route('/api/transcripts/<path:filepath>', methods=['GET'])
def transcript_file(filepath):
    full_path = os.path.realpath(os.path.join(TRANSCRIPTS_PATH, filepath))
    if not full_path.startswith(os.path.realpath(TRANSCRIPTS_PATH)):
        return jsonify({'error': 'Invalid path'}), 400
    if not os.path.isfile(full_path):
        return jsonify({'error': 'File not found'}), 404
    with open(full_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return jsonify({'content': content})


if __name__ == '__main__':
    print("ORT Knowledge Base API — http://localhost:5001")
    app.run(port=5001, debug=False)
