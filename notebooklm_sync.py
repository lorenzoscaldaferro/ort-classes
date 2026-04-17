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
  VERCEL_URL              — URL base del sitio Vercel (sin trailing slash)
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
import sys
from pathlib import Path


def load_config() -> dict | None:
    """Carga y valida la configuración desde env vars. Retorna None si faltan vars."""
    auth_json = os.environ.get('NOTEBOOKLM_AUTH_JSON', '').strip()
    notebook_ids_raw = os.environ.get('NOTEBOOKLM_NOTEBOOK_IDS', '').strip()
    site_url = os.environ.get('VERCEL_URL', '').strip().rstrip('/')

    missing = [k for k, v in {
        'NOTEBOOKLM_AUTH_JSON': auth_json,
        'NOTEBOOKLM_NOTEBOOK_IDS': notebook_ids_raw,
        'VERCEL_URL': site_url,
    }.items() if not v]

    if missing:
        if os.environ.get('GITHUB_ACTIONS'):
            print(f"[notebooklm-sync] ERROR — env vars requeridas no configuradas en CI: {', '.join(missing)}")
            sys.exit(1)
        print(f"[notebooklm-sync] Skipping — env vars no configuradas: {', '.join(missing)}")
        return None

    try:
        auth_data = json.loads(auth_json)
    except json.JSONDecodeError as e:
        print(f"[notebooklm-sync] NOTEBOOKLM_AUTH_JSON JSON inválido: {e}")
        sys.exit(1)

    try:
        notebook_ids = json.loads(notebook_ids_raw)
    except json.JSONDecodeError as e:
        print(f"[notebooklm-sync] NOTEBOOKLM_NOTEBOOK_IDS JSON inválido: {e}")
        sys.exit(1)

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
        print(f"  [DEBUG] {len(existing)} fuente(s) encontradas:")
        for src in existing:
            print(f"    id={src.get('id')!r} | type={src.get('source_type_name')!r} | url={src.get('url')!r} | title={src.get('title')!r}")

        # 2. Borrar fuentes que apuntan a nuestros raw files (cualquier host)
        # Match primario: URL contiene nuestro path
        # Match fallback: url vacía pero title contiene el path o "netlify.app"
        # (necesario si la librería no extrae el url del metadata correctamente)
        deleted = 0
        for source in existing:
            source_url = source.get('url') or ''
            source_title = source.get('title') or ''
            should_delete = (
                f'/raw/{subject}' in source_url
                or (not source_url and (f'/raw/{subject}' in source_title or 'netlify.app' in source_title))
            )
            if should_delete:
                print(f"  [-] Borrando fuente antigua: url={source_url!r} | title={source_title!r}")
                client.delete_source(source['id'])
                deleted += 1

        if deleted == 0:
            if existing:
                print(f"  [!] ADVERTENCIA: ninguna fuente matcheó '/raw/{subject}' — la URL vieja puede no haberse borrado")
            else:
                print(f"  [i] No hay fuentes existentes — se agrega nueva directamente")

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
        sys.exit(1)

    # No pasamos csrf_token ni session_id: el cliente hace un page fetch fresco
    # para extraer el CSRF token actual, session_id, y el build label (bl) del
    # frontend de NotebookLM — los valores cacheados en auth.json expiran rápido.
    client = NotebookLMClient(cookies=cookies)

    success = 0
    total = len(config['notebook_ids'])

    for subject, notebook_id in config['notebook_ids'].items():
        raw_url = f"{config['site_url']}/raw/{subject}.txt"
        print(f"\n[{subject}]")
        ok = sync_notebook(client, notebook_id, subject, raw_url)
        if ok:
            success += 1

    print(f"\n[notebooklm-sync] Completado — {success}/{total} notebooks sincronizados")
    if success < total:
        failed = total - success
        print(f"[notebooklm-sync] ERROR — {failed} notebook(s) fallaron.")
        print("  Si el error es de autenticación, correr 'notebooklm-mcp-auth' y actualizar")
        print("  el secret NOTEBOOKLM_AUTH_JSON en GitHub con el nuevo auth.json")
        sys.exit(1)


if __name__ == '__main__':
    cfg = load_config()
    if cfg:
        run(cfg)
