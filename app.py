from flask import Flask, request, jsonify, Response, render_template
import os
import threading
import requests
import re
from mutagen.flac import FLAC, Picture
from io import BytesIO
import time
from queue import Queue
import json
import qobuz
import hashlib
from dotenv import load_dotenv
import zipfile

# --- Environment Setup ---
load_dotenv()

# --- Configuration ---
MAX_THREADS = 10
QOBUZ_APP_ID = "798273057"
QOBUZ_APP_SECRET = "abb21364945c0583309667d13ca3d93a"
QOBUZ_USER_AUTH_TOKEN = os.getenv("QOBUZ_USER_AUTH_TOKEN")

if not QOBUZ_USER_AUTH_TOKEN:
    print("Warning: QOBUZ_USER_AUTH_TOKEN is not set. Please create a .env file and add your token.")

# --- Flask App Initialization ---
app = Flask(__name__, static_folder='gui', static_url_path='', template_folder='gui')

# --- Global Variables ---
status_messages = []
status_lock = threading.Lock()

# --- Qobuz API Initialization ---
qobuz.api.register_app(
    app_id=QOBUZ_APP_ID,
    app_secret=QOBUZ_APP_SECRET
)

# --- Core Music Downloading Logic ---

def update_status(message, type='info'):
    """Adds a filtered status message to the list."""
    allowed_keywords = ['downloading', 'completed', 'progress']

    if not any(keyword in message.lower() for keyword in allowed_keywords):
        return

    with status_lock:
        status_messages.append({
            'message': message,
            'type': type,
            'timestamp': time.time(),
            'id': len(status_messages)
        })
        if len(status_messages) > 100:
            status_messages.pop(0)

def _get_download_url(track_id):
    """Gets a download URL for a given track ID."""
    format_id = 27  # FLAC
    intent = 'stream'
    request_ts = int(time.time())
    
    sig_string = f"trackgetFileUrlformat_id{format_id}intent{intent}track_id{track_id}{request_ts}{QOBUZ_APP_SECRET}"
    request_sig = hashlib.md5(sig_string.encode()).hexdigest()
    
    url = "https://www.qobuz.com/api.json/0.2/track/getFileUrl"
    params = {
        'app_id': QOBUZ_APP_ID,
        'track_id': track_id,
        'format_id': format_id,
        'intent': intent,
        'request_ts': request_ts,
        'request_sig': request_sig
    }
    headers = {'X-User-Auth-Token': QOBUZ_USER_AUTH_TOKEN}
    
    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()
    file_url_response = response.json()
    
    if not file_url_response or 'url' not in file_url_response:
        raise ValueError("Could not get download URL.")
        
    return file_url_response['url']

def _add_metadata(audio, track):
    """Adds metadata and album art to an in-memory FLAC object."""
    audio['title'] = track.title
    audio['artist'] = track.artist.name
    audio['album'] = track.album.title
    audio['date'] = str(track.album.released_at) if hasattr(track.album, 'released_at') else ''

    try:
        album_data = qobuz.api.request('album/get', album_id=track.album.id)
        image_url = album_data.get('image', {}).get('large') or album_data.get('image', {}).get('thumbnail')

        if image_url:
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()

            picture = Picture()
            picture.type = 3
            picture.mime = "image/jpeg"
            picture.desc = "Cover"
            picture.data = img_response.content
            audio.add_picture(picture)
    except Exception as e:
        update_status(f"Failed to fetch album art: {e}", 'error')

def _process_track_for_download(track):
    """Downloads a track, adds metadata, and returns it as a BytesIO object."""
    download_url = _get_download_url(track.id)
    stream_response = requests.get(download_url, stream=True, timeout=120)
    stream_response.raise_for_status()

    file_buffer = BytesIO()
    for chunk in stream_response.iter_content(chunk_size=8192):
        file_buffer.write(chunk)
    file_buffer.seek(0)

    audio = FLAC(file_buffer)
    _add_metadata(audio, track)
    
    output_buffer = BytesIO()
    audio.save(output_buffer)
    output_buffer.seek(0)
    
    filename = f"{re.sub(r'[<>:\"/\\\\|?*]', '', track.artist.name)} - {re.sub(r'[<>:\"/\\\\|?*]', '', track.title)}.flac"
    
    return filename, output_buffer

# --- Helper function to get raw API data ---
def _get_track_data_with_images(query, search_type='track', limit=10, offset=0):
    """Get track/album data directly from API to include image URLs."""
    try:
        qobuz.api.user_auth_token = QOBUZ_USER_AUTH_TOKEN
        
        if search_type == 'track':
            response = qobuz.api.request('track/search', query=query, limit=limit, offset=offset)
            return response.get('tracks', {}).get('items', [])
        elif search_type == 'album':
            response = qobuz.api.request('album/search', query=query, limit=limit, offset=offset)
            return response.get('albums', {}).get('items', [])
    except Exception as e:
        print(f"Error getting raw API data: {e}")
        return []

def _get_album_tracks_with_images(album_id):
    """Get album tracks directly from API to include image URLs."""
    try:
        qobuz.api.user_auth_token = QOBUZ_USER_AUTH_TOKEN
        response = qobuz.api.request('album/get', album_id=album_id)
        return response
    except Exception as e:
        print(f"Error getting album data: {e}")
        return None

# --- API Endpoints ---

@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html')

def track_to_dict(track_data):
    """Convert raw API track data to frontend format."""
    if isinstance(track_data, dict):
        album = track_data.get('album', {})
        performer = track_data.get('performer', {})
        image = album.get('image', {})
        
        return {
            'id': track_data.get('id'),
            'title': track_data.get('title'),
            'duration': track_data.get('duration'),
            'performer': { 'id': performer.get('id'), 'name': performer.get('name') },
            'album': {
                'id': album.get('id'),
                'title': album.get('title'),
                'image': { 'small': image.get('small') or image.get('thumbnail') or f"https://static.qobuz.com/images/covers/{album.get('id')}_230.jpg" }
            }
        }
    else:
        image_url = f"https://static.qobuz.com/images/covers/{track_data.album.id}_230.jpg"
        return {
            'id': track_data.id,
            'title': track_data.title,
            'duration': track_data.duration,
            'performer': { 'id': track_data.artist.id, 'name': track_data.artist.name },
            'album': { 'id': track_data.album.id, 'title': track_data.album.title, 'image': { 'small': image_url } }
        }

def album_to_dict(album_data):
    """Convert raw API album data to frontend format."""
    if isinstance(album_data, dict):
        artist = album_data.get('artist', {})
        image = album_data.get('image', {})
        
        return {
            'id': album_data.get('id'),
            'title': album_data.get('title'),
            'artist': { 'id': artist.get('id'), 'name': artist.get('name') },
            'image': { 'small': image.get('small') or image.get('thumbnail') or f"https://static.qobuz.com/images/covers/{album_data.get('id')}_230.jpg" }
        }
    else:
        image_url = f"https://static.qobuz.com/images/covers/{album_data.id}_230.jpg"
        return {
            'id': album_data.id,
            'title': album_data.title,
            'artist': { 'id': album_data.artist.id, 'name': album_data.artist.name },
            'image': { 'small': image_url }
        }

@app.route('/api/search', methods=['POST'])
def search():
    """API endpoint to search for songs or albums."""
    data = request.get_json()
    query = data.get('query')
    search_type = data.get('type', 'track')
    limit = data.get('limit', 10)
    offset = data.get('offset', 0)

    if not query:
        return jsonify({'error': 'Please enter a search query.'}), 400

    try:
        raw_results = _get_track_data_with_images(query, search_type, limit, offset)
        
        if search_type == 'track':
            results = [track_to_dict(item) for item in raw_results]
        elif search_type == 'album':
            results = [album_to_dict(item) for item in raw_results]
        else:
            results = []
            
        return jsonify(results)
    except Exception as e:
        update_status(f"Search failed: {e}", 'error')
        return jsonify({'error': 'Search failed.'}), 500

@app.route('/api/download-song', methods=['POST'])
def download_song():
    """API endpoint to stream a single song to the user."""
    data = request.get_json()
    track_data = data.get('track')
    if not track_data or not track_data.get('id'):
        return jsonify({'error': 'Invalid track data provided.'}), 400

    try:
        track = qobuz.Track.from_id(track_data['id'])
        filename, file_buffer = _process_track_for_download(track)
        
        return Response(
            file_buffer,
            mimetype='audio/flac',
            headers={'Content-Disposition': f'attachment;filename="{filename}"'}
        )
    except Exception as e:
        update_status(f"Failed to prepare download: {e}", 'error')
        return jsonify({'error': 'Failed to prepare download.'}), 500

@app.route('/api/get-album-tracks', methods=['POST'])
def get_album_tracks():
    """API endpoint to get all tracks from an album."""
    data = request.get_json()
    album_id = data.get('album_id')
    if not album_id:
        return jsonify({'error': 'Invalid album ID provided.'}), 400

    try:
        album_data = _get_album_tracks_with_images(album_id)
        if album_data and 'tracks' in album_data:
            track_items = album_data['tracks'].get('items', [])
            for track in track_items:
                track['album'] = {
                    'id': album_data.get('id'),
                    'title': album_data.get('title'),
                    'image': album_data.get('image', {})
                }
                track['performer'] = track.get('performer') or album_data.get('artist', {})
            
            results = [track_to_dict(track) for track in track_items]
            return jsonify(results)
        else:
            return jsonify([])
    except Exception as e:
        update_status(f"Failed to get album tracks: {e}", 'error')
        return jsonify({'error': 'Failed to get album tracks.'}), 500

@app.route('/api/download-playlist', methods=['POST'])
def download_playlist():
    """API endpoint to download a playlist from an uploaded file as a ZIP."""
    if 'playlist' not in request.files:
        return jsonify({'error': 'No playlist file provided.'}), 400
    
    file = request.files['playlist']
    if file.filename == '':
        return jsonify({'error': 'No selected file.'}), 400

    try:
        content = file.read().decode('utf-8-sig')
        songs_and_artists = [
            (line.split(" - ")[0].strip(), line.split(" - ")[1].strip())
            for line in content.splitlines() if " - " in line
        ]
        
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for artist, song in songs_and_artists:
                try:
                    track = qobuz.Track.search(query=f"{artist} {song}", limit=1)[0]
                    if track:
                        filename, file_buffer = _process_track_for_download(track)
                        zip_file.writestr(filename, file_buffer.getvalue())
                        update_status(f"Added to ZIP: {filename}", 'info')
                except Exception as e:
                    update_status(f"Skipping track {artist} - {song}: {e}", 'error')

        zip_buffer.seek(0)
        
        return Response(
            zip_buffer,
            mimetype='application/zip',
            headers={'Content-Disposition': 'attachment;filename="playlist.zip"'}
        )
    except Exception as e:
        update_status(f"Error processing playlist: {e}", 'error')
        return jsonify({'error': 'Failed to process playlist file.'}), 500

@app.route('/api/status')
def status_stream():
    """Server-Sent Events endpoint to stream status updates."""
    def event_stream():
        last_id = -1
        while True:
            try:
                with status_lock:
                    new_messages = [msg for msg in status_messages if msg['id'] > last_id]
                
                for msg in new_messages:
                    yield f"data: {json.dumps(msg)}\n\n"
                    last_id = msg['id']
                
                if not new_messages:
                    yield f"data: {json.dumps({'message': 'heartbeat', 'type': 'heartbeat'})}\n\n"
                
                time.sleep(1)
                
            except GeneratorExit:
                break
            except Exception as e:
                print(f"SSE Error: {e}")
                break
    
    return Response(event_stream(), mimetype='text/event-stream',
                   headers={'Cache-Control': 'no-cache',
                           'Connection': 'keep-alive'})

# --- Main Execution ---

def main():
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    main()
