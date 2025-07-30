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
DOWNLOAD_DIRECTORY = os.getenv("DOWNLOAD_DIRECTORY", "/app/downloads")
if not os.getenv("DOWNLOAD_DIRECTORY"):
    print("Warning: DOWNLOAD_DIRECTORY environment variable not set. Using default: /app/downloads")
QOBUZ_APP_ID = "798273057"
QOBUZ_APP_SECRET = "abb21364945c0583309667d13ca3d93a"
FLACCY_PASSWORD = os.getenv("FLACCY_PASSWORD")
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(16))

# --- Flask App Initialization ---
app = Flask(__name__, static_folder='gui', static_url_path='', template_folder='gui')
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

# --- Qobuz API Initialization ---
qobuz.api.register_app(
    app_id=QOBUZ_APP_ID,
    app_secret=QOBUZ_APP_SECRET
)

# --- Global Variables ---
status_messages = []
download_queue = queue.Queue()
MAX_WORKERS = 3
qobuz_session_data = {}

def load_qobuz_session():
    """Loads Qobuz session from file if it exists."""
    global qobuz_session_data
    if os.path.exists('.qobuz_session'):
        try:
            with open('.qobuz_session', 'r') as f:
                qobuz_session_data = json.load(f)
                print("Qobuz session loaded from file.")
        except (IOError, json.JSONDecodeError) as e:
            print(f"Could not load Qobuz session: {e}")
            qobuz_session_data = {}

# --- Core Music Downloading Logic ---

def update_status(type, **kwargs):
    """Adds a status message to the list."""
    message_data = {
        'type': type,
        'timestamp': time.time(),
        'id': len(status_messages)
    }
    message_data.update(kwargs)
    status_messages.append(message_data)
    
    if len(status_messages) > 100:
        status_messages[:50] = []

@app.route('/api/status')
def status_stream():
    """Server-Sent Events endpoint with improved reliability."""
    if 'logged_in' not in session and FLACCY_PASSWORD:
        return Response("Authentication required.", status=401)
    
    last_id = request.args.get('lastEventId', -1, type=int)
    
    def event_stream():
        nonlocal last_id
        while True:
            try:
                new_messages = [msg for msg in status_messages if msg['id'] > last_id]
                
                for msg in new_messages:
                    yield f"id: {msg['id']}\ndata: {json.dumps(msg)}\n\n"
                    last_id = msg['id']
                
                if not new_messages:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                
                time.sleep(0.3)
                
            except GeneratorExit:
                break
            except Exception as e:
                print(f"SSE Error: {e}")
                break
    
    response = Response(
        event_stream(), 
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )
    return response

def _search_track(artist, song):
    """Searches for a track and returns the first result."""
    try:
        query = f"{artist} {song}"
        tracks = qobuz.Track.search(query=query, limit=1)
        if tracks:
            return tracks[0]
        return None
    except Exception as e:
        update_status(type='error', message=f"Search failed for {artist} - {song}: {e}")
        return None

def _download_song_logic(artist, song, user_id, auth_token):
    """Searches for a song and then downloads it."""
    song_display = f"{artist} - {song}"
    update_status(type='info', message=f"Searching for: {song_display}")
    track = _search_track(artist, song)
    if track:
        # Get album art url
        album_art_url = ''
        try:
            album_data = qobuz.api.request('album/get', album_id=track.album.id)
            album_art_url = album_data.get('image', {}).get('small', '')
        except Exception as e:
            update_status(type='warning', message=f"Could not get album art for {song_display}: {e}")

        download_queue.put((track, user_id, auth_token, album_art_url))
    else:
        update_status(type='error', message=f"Could not find a match for: {song_display}")

def worker():
    """Worker greenlet to process the download queue."""
    print(f"DEBUG: Worker started!")
    while True:
        try:
            track, user_id, auth_token, album_art_url = download_queue.get()
            _download_song_logic_by_track(track, user_id, auth_token, album_art_url)
        except Exception as e:
            update_status(type='error', message=f"An error occurred in the download worker: {e}")

def _download_song_logic_by_track(track, user_id, auth_token, album_art_url):
    """The main logic for downloading and processing a single song using track data."""
    song_display = f"{track.artist.name} - {track.title}"
    download_id = f"{track.id}-{int(time.time())}"

    update_status(type='download_start', download_id=download_id, track_info={
        'title': track.title,
        'artist': track.artist.name,
        'album': track.album.title,
        'albumArtUrl': album_art_url
    })

    try:
        # Create request signature as required by Qobuz API
        request_ts = str(int(time.time()))
        format_id = 27
        
        # Build signature string: trackgetFileUrlformat_id{format_id}track_id{track_id}{timestamp}{app_secret}
        sig_string = f"trackgetFileUrlformat_id{format_id}track_id{track.id}{request_ts}{QOBUZ_APP_SECRET}"
        request_sig = hashlib.md5(sig_string.encode()).hexdigest()
        
        file_url_info = qobuz.api.request(
            'track/getFileUrl',
            track_id=track.id,
            format_id=format_id,
            user_auth_token=auth_token,
            request_ts=request_ts,
            request_sig=request_sig
        )
        
        if not file_url_info or 'url' not in file_url_info:
            raise ValueError(f"Could not get download URL. Response: {file_url_info}")
        
        download_url = file_url_info['url']
        
        # Use a standard requests session for downloading the file content with retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                stream_response = requests.get(download_url, stream=True, timeout=120)
                stream_response.raise_for_status()
                break
            except Exception as download_error:
                if attempt < max_retries - 1:
                    update_status(type='warning', message=f"Download attempt {attempt + 1} failed, retrying: {download_error}")
                    time.sleep(2)  # Wait 2 seconds before retry
                    continue
                else:
                    raise download_error
        
        total_length = int(stream_response.headers.get('content-length', 0))
        downloaded = 0
        
        safe_artist = re.sub(r'[<>:"/\\|?*]', '', track.artist.name)
        safe_title = re.sub(r'[<>:"/\\|?*]', '', track.title)
        filename = f"{safe_artist} - {safe_title}.flac"

        
        os.makedirs(DOWNLOAD_DIRECTORY, exist_ok=True)
        filepath = os.path.join(DOWNLOAD_DIRECTORY, filename)

        update_status(type='info', message=f"Attempting to write to: {filepath}")
        
        # Check if we can write to the directory
        if not os.path.exists(DOWNLOAD_DIRECTORY):
            update_status(type='error', message=f"Directory does not exist: {DOWNLOAD_DIRECTORY}")
        elif not os.access(DOWNLOAD_DIRECTORY, os.W_OK):
            update_status(type='error', message=f"Cannot write to directory: {DOWNLOAD_DIRECTORY}")
        else:
            update_status(type='info', message=f"Directory is writable: {DOWNLOAD_DIRECTORY}")
            
        try:
            import pwd
            import grp
            uid = os.getuid()
            gid = os.getgid()
            user = pwd.getpwuid(uid).pw_name
            group = grp.getgrgid(gid).gr_name
            update_status(type='info', message=f"Running as user: {user}, group: {group}")
        except Exception as e:
            update_status(type='warning', message=f"Could not get user/group info: {e}")

        try:
            with open(filepath, 'wb') as f:
                last_update_time = time.time()
                for chunk in stream_response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    current_time = time.time()
                    if total_length > 0 and (current_time - last_update_time) > 0.2:
                        progress = (downloaded / total_length) * 100
                        update_status(type='progress', download_id=download_id, progress=min(progress, 99))
                        last_update_time = current_time
                        time.sleep(0)
        except PermissionError as pe:
            update_status(type='error', message=f"Permission denied for file: {filepath}")
            update_status(type='error', message=f"Error details: {str(pe)}")
            raise

        _add_metadata(filepath, track)
        update_status(type='progress', download_id=download_id, progress=100)
        update_status(type='success', message=f"Completed: {song_display}")
        return True

    except Exception as e:
        update_status(type='error', message=f"Failed: {song_display} ({e})")
        update_status(type='progress', download_id=download_id, progress=100)
        return False

def _add_metadata(filepath, track):
    """Adds metadata and album art to the downloaded FLAC file."""
    try:
        # Wait a moment to ensure file is fully written
        time.sleep(0.1)
        
        # Check if file exists and has content
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            raise ValueError(f"File is empty or doesn't exist: {filepath}")
        
        audio = FLAC(filepath)

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
            else:
                update_status(type='warning', message="Album image URL not found in API response.")
        except Exception as e:
            update_status(type='error', message=f"Failed to fetch album art from API: {e}")

        # Save with error handling
        try:
            audio.save()
        except Exception as save_error:
            # Try to save without album art if main save fails
            try:
                audio.clear_pictures()
                audio.save()
                update_status(type='warning', message=f"Metadata saved without album art")
            except Exception as fallback_error:
                update_status(type='error', message=f"Failed to save metadata: {str(fallback_error)}")
        
    except Exception as e:
        update_status(type='error', message=f"Metadata error: {str(e)}")

def _get_track_data_with_images(query, search_type='track', limit=10, offset=0):
    """Get track/album data directly from API to include image URLs."""
    try:
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
        response = qobuz.api.request('album/get', album_id=album_id)
        return response
    except Exception as e:
        print(f"Error getting album data: {e}")
        return None

# --- API Endpoints ---

@app.route('/api/qobuz-login', methods=['POST'])
def qobuz_login():
    """Logs into Qobuz using user credentials and saves the session."""
    if FLACCY_PASSWORD and not session.get('logged_in'):
        return jsonify({'error': 'App authentication required'}), 401

    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    try:
        response = qobuz.api.request('user/login', username=email, password=password)
        
        if response and 'user_auth_token' in response:
            user_data = response.get('user', {})
            user_id = user_data.get('id')
            auth_token = response['user_auth_token']
            
            # Save session to file
            with open('.qobuz_session', 'w') as f:
                json.dump({'user_id': user_id, 'auth_token': auth_token}, f)
            
            # Also update the current Flask session
            session['qobuz_user_id'] = user_id
            session['qobuz_auth_token'] = auth_token
            
            return jsonify({'success': True, 'message': 'Qobuz login successful!'})
        else:
            return jsonify({'error': 'Invalid Qobuz credentials'}), 401
            
    except Exception as e:
        return jsonify({'error': f'Qobuz login failed: {e}'}), 500

@app.route('/api/check-session')
def check_session():
    """Checks if the user is logged into the app and Qobuz."""
    qobuz_logged_in = 'qobuz_auth_token' in session or (qobuz_session_data.get('auth_token') is not None)
    return jsonify({
        'flaccy_logged_in': session.get('logged_in', False),
        'qobuz_logged_in': qobuz_logged_in
    })

@app.route('/')
def index():
    """Serves the main HTML page."""
    if FLACCY_PASSWORD and not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user login to the Flaccy application itself."""
    error = None
    if request.method == 'POST':
        if request.form['password'] == FLACCY_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            error = 'Invalid password'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    global qobuz_session_data
    session.pop('logged_in', None)
    session.pop('qobuz_user_id', None)
    session.pop('qobuz_auth_token', None)
    qobuz_session_data = {}
    if os.path.exists('.qobuz_session'):
        os.remove('.qobuz_session')
    return redirect(url_for('login'))

def track_to_dict(track_data):
    """Converts a track data object (dict or class) to a standardized dictionary."""
    if isinstance(track_data, dict):
        album = track_data.get('album', {})
        # Handle both 'performer' and 'artist' fields from API
        performer = track_data.get('performer', {}) or track_data.get('artist', {})
        image = album.get('image', {})

        # Get the highest resolution image available
        def get_best_image_url(image_dict, album_id):
            if not image_dict and album_id:
                return f"https://static.qobuz.com/images/covers/{album_id}_600.jpg"
            
            # Priority order: highest to lowest resolution
            for size in ['mega', 'extralarge', 'large', 'medium', 'small', 'thumbnail']:
                if image_dict.get(size):
                    return image_dict[size]
            
            # Fallback to constructed URL with high resolution
            if album_id:
                return f"https://static.qobuz.com/images/covers/{album_id}_600.jpg"
            
            return 'flaccy.png'

        best_image_url = get_best_image_url(image, album.get('id'))

        return {
            'id': track_data.get('id'),
            'title': track_data.get('title', 'Unknown Title'),
            'duration': track_data.get('duration'),
            'track_number': track_data.get('track_number'),
            'performer': {
                'id': performer.get('id'),
                'name': performer.get('name', 'Unknown Artist'),
            },
            'album': {
                'id': album.get('id'),
                'title': album.get('title', 'Unknown Album'),
                'image': {
                    'small': best_image_url,
                }
            },
            'image': {  # Keep this for backward compatibility
                'small': best_image_url,
            }
        }
    else:  # It's a qobuz.Track object
        image_url = f"https://static.qobuz.com/images/covers/{track_data.album.id}_600.jpg"
        return {
            'id': track_data.id,
            'title': track_data.title,
            'duration': track_data.duration,
            'track_number': track_data.track_number,
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
            },
            'image': {  # Keep this for backward compatibility
                'small': image_url,
            }
        }

def album_to_dict(album_data):
    """Converts an album data object (dict or class) to a standardized dictionary."""
    if isinstance(album_data, dict):
        artist = album_data.get('artist', {})
        image = album_data.get('image', {})
        
        # Get the highest resolution image available
        def get_best_image_url(image_dict, album_id):
            if not image_dict and album_id:
                return f"https://static.qobuz.com/images/covers/{album_id}_600.jpg"
            
            # Priority order: highest to lowest resolution
            for size in ['mega', 'extralarge', 'large', 'medium', 'small', 'thumbnail']:
                if image_dict.get(size):
                    return image_dict[size]
            
            # Fallback to constructed URL with high resolution
            if album_id:
                return f"https://static.qobuz.com/images/covers/{album_id}_600.jpg"
            
            return 'flaccy.png'

        best_image_url = get_best_image_url(image, album_data.get('id'))
        
        return {
            'id': album_data.get('id'),
            'title': album_data.get('title', 'Unknown Album'),
            'artist': {
                'id': artist.get('id'),
                'name': artist.get('name', 'Unknown Artist'),
            },
            'image': {
                'small': best_image_url,
            }
        }
    else:
        # For constructed URLs, use the highest resolution available (_600)
        image_url = f"https://static.qobuz.com/images/covers/{album_data.id}_600.jpg"
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
        raw_results = _get_track_data_with_images(query, search_type, limit, offset)
        
        if search_type == 'track':
            results = [track_to_dict(item) for item in raw_results]
        elif search_type == 'album':
            results = [album_to_dict(item) for item in raw_results]
        else:
            results = []
            
        return jsonify(results)
    except Exception as e:
        update_status(type='error', message=f"Search failed: {e}")
        return jsonify({'error': 'Search failed.'}), 500

@app.route('/api/download-song', methods=['POST'])
def download_song():
    print("DEBUG: download_song called!")
    if not session.get('logged_in') and FLACCY_PASSWORD:
        return jsonify({'error': 'Authentication required.'}), 401
    
    user_id = session.get('qobuz_user_id') or qobuz_session_data.get('user_id')
    auth_token = session.get('qobuz_auth_token') or qobuz_session_data.get('auth_token')
    
    if not user_id or not auth_token:
        return jsonify({'error': 'Qobuz session expired, please log in again.'}), 401

    data = request.get_json()
    track_data = data.get('track')
    if not track_data or not track_data.get('id'):
        return jsonify({'error': 'Invalid track data provided.'}), 400
    
    try:
        # Get the full track object from Qobuz
        track = qobuz.Track.from_id(track_data['id'])
        album_art_url = track_data.get('album_art', '')
        
        # Put the track on the queue to be processed by a worker
        download_queue.put((track, user_id, auth_token, album_art_url))
        
        return jsonify({'message': 'Download queued.'}), 202
    except Exception as e:
        update_status(type='error', message=f"Failed to fetch track: {e}")
        return jsonify({'error': 'Failed to fetch track data.'}), 500

@app.route('/api/download-album', methods=['POST'])
def download_album():
    if not session.get('logged_in') and FLACCY_PASSWORD:
        return jsonify({'error': 'Authentication required.'}), 401
    
    user_id = session.get('qobuz_user_id') or qobuz_session_data.get('user_id')
    auth_token = session.get('qobuz_auth_token') or qobuz_session_data.get('auth_token')
    
    if not user_id or not auth_token:
        return jsonify({'error': 'Qobuz session expired, please log in again.'}), 401

    data = request.get_json()
    album_id = data.get('album_id')
    if not album_id:
        return jsonify({'error': 'Invalid album ID provided.'}), 400

    try:
        # Use the API directly to get album data with tracks
        album_data = qobuz.api.request('album/get', album_id=album_id)
        
        if not album_data:
            raise ValueError(f"Could not get album data for ID: {album_id}")
        
        # Extract tracks from the album data
        tracks_data = album_data.get('tracks', {}).get('items', [])
        album_title = album_data.get('title', 'Unknown Album')
        
        if not tracks_data:
            raise ValueError(f"No tracks found in album: {album_title}")
        
        update_status(type='info', message=f"Queueing {len(tracks_data)} tracks from album: {album_title}")
        
        # Convert track data to track objects and queue them
        album_art_url = album_data.get('image', {}).get('small', '')
        for track_data in tracks_data:
            try:
                # Create a track object from the track data
                track = qobuz.Track.from_id(track_data['id'])
                # Put the track on the queue to be processed by a worker
                download_queue.put((track, user_id, auth_token, album_art_url))
            except Exception as track_error:
                update_status(type='error', message=f"Failed to create track object for ID {track_data.get('id')}: {track_error}")
                continue
        
        return jsonify({'message': f'Queued {len(tracks_data)} tracks for download.'}), 202
        
    except Exception as e:
        update_status(type='error', message=f"Failed to get album tracks: {e}")
        return jsonify({'error': 'Failed to get album tracks.'}), 500

@app.route('/api/get-album-tracks', methods=['POST'])
def get_album_tracks():
    if 'logged_in' not in session and FLACCY_PASSWORD:
        return jsonify({'error': 'Authentication required.'}), 401
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
        update_status(type='error', message=f"Failed to get album tracks: {e}")
        return jsonify({'error': 'Failed to get album tracks.'}), 500

@app.route('/api/download-playlist', methods=['POST'])
def download_playlist():
    if not session.get('logged_in') and FLACCY_PASSWORD:
        return jsonify({'error': 'Authentication required.'}), 401
    user_id = session.get('qobuz_user_id') or qobuz_session_data.get('user_id')
    auth_token = session.get('qobuz_auth_token') or qobuz_session_data.get('auth_token')
    if not user_id or not auth_token:
        return jsonify({'error': 'Qobuz session expired, please log in again.'}), 401
    if 'playlist' not in request.files:
        return jsonify({'error': 'No playlist file provided.'}), 400
    
    file = request.files['playlist']
    if file.filename == '':
        return jsonify({'error': 'No selected file.'}), 400

    def process_playlist():
        content = file.read().decode('utf-8-sig')
        songs_and_artists = [
            (line.split(" - ")[0].strip(), line.split(" - ")[1].strip())
            for line in content.splitlines() if " - " in line
        ]
        
        update_status(type='info', message=f"Playlist loaded with {len(songs_and_artists)} songs. Starting downloads...")
        for artist, song in songs_and_artists:
            _download_song_logic(artist, song, user_id, auth_token)
            time.sleep(0.1)

    spawn(process_playlist)
    return jsonify({'message': 'Playlist processing started.'}), 202

# --- Main Execution ---
def start_workers():
    print("DEBUG: Starting workers...")
    for _ in range(MAX_WORKERS):
        spawn(worker)

load_qobuz_session()
start_workers()
print("DEBUG: App initialization complete")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
