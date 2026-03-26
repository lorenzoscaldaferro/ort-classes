# NotebookLM Setup — Approach Kortex-style con `pynotebooklm`

Este archivo documenta el nuevo approach de integración con NotebookLM,
reemplazando el Google Drive approach anterior (eliminado).

---

## Qué hace ahora el sistema

En vez de Google Drive, el pipeline usa **archivos estáticos en Netlify**:

1. Después de cada scrape, `generate_raw_files.py` crea un `.txt` concatenado
   por materia en `ui/public/raw/`
2. Esos archivos se commitean y Netlify los sirve en URLs públicas:
   ```
   https://[netlify-url]/raw/business_intelligence.txt
   https://[netlify-url]/raw/economia_y_gestion.txt
   https://[netlify-url]/raw/contabilidad_y_costos.txt
   https://[netlify-url]/raw/project_management.txt
   https://[netlify-url]/raw/ecommerce_y_servicios.txt
   https://[netlify-url]/raw/matematica_financiera.txt
   ```
3. `notebooklm_sync.py` usa `pynotebooklm` para borrar y re-agregar la fuente URL
   en cada notebook → NotebookLM re-fetcha el contenido actualizado

---

## Flujo automático (post-setup)

```
Lun-Jue 23:00 UTC — GitHub Actions
  → vimeo_scraper.py descarga nuevas clases
  → generate_raw_files.py actualiza ui/public/raw/*.txt
  → git commit + push → Netlify rebuilda → URLs actualizadas
  → notebooklm_sync.py refresca fuentes en los 6 notebooks
  → Si falla → Telegram notification
```

---

## Setup manual (una sola vez)

### PASO 1: Auth local con pynotebooklm

```bash
pip3 install pynotebooklm
python3 -m pynotebooklm auth
```

Esto abre un browser → login normal con Google → las cookies se guardan en
`~/.pynotebooklm/auth.json`.

```bash
cat ~/.pynotebooklm/auth.json
# Copiar todo el contenido — va como NOTEBOOKLM_AUTH_JSON en GitHub Secrets
```

**Nota**: Las cookies expiran cada ~2 semanas. Repetir este paso y actualizar
el secret cuando el sync falle por auth inválida.

### PASO 2: Generar y pushear los archivos raw

```bash
cd /Users/lolescaldaferro/Antigravity/Vimeo/cloud_production
python3 generate_raw_files.py
git add ui/public/raw/
git commit -m "feat: add NotebookLM raw transcript files"
git push
```

Netlify rebuilda automáticamente. Verificar que las URLs funcionan:
```
https://[netlify-url]/raw/business_intelligence.txt
```

### PASO 3: Crear los 6 notebooks en NotebookLM

1. Ir a https://notebooklm.google.com
2. Crear **6 notebooks** (uno por materia):
   - ORT - Business Intelligence
   - ORT - Economía y Gestión
   - ORT - Contabilidad y Costos
   - ORT - Project Management
   - ORT - E-commerce y Servicios
   - ORT - Matemática Financiera
3. En cada notebook: **"+" → Website → pegar la URL de Netlify correspondiente**
4. Copiar las **URLs de los notebooks** desde el browser:
   - Formato: `https://notebooklm.google.com/notebook/{NOTEBOOK_ID}`

### PASO 4: GitHub Secrets

Ir a `github.com/lorenzoscaldaferro/ort-classes` → Settings → Secrets → Actions

Agregar:

| Secret | Valor |
|---|---|
| `NOTEBOOKLM_AUTH_JSON` | Contenido de `~/.pynotebooklm/auth.json` |
| `NOTEBOOKLM_NOTEBOOK_IDS` | JSON con los 6 IDs (ver formato abajo) |
| `NETLIFY_URL` | URL base del sitio (ej: `https://ort-classes.netlify.app`) |
| `TELEGRAM_BOT_TOKEN` | Token del bot |
| `TELEGRAM_CHAT_ID` | Tu chat ID |

**Formato de `NOTEBOOKLM_NOTEBOOK_IDS`:**
```json
{
  "business_intelligence":   "ID_DEL_NOTEBOOK_BI",
  "economia_y_gestion":      "ID_DEL_NOTEBOOK_EG",
  "contabilidad_y_costos":   "ID_DEL_NOTEBOOK_CC",
  "project_management":      "ID_DEL_NOTEBOOK_PM",
  "ecommerce_y_servicios":   "ID_DEL_NOTEBOOK_ES",
  "matematica_financiera":   "ID_DEL_NOTEBOOK_MF"
}
```

El ID es la parte final de la URL del notebook:
`https://notebooklm.google.com/notebook/**ESTE_ES_EL_ID**`

### PASO 5: Actualizar los URLs en el código

Con los IDs del Paso 3, reemplazar los PLACEHOLDERs en:

**`ui/src/components/dashboard/TranscriptsView.tsx`** (líneas ~28-35):
```typescript
const SUBJECT_NOTEBOOKS: Record<string, string> = {
  business_intelligence:   "https://notebooklm.google.com/notebook/REAL_ID",
  economia_y_gestion:      "https://notebooklm.google.com/notebook/REAL_ID",
  contabilidad_y_costos:   "https://notebooklm.google.com/notebook/REAL_ID",
  project_management:      "https://notebooklm.google.com/notebook/REAL_ID",
  ecommerce_y_servicios:   "https://notebooklm.google.com/notebook/REAL_ID",
  matematica_financiera:   "https://notebooklm.google.com/notebook/REAL_ID",
};
```

**`ui/src/components/dashboard/DashboardSidebar.tsx`** (líneas ~14-21):
```typescript
const NOTEBOOKLM_NOTEBOOKS = [
  { label: "Business Intelligence",  url: "https://notebooklm.google.com/notebook/REAL_ID" },
  ...
];
```

### PASO 6: Commit y push final

```bash
git add ui/src/components/dashboard/TranscriptsView.tsx
git add ui/src/components/dashboard/DashboardSidebar.tsx
git commit -m "feat: add NotebookLM notebook URLs"
git push
```

---

## Secrets configurados en GitHub

| Secret | Estado |
|---|---|
| `PINECONE_API_KEY` | Ya configurado |
| `PINECONE_HOST` | Ya configurado |
| `OPENAI_API_KEY` | Ya configurado |
| `SUBJECTS_JSON` | Ya configurado |
| `NOTEBOOKLM_AUTH_JSON` | **Nuevo — Paso 4** |
| `NOTEBOOKLM_NOTEBOOK_IDS` | **Nuevo — Paso 4** |
| `NETLIFY_URL` | **Nuevo — Paso 4** |
| `TELEGRAM_BOT_TOKEN` | **Nuevo — Paso 4** |
| `TELEGRAM_CHAT_ID` | **Nuevo — Paso 4** |

---

## Por qué no es 100% automático como Kortex

Kortex funciona como extensión de Chrome porque corre en el contexto del browser
con tu sesión de Google ya activa. Sin extensión, `pynotebooklm` necesita cookies
guardadas manualmente — de ahí el `auth` inicial y el refresh periódico (~2 semanas).

La buena noticia: una vez configurado, el sync es completamente automático después
de cada scrape sin intervención manual.
