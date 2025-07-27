import webview
import os
import threading
import requests
import re
from mutagen.flac import FLAC, Picture
from io import BytesIO
import time
from queue import Queue
import json

window = None
MAX_THREADS = 5
download_queue = Queue()
status_queue = Queue()

class Api:
    def __init__(self):
        self.playlist_path = ""
        self.download_directory = ""
        threading.Thread(target=self.process_status_updates, daemon=True).start()

    def process_status_updates(self):
        while True:
            message, type = status_queue.get()
            if window:
                safe_message = json.dumps(message)
                window.evaluate_js(f"update_status({safe_message}, '{type}')")
            status_queue.task_done()

    def select_playlist(self):
        file_types = ('Text Files (*.txt)', 'All files (*.*)')
        result = window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
        if result:
            self.playlist_path = result[0]
            return self.playlist_path
        return None
    
    def move_window(self, dx, dy):
        if window:
            try:
                # For pywebview, we need to use the window's current position differently
                # Some versions use x, y properties directly
                if hasattr(window, 'x') and hasattr(window, 'y'):
                    window.move(window.x + int(dx), window.y + int(dy))
                else:
                    # If that doesn't work, we'll track position manually
                    if not hasattr(self, 'window_x'):
                        self.window_x = 100  # Default position
                        self.window_y = 100
                    
                    self.window_x += int(dx)
                    self.window_y += int(dy)
                    window.move(self.window_x, self.window_y)
            except Exception as e:
                print(f"Error moving window: {e}")

    def select_directory(self):
        result = window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
        if result:
            self.download_directory = result[0]
            return self.download_directory
        return None

    def start_download(self, mode, query=None):
        if not self.download_directory:
            self.update_status('Please select a download directory.', 'error')
            return

        if mode == 'playlist':
            if not self.playlist_path:
                self.update_status('Please select a playlist file.', 'error')
                return
            threading.Thread(target=self.process_playlist).start()
        elif mode == 'search' and query:
            threading.Thread(target=self.download_single_song, args=(query,)).start()

    def process_playlist(self):
        with open(self.playlist_path, "r", encoding="utf-8-sig") as file:
            songs_and_artists = [
                (line.split(" - ")[0].strip(), line.split(" - ")[1].strip())
                for line in file if " - " in line
            ]
        
        for _ in range(MAX_THREADS):
            threading.Thread(target=self.worker, daemon=True).start()

        for artist, song in songs_and_artists:
            download_queue.put((artist, song))

        download_queue.join()
        self.update_status('All playlist downloads complete.')

    def download_single_song(self, query):
        try:
            artist, song = [x.strip() for x in query.split('-', 1)]
            success = self._download_song_logic(artist, song)
            if not success:
                self.update_status(f"Failed: {artist} - {song}", 'error')
        except ValueError:
            self.update_status("Invalid format. Use Artist - Song.", 'error')
        except Exception as e:
            self.update_status(f"Error: {e}", 'error')

    def worker(self):
        while True:
            artist, song = download_queue.get()
            self._download_song_logic(artist, song)
            download_queue.task_done()

    def _download_song_logic(self, artist, song):
        service_url = "https://us.qobuz.squid.wtf"
        song_display = f"{artist} - {song}"
        
        try:
            self.test_connection(service_url)
            self.update_status(f"Searching: {song_display}")
            search_query = f"{artist} {song}"
            search_url = f"{service_url}/api/get-music?q={requests.utils.quote(search_query)}&offset=0"
            
            response = requests.get(search_url, timeout=30)
            response.raise_for_status()
            data = response.json()['data']
            
            tracks = data.get('tracks', {}).get('items', [])
            if not tracks and 'most_popular' in data:
                tracks = [item['content'] for item in data['most_popular'].get('items', []) if item.get('type') == 'tracks']

            if not tracks:
                raise ValueError("No tracks found")

            track = tracks[0] # Simplified: take the first result

            track_id = track.get('id')
            download_url = f"{service_url}/api/download-music?track_id={track_id}&quality=27"
            download_response = requests.get(download_url, timeout=60)
            streaming_data = download_response.json()
            streaming_url = streaming_data['data']['url']

            stream_response = requests.get(streaming_url, stream=True, timeout=120)
            total_size = int(stream_response.headers.get('content-length', 0))

            self.update_status(f"Downloading: {song_display}")
            real_artist = track.get('performer', {}).get('name', artist)
            real_title = track.get('title', song)
            filename = f"{re.sub(r'[<>:\"/\\\\|?*]', '', real_artist)} - {re.sub(r'[<>:\"/\\\\|?*]', '', real_title)}.flac"
            filepath = os.path.join(self.download_directory, filename)

            downloaded_size = 0
            with open(filepath, 'wb') as f:
                for chunk in stream_response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if total_size > 0:
                        progress = (downloaded_size / total_size) * 100
                        self.update_status(f"Downloading: {song_display} ({progress:.2f}%)")

            self.update_progress(0)
            self._add_metadata(filepath, track)
            self.update_status(f"Completed: {song_display}")
            return True

        except Exception as e:
            self.update_status(f"Failed: {song_display} ({e})", 'error')
            return False

    def _add_metadata(self, filepath, track):
        audio = FLAC(filepath)
        audio['title'] = track.get('title', '')
        audio['artist'] = track.get('performer', {}).get('name', '')
        if track.get('album'):
            audio['album'] = track['album'].get('title', '')
        # Add more metadata as needed...
        if track.get('album') and track['album'].get('image'):
            img_url = track['album']['image'].get('large')
            if img_url:
                img_response = requests.get(img_url)
                picture = Picture()
                picture.type = 3
                picture.mime = "image/jpeg"
                picture.desc = "Cover"
                picture.data = img_response.content
                audio.add_picture(picture)
        audio.save()

    def update_status(self, message, type='info'):
        status_queue.put((message, type))

    def update_progress(self, progress):
        if window:
            window.evaluate_js(f"update_progress({progress})")

            
    def close_window(self):
        if window:
            window.destroy()

    def minimize_window(self):
        if window:
            window.minimize()

    def test_connection(self, url):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            self.update_status("Connection to service successful.")
        except requests.exceptions.RequestException as e:
            self.update_status(f"Connection to service failed: {e}", 'error')
            raise

def main():
    global window
    api = Api()
    window = webview.create_window(
        'Flaccy',
        'gui/index.html',
        js_api=api,
        width=1024,
        height=600,
        resizable=False,
        frameless=True,
        #easy_drag=True,
        background_color='#0c0c0d'
    )
    webview.start(http_server=True)

if __name__ == '__main__':
    main()
