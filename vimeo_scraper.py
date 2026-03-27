import requests
import re
import json
import os
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Loaded from config.json or environment variables at startup
PINECONE_CFG = {}

SUBJECT_LABELS = {
    'economia_y_gestion':    'Economía y Gestión',
    'business_intelligence': 'Business Intelligence',
    'contabilidad_y_costos': 'Contabilidad y Costos',
    'project_management':    'Project Management',
    'ecommerce_y_servicios': 'E-commerce y Servicios',
    'matematica_financiera':  'Matemática Financiera',
}

# Chunk size for Pinecone ingestion (chars). text-embedding-3-small allows ~32K tokens,
# but storing ~3000 chars per chunk keeps metadata lean and retrieval precise.
CHUNK_SIZE = 3000
CHUNK_OVERLAP = 300


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def vtt_to_text(vtt_content):
    """Convert VTT subtitle content to plain text."""
    lines = vtt_content.splitlines()
    text_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('WEBVTT') or line.startswith('NOTE') or '-->' in line:
            continue
        if re.match(r'^\d+$', line):
            continue
        text_lines.append(line)
    return ' '.join(text_lines)


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return chunks


# ---------------------------------------------------------------------------
# Pinecone ingestion
# ---------------------------------------------------------------------------

def get_embedding(text, api_key):
    resp = requests.post(
        'https://api.openai.com/v1/embeddings',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={'input': text, 'model': 'text-embedding-3-small'},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()['data'][0]['embedding']


def ingest_to_pinecone(text, video_id, metadata):
    """Chunk text, embed with OpenAI, and upsert to Pinecone."""
    if not PINECONE_CFG.get('pinecone_api_key'):
        return

    openai_key = PINECONE_CFG['openai_api_key']
    pinecone_key = PINECONE_CFG['pinecone_api_key']
    host = PINECONE_CFG['pinecone_host'].rstrip('/')

    chunks = chunk_text(text)
    print(f"    Ingesting {len(chunks)} chunk(s) into Pinecone...")

    vectors = []
    for i, chunk in enumerate(chunks):
        try:
            embedding = get_embedding(chunk, openai_key)
            vectors.append({
                'id': f"{video_id}_{i}",
                'values': embedding,
                'metadata': {**metadata, 'text': chunk, 'chunk_index': i},
            })
        except Exception as e:
            print(f"    [!] Embedding chunk {i} failed: {e}")

    if not vectors:
        print("    [!] No vectors to upsert.")
        return

    try:
        resp = requests.post(
            f"{host}/vectors/upsert",
            headers={'Api-Key': pinecone_key, 'Content-Type': 'application/json'},
            json={'vectors': vectors},
            timeout=60,
        )
        resp.raise_for_status()
        upserted = resp.json().get('upsertedCount', len(vectors))
        print(f"    [+] Pinecone: {upserted} vector(s) upserted")
    except Exception as e:
        print(f"    [!] Pinecone upsert failed: {e}")


# ---------------------------------------------------------------------------
# File saving
# ---------------------------------------------------------------------------

def save_transcript(subject_name, semester, video_id, video_title, upload_date, text):
    """Save plain text as a Markdown transcript.
    Returns (saved: bool, date_str: str).
    """
    date_str = None
    if upload_date:
        try:
            ts = float(upload_date)
            date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%d-%m-%Y')
        except (TypeError, ValueError, OSError):
            pass
    if not date_str and upload_date:
        try:
            dt = datetime.strptime(str(upload_date)[:10], '%Y-%m-%d')
            date_str = dt.strftime('%d-%m-%Y')
        except ValueError:
            pass
    if not date_str:
        date_str = datetime.now().strftime('%d-%m-%Y')

    safe_title = re.sub(r'[<>:"/\\|?*]', '', str(video_title))
    filename = f"{date_str} - {safe_title}.md"

    output_dir = os.path.join(BASE_DIR, 'transcripts', f'semestre_{semester}', subject_name)
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    existing = [f for f in os.listdir(output_dir) if f.startswith(f"{date_str} - ")]
    if existing:
        print(f"    [~] Skipping (already exists): {existing[0]}")
        return False, date_str

    header = (
        f"# {date_str} - {safe_title}\n\n"
        f"**Subject:** {subject_name}\n"
        f"**Video ID:** {video_id}\n\n"
        f"---\n\n"
    )
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(header + text)

    print(f"    [+] Saved: {filename}")
    return True, date_str


# ---------------------------------------------------------------------------
# VTT extraction
# ---------------------------------------------------------------------------

def extract_text_tracks(player_config, subject_name, semester):
    try:
        text_tracks = player_config['request']['text_tracks']
        if not text_tracks:
            print("[-] No text tracks (captions/subtitles) found for this video.")
            return

        video = player_config.get('video', {})
        video_id = video.get('id', 'unknown')
        video_title = video.get('title', f'video_{video_id}')
        upload_date = video.get('upload_date')

        print(f"    Video: {video_title} (ID: {video_id})")
        print(f"    Found {len(text_tracks)} text track(s)")

        track = next((t for t in text_tracks if t.get('kind') == 'captions'), text_tracks[0])
        lang = track.get('language', 'unknown')
        url = track.get('url', '')
        if url.startswith('/'):
            url = f"https://player.vimeo.com{url}"

        print(f"    Downloading VTT [{lang}]...")
        resp = requests.get(url)
        if resp.status_code != 200:
            print(f"    [!] Failed to download VTT. Status: {resp.status_code}")
            return

        text = vtt_to_text(resp.text)
        saved, date_str = save_transcript(subject_name, semester, video_id, video_title, upload_date, text)

        if saved:
            ingest_to_pinecone(text, str(video_id), {
                'subject': subject_name,
                'semester': str(semester),
                'title': str(video_title),
                'date': date_str,
            })

    except KeyError:
        print("[-] 'text_tracks' not found in player config structure.")


# ---------------------------------------------------------------------------
# Showcase scraping — Playwright (primary)
# ---------------------------------------------------------------------------

def _extract_vtt_playwright(showcase_url, password, subject_name, semester):
    """Use Playwright to authenticate, intercept video list + player configs, download VTTs."""
    from playwright.sync_api import sync_playwright

    showcase_id = showcase_url.rstrip('/').split('/')[-1]
    seen_ids = set()
    videos = []          # [{uri, name, release_time, ...}], deduplicated
    player_configs = {}  # vid_id -> player config JSON (captured via response listener)

    def on_response(response):
        url = response.url
        try:
            if ('api.vimeo.com/albums' in url and 'videos' in url
                    and response.status == 200):
                data = response.json()
                for item in data.get('data', []):
                    uri = item.get('uri', '')
                    v = uri.split('/')[-1] if uri else str(item.get('id', ''))
                    if v and v.isdigit() and v not in seen_ids:
                        seen_ids.add(v)
                        videos.append(item)
            elif ('player.vimeo.com/video/' in url and '/config' in url
                  and response.status == 200):
                v = url.split('/video/')[1].split('/')[0]
                player_configs[v] = response.json()
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/122.0.0.0 Safari/537.36'
            )
        )
        page = context.new_page()
        page.on('response', on_response)

        print(f"[PW] Loading showcase: {showcase_url}")
        try:
            page.goto(showcase_url, wait_until='domcontentloaded', timeout=60000)
        except Exception as e:
            print(f"[PW] Navigation warning: {e}")
        page.wait_for_timeout(3000)

        # Authenticate with password
        password_input = page.query_selector('input[type="password"]')
        if password_input:
            print("[PW] Entering password...")
            password_input.fill(password)
            page.keyboard.press('Enter')
            page.wait_for_timeout(6000)
        else:
            print("[PW] No password prompt — may already be authenticated")

        # Extra wait for the authenticated video list API call to complete
        page.wait_for_timeout(3000)
        print(f"[PW] Found {len(videos)} unique video(s) from API interception", flush=True)

        # Capture session cookies for direct API calls (bypass browser for config fetching)
        vimeo_cookies = {
            c['name']: c['value']
            for c in context.cookies()
            if 'vimeo' in c.get('domain', '')
        }
        print(f"[PW] Session cookies: {list(vimeo_cookies.keys())}", flush=True)

        # "Warm up" by clicking the last video in the list before the main loop.
        # The showcase auto-selects the first video on page load; clicking it again
        # does nothing (already active). By activating the last video first, every
        # subsequent click in the loop triggers a real player state change.
        if len(videos) > 1:
            last_uri = videos[-1].get('uri', '')
            last_id = last_uri.split('/')[-1] if last_uri else str(videos[-1].get('id', ''))
            if last_id.isdigit():
                try:
                    page.evaluate(f"""() => {{
                        const el = document.querySelector('[href*="?video={last_id}"]');
                        if (el) el.click();
                    }}""")
                    page.wait_for_timeout(3000)
                    print(f"[PW] Warm-up click on last video ({last_id})", flush=True)
                except Exception:
                    pass

        if not videos:
            print("[-] No videos found via Playwright — check password or showcase URL")
            browser.close()
            return

        for video_data in videos:
            uri = video_data.get('uri', '')
            vid_id = uri.split('/')[-1] if uri else str(video_data.get('id', ''))
            if not vid_id or not vid_id.isdigit():
                continue

            vid_title = video_data.get('name', f'video_{vid_id}')
            upload_date = (
                video_data.get('release_time')
                or video_data.get('created_time', '')
            )

            # Vimeo ORT titles embed the lecture date: "FACS-... | DD-MM-YYYY"
            # Extract the date, convert to YYYY-MM-DD (for save_transcript parser),
            # and strip the " | DD-MM-YYYY" suffix from the title.
            date_in_title = re.search(r'\s*\|\s*(\d{2}-\d{2}-\d{4})\s*$', vid_title)
            if date_in_title:
                day, month, year = date_in_title.group(1).split('-')
                if not upload_date:
                    upload_date = f"{year}-{month}-{day}"
                vid_title = vid_title[:date_in_title.start()].strip()

            print(f"\n[PW] Processing: {vid_title} (ID: {vid_id})", flush=True)

            # Quick skip-check before navigating
            date_str_check = datetime.now().strftime('%d-%m-%Y')
            if upload_date:
                try:
                    dt = datetime.strptime(upload_date[:10], '%Y-%m-%d')
                    date_str_check = dt.strftime('%d-%m-%Y')
                except ValueError:
                    pass

            safe_title = re.sub(r'[<>:"/\\|?*]', '', str(vid_title))
            filepath = os.path.join(
                BASE_DIR, 'transcripts', f'semestre_{semester}',
                subject_name, f"{date_str_check} - {safe_title}.md"
            )
            if os.path.exists(filepath):
                print(f"    [~] Skipping (already exists)")
                continue

            # --- Config extraction ---
            # Layer 1: already captured by response listener during showcase load
            config = player_configs.get(vid_id)

            if not config:
                # Layer 2: direct HTTP fetch using Playwright session cookies.
                # After showcase auth, Vimeo sets cookies that authorize the player
                # config endpoint. We bypass the browser for this step (much faster).
                try:
                    config_url = f"https://player.vimeo.com/video/{vid_id}/config"
                    r = requests.get(
                        config_url,
                        cookies=vimeo_cookies,
                        headers={
                            'Referer': showcase_url,
                            'Origin': 'https://vimeo.com',
                            'User-Agent': (
                                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                                'AppleWebKit/537.36 (KHTML, like Gecko) '
                                'Chrome/122.0.0.0 Safari/537.36'
                            ),
                        },
                        timeout=20,
                    )
                    if r.status_code == 200:
                        candidate = r.json()
                        # Reject if text_tracks is empty (unauthenticated response)
                        if candidate.get('request', {}).get('text_tracks'):
                            config = candidate
                            print(f"    [PW] Config via cookie fetch (Layer 2)")
                        else:
                            print(f"    [!] Cookie fetch returned empty text_tracks")
                    else:
                        print(f"    [!] Cookie fetch status: {r.status_code}")
                except Exception as e:
                    print(f"    [!] Cookie fetch failed: {e}")

            if not config:
                # Layer 3: click the video thumbnail within the showcase page to trigger
                # client-side player loading with proper in-memory auth context.
                try:
                    if showcase_id not in page.url:
                        page.goto(showcase_url, wait_until='domcontentloaded', timeout=30000)
                        page.wait_for_timeout(4000)

                    # Showcase hrefs use ?video=ID format (not /video/ID)
                    clicked = page.evaluate(f"""() => {{
                        const el = document.querySelector('[href*="?video={vid_id}"]') ||
                                   document.querySelector('[href*="{vid_id}"]') ||
                                   document.querySelector('[data-id="{vid_id}"]') ||
                                   document.querySelector('[data-clip-id="{vid_id}"]');
                        if (el) {{ el.click(); return true; }}
                        return false;
                    }}""")
                    if clicked:
                        print(f"    [PW] Clicked thumbnail — waiting for player...", flush=True)
                        page.wait_for_timeout(6000)
                        config = player_configs.get(vid_id)
                        if not config:
                            # Also try JS global after click
                            raw = page.evaluate("""() => {
                                const cc = window.vimeo && window.vimeo.clip_page_config;
                                if (cc) return cc;
                                return null;
                            }""")
                            if raw:
                                config_url2 = (raw.get('player') or {}).get('config_url')
                                if config_url2:
                                    rr = requests.get(config_url2, timeout=20)
                                    if rr.status_code == 200:
                                        config = rr.json()
                    else:
                        print(f"    [!] No thumbnail found for {vid_id} — DOM hrefs may use different format")
                except Exception as e:
                    print(f"    [!] Click/eval failed: {e}")

            if not config:
                print(f"    [!] No player config captured — skipping")
                continue

            text_tracks = config.get('request', {}).get('text_tracks', [])
            if not text_tracks:
                print(f"    [-] No text tracks for this video")
                continue

            track = next(
                (t for t in text_tracks if t.get('kind') == 'captions'),
                text_tracks[0]
            )
            lang = track.get('language', 'unknown')
            vtt_url = track.get('url', '')
            if vtt_url.startswith('/'):
                vtt_url = f"https://player.vimeo.com{vtt_url}"

            print(f"    Downloading VTT [{lang}]...")
            resp = requests.get(vtt_url, timeout=30)
            if resp.status_code != 200:
                print(f"    [!] VTT download failed: {resp.status_code}")
                continue

            text = vtt_to_text(resp.text)
            saved, date_str_final = save_transcript(
                subject_name, semester, vid_id, vid_title, upload_date, text
            )
            if saved:
                ingest_to_pinecone(text, str(vid_id), {
                    'subject': subject_name,
                    'semester': str(semester),
                    'title': str(vid_title),
                    'date': date_str_final,
                })

        browser.close()


# ---------------------------------------------------------------------------
# Showcase scraping — HTTP fallback
# ---------------------------------------------------------------------------

def extract_vtt_from_showcase(showcase_url, password, subject_name, semester):
    """Try Playwright first (handles Cloudflare/CSR); fall back to HTTP."""
    try:
        import playwright  # noqa: F401
        _extract_vtt_playwright(showcase_url, password, subject_name, semester)
        return
    except ImportError:
        print("[!] Playwright not installed — using HTTP fallback")

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9,es;q=0.8',
    })

    print(f"[*] Accessing showcase: {showcase_url}")

    response = session.get(showcase_url)
    if response.status_code != 200:
        print(f"[-] Failed to access showcase. Status: {response.status_code}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')

    # Vimeo renders password forms client-side (JS), so we can't rely on HTML detection.
    # Always attempt auth via the known Vimeo showcase password endpoint.
    print("[*] Attempting password authentication...")
    showcase_id = showcase_url.rstrip('/').split('/')[-1]
    auth_url = f"https://vimeo.com/showcase/{showcase_id}/auth"

    # Also collect any hidden fields from the form if present (fallback)
    form = soup.find('form')
    data = {'password': password, 'token': ''}
    if form:
        for input_tag in form.find_all('input', type='hidden'):
            name = input_tag.get('name')
            if name:
                data[name] = input_tag.get('value', '')
        if form.get('action'):
            auth_url = urljoin(showcase_url, form.get('action'))

    auth_resp = session.post(
        auth_url,
        data=data,
        headers={
            'Referer': showcase_url,
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
        },
    )
    print(f"[*] Auth response status: {auth_resp.status_code}")

    # After auth, re-fetch the showcase page with the session cookies
    page_resp = session.get(showcase_url)
    if page_resp.status_code != 200:
        print(f"[-] Failed to load showcase after auth. Status: {page_resp.status_code}")
        return

    html_content = page_resp.text

    if "This showcase is private" in html_content or "incorrect password" in html_content.lower():
        print("[-] Authentication failed — incorrect password or Vimeo structure changed.")
        return

    print("[+] Showcase loaded after auth attempt.")

    soup = BeautifulSoup(html_content, 'html.parser')

    video_links = set()

    # Strategy A: Parse <a href> links (works if Vimeo renders server-side)
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/video/' in href and showcase_id in href:
            full_url = urljoin(showcase_url, href)
            video_links.add(full_url)

    # Strategy B: Extract video IDs from __NEXT_DATA__ JSON (Next.js client-side render)
    if not video_links:
        next_data_tag = soup.find('script', {'id': '__NEXT_DATA__'})
        if next_data_tag:
            try:
                next_data = json.loads(next_data_tag.string)
                # Navigate common Next.js props structures to find clip/video IDs
                clips = (
                    next_data.get('props', {})
                    .get('pageProps', {})
                    .get('clips', [])
                ) or (
                    next_data.get('props', {})
                    .get('pageProps', {})
                    .get('album', {})
                    .get('clips', [])
                )
                for clip in clips:
                    vid_id = clip.get('id') or clip.get('clip_id')
                    if vid_id:
                        video_links.add(f"https://vimeo.com/showcase/{showcase_id}/video/{vid_id}")
                if clips:
                    print(f"[*] Found {len(clips)} clip(s) via __NEXT_DATA__")
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                print(f"[!] __NEXT_DATA__ parse failed: {e}")

    # Strategy C: Find video IDs in inline JSON blobs (fallback regex)
    if not video_links:
        video_id_matches = re.findall(r'"clip_id"\s*:\s*(\d+)', html_content)
        if not video_id_matches:
            video_id_matches = re.findall(
                rf'/showcase/{re.escape(showcase_id)}/video/(\d+)', html_content
            )
        for vid_id in set(video_id_matches):
            video_links.add(f"https://vimeo.com/showcase/{showcase_id}/video/{vid_id}")
        if video_id_matches:
            print(f"[*] Found {len(video_id_matches)} video ID(s) via regex fallback")

    print(f"[*] Found {len(video_links)} videos in the showcase.")

    if not video_links:
        print("[-] Could not find any video links.")
        return

    for video_url in video_links:
        print(f"\n[*] Processing video: {video_url}")
        vid_resp = session.get(video_url)

        config_match = re.search(r'window\.vimeo\.clip_page_config\s*=\s*({.+?});', vid_resp.text)
        if config_match:
            try:
                config = json.loads(config_match.group(1))
                player_url = config.get('player', {}).get('config_url')
                if player_url:
                    print(f"[*] Found player config URL: {player_url}")
                    player_resp = session.get(player_url)
                    player_config = player_resp.json()
                    extract_text_tracks(player_config, subject_name, semester)
                    continue
            except json.JSONDecodeError:
                pass

        config_match2 = re.search(r'var config = ({.+?});', vid_resp.text)
        if config_match2:
            try:
                player_config = json.loads(config_match2.group(1))
                extract_text_tracks(player_config, subject_name, semester)
                continue
            except json.JSONDecodeError:
                pass

        soup_vid = BeautifulSoup(vid_resp.text, 'html.parser')
        iframe = soup_vid.find('iframe')
        if iframe and 'player.vimeo.com' in iframe.get('src', ''):
            iframe_src = iframe['src']
            print(f"[*] Found player iframe: {iframe_src}")
            iframe_resp = session.get(urljoin(video_url, iframe_src))

            config_match3 = re.search(r'window\.playerConfig\s*=\s*({.+?});', iframe_resp.text)
            if config_match3:
                try:
                    player_config = json.loads(config_match3.group(1))
                    extract_text_tracks(player_config, subject_name, semester)
                    continue
                except json.JSONDecodeError:
                    pass

        print("[-] Could not locate player config for this video.")


# ---------------------------------------------------------------------------
# Transcript index generation (for static frontend)
# ---------------------------------------------------------------------------

def generate_transcript_index():
    """Build transcripts_index.json mirroring the GET /api/transcripts response.

    The static React frontend reads this file instead of calling Flask.
    """
    transcripts_path = os.path.join(BASE_DIR, 'transcripts')
    result = {}

    if os.path.isdir(transcripts_path):
        for semester_dir in sorted(os.listdir(transcripts_path)):
            s_path = os.path.join(transcripts_path, semester_dir)
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
                label = SUBJECT_LABELS.get(
                    subject_dir,
                    subject_dir.replace('_', ' ').title(),
                )
                result[semester_dir][subject_dir] = {
                    'label': label,
                    'files': files,
                }

    index_path = os.path.join(BASE_DIR, 'transcripts_index.json')
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total = sum(
        len(v['files'])
        for sem in result.values()
        for v in sem.values()
    )
    print(f"[+] transcripts_index.json updated ({total} file(s) across {len(result)} semester(s))")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # GitHub Actions provides secrets via environment variables.
    # Fall back to config.json for local development.
    pinecone_key = os.environ.get('PINECONE_API_KEY')
    pinecone_host = os.environ.get('PINECONE_HOST')
    openai_key = os.environ.get('OPENAI_API_KEY')
    subjects_env = os.environ.get('SUBJECTS_JSON')

    if pinecone_key:
        # Running in GitHub Actions
        PINECONE_CFG.update({
            'pinecone_api_key': pinecone_key,
            'pinecone_host': pinecone_host or '',
            'openai_api_key': openai_key or '',
        })
        subjects = json.loads(subjects_env) if subjects_env else []
        print(f"[CI] Loaded {len(subjects)} subject(s) from environment variables")
    else:
        # Running locally
        config_path = os.path.join(BASE_DIR, 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        PINECONE_CFG.update({
            'pinecone_api_key': config.get('pinecone_api_key', ''),
            'pinecone_host': config.get('pinecone_host', ''),
            'openai_api_key': config.get('openai_api_key', ''),
        })
        subjects = config.get('subjects', [])
        print(f"[Local] Loaded {len(subjects)} subject(s) from config.json")

    if not PINECONE_CFG['pinecone_api_key']:
        print("[!] Warning: No Pinecone API key found — transcripts will be saved locally only.")

    for subject in subjects:
        print(f"\n{'='*60}")
        print(f"Subject: {subject['name']} (semestre {subject['semester']})")
        extract_vtt_from_showcase(
            subject['showcase_url'],
            subject['password'],
            subject['name'],
            subject['semester'],
        )

    print(f"\n{'='*60}")
    generate_transcript_index()
    print("Done.")
