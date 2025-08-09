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
from . import db
from .models import Job, JobStatus
from .tasks import download_task
from . import events
from . import files as files_module
from flask import current_app
from rq import Queue

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



@main_bp.route('/jobs', methods=['POST'])
def create_job():
    data = request.get_json()
    source = data.get('source')
    options = data.get('options')
    current_app.logger.info("Received job request", data=data)

    if not source:
        current_app.logger.error("Job request missing source", data=data)
        return jsonify({'error': 'Missing source'}), 400

    job_id = str(uuid.uuid4())
    new_job = Job(
        id=job_id,
        status=JobStatus.QUEUED,
        input={'source': source, 'options': options}
    )
    db.session.add(new_job)
    db.session.commit()
    current_app.logger.info("Created new job", job_id=job_id)

    q = Queue(connection=current_app.redis)
    # Enqueue with extended job timeout to allow zipping large albums (600s)
    q.enqueue(download_task, new_job.id, job_timeout=600)
    current_app.logger.info("Enqueued job", job_id=job_id, job_timeout=600)

    return jsonify({'id': new_job.id, 'status': new_job.status.value}), 201

@main_bp.route('/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    job = Job.query.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    return jsonify({
        'id': job.id,
        'status': job.status.value,
        'progress': job.progress,
        'step': job.step,
        'error': job.error,
        'result': job.result
    })

@main_bp.route('/jobs/<job_id>/events', methods=['GET'])
def job_events(job_id):
    """
    Per-job SSE stream. Clients may provide ?last_id=N to only receive events after that id.
    Heartbeats are sent every ~15s to keep proxies from closing the connection.
    """
    # Read request args while we're still inside the request context so the generator
    # doesn't attempt to access request.* later when the context may be gone.
    last_id = int(request.args.get('last_id', -1))

    def event_stream():
        nonlocal last_id
        while True:
            try:
                evs = events.get_events(job_id, last_id)
                for ev in evs:
                    yield f"id: {ev['id']}\ndata: {json.dumps(ev)}\n\n"
                    last_id = ev['id']
                # heartbeat
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                sleep(15)
            except GeneratorExit:
                break
            except Exception as e:
                current_app.logger.error("SSE error", error=str(e))
                break
    return Response(event_stream(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'})

@main_bp.route('/api/health', methods=['GET'])
def health():
    """
    Health endpoint that checks DB connectivity, Redis connectivity, and artifacts directory writability.
    Returns 200 when all checks pass, otherwise 503.
    """
    checks = {'db': False, 'redis': False, 'artifacts': False}
    # DB check
    try:
        # Use SQLAlchemy text() for literal SQL in modern SQLAlchemy versions
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))
        checks['db'] = True
    except Exception as e:
        current_app.logger.error("DB health check failed", error=str(e))

    # Redis check
    try:
        current_app.redis.ping()
        checks['redis'] = True
    except Exception as e:
        current_app.logger.error("Redis health check failed", error=str(e))

    # Artifacts directory writable check
    try:
        artifacts_dir = current_app.config.get('ARTIFACTS_DIR') or os.path.join(current_app.instance_path, 'artifacts')
        os.makedirs(artifacts_dir, exist_ok=True)
        test_path = os.path.join(artifacts_dir, '.healthcheck')
        with open(test_path, 'w') as f:
            f.write('ok')
        os.remove(test_path)
        checks['artifacts'] = True
    except Exception as e:
        current_app.logger.error("Artifacts dir health check failed", error=str(e))

    overall_ok = all(checks.values())
    status_code = 200 if overall_ok else 503
    return jsonify({'status': 'ok' if overall_ok else 'degraded', 'checks': checks}), status_code

@main_bp.route('/files/<filename>', methods=['GET'])
def get_file(filename):
    """
    Serve artifacts from the instance/artifacts directory via Nginx's X-Accel-Redirect.

    Access rules:
      - If a valid signed token is provided via ?token=..., serve the file (anonymous signed link).
      - Otherwise, only serve when the filename exists in a job's result manifest (authenticated flow).
    """
    token = request.args.get('token')
    # Prevent path traversal by taking the basename
    safe_name = os.path.basename(filename)
    
    # Check if file exists physically
    artifacts_dir = current_app.config.get('ARTIFACTS_DIR') or os.path.join(current_app.instance_path, 'artifacts')
    file_path = os.path.join(artifacts_dir, safe_name)
    if not os.path.isfile(file_path):
        return jsonify({'error': 'File not found'}), 404

    # Authorization logic
    allowed = False
    if token:
        payload = files_module.verify_signed_token(token)
        if payload and payload.get('filename') == safe_name:
            allowed = True
    else:
        # No token: require the filename appears in a job manifest
        try:
            jobs = Job.query.filter(Job.result != None).all()
            for j in jobs:
                if not j.result: continue
                files = j.result.get('files', [])
                if any(f.get('filename') == safe_name for f in files):
                    allowed = True
                    break
        except Exception:
            # On DB errors, be conservative
            allowed = False

    if not allowed:
        return jsonify({'error': 'Access denied'}), 403

    # If allowed, send the redirect header to Nginx.
    # Prefer to suggest the original filename to the browser (for a nicer download name)
    # while still using the safe stored filename for on-disk storage and internal redirect.
    display_name = safe_name
    try:
        # Try to find the original display name from job manifests
        jobs = Job.query.filter(Job.result != None).all()
        for j in jobs:
            if not j.result:
                continue
            for f in j.result.get('files', []):
                if f.get('filename') == safe_name:
                    display_name = f.get('name') or safe_name
                    break
            if display_name != safe_name:
                break
    except Exception:
        # If anything goes wrong, fall back to the safe filename
        display_name = safe_name

    # If configured to use Nginx's X-Accel-Redirect, send the redirect header.
    # Otherwise, serve the file directly with Flask's send_file.
    if current_app.config.get('USE_X_ACCEL_REDIRECT', False):
        internal_redirect_path = f'/internal/artifacts/{safe_name}'
        response = Response(status=200)
        response.headers['X-Accel-Redirect'] = internal_redirect_path
        response.headers['Content-Disposition'] = f'attachment; filename="{display_name}"'
        return response
    else:
        # Fallback for development: serve the file directly from the filesystem.
        return send_file(
            file_path,
            as_attachment=True,
            download_name=display_name
        )


@main_bp.route('/files/<filename>/sign', methods=['POST'])
def sign_file(filename):
    """
    Return a signed URL for a given stored filename. Body may include {"ttl": seconds}.
    The filename must be present in some job's result manifest.
    """
    data = request.get_json(force=True, silent=True) or {}
    ttl = int(data.get('ttl', 1800))  # default 30 minutes

    safe_name = os.path.basename(filename)

    # Validate filename exists in a job manifest
    allowed = False
    try:
        jobs = Job.query.filter(Job.result != None).all()
        for j in jobs:
            if not j.result:
                continue
            files = j.result.get('files', [])
            for f in files:
                if f.get('filename') == safe_name:
                    allowed = True
                    break
            if allowed:
                break
    except Exception:
        allowed = False

    if not allowed:
        return jsonify({'error': 'File not found or not allowed to be signed'}), 404

    signed_url = files_module.get_signed_url_for(safe_name, ttl_seconds=ttl, host_url=None)
    return jsonify({'signed_url': signed_url, 'ttl': ttl})
