import os, sys, json, re, time, shutil, threading, uuid
from urllib.parse import quote
from flask import Flask, jsonify, request, Response, send_from_directory, render_template
import requests

app = Flask(__name__, template_folder='templates')

# ============================================
# CONFIGURAR DENO PARA YT-DLP
# ============================================
def find_deno():
    """Procura deno em todos os locais possíveis"""
    deno_name = 'deno.exe' if os.name == 'nt' else 'deno'
    deno_path = shutil.which(deno_name)
    if deno_path:
        return os.path.dirname(deno_path)

    possible_paths = [
        os.path.expanduser('~/.deno/bin'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'deno'),
    ]

    if os.name == 'nt':
        possible_paths.extend([
            os.path.expandvars(r'%USERPROFILE%\.deno\bin'),
            os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\WinGet\Packages\DenoLand.Deno_Microsoft.Winget.Source_8wekyb3d8bbwe'),
            os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\WinGet\Links'),
            os.path.expandvars(r'%PROGRAMFILES%\Deno'),
            os.path.expandvars(r'%PROGRAMFILES(x86)%\Deno'),
        ])

    for path in possible_paths:
        exe = os.path.join(path, deno_name)
        if os.path.exists(exe):
            return path

    return None

# Adicionar Deno ao PATH do processo Python
deno_dir = find_deno()
if deno_dir:
    os.environ['PATH'] = deno_dir + os.pathsep + os.environ.get('PATH', '')
    print(f"[OK] Deno encontrado em: {deno_dir}")
else:
    print("[AVISO] Deno não encontrado. Usando formatos fallback sem assinatura.")

# ============================================
# IMPORTAR YT-DLP DEPOIS DE CONFIGURAR PATH
# ============================================
from yt_dlp import YoutubeDL

# ============================================
# CONFIGS
# ============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.environ.get('TOCA_DOWNLOAD_DIR') or os.path.join(BASE_DIR, 'Toca_Downloads')
LIBRARY_PATH = os.environ.get('TOCA_LIBRARY_PATH') or os.path.join(BASE_DIR, 'toca_library.json')
DEBUG = os.environ.get('TOCA_DEBUG', '').lower() in ('1', 'true', 'yes')
HOST = os.environ.get('TOCA_HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT') or os.environ.get('TOCA_PORT') or 5000)

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ============================================
# LIBRARY HELPERS
# ============================================
def load_library():
    if not os.path.exists(LIBRARY_PATH):
        return {'library': [], 'playlists': {'Favoritos': []}, 'favorites': []}
    try:
        with open(LIBRARY_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {'library': [], 'playlists': {'Favoritos': []}, 'favorites': []}

def save_library(data):
    with open(LIBRARY_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

# ============================================
# YT-DLP HELPERS
# ============================================
def get_yt_opts(base_opts):
    """Adiciona cookies.txt se disponível às opções do yt-dlp."""
    opts = base_opts.copy()
    cookie_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
    if os.path.exists(cookie_path):
        opts['cookiefile'] = cookie_path
        print(f"[OK] Cookies carregados de: {cookie_path}")
    else:
        print(f"[AVISO] Cookies não encontrados em: {cookie_path}")
    return opts

def safe_filename(title):
    return re.sub(r'[\\/*?:"<>|]', '_', title)[:120]

def get_stream_url(youtube_url):
    """Extrai URL de stream direto do YouTube."""
    configs = [
        {
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio[ext=webm]/bestaudio/best',
            'quiet': True, 'no_warnings': True, 'skip_download': True,
            'extract_flat': False,
            'socket_timeout': 30,
        },
        {
            'format': 'worstaudio/worst',
            'quiet': True, 'no_warnings': True, 'skip_download': True,
            'extract_flat': False,
            'socket_timeout': 30,
        },
        {
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio[ext=webm]/bestaudio/best',
            'quiet': True, 'no_warnings': True, 'skip_download': True,
            'extract_flat': False,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'socket_timeout': 30,
        },
    ]
    
    for opts in configs:
        try:
            with YoutubeDL(get_yt_opts(opts)) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                if not info:
                    continue
                
                url = info.get('url')
                if url:
                    return url, info
                
                formats = info.get('formats') or []
                audio = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none' and f.get('url')]
                if audio:
                    audio.sort(key=lambda f: f.get('abr', 0) or 0, reverse=True)
                    return audio[0]['url'], info
                
                for f in formats:
                    if f.get('url'):
                        return f['url'], info
        except Exception as e:
            print(f"[FALHA stream] config: {e}")
            continue
    
    return None, None

def search_youtube(query, max_results=10):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': True,
        'default_search': 'ytsearch',
    }
    try:
        with YoutubeDL(opts) as ydl:
            search_query = f"ytsearch{max_results}:{query}"
            result = ydl.extract_info(search_query, download=False)
            if result and 'entries' in result:
                entries = []
                for e in result['entries']:
                    entries.append({
                        'id': e.get('id'),
                        'title': e.get('title'),
                        'uploader': e.get('uploader', e.get('channel', 'Desconhecido')),
                        'duration': e.get('duration') or 0,
                        'thumbnail': f"https://i.ytimg.com/vi/{e.get('id')}/mqdefault.jpg",
                        'url': f"https://www.youtube.com/watch?v={e.get('id')}"
                    })
                return entries
    except Exception as e:
        print(f"[ERRO search] {e}")
    return []

# ============================================
# ROTAS
# ============================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search')
def api_search():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'Query vazia'}), 400
    results = search_youtube(q)
    return jsonify({'results': results})

@app.route('/api/stream')
def api_stream():
    youtube_url = request.args.get('url', '')
    if not youtube_url:
        return jsonify({'error': 'URL vazio'}), 400
    
    stream_url, info = get_stream_url(youtube_url)
    if not stream_url:
        return jsonify({'error': 'Não foi possível extrair stream'}), 404
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': '*/*',
        'Referer': 'https://www.youtube.com/',
        'Origin': 'https://www.youtube.com',
    }
    range_h = request.headers.get('Range', '')
    if range_h:
        headers['Range'] = range_h
    
    for attempt in range(2):
        try:
            resp = requests.get(stream_url, headers=headers, stream=True, timeout=30, verify=False)
            if resp.status_code >= 400:
                print(f"[ERRO proxy] status {resp.status_code}, tentativa {attempt+1}")
                if attempt == 0:
                    stream_url, info = get_stream_url(youtube_url)
                    if not stream_url:
                        return jsonify({'error': 'Stream não disponível'}), 404
                    headers.pop('Range', None)
                    continue
                return jsonify({'error': f'Stream retornou {resp.status_code}'}), resp.status_code
            
            rh = {}
            for k in ['Content-Type', 'Content-Length', 'Accept-Ranges', 'Content-Range']:
                if k in resp.headers:
                    rh[k] = resp.headers[k]
            ct = rh.get('Content-Type', '')
            if not ct or 'audio' not in ct:
                rh['Content-Type'] = 'audio/mpeg'
            sc = resp.status_code if resp.status_code in [200, 206] else 200
            
            def gen():
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk: yield chunk
            
            return Response(gen(), status=sc, headers=rh)
        except Exception as e:
            print(f"[ERRO proxy] tentativa {attempt+1}: {e}")
            if attempt == 0:
                stream_url, info = get_stream_url(youtube_url)
                if not stream_url:
                    return jsonify({'error': 'Stream não disponível'}), 404
                headers.pop('Range', None)
                continue
            return jsonify({'error': str(e)}), 500

@app.route('/api/stream-url')
def api_stream_url():
    youtube_url = request.args.get('url', '')
    if not youtube_url:
        return jsonify({'error': 'URL vazio'}), 400
    stream_url, _ = get_stream_url(youtube_url)
    if not stream_url:
        return jsonify({'error': 'Não foi possível extrair stream'}), 404
    return jsonify({'url': stream_url})

@app.route('/api/stream-mp3')
def api_stream_mp3():
    youtube_url = request.args.get('url', '')
    if not youtube_url:
        return jsonify({'error': 'URL vazio'}), 400

    opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': False,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'skip': ['webpage', 'hls'],
            }
        },
        'socket_timeout': 30,
    }

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            if not info:
                return jsonify({'error': 'Não foi possível extrair stream'}), 404
            stream_url = info.get('url')
            if not stream_url:
                formats = info.get('formats') or []
                for f in formats:
                    if f.get('url'):
                        stream_url = f['url']
                        break
            if not stream_url:
                return jsonify({'error': 'Sem URL de áudio'}), 404
    except Exception as e:
        print(f"[FALHA stream-mp3] {e}")
        return jsonify({'error': str(e)}), 500

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': '*/*',
        'Referer': 'https://www.youtube.com/',
        'Origin': 'https://www.youtube.com',
    }
    range_h = request.headers.get('Range', '')
    if range_h:
        headers['Range'] = range_h

    try:
        resp = requests.get(stream_url, headers=headers, stream=True, timeout=30)
        rh = {'Content-Type': 'audio/mpeg'}
        for k in ['Content-Length', 'Accept-Ranges', 'Content-Range']:
            if k in resp.headers:
                rh[k] = resp.headers[k]
        sc = resp.status_code if resp.status_code in [200, 206] else 200

        def gen():
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk: yield chunk

        return Response(gen(), status=sc, headers=rh)
    except Exception as e:
        print(f"[ERRO proxy mp3] {e}")
        return jsonify({'error': str(e)}), 500

# ============================================
# LIBRARY & PLAYLISTS
# ============================================
@app.route('/api/library', methods=['GET', 'POST'])
def api_library():
    if request.method == 'POST':
        data = request.get_json()
        if data:
            save_library(data)
            return jsonify({'status': 'ok'})
        return jsonify({'error': 'Dados inválidos'}), 400
    return jsonify(load_library())

@app.route('/api/library/track', methods=['POST'])
def api_add_track():
    lib = load_library()
    track = request.get_json()
    if not track:
        return jsonify({'error': 'Track inválida'}), 400
    track['id'] = track.get('id', str(uuid.uuid4()))
    track['added_at'] = time.time()
    lib['library'].append(track)
    save_library(lib)
    return jsonify({'status': 'ok', 'track': track})

@app.route('/api/library/track/<track_id>', methods=['DELETE'])
def api_remove_track(track_id):
    lib = load_library()
    lib['library'] = [t for t in lib['library'] if t.get('id') != track_id]
    for pl_name in lib['playlists']:
        lib['playlists'][pl_name] = [t for t in lib['playlists'][pl_name] if t.get('id') != track_id]
    lib['favorites'] = [t for t in lib['favorites'] if t.get('id') != track_id]
    save_library(lib)
    return jsonify({'status': 'ok'})

@app.route('/api/playlists', methods=['GET'])
def api_get_playlists():
    lib = load_library()
    return jsonify(lib.get('playlists', {}))

@app.route('/api/playlists/<name>', methods=['PUT', 'DELETE'])
def api_manage_playlist(name):
    lib = load_library()
    if request.method == 'DELETE':
        if name in lib['playlists']:
            del lib['playlists'][name]
        save_library(lib)
        return jsonify({'status': 'ok'})
    data = request.get_json() or {}
    new_name = data.get('name', name)
    if new_name != name and name in lib['playlists']:
        lib['playlists'][new_name] = lib['playlists'].pop(name)
    elif new_name not in lib['playlists']:
        lib['playlists'][new_name] = data.get('tracks', [])
    save_library(lib)
    return jsonify({'status': 'ok', 'playlists': lib['playlists']})

@app.route('/api/playlists/<name>/tracks', methods=['POST', 'DELETE'])
def api_manage_playlist_tracks(name):
    lib = load_library()
    data = request.get_json() or {}
    if name not in lib['playlists']:
        lib['playlists'][name] = []
    if request.method == 'DELETE':
        track_id = data.get('track_id')
        if track_id:
            lib['playlists'][name] = [t for t in lib['playlists'][name] if t.get('id') != track_id]
    else:
        track = data.get('track')
        if track:
            track['id'] = track.get('id', str(uuid.uuid4()))
            lib['playlists'][name].append(track)
    save_library(lib)
    return jsonify({'status': 'ok', 'tracks': lib['playlists'][name]})

# ============================================
# LYRICS
# ============================================
@app.route('/api/lyrics')
def api_lyrics():
    title = request.args.get('title', '')
    artist = request.args.get('artist', '')
    if not title:
        return jsonify({'lyrics': None})
    lyrics = None
    try:
        resp = requests.get(f"https://api.lyrics.ovh/v1/{quote(artist)}/{quote(title)}", timeout=10)
        if resp.status_code == 200:
            lyrics = resp.json().get('lyrics')
    except: pass
    if lyrics and len(lyrics) > 20:
        return jsonify({'lyrics': lyrics})
    search_query = f"{artist} {title} lyrics".strip()
    try:
        with YoutubeDL({'quiet': True, 'no_warnings': True, 'extract_flat': False, 'skip_download': True}) as ydl:
            info = ydl.extract_info(f"ytsearch:{search_query}", download=False)
            entries = list(info.get('entries') or [])
            if entries:
                desc = (entries[0] or {}).get('description', '')
                if desc:
                    lines = [l.strip() for l in desc.split('\n') if l.strip() and not l.startswith('http') and '▶' not in l and 'Subscribe' not in l]
                    if len(lines) > 4:
                        lyrics = '\n'.join(lines[:60])
    except: pass
    return jsonify({'lyrics': lyrics})

@app.route('/api/artist-bio')
def api_artist_bio():
    artist = request.args.get('artist', '')
    if not artist:
        return jsonify({'bio': None})
    try:
        with YoutubeDL({'quiet': True, 'no_warnings': True, 'extract_flat': False, 'skip_download': True}) as ydl:
            info = ydl.extract_info(f"ytsearch:{artist} topic", download=False)
            entries = list(info.get('entries') or [])
            if entries:
                desc = (entries[0] or {}).get('description', '')
                if desc:
                    lines = [l.strip() for l in desc.split('\n') if l.strip() and not l.startswith('http') and '▶' not in l and 'Subscribe' not in l]
                    bio = '\n'.join(lines[:30]) if lines else None
                    if bio:
                        return jsonify({'bio': bio})
    except: pass
    return jsonify({'bio': None})

@app.route('/api/favorites', methods=['GET', 'POST'])
def api_favorites():
    lib = load_library()
    if request.method == 'POST':
        data = request.get_json() or {}
        track = data.get('track')
        if track:
            existing = any(t.get('id') == track.get('id') for t in lib['favorites'])
            if data.get('remove') or existing:
                lib['favorites'] = [t for t in lib['favorites'] if t.get('id') != track.get('id')]
            else:
                track['id'] = track.get('id', str(uuid.uuid4()))
                track['added_at'] = time.time()
                lib['favorites'].append(track)
        save_library(lib)
        return jsonify({'status': 'ok', 'favorites': lib['favorites']})
    return jsonify(lib.get('favorites', []))

@app.route('/api/related')
def api_related():
    video_id = request.args.get('video_id', '')
    title = request.args.get('title', '')
    artist = request.args.get('artist', '')
    query = artist or title
    if not query:
        return jsonify({'results': []})
    results = search_youtube(f"{query} música", 8)
    return jsonify({'results': results})

# ============================================
# DOWNLOAD
# ============================================
download_progress = {}

@app.route('/api/download')
def api_download():
    youtube_url = request.args.get('url', '')
    if not youtube_url:
        return jsonify({'error': 'URL vazio'}), 400
    
    dl_id = str(uuid.uuid4())
    download_progress[dl_id] = {'progress': 0, 'status': 'starting', 'filename': None}
    
    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            if total > 0:
                pct = int(d.get('downloaded_bytes', 0) / total * 100)
            else:
                pct = d.get('_percent_str', '0%').replace('%', '').strip()
                try: pct = int(float(pct))
                except: pct = 0
            download_progress[dl_id]['progress'] = pct
            download_progress[dl_id]['status'] = 'downloading'
        elif d['status'] == 'finished':
            download_progress[dl_id]['progress'] = 100
            download_progress[dl_id]['status'] = 'converting'
            download_progress[dl_id]['filename'] = d.get('filename')
    
    def download_worker():
        try:
            opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio',
                'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [progress_hook],
            }
            with YoutubeDL(get_yt_opts(opts)) as ydl:
                ydl.download([youtube_url])
            download_progress[dl_id]['status'] = 'done'
        except Exception as e:
            print(f"[ERRO download] {e}")
            download_progress[dl_id]['status'] = 'error'
            download_progress[dl_id]['error'] = str(e)
    
    threading.Thread(target=download_worker, daemon=True).start()
    return jsonify({'status': 'Download iniciado', 'dl_id': dl_id, 'folder': DOWNLOAD_DIR})

@app.route('/api/download/progress/<dl_id>')
def api_download_progress(dl_id):
    info = download_progress.get(dl_id, {'progress': 0, 'status': 'unknown'})
    return jsonify(info)

@app.route('/api/downloads')
def api_downloads():
    try:
        files = [f for f in os.listdir(DOWNLOAD_DIR) 
                 if f.endswith(('.mp3', '.m4a', '.webm', '.mp4')) and not f.endswith('.part')]
        return jsonify({'files': sorted(files, key=lambda f: os.path.getmtime(os.path.join(DOWNLOAD_DIR, f)), reverse=True)})
    except:
        return jsonify({'files': []})

@app.route('/downloads/<path:filename>')
def serve_download(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    print('=' * 60)
    print('TOCA WEB - Servidor iniciado')
    print(f"Deno: {'ENCONTRADO em ' + deno_dir if deno_dir else 'NÃO ENCONTRADO'}")
    print(f"Debug: {'SIM' if DEBUG else 'NÃO'}")
    print(f"URL: http://{HOST}:{PORT}")
    print('=' * 60)
    app.run(host=HOST, port=PORT, debug=DEBUG, use_reloader=False)
