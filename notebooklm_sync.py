#!/usr/bin/env python3
"""
Sincroniza las fuentes URL de NotebookLM después de cada scrape.

Para cada materia configurada, este script:
1. Lista las fuentes existentes en el notebook
2. Elimina la fuente que apunta a nuestro archivo /raw/ (cualquier host)
3. Re-agrega la URL actualizada — NotebookLM re-fetcha el contenido

Requiere estas env vars (GitHub Secrets):
  NOTEBOOKLM_AUTH_JSON    — Contenido JSON de ~/.notebooklm-mcp/auth.json
                            (generado localmente con: notebooklm-mcp-auth)
  NOTEBOOKLM_NOTEBOOK_IDS — JSON map: {"subject_name": "notebook_id", ...}
  NETLIFY_URL             — URL base del sitio (sin trailing slash)
                            Ej: https://ort-classes.vercel.app

Si alguna de estas env vars no está seteada, el script sale limpiamente
sin marcar el workflow como fallido.

Setup inicial (una sola vez, localmente):
  pip3 install notebooklm-mcp
  notebooklm-mcp-auth      # abre Chrome real → login con Google
  cat ~/.notebooklm-mcp/auth.json  # copiar como NOTEBOOKLM_AUTH_JSON en GitHub Secrets

Nota: Las cookies expiran cada ~2-4 semanas. Repetir notebooklm-mcp-auth y actualizar
el secret NOTEBOOKLM_AUTH_JSON cuando fallen.
"""

import json
import os
from pathlib import Path


def load_config() -> dict | None:
    """Carga y valida la configuración desde env vars. Retorna None si faltan vars."""
    auth_json = os.environ.get('NOTEBOOKLM_AUTH_JSON', '').strip()
    notebook_ids_raw = os.environ.get('NOTEBOOKLM_NOTEBOOK_IDS', '').strip()
    site_url = os.environ.get('NETLIFY_URL', '').strip().rstrip('/')

    missing = [k for k, v in {
        'NOTEBOOKLM_AUTH_JSON': auth_json,
        'NOTEBOOKLM_NOTEBOOK_IDS': notebook_ids_raw,
        'NETLIFY_URL': site_url,
    }.items() if not v]

    if missing:
        print(f"[notebooklm-sync] Skipping — env vars no configuradas: {', '.join(missing)}")
        return None

    try:
        auth_data = json.loads(auth_json)
    except json.JSONDecodeError as e:
        print(f"[notebooklm-sync] NOTEBOOKLM_AUTH_JSON JSON inválido: {e}")
        return None

    try:
        notebook_ids = json.loads(notebook_ids_raw)
    except json.JSONDecodeError as e:
        print(f"[notebooklm-sync] NOTEBOOKLM_NOTEBOOK_IDS JSON inválido: {e}")
        return None

    return {
        'auth_data': auth_data,
        'notebook_ids': notebook_ids,
        'site_url': site_url,
    }


def sync_notebook(client, notebook_id: str, subject: str, raw_url: str) -> bool:
    """
    Actualiza la fuente URL de un notebook.
    Borra la fuente existente (si existe) y agrega la URL actualizada.
    """
    try:
        # 1. Listar fuentes existentes con sus URLs
        existing = client.get_notebook_sources_with_types(notebook_id)

        # 2. Borrar fuentes que apuntan a nuestros raw files (cualquier host)
        for source in existing:
            source_url = source.get('url') or ''
            if f'/raw/{subject}' in source_url:
                print(f"  [-] Borrando fuente antigua: {source_url or source['id']}")
                client.delete_source(source['id'])

        # 3. Agregar URL actualizada
        print(f"  [+] Agregando: {raw_url}")
        result = client.add_url_source(notebook_id, raw_url)
        if result and isinstance(result, dict):
            status = result.get('status', 'ok')
            if status == 'timeout':
                print(f"  [~] Timeout (puede que haya funcionado igual): {result.get('message', '')}")
            else:
                print(f"  [✓] Fuente agregada")
        else:
            print(f"  [✓] Fuente agregada")
        return True

    except Exception as e:
        print(f"  [!] Error sincronizando {subject}: {e}")
        return False


def run(config: dict) -> None:
    try:
        from notebooklm_mcp.api_client import NotebookLMClient
    except ImportError:
        print("[notebooklm-sync] notebooklm-mcp no instalado. Correr: pip3 install notebooklm-mcp")
        return

    auth_data = config['auth_data']
    cookies = auth_data.get('cookies', {})
    csrf_token = auth_data.get('csrf_token', '')
    session_id = auth_data.get('session_id', '')

    if not cookies:
        print("[notebooklm-sync] Auth inválida — no hay cookies en NOTEBOOKLM_AUTH_JSON")
        print("  Solución: correr 'notebooklm-mcp-auth' localmente y actualizar")
        print("  el secret NOTEBOOKLM_AUTH_JSON en GitHub con el nuevo auth.json")
        return

    client = NotebookLMClient(
        cookies=cookies,
        csrf_token=csrf_token,
        session_id=session_id,
    )

    success = 0
    total = len(config['notebook_ids'])

    for subject, notebook_id in config['notebook_ids'].items():
        raw_url = f"{config['site_url']}/raw/{subject}.txt"
        print(f"\n[{subject}]")
        ok = sync_notebook(client, notebook_id, subject, raw_url)
        if ok:
            success += 1

    print(f"\n[notebooklm-sync] Completado — {success}/{total} notebooks sincronizados")


if __name__ == '__main__':
    cfg = load_config()
    if cfg:
        run(cfg)
