from flask import Flask, request, jsonify, Response, render_template, session, redirect, url_for
import os
import secrets
import requests
import re
from mutagen.flac import FLAC, Picture
from io import BytesIO
import time
import json
import qobuz
import hashlib
from dotenv import load_dotenv
from gevent import monkey, spawn, queue
monkey.patch_all()

# --- Environment Setup ---
load_dotenv()

# --- Configuration ---
DOWNLOAD_DIRECTORY = os.getenv("DOWNLOAD_DIRECTORY", "/downloads")
MAX_THREADS = 10
QOBUZ_APP_ID = "798273057"
QOBUZ_APP_SECRET = "abb21364945c0583309667d13ca3d93a"
QOBUZ_USER_AUTH_TOKEN = os.getenv("QOBUZ_USER_AUTH_TOKEN")
FLACCY_PASSWORD = os.getenv("FLACCY_PASSWORD")
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(16))

if not QOBUZ_USER_AUTH_TOKEN:
    print("Warning: QOBUZ_USER_AUTH_TOKEN is not set. Please create a .env file and add your token.")

# --- Flask App Initialization ---
app = Flask(__name__, static_folder='gui', static_url_path='', template_folder='gui')
app.secret_key = SECRET_KEY

# --- Global Variables ---
download_queue = queue.Queue()
status_messages = []
status_lock = secrets.token_hex(16) # Using a simple lock for gevent

# --- Qobuz API Initialization ---
qobuz.api.register_app(
    app_id=QOBUZ_APP_ID,
    app_secret=QOBUZ_APP_SECRET
)


# --- Core Music Downloading Logic ---

def update_status(message, type='info'):
    """Adds a status message to the list."""
    status_messages.append({
        'message': message,
        'type': type,
        'timestamp': time.time(),
        'id': len(status_messages)
    })
    if len(status_messages) > 100:
        status_messages.pop(0)


def _search_track(artist, song):
    """Searches for a track and returns the first result."""
    try:
        qobuz.api.user_auth_token = QOBUZ_USER_AUTH_TOKEN
        query = f"{artist} {song}"
        tracks = qobuz.Track.search(query=query, limit=1)
        if tracks:
            return tracks[0]
        return None
    except Exception as e:
        update_status(f"Search failed for {artist} - {song}: {e}", 'error')
        return None

def _download_song_logic(artist, song):
    """Searches for a song and then downloads it."""
    song_display = f"{artist} - {song}"
    update_status(f"Searching for: {song_display}", 'info')
    track = _search_track(artist, song)
    if track:
        _download_song_logic_by_track(track)
    else:
        update_status(f"Could not find a match for: {song_display}", 'error')

def worker():
    """Worker greenlet to process the download queue."""
    while True:
        track = download_queue.get()
        _download_song_logic_by_track(track)

def _download_song_logic_by_track(track):
    """The main logic for downloading and processing a single song using track data."""
    song_display = f"{track.artist.name} - {track.title}"

    try:
        update_status(f"Initiating download for: {song_display}", 'info')
        
        # Build the signed request for file URL
        track_id = track.id
        format_id = 27  # Try highest quality first
        intent = 'stream'
        request_ts = int(time.time())
        
        # Build signature
        sig_string = f"trackgetFileUrlformat_id{format_id}intent{intent}track_id{track_id}{request_ts}{QOBUZ_APP_SECRET}"
        request_sig = hashlib.md5(sig_string.encode()).hexdigest()
        
        # Make the request
        url = "https://www.qobuz.com/api.json/0.2/track/getFileUrl"
        params = {
            'app_id': QOBUZ_APP_ID,
            'track_id': track_id,
            'format_id': format_id,
            'intent': intent,
            'request_ts': request_ts,
            'request_sig': request_sig
        }
        
        headers = {
            'X-User-Auth-Token': QOBUZ_USER_AUTH_TOKEN
        }
        
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        file_url_response = response.json()
        
        if not file_url_response or 'url' not in file_url_response:
            raise ValueError(f"Could not get download URL. Response: {file_url_response}")
        
        # Check if we got the quality we requested
        actual_format = file_url_response.get('format_id', format_id)
        if actual_format != format_id:
            update_status(f"Quality adjusted from format {format_id} to {actual_format}", 'info')
        
        # Get quality info
        bit_depth = file_url_response.get('bit_depth', 16)
        sampling_rate = file_url_response.get('sampling_rate', 44.1)
        update_status(f"Downloading in {bit_depth}bit/{sampling_rate}kHz", 'info')
        
        download_url = file_url_response['url']
        
        stream_response = requests.get(download_url, stream=True, timeout=120)
        stream_response.raise_for_status()
        
        update_status(f"Downloading: {song_display}", 'info')
        filename = f"{re.sub(r'[<>:\"/\\\\|?*]', '', track.artist.name)} - {re.sub(r'[<>:\"/\\\\|?*]', '', track.title)}.flac"
        
        os.makedirs(DOWNLOAD_DIRECTORY, exist_ok=True)
        filepath = os.path.join(DOWNLOAD_DIRECTORY, filename)

        with open(filepath, 'wb') as f:
            for chunk in stream_response.iter_content(chunk_size=8192):
                f.write(chunk)

        _add_metadata(filepath, track)
        update_status(f"Completed: {song_display}", 'success')
        update_status('progress', 'progress')
        return True

    except Exception as e:
        update_status(f"Failed: {song_display} ({e})", 'error')
        return False

def _add_metadata(filepath, track):
    """Adds metadata and album art to the downloaded FLAC file."""
    from mutagen.flac import FLAC, Picture
    audio = FLAC(filepath)

    # Basic tags
    audio['title'] = track.title
    audio['artist'] = track.artist.name
    audio['album'] = track.album.title
    audio['date'] = str(track.album.released_at) if hasattr(track.album, 'released_at') else ''

    # Fetch more detailed album info from Qobuz API
    try:
        album_data = qobuz.api.request('album/get', album_id=track.album.id)
        image_url = album_data.get('image', {}).get('large') or album_data.get('image', {}).get('thumbnail')

        if image_url:
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()

            picture = Picture()
            picture.type = 3  # Cover front
            picture.mime = "image/jpeg"
            picture.desc = "Cover"
            picture.data = img_response.content
            audio.add_picture(picture)
            update_status(f"Added album art from {image_url}", 'info')
        else:
            update_status("Album image URL not found in API response.", 'warning')
    except Exception as e:
        update_status(f"Failed to fetch album art from API: {e}", 'error')

    audio.save()


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
    if 'logged_in' not in session and FLACCY_PASSWORD:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user login."""
    error = None
    if request.method == 'POST':
        if request.form['password'] == FLACCY_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            error = 'Invalid password'
    return render_template('login.html', error=error)

def track_to_dict(track_data):
    """Convert raw API track data to frontend format."""
    if isinstance(track_data, dict):
        # Working with raw API data
        album = track_data.get('album', {})
        performer = track_data.get('performer', {})
        image = album.get('image', {})
        
        return {
            'id': track_data.get('id'),
            'title': track_data.get('title'),
            'duration': track_data.get('duration'),
            'performer': {
                'id': performer.get('id'),
                'name': performer.get('name'),
            },
            'album': {
                'id': album.get('id'),
                'title': album.get('title'),
                'image': {
                    'small': image.get('small') or image.get('thumbnail') or f"https://static.qobuz.com/images/covers/{album.get('id')}_230.jpg",
                }
            }
        }
    else:
        # Fallback for qobuz library Track objects
        image_url = f"https://static.qobuz.com/images/covers/{track_data.album.id}_230.jpg"
        return {
            'id': track_data.id,
            'title': track_data.title,
            'duration': track_data.duration,
            'performer': {
                'id': track_data.artist.id,
                'name': track_data.artist.name,
            },
            'album': {
                'id': track_data.album.id,
                'title': track_data.album.title,
                'image': {
                    'small': image_url,
                }
            }
        }

def album_to_dict(album_data):
    """Convert raw API album data to frontend format."""
    if isinstance(album_data, dict):
        # Working with raw API data
        artist = album_data.get('artist', {})
        image = album_data.get('image', {})
        
        return {
            'id': album_data.get('id'),
            'title': album_data.get('title'),
            'artist': {
                'id': artist.get('id'),
                'name': artist.get('name'),
            },
            'image': {
                'small': image.get('small') or image.get('thumbnail') or f"https://static.qobuz.com/images/covers/{album_data.get('id')}_230.jpg",
            }
        }
    else:
        # Fallback for qobuz library Album objects
        image_url = f"https://static.qobuz.com/images/covers/{album_data.id}_230.jpg"
        return {
            'id': album_data.id,
            'title': album_data.title,
            'artist': {
                'id': album_data.artist.id,
                'name': album_data.artist.name,
            },
            'image': {
                'small': image_url,
            }
        }

@app.route('/api/search', methods=['POST'])
def search():
    """API endpoint to search for songs or albums."""
    if 'logged_in' not in session and FLACCY_PASSWORD:
        return jsonify({'error': 'Authentication required.'}), 401
    data = request.get_json()
    query = data.get('query')
    search_type = data.get('type', 'track')
    limit = data.get('limit', 10)
    offset = data.get('offset', 0)

    if not query:
        return jsonify({'error': 'Please enter a search query.'}), 400

    try:
        # Get raw API data which includes image URLs
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
    """API endpoint to download a single song by its track_id."""
    if 'logged_in' not in session and FLACCY_PASSWORD:
        return jsonify({'error': 'Authentication required.'}), 401
    data = request.get_json()
    track_data = data.get('track')
    if not track_data or not track_data.get('id'):
        return jsonify({'error': 'Invalid track data provided.'}), 400
    
    # Fetch the track using its ID from Qobuz API
    try:
        qobuz.api.user_auth_token = QOBUZ_USER_AUTH_TOKEN
        track = qobuz.Track.from_id(track_data['id'])
        download_queue.put(track)
        return jsonify({'message': 'Download started.'}), 202
    except Exception as e:
        update_status(f"Failed to fetch track: {e}", 'error')
        return jsonify({'error': 'Failed to fetch track data.'}), 500

@app.route('/api/get-album-tracks', methods=['POST'])
def get_album_tracks():
    """API endpoint to get all tracks from an album."""
    if 'logged_in' not in session and FLACCY_PASSWORD:
        return jsonify({'error': 'Authentication required.'}), 401
    data = request.get_json()
    album_id = data.get('album_id')
    if not album_id:
        return jsonify({'error': 'Invalid album ID provided.'}), 400

    try:
        # Get album data with tracks
        album_data = _get_album_tracks_with_images(album_id)
        if album_data and 'tracks' in album_data:
            track_items = album_data['tracks'].get('items', [])
            # Add album info to each track
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
    """API endpoint to download a playlist from an uploaded file."""
    if 'logged_in' not in session and FLACCY_PASSWORD:
        return jsonify({'error': 'Authentication required.'}), 401
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
        
        for artist, song in songs_and_artists:
            track = _search_track(artist, song)
            if track:
                download_queue.put(track)
        
        update_status(f"Playlist loaded with {len(songs_and_artists)} songs. Starting downloads...", 'info')
        return jsonify({'message': 'Playlist processing started.'}), 202
    except Exception as e:
        update_status(f"Error processing playlist: {e}", 'error')
        return jsonify({'error': 'Failed to process playlist file.'}), 500

@app.route('/api/status')
def status_stream():
    """Server-Sent Events endpoint to stream status updates."""
    if 'logged_in' not in session and FLACCY_PASSWORD:
        return Response("Authentication required.", status=401)
    def event_stream():
        last_id = -1
        while True:
            try:
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

# Start the background worker greenlets for Gunicorn
for _ in range(MAX_THREADS):
    spawn(worker)

if __name__ == '__main__':
    # This part is for local development/debugging, not for Gunicorn
    app.run(host='0.0.0.0', port=5000, debug=False)
