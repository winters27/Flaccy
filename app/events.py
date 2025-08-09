import time
import json
from threading import Lock

"""
Events module.

This implements a lightweight per-job event buffer with two modes:
 - Redis-backed (preferred): uses Redis to store event lists and an auto-incrementing id.
 - In-memory fallback: single-process in-memory lists (original behavior).

API:
 - initialize(redis_client): call once with a redis.Redis instance to enable Redis mode.
 - add_event(job_id, type, **kwargs)
 - get_events(job_id, last_id)
 - clear_events(job_id)

Behavioral notes:
 - Events have a numeric incremental 'id' per job. Clients can pass last_id to receive events with id > last_id.
 - When using Redis, events are stored as JSON strings in a list key 'events:{job_id}:list' and the id counter is 'events:{job_id}:id'.
 - We trim stored events to _MAX_EVENTS_PER_JOB to avoid unbounded growth.
"""

_job_events = {}  # in-memory fallback
_lock = Lock()
_MAX_EVENTS_PER_JOB = 1000
_TRIM_TO = 500

_redis = None

def initialize(redis_client):
    """
    Enable Redis-backed event storage. Pass a redis.Redis (or StrictRedis) instance.
    Call from app initialization when available.
    """
    global _redis
    _redis = redis_client

def _use_redis():
    return _redis is not None

def _redis_keys(job_id):
    return f"events:{job_id}:list", f"events:{job_id}:id"

def add_event(job_id, type, **kwargs):
    """
    Append an event for a job. Events are dicts with an incremental id.
    """
    ev = {'type': type, 'timestamp': time.time()}
    ev.update(kwargs)

    if _use_redis():
        try:
            list_key, id_key = _redis_keys(job_id)
            # assign an incremental id
            ev_id = _redis.incr(id_key) - 1  # make ids start at 0 like in-memory impl
            ev['id'] = ev_id
            _redis.rpush(list_key, json.dumps(ev))
            # trim list to max size
            _redis.ltrim(list_key, -_MAX_EVENTS_PER_JOB, -1)
            return
        except Exception:
            # If Redis fails for any reason, fall back to in-memory implementation
            pass

    # In-memory fallback
    with _lock:
        lst = _job_events.setdefault(job_id, [])
        ev_id = len(lst)
        ev['id'] = ev_id
        lst.append(ev)
        if len(lst) > _MAX_EVENTS_PER_JOB:
            _job_events[job_id] = lst[-_TRIM_TO:]
            for idx, e in enumerate(_job_events[job_id]):
                e['id'] = idx

def get_events(job_id, last_id):
    """
    Return events for job_id with id > last_id.
    """
    if _use_redis():
        try:
            list_key, id_key = _redis_keys(job_id)
            raw = _redis.lrange(list_key, 0, -1)
            events = []
            for item in raw:
                try:
                    # redis-py returns bytes; decode if necessary
                    if isinstance(item, bytes):
                        item = item.decode('utf-8')
                    ev = json.loads(item)
                    if ev.get('id', -1) > last_id:
                        events.append(ev)
                except Exception:
                    # skip malformed entries
                    continue
            return events
        except Exception:
            # on error, fall back to in-memory
            pass

    with _lock:
        lst = _job_events.get(job_id, [])
        return [e for e in lst if e['id'] > last_id]

def clear_events(job_id):
    """
    Remove stored events for a job.
    """
    if _use_redis():
        try:
            list_key, id_key = _redis_keys(job_id)
            _redis.delete(list_key)
            _redis.delete(id_key)
            return
        except Exception:
            pass

    with _lock:
        _job_events.pop(job_id, None)
