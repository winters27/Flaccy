from app import create_app
from app.models import Job, JobStatus
from app import db
from OrpheusDL.orpheus.core import orpheus_core_download
from OrpheusDL.utils.models import DownloadTypeEnum, MediaIdentification
from .orpheus_handler import get_module, construct_third_party_modules, orpheus_session, initialize_modules
import tempfile
import os
import shutil
import uuid
import re
import subprocess

from . import events

def download_task(job_id):
    app = create_app()
    with app.app_context():
        log = app.logger.bind(job_id=job_id)
        log.info("Starting download task")
        job = Job.query.get(job_id)
        if not job:
            log.error("Job not found in database")
            return

        download_path = None

        # Mark running and emit event
        job.status = JobStatus.RUNNING
        job.step = "Initializing"
        job.progress = 0
        db.session.commit()
        events.add_event(job.id, 'status', status=job.status.value, step=job.step)
        log.info("Job status updated to running")

        try:
            initialize_modules()
            log.info("Modules initialized")
            
            source = job.input['source']
            options = job.input.get('options') or {}
            # Ensure options is a dict; callers may pass non-dict values
            if not isinstance(options, dict):
                options = {}
            
            service = source['service']
            media_id = source['id']
            media_type_str = source.get('type', 'track')
            media_type = DownloadTypeEnum[media_type_str]

            module = get_module(service)

            download_path = tempfile.mkdtemp(prefix="flaccy_job_")

            # Track how many files we've already stored and an estimated total to allow
            # smooth, per-track progress mapping during the download phase.
            stored_count = 0
            estimated_total_files = None

            def progress_callback(current, total):
                try:
                    raw = int((current / total) * 100)
                except Exception:
                    raw = 0

                # Smooth mapping with per-track contribution:
                # - Album: total download phase maps to 0..70. Each track contributes 70 / estimated_total_files.
                #   We approximate the number of completed tracks by counting finished files in the download_path
                #   (best-effort: the downloader writes completed files into download_path as it finishes them).
                # - Track: map raw 0-100 -> 0-95 (reserve 95-99 for storing)
                try:
                    if media_type_str == 'album':
                        etf = estimated_total_files or 1
                        per_track = 70.0 / float(etf)

                        # Best-effort estimate of completed tracks by inspecting download_path for audio files
                        try:
                            audio_exts = ('.flac', '.wav', '.mp3', '.m4a', '.aac')
                            files_in_dl = []
                            if download_path and os.path.isdir(download_path):
                                files_in_dl = [f for f in os.listdir(download_path) if os.path.isfile(os.path.join(download_path, f))]
                            completed_tracks = 0
                            for f in files_in_dl:
                                if os.path.splitext(f)[1].lower() in audio_exts:
                                    completed_tracks += 1
                        except Exception:
                            completed_tracks = stored_count or 0

                        # Fractional progress: completed_tracks + current file fraction
                        frac = (completed_tracks + (raw / 100.0))
                        mapped = int(frac * per_track)
                        # clamp to a sensible upper bound (storing/zip phases will push higher later)
                        mapped = max(0, min(mapped, 95))
                    else:
                        mapped = int((raw * 95) / 100)
                except Exception:
                    mapped = raw

                job.progress = mapped

                # Persist progress and emit an event including both the mapped and raw progress,
                # plus the current step so the UI can present accurate, phase-aware feedback.
                try:
                    db.session.commit()
                    events.add_event(job.id, 'progress', progress=job.progress, raw_progress=raw, step=job.step)
                except Exception:
                    # If DB commit fails, still try to emit the progress event
                    try:
                        events.add_event(job.id, 'progress', progress=job.progress, raw_progress=raw, step=job.step)
                    except Exception:
                        pass

            media_to_download = {service: [MediaIdentification(media_id=media_id, media_type=media_type)]}
            third_party_modules = construct_third_party_modules(service)

            # Update job step to Downloading and emit status so clients know download started.
            try:
                job.step = "Downloading"
                job.progress = 0
                db.session.commit()
                try:
                    events.add_event(job.id, 'status', status=job.status.value, step=job.step)
                except Exception:
                    pass
            except Exception:
                pass

            log.info("Calling orpheus_core_download", media=media_to_download, output_path=download_path)
            try:
                rv = orpheus_core_download(
                    orpheus_session=orpheus_session,
                    media_to_download=media_to_download,
                    third_party_modules=third_party_modules,
                    separate_download_module=None,
                    output_path=download_path,
                    progress_callback=progress_callback
                )
                log.info("orpheus_core_download returned", result=rv)
                # Emit a checkpoint event so frontends know the download step finished
                events.add_event(job.id, 'checkpoint', message='download_complete')

                # Conservatively try to extract an album title from the downloader return value (rv).
                # Probe several common keys/nesting patterns used by different backends.
                album_title_from_rv = None
                try:
                    if isinstance(rv, dict):
                        # Top-level common keys
                        for k in ('album_name', 'album', 'name', 'title', 'albumTitle', 'album_title', 'release', 'release_name', 'collection', 'collection_name', 'collectionTitle'):
                            album_title_from_rv = album_title_from_rv or rv.get(k)

                        # Some backends return a media map keyed by service
                        media_map = rv.get('media') or {}
                        svc_entries = media_map.get(service) or media_map.get(service.lower()) or []
                        first = {}
                        if svc_entries and isinstance(svc_entries, (list, tuple)):
                            first = svc_entries[0] or {}
                        else:
                            # try to pick the first entry in the media map if present
                            try:
                                entries = list(media_map.values())
                                if entries:
                                    maybe = entries[0]
                                    if isinstance(maybe, (list, tuple)) and maybe:
                                        first = maybe[0] or {}
                                    elif isinstance(maybe, dict):
                                        first = maybe
                            except Exception:
                                first = {}

                        if isinstance(first, dict):
                            for k in ('album', 'album_name', 'name', 'title', 'albumTitle', 'release', 'release_name', 'collection'):
                                album_title_from_rv = album_title_from_rv or first.get(k)
                            meta = first.get('metadata') or first.get('meta') or first.get('info') or {}
                            if isinstance(meta, dict):
                                for k in ('album', 'album_name', 'name', 'title', 'release', 'release_name'):
                                    album_title_from_rv = album_title_from_rv or meta.get(k)

                    # Normalize to string if found
                    if album_title_from_rv:
                        album_title_from_rv = str(album_title_from_rv)
                except Exception:
                    album_title_from_rv = None

                # Debug: log what (if anything) we extracted from rv so we can iterate if misses continue.
                try:
                    log.info("Album title extraction from rv", album_title_from_rv=album_title_from_rv)
                except Exception:
                    pass

                # Try to estimate total files from rv metadata so progress can allocate per-track portions.
                try:
                    if isinstance(rv, dict):
                        media_map = rv.get('media') or {}
                        svc_entries = media_map.get(service) or media_map.get(service.lower()) or []
                        if isinstance(svc_entries, (list, tuple)) and len(svc_entries) > 0:
                            estimated_total_files = len(svc_entries)
                except Exception:
                    # best-effort only
                    pass
            except Exception as exc:
                # Log full exception with stack for diagnostics
                log.exception("orpheus_core_download raised an exception", error=str(exc))
                # Emit an error event for the job so SSE clients get immediate feedback
                try:
                    events.add_event(job.id, 'error', message=str(exc))
                except Exception:
                    log.exception("Failed to emit error event for job")
                # Re-raise so outer exception handler marks job as failed and persists error
                raise

            log.info("orpheus_core_download completed")

            all_files = []
            for root, dirs, files in os.walk(download_path):
                for file in files:
                    all_files.append(os.path.join(root, file))
            
            log.info("Files found in download path", files=all_files)

            if not all_files:
                raise Exception("No files were downloaded")

            artifacts_dir = app.config.get('ARTIFACTS_DIR') or os.path.join(app.instance_path, 'artifacts')
            os.makedirs(artifacts_dir, exist_ok=True)

            stored_files = []
            # Prefer audio files first so the UI redirects to the primary audio (not sidecar files like .lrc).
            # Sort by extension priority (audio first) and by file size descending so the main audio file is chosen.
            def _ext_priority(p):
                ext = os.path.splitext(p)[1].lower()
                if ext in ('.flac', '.wav', '.mp3', '.m4a', '.aac'):
                    return 0
                return 1

            all_files.sort(key=lambda p: (_ext_priority(p), -os.path.getsize(p)))

            total_files = len(all_files)
            stored_count = 0

            for file_path in all_files:
                orig_filename = os.path.basename(file_path)
                # ensure uniqueness and traceability
                safe_filename = f"{job.id}_{uuid.uuid4().hex}_{orig_filename}"
                new_path = os.path.join(artifacts_dir, safe_filename)
                shutil.move(file_path, new_path)
                # Ensure consistent ownership if configured (ARTIFACTS_OWNER_UID/GID)
                try:
                    owner_uid = app.config.get('ARTIFACTS_OWNER_UID')
                    owner_gid = app.config.get('ARTIFACTS_OWNER_GID')
                    if owner_uid is not None and owner_gid is not None:
                        os.chown(new_path, int(owner_uid), int(owner_gid))
                except Exception:
                    log.exception("Failed to set artifact ownership", path=new_path)
                stored_files.append({'name': orig_filename, 'filename': safe_filename})

                # Emit a per-file stored event and update aggregate progress for album downloads.
                try:
                    stored_count += 1
                    events.add_event(job.id, 'file', name=orig_filename, filename=safe_filename, index=stored_count, total=total_files)
                    if media_type_str == 'album' and total_files > 0:
                        # Map stored file completion into the storing phase portion (70..95).
                        # Each stored file advances progress by a slice of the 25% storing window.
                        move_progress = 70 + int((stored_count / total_files) * 25)
                        # Clamp to not exceed 95 and never regress progress
                        job.progress = max(job.progress, min(move_progress, 95))
                    else:
                        # Non-album downloads: ensure we show substantial progress once the file is stored (95)
                        job.progress = max(job.progress, 95)
                    try:
                        db.session.commit()
                        events.add_event(job.id, 'progress', progress=job.progress, step=job.step)
                    except Exception:
                        # If commit fails, still try to emit progress
                        try:
                            events.add_event(job.id, 'progress', progress=job.progress, step=job.step)
                        except Exception:
                            pass
                except Exception:
                    # Ignore best-effort notifications
                    pass

            # If this was an album download, create a zip archive containing all tracks
            # inside a folder named after the album (sanitized). Insert the zip as the primary
            # artifact so the UI will offer the full album download.
            try:
                if media_type_str == 'album':
                    # Determine album title with preferred priority:
                    # 1) options.album_name, 2) downloader-returned metadata, 3) source.album, 4) fallback album_{job.id}
                    album_title = None
                    try:
                        album_title = (options.get('album_name') if isinstance(options, dict) else None) or album_title_from_rv or job.input.get('source', {}).get('album') or f"album_{job.id}"
                    except Exception:
                        album_title = album_title_from_rv or f"album_{job.id}"
                    # Sanitize: collapse whitespace, replace spaces with underscores, allow only A-Z a-z 0-9 . _ -
                    try:
                        collapsed = re.sub(r'\s+', ' ', str(album_title)).strip()
                        collapsed = collapsed.replace(' ', '_')
                        safe_album = re.sub(r'[^A-Za-z0-9._-]', '', collapsed)[:120] or f"album_{job.id}"
                    except Exception:
                        safe_album = f"album_{job.id}"

                    # If we still have a fallback-style album name (album_{job.id}) try to read
                    # album metadata from the first audio file stored. This helps when the
                    # downloader didn't provide metadata in rv but did tag the files.
                    try:
                        if safe_album.startswith(f"album_{job.id}"):
                            # find first audio artifact
                            audio_exts = ('.flac', '.wav', '.mp3', '.m4a', '.aac')
                            first_audio = None
                            for fmeta in stored_files:
                                if os.path.splitext(fmeta['filename'])[1].lower() in audio_exts:
                                    first_audio = os.path.join(artifacts_dir, fmeta['filename'])
                                    break
                            if first_audio and os.path.isfile(first_audio):
                                try:
                                    # Use mutagen to read album tag if available (best-effort)
                                    from mutagen import File as MutagenFile
                                    m = MutagenFile(first_audio)
                                    album_tag = None
                                    if m:
                                        # Common tag keys across formats
                                        for key in ('album', 'ALBUM', '\xa9alb'):
                                            try:
                                                val = m.tags.get(key) if hasattr(m, 'tags') and m.tags else None
                                                if val:
                                                    # mutagen tag values may be lists
                                                    if isinstance(val, (list, tuple)):
                                                        album_tag = val[0]
                                                    else:
                                                        album_tag = str(val)
                                                    break
                                            except Exception:
                                                continue
                                        # For FLAC/ID3 cases provide alternative lookups
                                        if not album_tag:
                                            try:
                                                # For easy access, try m.tags.get('ALBUM') if present
                                                if hasattr(m, 'tags') and m.tags:
                                                    for k in m.tags.keys():
                                                        if k.lower() == 'album':
                                                            v = m.tags.get(k)
                                                            if isinstance(v, (list, tuple)):
                                                                album_tag = v[0]
                                                            else:
                                                                album_tag = str(v)
                                                            break
                                            except Exception:
                                                pass
                                    if album_tag:
                                        collapsed = re.sub(r'\s+', ' ', str(album_tag)).strip()
                                        collapsed = collapsed.replace(' ', '_')
                                        alt_safe = re.sub(r'[^A-Za-z0-9._-]', '', collapsed)[:120]
                                        if alt_safe:
                                            safe_album = alt_safe
                                except Exception:
                                    # If mutagen isn't present or fails, ignore and keep fallback
                                    pass
                    except Exception:
                        pass
                    # Before creating the zip, mark the job step as Zipping and emit progress so the UI toast
                    # for album jobs reflects zipping activity as part of overall progress.
                    try:
                        job.step = "Zipping"
                        # Move progress towards completion for the zipping phase (download step should
                        # have reported earlier progress). 90 is a reasonable marker before zipping.
                        job.progress = max(job.progress, 90)
                        db.session.commit()
                        try:
                            events.add_event(job.id, 'status', status=job.status.value, step=job.step)
                            events.add_event(job.id, 'progress', progress=job.progress, step=job.step)
                        except Exception:
                            # ignore event emit failures
                            pass
                    except Exception:
                        # best-effort only; continue even if DB commit fails
                        pass

                    zip_name = f"{uuid.uuid4().hex}_{safe_album}.zip"
                    zip_path = os.path.join(artifacts_dir, zip_name)
                    import zipfile as _zipfile
                    try:
                        with _zipfile.ZipFile(zip_path, 'w', _zipfile.ZIP_DEFLATED) as zf:
                            for fmeta in stored_files:
                                stored_path = os.path.join(artifacts_dir, fmeta['filename'])
                                # Add into a folder inside the zip named after the album for clearer extraction
                                arcname = os.path.join(safe_album, fmeta['name'])
                                zf.write(stored_path, arcname)
                        # Ensure ownership of the created zip matches configured artifacts owner
                        try:
                            owner_uid = app.config.get('ARTIFACTS_OWNER_UID')
                            owner_gid = app.config.get('ARTIFACTS_OWNER_GID')
                            if owner_uid is not None and owner_gid is not None:
                                os.chown(zip_path, int(owner_uid), int(owner_gid))
                        except Exception:
                            log.exception("Failed to set ownership on album zip", path=zip_path)
                        # Prepend the zip to the stored_files so UI picks it first and report checkpoint
                        stored_files.insert(0, {'name': f"{safe_album}.zip", 'filename': zip_name})
                        # Update progress slightly to reflect zip completion
                        try:
                            job.progress = 95
                            db.session.commit()
                        except Exception:
                            pass
                        try:
                            events.add_event(job.id, 'checkpoint', message='zip_complete')
                            events.add_event(job.id, 'progress', progress=job.progress, step=job.step)
                        except Exception:
                            log.exception("Failed to emit zip_complete/progress event")
                    except Exception as exc:
                        # If anything goes wrong creating the zip, ignore and continue with individual files.
                        log.exception("Failed to create album zip", error=str(exc))
                        try:
                            events.add_event(job.id, 'zip_failed', message='zip_failed', error=str(exc))
                        except Exception:
                            log.exception("Failed to emit zip_failed event")
            except Exception as exc:
                # If anything goes wrong creating the zip, ignore and continue with individual files.
                log.exception("Failed to create album zip", error=str(exc))
                try:
                    events.add_event(job.id, 'zip_failed', message='zip_failed', error=str(exc))
                except Exception:
                    log.exception("Failed to emit zip_failed event")

            job.status = JobStatus.SUCCEEDED
            job.progress = 100
            job.step = "Completed"
            # Store metadata only (no absolute paths)
            job.result = {'files': stored_files}
            db.session.commit()
            events.add_event(job.id, 'status', status=job.status.value, step=job.step)
            events.add_event(job.id, 'result', files=stored_files)
            log.info("Job succeeded")

        except Exception as e:
            log.error("Job failed", error=str(e))
            try:
                job.status = JobStatus.FAILED
                job.error = str(e)
                db.session.commit()
                events.add_event(job.id, 'status', status=job.status.value, error=str(e))
            except Exception:
                # If DB update fails, just log
                log.exception("Failed to persist job failure state")

        finally:
            if download_path and os.path.exists(download_path):
                try:
                    shutil.rmtree(download_path)
                except Exception:
                    log.exception("Failed to remove temporary download path")
