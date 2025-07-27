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

# --- Configuration ---
DOWNLOAD_DIRECTORY = '/var/lib/docker/volumes/nextcloud_nextcloud_data/_data/data/admin/files/Media/Music'
MAX_THREADS = 5

# --- Flask App Initialization ---
app = Flask(__name__, static_folder='gui', static_url_path='', template_folder='gui')

# --- Global Variables ---
download_queue = Queue()
status_messages = []
status_lock = threading.Lock()

# --- Core Music Downloading Logic (Adapted from gui.py) ---

def update_status(message, type='info'):
    """Adds a status message to the list."""
    with status_lock:
        status_messages.append({
            'message': message, 
            'type': type, 
            'timestamp': time.time(),
            'id': len(status_messages)
        })
        # Keep only last 100 messages to prevent memory issues
        if len(status_messages) > 100:
            status_messages.pop(0)

def _search_track(artist, song):
    """Searches for a track and returns the first result."""
    try:
        query = f"{artist} {song}"
        service_url = "https://us.qobuz.squid.wtf"
        search_url = f"{service_url}/api/get-music?q={requests.utils.quote(query)}&limit=1&offset=0"
        
        response = requests.get(search_url, timeout=30)
        response.raise_for_status()
        response_data = response.json()
        data = response_data.get('data', {})
        
        tracks = data.get('tracks', {}).get('items', [])
        if not tracks and 'most_popular' in data:
            tracks = [item['content'] for item in data['most_popular'].get('items', []) if item.get('type') == 'tracks']

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
        # Use the more specific artist/song info from the track if available
        track_artist = track.get('performer', {}).get('name', artist)
        track_song = track.get('title', song)
        _download_song_logic_by_track(track, track_artist, track_song)
    else:
        update_status(f"Could not find a match for: {song_display}", 'error')

def worker():
    """Worker thread to process the download queue."""
    while True:
        artist, song = download_queue.get()
        _download_song_logic(artist, song)
        download_queue.task_done()

def _download_song_logic_by_track(track, artist, song, album_data=None):
    """The main logic for downloading and processing a single song using track data."""
    service_url = "https://us.qobuz.squid.wtf"
    song_display = f"{artist} - {song}"
    
    try:
        update_status(f"Initiating download for: {song_display}", 'info')
        track_id = track.get('id')
        if not track_id:
            raise ValueError("Track ID is missing")
        download_url = f"{service_url}/api/download-music?track_id={track_id}&quality=27"
        download_response = requests.get(download_url, timeout=60)
        streaming_data = download_response.json()
        streaming_url = streaming_data['data']['url']

        stream_response = requests.get(streaming_url, stream=True, timeout=120)
        
        update_status(f"Downloading: {song_display}", 'info')
        real_artist = track.get('performer', {}).get('name', artist)
        real_title = track.get('title', song)
        filename = f"{re.sub(r'[<>:\"/\\\\|?*]', '', real_artist)} - {re.sub(r'[<>:\"/\\\\|?*]', '', real_title)}.flac"
        
        # Ensure the download directory exists
        os.makedirs(DOWNLOAD_DIRECTORY, exist_ok=True)
        filepath = os.path.join(DOWNLOAD_DIRECTORY, filename)

        with open(filepath, 'wb') as f:
            for chunk in stream_response.iter_content(chunk_size=8192):
                f.write(chunk)

        _add_metadata(filepath, track, album_data)
        update_status(f"Completed: {song_display}", 'success')
        update_status('progress', 'progress') # Signal progress update
        return True

    except Exception as e:
        update_status(f"Failed: {song_display} ({e})", 'error')
        return False

def _add_metadata(filepath, track, album_data=None):
    """Adds metadata to the downloaded FLAC file."""
    audio = FLAC(filepath)
    audio['title'] = track.get('title', '')
    audio['artist'] = track.get('performer', {}).get('name', '')

    album_info = track.get('album')
    if album_data:
        audio['album'] = album_data.get('title', '')
        img_url = album_data.get('image', {}).get('large')
    elif album_info:
        audio['album'] = album_info.get('title', '')
        img_url = album_info.get('image', {}).get('large')
    else:
        img_url = None

    if img_url:
        try:
            img_response = requests.get(img_url)
            img_response.raise_for_status()
            picture = Picture()
            picture.type = 3
            picture.mime = "image/jpeg"
            picture.desc = "Cover"
            picture.data = img_response.content
            audio.add_picture(picture)
        except Exception as e:
            update_status(f"Could not download album art: {e}", 'error')
    audio.save()

# --- API Endpoints ---

@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html')

@app.route('/api/search', methods=['POST'])
def search():
    """API endpoint to search for songs or albums."""
    data = request.get_json()
    query = data.get('query')
    search_type = data.get('type', 'track') # Default to track search

    if not query:
        return jsonify({'error': 'Please enter a search query.'}), 400

    try:
        service_url = "https://us.qobuz.squid.wtf"
        search_query = query
        # The API seems to use 'tracks' and 'albums' as keys in the response, not a query param
        search_url = f"{service_url}/api/get-music?q={requests.utils.quote(search_query)}&limit=10&offset=0"
        
        response = requests.get(search_url, timeout=30)
        response.raise_for_status()
        data = response.json()['data']
        
        results = []
        if search_type == 'track':
            tracks = data.get('tracks', {}).get('items', [])
            if not tracks and 'most_popular' in data:
                tracks = [item['content'] for item in data['most_popular'].get('items', []) if item.get('type') == 'tracks']
            results = tracks
        elif search_type == 'album':
            results = data.get('albums', {}).get('items', [])

        return jsonify(results)
    except Exception as e:
        update_status(f"Search failed: {e}", 'error')
        return jsonify({'error': 'Search failed.'}), 500

@app.route('/api/download-song', methods=['POST'])
def download_song():
    """API endpoint to download a single song by its track_id."""
    data = request.get_json()
    track_data = data.get('track')
    if not track_data or not track_data.get('id'):
        return jsonify({'error': 'Invalid track data provided.'}), 400
    
    artist = track_data.get('performer', {}).get('name', 'Unknown Artist')
    song = track_data.get('title', 'Unknown Title')

    threading.Thread(target=_download_song_logic_by_track, args=(track_data, artist, song)).start()
    return jsonify({'message': 'Download started.'}), 202

@app.route('/api/get-album-tracks', methods=['POST'])
def get_album_tracks():
    """API endpoint to get all tracks from an album."""
    data = request.get_json()
    album_id = data.get('album_id')
    if not album_id:
        return jsonify({'error': 'Invalid album ID provided.'}), 400

    try:
        service_url = "https://us.qobuz.squid.wtf"
        album_url = f"{service_url}/api/get-album?album_id={album_id}"
        response = requests.get(album_url, timeout=30)
        response.raise_for_status()
        album_data = response.json()['data']
        
        tracks = album_data.get('tracks', {}).get('items', [])
        if not tracks:
            return jsonify({'error': 'No tracks found for this album.'}), 404

        # Add album data to each track for metadata purposes
        for track in tracks:
            if 'album' not in track or not track['album']:
                track['album'] = {
                    'title': album_data.get('title'),
                    'image': album_data.get('image')
                }

        return jsonify(tracks)
    except Exception as e:
        update_status(f"Failed to get album tracks: {e}", 'error')
        return jsonify({'error': 'Failed to get album tracks.'}), 500

@app.route('/api/download-playlist', methods=['POST'])
def download_playlist():
    """API endpoint to download a playlist from an uploaded file."""
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
            download_queue.put((artist, song))
        
        update_status(f"Playlist loaded with {len(songs_and_artists)} songs. Starting downloads...", 'info')
        return jsonify({'message': 'Playlist processing started.'}), 202
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
                    # Send any new messages
                    new_messages = [msg for msg in status_messages if msg['id'] > last_id]
                
                for msg in new_messages:
                    yield f"data: {json.dumps(msg)}\n\n"
                    last_id = msg['id']
                
                if not new_messages:
                    # Send heartbeat every 30 seconds
                    yield f"data: {json.dumps({'message': 'heartbeat', 'type': 'heartbeat'})}\n\n"
                
                time.sleep(1)  # Small delay to prevent excessive CPU usage
                
            except Exception as e:
                print(f"SSE Error: {e}")
                break
    
    return Response(event_stream(), mimetype='text/event-stream',
                   headers={'Cache-Control': 'no-cache',
                           'Connection': 'keep-alive'})

# --- Main Execution ---

if __name__ == '__main__':
    # Start the background worker threads
    for _ in range(MAX_THREADS):
        threading.Thread(target=worker, daemon=True).start()
    
    # Run the Flask app
    # For production, use a proper WSGI server like Gunicorn or Waitress
    app.run(host='0.0.0.0', port=5000, debug=True)
