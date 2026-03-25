"""
One-shot script to ingest all existing transcripts into Pinecone.
Run once to populate the index with transcripts downloaded before
the automatic ingestion was added to vimeo_scraper.py.
"""
import os
import re
import json
import requests
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHUNK_SIZE = 3000
CHUNK_OVERLAP = 300


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return chunks


def get_embedding(text, api_key):
    resp = requests.post(
        'https://api.openai.com/v1/embeddings',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={'input': text, 'model': 'text-embedding-3-small'},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()['data'][0]['embedding']


def upsert_vectors(vectors, host, api_key):
    resp = requests.post(
        f"{host.rstrip('/')}/vectors/upsert",
        headers={'Api-Key': api_key, 'Content-Type': 'application/json'},
        json={'vectors': vectors},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get('upsertedCount', len(vectors))


def ingest_file(filepath, subject_name, semester, openai_key, pinecone_host, pinecone_key):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract video ID from file header
    video_id_match = re.search(r'\*\*Video ID:\*\*\s*(\S+)', content)
    video_id = video_id_match.group(1) if video_id_match else os.path.basename(filepath)

    # Extract date from filename (DD-MM-YYYY prefix)
    date_match = re.match(r'(\d{2}-\d{2}-\d{4})', os.path.basename(filepath))
    date_str = date_match.group(1) if date_match else ''

    # Extract title (filename without date prefix and .md)
    title = re.sub(r'^\d{2}-\d{2}-\d{4} - ', '', os.path.basename(filepath))
    title = re.sub(r'\.md$', '', title)

    # Strip markdown header, use just the transcript body
    body = re.sub(r'^.*?---\n\n', '', content, flags=re.DOTALL)

    chunks = chunk_text(body)
    vectors = []
    for i, chunk in enumerate(chunks):
        try:
            embedding = get_embedding(chunk, openai_key)
            vectors.append({
                'id': f"{video_id}_{i}",
                'values': embedding,
                'metadata': {
                    'subject': subject_name,
                    'semester': str(semester),
                    'title': title,
                    'date': date_str,
                    'text': chunk,
                    'chunk_index': i,
                },
            })
        except Exception as e:
            print(f"  [!] Embedding chunk {i} failed: {e}")

    if vectors:
        count = upsert_vectors(vectors, pinecone_host, pinecone_key)
        print(f"  [+] {os.path.basename(filepath)}: {count} vector(s) upserted")
    else:
        print(f"  [!] {os.path.basename(filepath)}: no vectors generated")


if __name__ == "__main__":
    config_path = os.path.join(BASE_DIR, 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    openai_key = config['openai_api_key']
    pinecone_key = config['pinecone_api_key']
    pinecone_host = config['pinecone_host']

    transcripts_root = os.path.join(BASE_DIR, 'transcripts')

    for semester_dir in sorted(os.listdir(transcripts_root)):
        semester_path = os.path.join(transcripts_root, semester_dir)
        if not os.path.isdir(semester_path):
            continue
        semester_num = semester_dir.replace('semestre_', '')

        for subject_dir in sorted(os.listdir(semester_path)):
            subject_path = os.path.join(semester_path, subject_dir)
            if not os.path.isdir(subject_path):
                continue

            md_files = [f for f in os.listdir(subject_path) if f.endswith('.md')]
            print(f"\n{semester_dir}/{subject_dir} — {len(md_files)} file(s)")

            for md_file in sorted(md_files):
                print(f"  Processing: {md_file}")
                try:
                    ingest_file(
                        os.path.join(subject_path, md_file),
                        subject_dir,
                        semester_num,
                        openai_key,
                        pinecone_host,
                        pinecone_key,
                    )
                except Exception as e:
                    print(f"  [!] Failed: {e}")

    print("\nDone ingesting all existing transcripts.")
