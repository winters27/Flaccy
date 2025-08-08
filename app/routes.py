from flask import Blueprint, request, jsonify, Response, render_template, session, send_file
from gevent import sleep
from gevent.pool import Pool
import time
import json
import os
import re
import tempfile
import zipfile
from io import BytesIO
import uuid

from OrpheusDL.orpheus.core import orpheus_core_download
from OrpheusDL.utils.models import DownloadTypeEnum, MediaIdentification, CodecOptions, QualityEnum

from .orpheus_handler import get_module, construct_third_party_modules, orpheus_session, initialize_modules

main_bp = Blueprint('main', __name__)

status_messages = {}
modules_initialized = False

def update_status(session_id, type, **kwargs):
    if session_id not in status_messages:
        status_messages[session_id] = []
    
    message_data = {'type': type, 'timestamp': time.time(), 'id': len(status_messages[session_id])}
    message_data.update(kwargs)
    status_messages[session_id].append(message_data)
    
    if len(status_messages[session_id]) > 100:
        status_messages[session_id] = status_messages[session_id][50:]

@main_bp.before_request
def ensure_session_id():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())

@main_bp.route('/api/status')
def status_stream():
    session_id = session['user_id']
    if session_id not in status_messages:
        status_messages[session_id] = []

    def event_stream():
        last_id = -1
        while True:
            try:
                if session_id in status_messages:
                    new_messages = [msg for msg in status_messages[session_id] if msg['id'] > last_id]
                    for msg in new_messages:
                        yield f"id: {msg['id']}\ndata: {json.dumps(msg)}\n\n"
                        last_id = msg['id']
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                sleep(0.3)
            except GeneratorExit:
                break
            except Exception as e:
                print(f"SSE Error: {e}")
                break
    return Response(event_stream(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'})

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/api/search', methods=['POST'])
def search():
    global modules_initialized
    if not modules_initialized:
        initialize_modules()
        modules_initialized = True
    data = request.get_json()
    try:
        service = data.get('service')
        module = get_module(service)
        query = data.get('query')
        search_type_str = data.get('type', 'track')
        limit = data.get('limit', 10)
        offset = data.get('offset', 0)

        if not query:
            return jsonify({'error': 'Please enter a search query.'}), 400

        search_type = DownloadTypeEnum.track if search_type_str == 'track' else DownloadTypeEnum.album
        search_results = module.search(query_type=search_type, query=query, limit=limit, offset=offset)
        results = []

        pool = Pool(10)

        if search_type == DownloadTypeEnum.album:
            def fetch_album_info(item):
                try:
                    album_info = module.get_album_info(item.result_id)
                    return {
                        'id': item.result_id,
                        'title': album_info.name if album_info else item.name,
                        'artist': {'name': album_info.artist if album_info else (item.artists[0] if item.artists else 'Unknown Artist')},
                        'image': {'small': album_info.cover_url if album_info else ''}
                    }
                except:
                    return {
                        'id': item.result_id,
                        'title': item.name,
                        'artist': {'name': item.artists[0] if item.artists else 'Unknown Artist'},
                        'image': {'small': ''}
                    }

            jobs = [pool.spawn(fetch_album_info, item) for item in search_results]
            pool.join()
            results = [job.value for job in jobs]

        else:  # track search
            if service == 'qobuz':
                for item in search_results:
                    raw_data = item.extra_kwargs.get('data', {}).get(item.result_id, {})
                    album_data = raw_data.get('album', {})
                    results.append({
                        'id': item.result_id,
                        'title': item.name,
                        'performer': {'name': item.artists[0] if item.artists else 'Unknown Artist'},
                        'album': {'title': album_data.get('title', 'Unknown Album')},
                        'image': {'small': album_data.get('image', {}).get('small', '')}
                    })

            elif service == 'tidal':
                codec_settings = orpheus_session.settings['global']['codecs']
                codec_options = CodecOptions(
                    proprietary_codecs=codec_settings['proprietary_codecs'],
                    spatial_codecs=codec_settings['spatial_codecs']
                )
                quality_str = orpheus_session.settings['global']['general']['download_quality']
                quality_tier = QualityEnum[quality_str.upper()]

                def fetch_track_album_info(item):
                    try:
                        track_info = module.get_track_info(item.result_id, quality_tier=quality_tier, codec_options=codec_options)
                        album_info = module.get_album_info(track_info.album_id)
                        return {
                            'id': item.result_id,
                            'title': item.name,
                            'performer': {'name': item.artists[0] if item.artists else 'Unknown Artist'},
                            'album': {'title': album_info.name},
                            'image': {'small': album_info.cover_url}
                        }
                    except:
                        return {
                            'id': item.result_id,
                            'title': item.name,
                            'performer': {'name': item.artists[0] if item.artists else 'Unknown Artist'},
                            'album': {'title': 'Unknown Album'},
                            'image': {'small': ''}
                        }

                jobs = [pool.spawn(fetch_track_album_info, item) for item in search_results]
                pool.join()
                results = [job.value for job in jobs]

            else:  # fallback for unknown service
                for item in search_results:
                    results.append({
                        'id': item.result_id,
                        'title': item.name,
                        'performer': {'name': item.artists[0] if item.artists else 'Unknown Artist'},
                        'album': {'title': 'Unknown Album'},
                        'image': {'small': ''}
                    })

        return jsonify(results)

    except Exception as e:
        error_message = f"Search failed: {e}"
        if 'user_id' in session:
            update_status(session['user_id'], type='error', message=error_message)
        return jsonify({'error': error_message}), 500

@main_bp.route('/api/download-song', methods=['POST'])
def download_song():
    data = request.get_json()
    download_path = None
    try:
        service = data.get('service')
        module = get_module(service)
        track_data = data.get('track')
        if not track_data or not track_data.get('id'):
            return jsonify({'error': 'Invalid track data provided.'}), 400
        
        track_id = track_data['id']
        session_id = session.get('user_id')
        update_status(session_id, type='info', message=f"Starting download for track ID: {track_id} from {service}", track_id=track_id)

        def progress_callback(current, total):
            update_status(session_id, type='download_progress', track_id=track_id, current=current, total=total)
            sleep(0) # Yield to other greenlets

        download_path = tempfile.mkdtemp(prefix="flaccy_")
        
        media_to_download = {service: [MediaIdentification(media_id=track_id, media_type=DownloadTypeEnum.track)]}
        third_party_modules = construct_third_party_modules(service)
        
        orpheus_core_download(
            orpheus_session=orpheus_session,
            media_to_download=media_to_download,
            third_party_modules=third_party_modules,
            separate_download_module=None,
            output_path=download_path,
            progress_callback=progress_callback
        )

        time.sleep(0.5)

        all_files = []
        for root, dirs, files in os.walk(download_path):
            for file in files:
                all_files.append(os.path.join(root, file))

        if not all_files:
            raise Exception("No files were downloaded")

        audio_file_path = all_files[0]
        filename = os.path.basename(audio_file_path)
        
        with open(audio_file_path, 'rb') as f:
            file_content = f.read()
        
        import shutil
        shutil.rmtree(download_path)
        
        update_status(session.get('user_id'), type='success', message=f"Completed: {filename}")
        
        file_stream = BytesIO(file_content)
        file_stream.seek(0)
        return send_file(
            file_stream,
            mimetype='audio/flac',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        error_msg = f"Failed to download song: {str(e)}"
        if 'user_id' in session:
            update_status(session['user_id'], type='error', message=error_msg)
        return jsonify({'error': error_msg}), 500
        
    finally:
        if download_path and os.path.exists(download_path):
            import shutil
            shutil.rmtree(download_path)

@main_bp.route('/api/download-album', methods=['POST'])
def download_album():
    data = request.get_json()
    download_path = None
    is_temp_dir = False
    try:
        service = data.get('service')
        module = get_module(service)
        album_id = data.get('album_id')
        
        if not album_id:
            return jsonify({'error': 'Invalid album ID provided.'}), 400

        session_id = session.get('user_id')
        update_status(session_id, type='info', message=f"Starting download for album ID: {album_id} from {service}")
        
        album_info = module.get_album_info(album_id)
        album_name = album_info.name if album_info else f"album_{album_id}"
        artist_name = album_info.artist if album_info else "Unknown Artist"
        
        flaccy_mode = os.environ.get('FLACCY_MODE', 'public')
        if flaccy_mode == 'private':
            download_path = os.environ.get('DOWNLOAD_DIRECTORY', './downloads')
            os.makedirs(download_path, exist_ok=True)
        else:
            download_path = tempfile.mkdtemp(prefix="flaccy_album_")
            is_temp_dir = True

        media_to_download = {service: [MediaIdentification(media_id=album_id, media_type=DownloadTypeEnum.album)]}
        third_party_modules = construct_third_party_modules(service)
        
        orpheus_core_download(
            orpheus_session=orpheus_session,
            media_to_download=media_to_download,
            third_party_modules=third_party_modules,
            separate_download_module='default',
            output_path=download_path
        )

        album_folder_path = None
        for item in os.listdir(download_path):
            item_path = os.path.join(download_path, item)
            if os.path.isdir(item_path):
                album_folder_path = item_path
                break
        
        if not album_folder_path:
            raise Exception("Could not find downloaded album folder.")

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(album_folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, album_folder_path)
                    zipf.write(file_path, arcname)
        
        zip_buffer.seek(0)
        
        safe_album_title = re.sub(r'[<>:"/\\|?*]', '', album_name)
        safe_artist_name = re.sub(r'[<>:"/\\|?*]', '', artist_name)
        zip_filename = f"{safe_artist_name} - {safe_album_title}.zip"

        update_status(session.get('user_id'), type='success', message=f"Completed album: {album_name}")
        
        return Response(zip_buffer.getvalue(), 
                       mimetype='application/zip', 
                       headers={'Content-Disposition': f'attachment; filename="{zip_filename}"'})
                       
    except Exception as e:
        error_message = f"Failed to download album: {str(e)}"
        if 'user_id' in session:
            update_status(session['user_id'], type='error', message=error_message)
        return jsonify({'error': 'Failed to download album.', 'details': str(e)}), 500
    finally:
        if is_temp_dir and download_path and os.path.exists(download_path):
            import shutil
            shutil.rmtree(download_path)

@main_bp.route('/api/download-playlist', methods=['POST'])
def download_playlist():
    data = request.get_json()
    download_path = None
    is_temp_dir = False
    try:
        service = data.get('service')
        module = get_module(service)
        queries = data.get('queries', [])
        
        if not queries or not isinstance(queries, list):
            return jsonify({'error': 'Invalid or missing "queries"'}), 400

        flaccy_mode = os.environ.get('FLACCY_MODE', 'public')
        if flaccy_mode == 'private':
            download_path = os.environ.get('DOWNLOAD_DIRECTORY', './downloads')
            os.makedirs(download_path, exist_ok=True)
        else:
            download_path = tempfile.mkdtemp(prefix="flaccy_playlist_")
            is_temp_dir = True

        results = []
        for query in queries:
            try:
                artist, title = [x.strip() for x in query.split('-', 1)]
                search_results = module.search(
                    query_type=DownloadTypeEnum.track,
                    query=title,
                    limit=5,
                    offset=0
                )
                track = next((t for t in search_results if artist.lower() in [a.lower() for a in t.artists]), None)

                if not track:
                    results.append({'query': query, 'status': 'not found'})
                    continue

                media_to_download = {service: [MediaIdentification(media_id=track.result_id, media_type=DownloadTypeEnum.track)]}
                third_party_modules = construct_third_party_modules(service)
                
                orpheus_core_download(
                    orpheus_session=orpheus_session,
                    media_to_download=media_to_download,
                    third_party_modules=third_party_modules,
                    separate_download_module='default',
                    output_path=download_path
                )

                results.append({'query': query, 'status': 'success'})

            except Exception as e:
                results.append({'query': query, 'status': 'error', 'message': str(e)})
        
        if flaccy_mode == 'public':
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(download_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, download_path)
                        zipf.write(file_path, arcname)
            
            zip_buffer.seek(0)
            zip_filename = f"playlist_{uuid.uuid4()}.zip"
            
            return Response(zip_buffer.getvalue(), 
                           mimetype='application/zip', 
                           headers={'Content-Disposition': f'attachment; filename="{zip_filename}"'})

        return jsonify({'results': results}), 200

    except Exception as e:
        return jsonify({'error': f'Failed to download playlist: {str(e)}'}), 500
    finally:
        if is_temp_dir and download_path and os.path.exists(download_path):
            import shutil
            shutil.rmtree(download_path)
