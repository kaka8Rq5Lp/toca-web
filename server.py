"""
Toca Studio Backend - Servidor local para músicas completas
============================================================
Requisitos:
  pip install flask flask-cors yt-dlp

Como usar:
  1. Instala os requisitos: pip install flask flask-cors yt-dlp
  2. Corre: python server.py
  3. Abre o toca-studio.html no browser (ficheiro local)
  4. O player vai usar este servidor para pesquisar e reproduzir músicas completas

O servidor corre em http://localhost:5000
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import yt_dlp
import threading
import json

app = Flask(__name__)
CORS(app)  # Permite pedidos do HTML local

# Cache simples para evitar pesquisas repetidas
search_cache = {}
stream_cache = {}


@app.route('/api/search', methods=['GET'])
def search():
    """Pesquisa músicas no YouTube via yt-dlp"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'Query vazia'}), 400

    # Cache
    if query in search_cache:
        return jsonify(search_cache[query])

    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch15',  # 15 resultados
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(f'ytsearch15:{query}', download=False)

        entries = result.get('entries', [])
        tracks = []

        for entry in entries:
            if not entry:
                continue
            tracks.append({
                'id': entry.get('id', ''),
                'title': entry.get('title', 'Sem título'),
                'artist': entry.get('uploader', entry.get('channel', '')),
                'duration': entry.get('duration', 0),
                'thumbnail': entry.get('thumbnail', '') or f"https://i.ytimg.com/vi/{entry.get('id', '')}/mqdefault.jpg",
            })

        response = {'results': tracks}
        search_cache[query] = response
        return jsonify(response)

    except Exception as e:
        print(f'Erro na pesquisa: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/stream/<video_id>', methods=['GET'])
def stream(video_id):
    """Devolve o URL de stream de áudio para um vídeo"""
    if not video_id:
        return jsonify({'error': 'ID vazio'}), 400

    # Cache
    if video_id in stream_cache:
        return jsonify(stream_cache[video_id])

    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'extract_flat': False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)

        audio_url = info.get('url', '')
        if not audio_url:
            # Tenta formats
            formats = info.get('formats') or []
            audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
            if audio_formats:
                audio_formats.sort(key=lambda f: f.get('abr', 0), reverse=True)
                audio_url = audio_formats[0].get('url', '')
            elif formats:
                audio_url = formats[-1].get('url', '')

        if not audio_url:
            return jsonify({'error': 'Sem URL de áudio'}), 404

        response = {
            'url': audio_url,
            'title': info.get('title', ''),
            'artist': info.get('uploader', info.get('channel', '')),
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail', ''),
        }

        stream_cache[video_id] = response
        return jsonify(response)

    except Exception as e:
        print(f'Erro no stream: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/proxy', methods=['GET'])
def proxy_stream():
    """Proxy para stream de áudio (evita problemas de CORS do YouTube)"""
    import urllib.request

    url = request.args.get('url', '')
    if not url:
        return jsonify({'error': 'URL vazio'}), 400

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Range': request.headers.get('Range', ''),
        })

        resp = urllib.request.urlopen(req)
        headers = dict(resp.headers)

        def generate():
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                yield chunk

        return Response(
            generate(),
            content_type=headers.get('Content-Type', 'audio/mp4'),
            headers={
                'Accept-Ranges': 'bytes',
                'Content-Length': headers.get('Content-Length', ''),
                'Content-Range': headers.get('Content-Range', ''),
            }
        )

    except Exception as e:
        print(f'Erro no proxy: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Verifica se o servidor está a correr"""
    return jsonify({'status': 'ok', 'message': 'Toca Studio Backend activo'})


if __name__ == '__main__':
    print('\n🎵 Toca Studio Backend')
    print('=' * 40)
    print('Servidor a correr em: http://localhost:5000')
    print('Abre o toca-studio.html no browser')
    print('Ctrl+C para parar\n')
    app.run(host='0.0.0.0', port=5000, debug=False)
