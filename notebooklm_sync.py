#!/usr/bin/env python3
"""
Sincroniza las fuentes URL de NotebookLM después de cada scrape.

Para cada materia configurada, este script:
1. Lista las fuentes existentes en el notebook
2. Elimina la fuente que apunta a nuestro archivo /raw/ en Netlify
3. Re-agrega la misma URL — NotebookLM re-fetcha el contenido actualizado

Requiere estas env vars (GitHub Secrets):
  NOTEBOOKLM_AUTH_JSON   — Contenido JSON de ~/.pynotebooklm/auth.json
                           (generado localmente con: pynotebooklm auth)
  NOTEBOOKLM_NOTEBOOK_IDS — JSON map: {"subject_name": "notebook_id", ...}
  NETLIFY_URL             — URL base del sitio Netlify (sin trailing slash)
                           Ej: https://ort-classes.netlify.app

Si alguna de estas env vars no está seteada, el script sale limpiamente
sin marcar el workflow como fallido.

Setup inicial (una sola vez, localmente):
  pip3 install pynotebooklm
  python3 -m pynotebooklm auth   # abre browser → login con Google
  cat ~/.pynotebooklm/auth.json  # copiar como NOTEBOOKLM_AUTH_JSON en GitHub Secrets

Nota: Las cookies expiran cada ~2 semanas. Repetir el paso de auth cuando fallen.
"""

import asyncio
import json
import os
from pathlib import Path


def load_config() -> dict | None:
    """Carga y valida la configuración desde env vars. Retorna None si faltan vars."""
    auth_json = os.environ.get('NOTEBOOKLM_AUTH_JSON', '').strip()
    notebook_ids_raw = os.environ.get('NOTEBOOKLM_NOTEBOOK_IDS', '').strip()
    netlify_url = os.environ.get('NETLIFY_URL', '').strip().rstrip('/')

    missing = [k for k, v in {
        'NOTEBOOKLM_AUTH_JSON': auth_json,
        'NOTEBOOKLM_NOTEBOOK_IDS': notebook_ids_raw,
        'NETLIFY_URL': netlify_url,
    }.items() if not v]

    if missing:
        print(f"[notebooklm-sync] Skipping — env vars no configuradas: {', '.join(missing)}")
        return None

    try:
        notebook_ids = json.loads(notebook_ids_raw)
    except json.JSONDecodeError as e:
        print(f"[notebooklm-sync] NOTEBOOKLM_NOTEBOOK_IDS JSON inválido: {e}")
        return None

    return {
        'auth_json': auth_json,
        'notebook_ids': notebook_ids,
        'netlify_url': netlify_url,
    }


def write_auth_file(auth_json: str) -> Path:
    """Escribe el JSON de auth al archivo que AuthManager espera."""
    auth_path = Path.home() / '.pynotebooklm' / 'auth.json'
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text(auth_json)
    auth_path.chmod(0o600)
    return auth_path


async def sync_notebook(sources_mgr, notebook_id: str, subject: str, raw_url: str) -> bool:
    """
    Actualiza la fuente URL de un notebook.
    Borra la fuente existente (si existe) y agrega la URL actualizada.
    """
    try:
        # 1. Listar fuentes existentes
        existing = await sources_mgr.list_sources(notebook_id)

        # 2. Borrar fuentes que apuntan a nuestros raw files
        for source in existing:
            source_url = getattr(source, 'url', '') or getattr(source, 'uri', '') or ''
            if f'/raw/{subject}' in source_url or (subject in source_url and 'netlify' in source_url):
                print(f"  [-] Borrando fuente antigua: {source_url or source.id}")
                await sources_mgr.delete(notebook_id, source.id)

        # 3. Agregar URL actualizada
        print(f"  [+] Agregando: {raw_url}")
        result = await sources_mgr.add_url(notebook_id, raw_url)
        title = getattr(result, 'title', '') or raw_url
        print(f"  [✓] Fuente agregada: {title}")
        return True

    except Exception as e:
        print(f"  [!] Error sincronizando {subject}: {e}")
        return False


async def run(config: dict) -> None:
    auth_path = write_auth_file(config['auth_json'])

    try:
        from pynotebooklm import NotebookLMClient
        from pynotebooklm.auth import AuthManager
    except ImportError:
        print("[notebooklm-sync] pynotebooklm no instalado. Correr: pip3 install pynotebooklm")
        return

    auth = AuthManager(auth_path=auth_path)
    if not auth.is_authenticated():
        print("[notebooklm-sync] Auth inválida o expirada.")
        print("  Solución: correr 'python3 -m pynotebooklm auth' localmente y actualizar")
        print("  el secret NOTEBOOKLM_AUTH_JSON en GitHub con el nuevo auth.json")
        return

    success = 0
    total = len(config['notebook_ids'])

    async with NotebookLMClient(auth=auth) as client:
        for subject, notebook_id in config['notebook_ids'].items():
            raw_url = f"{config['netlify_url']}/raw/{subject}.txt"
            print(f"\n[{subject}]")
            ok = await sync_notebook(client.sources, notebook_id, subject, raw_url)
            if ok:
                success += 1

    print(f"\n[notebooklm-sync] Completado — {success}/{total} notebooks sincronizados")


if __name__ == '__main__':
    cfg = load_config()
    if cfg:
        asyncio.run(run(cfg))
