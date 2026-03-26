#!/usr/bin/env python3
"""
Genera un archivo .txt concatenado por materia en ui/public/raw/.
Estos archivos estáticos son servidos por Netlify y usados como
fuentes URL en NotebookLM (reemplaza el approach de Google Drive).

Ejecutar desde el directorio cloud_production/.
"""

import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRANSCRIPTS_DIR = os.path.join(BASE_DIR, 'transcripts')
OUTPUT_DIR = os.path.join(BASE_DIR, 'ui', 'public', 'raw')

METADATA_PATTERNS = [
    re.compile(r'^\s*#\s+'),           # Título markdown
    re.compile(r'^\*\*Subject:\*\*'),  # **Subject:**
    re.compile(r'^\*\*Video ID:\*\*'), # **Video ID:**
    re.compile(r'^---\s*$'),           # Separador ---
]


def extract_body(content: str) -> str:
    """Extrae solo el cuerpo del transcript, sin el encabezado markdown."""
    lines = content.splitlines()
    body_lines = []
    skipping_header = True
    blank_count = 0

    for line in lines:
        if skipping_header:
            is_meta = any(p.match(line) for p in METADATA_PATTERNS)
            if is_meta or line.strip() == '':
                if line.strip() == '':
                    blank_count += 1
                    # Después de 2 líneas vacías post-header, asumimos que estamos en el cuerpo
                    if blank_count >= 2:
                        skipping_header = False
                else:
                    blank_count = 0
                continue
            else:
                skipping_header = False

        body_lines.append(line)

    return '\n'.join(body_lines).strip()


def generate():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not os.path.isdir(TRANSCRIPTS_DIR):
        print("[!] No se encontró el directorio transcripts/")
        return

    # Recolectar todos los archivos por materia (across semesters)
    subject_entries: dict[str, list[tuple[str, str, str]]] = {}

    for semester_dir in sorted(os.listdir(TRANSCRIPTS_DIR)):
        s_path = os.path.join(TRANSCRIPTS_DIR, semester_dir)
        if not os.path.isdir(s_path):
            continue
        for subject_dir in sorted(os.listdir(s_path)):
            sub_path = os.path.join(s_path, subject_dir)
            if not os.path.isdir(sub_path):
                continue
            files = sorted([f for f in os.listdir(sub_path) if f.endswith('.md')])
            for filename in files:
                filepath = os.path.join(sub_path, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                body = extract_body(content)
                if not body:
                    continue
                if subject_dir not in subject_entries:
                    subject_entries[subject_dir] = []
                subject_entries[subject_dir].append((semester_dir, filename, body))

    generated = 0
    for subject, entries in sorted(subject_entries.items()):
        parts = []
        for semester, filename, body in entries:
            title = filename.replace('.md', '')
            parts.append(f"=== {title} ===\n\n{body}")
        full_text = '\n\n\n'.join(parts)

        output_path = os.path.join(OUTPUT_DIR, f'{subject}.txt')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_text)

        print(f"[+] {subject}.txt — {len(entries)} clases, {len(full_text):,} chars")
        generated += 1

    print(f"\n[+] {generated} archivo(s) generado(s) en ui/public/raw/")


if __name__ == '__main__':
    generate()
