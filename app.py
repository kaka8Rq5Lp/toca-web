import os, json, requests
from flask import Flask, jsonify, request, render_template
from urllib.parse import quote

app = Flask(__name__, template_folder='templates')

# ============================================
# CONFIGS
# ============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_PATH = os.environ.get('TOCA_LIBRARY_PATH') or os.path.join(BASE_DIR, 'toca_library.json')
PORT = int(os.environ.get('PORT') or 5000)

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
# DEEZER API HELPERS
# ============================================
def search_deezer(query, limit=10):
    url = f"https://api.deezer.com/search?q={quote(query)}&limit={limit}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for item in data.get('data', []):
                results.append({
                    'id': item.get('id'),
                    'title': item.get('title'),
                    'uploader': item.get('artist', {}).get('name', 'Desconhecido'),
                    'duration': item.get('duration'),
                    'thumbnail': item.get('album', {}).get('cover_medium', ''),
                    'url': item.get('preview', '')
                })
            return results
    except Exception as e:
        print(f"[ERRO Deezer search] {e}")
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
    return jsonify({'results': search_deezer(q)})

@app.route('/api/stream')
def api_stream():
    url = request.args.get('url', '')
    if not url: return jsonify({'error': 'URL vazio'}), 400
    return jsonify({'url': url})

@app.route('/api/stream-url')
def api_stream_url():
    url = request.args.get('url', '')
    if not url: return jsonify({'error': 'URL vazio'}), 400
    return jsonify({'url': url})

@app.route('/api/stream-mp3')
def api_stream_mp3():
    url = request.args.get('url', '')
    if not url: return jsonify({'error': 'URL vazio'}), 400
    return jsonify({'url': url})

@app.route('/api/lyrics')
def api_lyrics():
    return jsonify({'lyrics': "Letras não disponíveis nesta versão."})

@app.route('/api/artist-bio')
def api_artist_bio():
    return jsonify({'bio': "Informação de artista não disponível nesta versão."})

# ============================================
# LIBRARY & FAVORITES (simplified)
# ============================================
@app.route('/api/library', methods=['GET', 'POST'])
def api_library():
    if request.method == 'POST':
        data = request.get_json()
        if data: save_library(data)
        return jsonify({'status': 'ok'})
    return jsonify(load_library())

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
                lib['favorites'].append(track)
        save_library(lib)
        return jsonify({'status': 'ok', 'favorites': lib['favorites']})
    return jsonify(lib.get('favorites', []))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=True)
