# Changelog

All notable changes to the ORT Vimeo Scraper & RAG Knowledge Base project will be documented in this file.

## [Unreleased] - 2026-03-24 (Phase 4: Cloud Migration)

### Added
- **Production Isolation**: Created `cloud_production/` directory to separate the serverless production build from the local development codebase.
- **Serverless Scraper Pipeline**: Refactored `vimeo_scraper.py` into a pure Python/Requests script to remove Playwright/Node dependencies. Configured GitHub Action `.github/workflows/scraper.yml` to automate nightly scraping and Pinecone ingestion at 20:00 local time.
- **n8n AI Chat Agent**: Replaced the local Flask API with an industrial-grade n8n workflow (`ort-chat-agent`). Includes `n8n_chat_workflow.json` for one-shot deployment, handling Pinecone retrieval, context formatting, and GPT-4o-mini synthesis.
- **Static Frontend Architecture**: Migrated React UI to Netlify. Optimized the build process to bundle Markdown transcripts and a static `transcripts_index.json` directly into the `public/` directory for zero-latency loading.
- **CORS & Git Security**: Integrated `gh auth setup-git` protocols to bypass macOS Keychain credential conflicts. Implemented Repository Secrets for `PINECONE_API_KEY`, `OPENAI_API_KEY`, and `SUBJECTS_JSON`.

### Changed
- **Frontend Connectivity**: `ChatView.tsx` now POSTs directly to the n8n production webhook, eliminating the need for a persistent middleware server.
- **Scraper Persistence**: New GitHub Action commits new transcripts directly to the repository branch, ensuring the static frontend always has the latest data after each run.

## [Unreleased] - 2026-03-24 (UI Round 2)

### Fixed
- **Transcript deep-link 404**: `ingest_existing.py` stored `semester` as a bare number (`"5"`) but the filesystem uses `semestre_5`. `api_server.py` now converts it back before returning sources to the frontend (`semestre_{n}`).
- **Transcript deep-link filename mismatch**: `ingest_existing.py` stored `title` without the date prefix (e.g. `FACS-7990-...` instead of `18-03-2026 - FACS-7990-...`). `api_server.py` now reconstructs the full filename from `date` + `title` stored in metadata.
- **Chat history reset on view switch**: Messages state was local to `ChatView` and got destroyed when switching to Transcripciones. Lifted `messages` state to `Index.tsx` so it persists across view changes.

### Added
- **Copy button in transcript viewer**: Copy/Check button added to the file viewer header in `TranscriptsView.tsx`, mirroring the copy button available in the chat view.
- **Clickable source cards**: Each source citation card in the chat is now a clickable button. Clicking navigates to the Transcripciones view, auto-opens the referenced file, and scrolls to the cited excerpt with a subtle yellow highlight.
- **Transcript highlight on deep-link**: `TranscriptsView` accepts `initialOpen` prop with an optional `excerpt` field. The `HighlightedContent` component finds the excerpt in the full text and wraps it in a highlighted `<span>`, then scrolls it into view.
- **Semestre 5 shown first**: Transcript list now sorts semesters in reverse order so current subjects (semestre_5) appear at the top and Matemática Financiera (semestre_3) at the bottom.

### Changed
- **RAG context window**: Increased from 5 to 8 chunks passed to GPT-4o-mini for richer synthesis.
- **System prompt softened**: Replaced "Si la respuesta no está en los fragmentos, indicalo explícitamente" with "Si la información en los fragmentos es parcial, sintetizá lo que se pueda inferir y aclaralo" to avoid unnecessarily terse responses when partial information is available.
- **`ChatMessage` and `Source` interfaces exported** from `ChatView.tsx` so they can be reused by `Index.tsx` without duplication.

## [Unreleased] - 2026-03-24

### Added
- **Pinecone ingestion integrated into `vimeo_scraper.py`**: After saving each new transcript, the script now automatically chunks the text (~3000 chars with 300-char overlap), generates embeddings via OpenAI `text-embedding-3-small`, and upserts the vectors to the `ort-clases` Pinecone index. Uses the REST API directly with `requests` — no extra SDK dependencies.
- **`ingest_existing.py`**: One-shot utility script to bulk-ingest all previously downloaded transcripts (located in `transcripts/`) into Pinecone. Parses markdown headers to extract metadata (subject, semester, title, date) and stores the chunk text in vector metadata for retrieval.
- **macOS cron job**: Configured via `crontab` to run `vimeo_scraper.py` automatically Monday–Thursday at 20:00 local time (UYT). Logs output to `cron.log`.
- **Skip-existing logic**: `vimeo_scraper.py` now skips both file saving and Pinecone ingestion for transcripts that have already been processed.
- **Multi-subject loop**: `vimeo_scraper.py` now reads `config.json` and iterates over all 5 configured subjects instead of running a single hardcoded showcase.
- **API keys in `config.json`**: Added `pinecone_api_key`, `pinecone_host`, and `openai_api_key` fields.

## [Unreleased] - 2026-03-23

### Added
- **Phase 3 Pure RAG Retrieval (n8n)**: Designed and exported `ort-rag-workflow.json`, a highly optimized n8n workflow that operates entirely without a redundant LLM node. It functions as a pure semantic search API receiving a `query`, embedding it via OpenAI, scoring against Pinecone `ort-clases`, and outputting raw transcript chunks back to the calling LLM (Antigravity/Claude).
- **Phase 2 Vector Ingestion**: Engineered and successfully deployed `ingest.mjs`. This script iterates through `transcripts/`, parses markdown front-matter iteratively, chunks textual data via Langchain (`RecursiveCharacterTextSplitter`), and requests embeddings natively through OpenAI's `text-embedding-3-small`.
- **Pinecone RAG DB Mapping**: Integrated `@pinecone-database/pinecone` SDK (v3) within `ingest.mjs` to automatically stream, format, and batch-upsert over 50 embedded classes to the user's `ort-clases` serverless AWS index in real-time.
- **Semester Sorting Hierarchy**: Introduced a `semester` property to `config.json` and refactored `scraper.mjs` to dynamically organize VTT downloads into hierarchal nested folders (`transcripts/semestre_X/subject_name/`).
- **Targeted Extractions**: Programmed a CLI parser inside `scraper.mjs` (using `process.argv[2]`) to accept a single subject name. This allows scraping historic or one-off inactive classes (e.g. `matematica_financiera`) without spinning through the active `config.json` pipeline.
- **Multi-Subject Configuration**: `config.json` fully populated with 5 ORT subjects, showcase links, and passwords.
- **Dynamic File Naming**: `scraper.mjs` now extracts `document.title` and `h1` using Playwright, leveraging Regex to parse dates (e.g. `19-03-2026`) and saving the final Markdown transcripts as `DD-MM-YYYY - Title.md` instead of generic numeric IDs.
- **`test_scraper.mjs`**: Initial Playwright script to verify password bypass and VTT interception.
- **`config.json`**: Configuration file setup to manage subjects, showcase URLs, and passwords.
- **`scraper.js`**: Core loop script to process multiple showcases and extract subtitles using the `window._vimeoPlayerConfig` iframe injection technique.

### Changed
- **Architecture Shift**: Moved from programmatic `yt-dlp` / `requests` extraction to **Headless Playwright** extraction. This was necessary to bypass ORT's institutional Cloudflare and Next.js SSR session protections, which blocked pure HTTP requests from accessing Vimeo's video configurations.
- **RAG Architecture**: Decision made to build the RAG system using **n8n + MCP Server** and **Pinecone**, eliminating the need for Dockerized PostgreSQL or a custom Next.js chat frontend. This simplifies deployment and maximizes existing user capabilities.

### Fixed
- Fixed Vimeo iframe password bypass by capturing the Next.js rendered page, triggering a click on the video thumbnails, and intercepting the VTT URLs directly from the injected global JS state (`request.text_tracks`) instead of sniffing network packets, which were sometimes totally obfuscated.
