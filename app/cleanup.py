import os
import time
from typing import List, Tuple

ARTIFACTS_SUBDIR = 'artifacts'

def _file_mtime(path: str) -> float:
    return os.path.getmtime(path)

def _file_size(path: str) -> int:
    return os.path.getsize(path)

def _human_size(bytesize: int) -> str:
    for unit in ('B','KB','MB','GB','TB'):
        if bytesize < 1024:
            return f"{bytesize:.1f}{unit}"
        bytesize /= 1024
    return f"{bytesize:.1f}PB"

def cleanup_artifacts(base_instance_path: str, ttl_minutes: int = 1440, max_total_bytes: int = 20 * 1024**3) -> Tuple[int, int, List[str]]:
    """
    Cleanup artifacts older than ttl_minutes and enforce a max total size (delete oldest files).
    Returns (deleted_count, freed_bytes, deleted_files_list).

    Parameters:
    - base_instance_path: path to Flask instance folder (where 'artifacts' subdir lives)
    - ttl_minutes: time-to-live in minutes for completed artifacts (default 24 hours)
    - max_total_bytes: maximum total artifacts size; oldest files removed if exceeded (default 20 GiB)
    """
    artifacts_dir = os.path.join(base_instance_path, ARTIFACTS_SUBDIR)
    if not os.path.isdir(artifacts_dir):
        return 0, 0, []

    now = time.time()
    ttl_seconds = int(ttl_minutes * 60)
    files_info = []
    total_size = 0

    # Gather files with metadata
    for name in os.listdir(artifacts_dir):
        path = os.path.join(artifacts_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            mtime = _file_mtime(path)
            size = _file_size(path)
        except OSError:
            # Skip files we cannot stat
            continue
        files_info.append({'name': name, 'path': path, 'mtime': mtime, 'size': size})
        total_size += size

    # Sort by mtime ascending (oldest first)
    files_info.sort(key=lambda x: x['mtime'])

    deleted_files = []
    freed_bytes = 0
    deleted_count = 0

    # First pass: delete files older than TTL
    to_keep = []
    for info in files_info:
        age = now - info['mtime']
        if age > ttl_seconds:
            try:
                os.remove(info['path'])
                deleted_files.append(info['path'])
                freed_bytes += info['size']
                deleted_count += 1
                total_size -= info['size']
            except Exception:
                # If deletion fails, skip it
                to_keep.append(info)
        else:
            to_keep.append(info)

    # Second pass: enforce max total size by deleting oldest remaining files
    if total_size > max_total_bytes:
        # sort to_keep ascending by mtime (oldest first) - already.sorted, but ensure
        to_keep.sort(key=lambda x: x['mtime'])
        idx = 0
        while total_size > max_total_bytes and idx < len(to_keep):
            info = to_keep[idx]
            try:
                os.remove(info['path'])
                deleted_files.append(info['path'])
                freed_bytes += info['size']
                deleted_count += 1
                total_size -= info['size']
            except Exception:
                # cannot remove, skip
                pass
            idx += 1

    return deleted_count, freed_bytes, deleted_files

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Cleanup Flaccy artifacts directory.')
    parser.add_argument('--instance-path', '-i', default=os.path.join(os.getcwd(), 'instance'),
                        help='Path to the Flask instance directory (default: ./instance)')
    parser.add_argument('--ttl-minutes', '-t', type=float, default=10.0, help='Artifact TTL in minutes (default 10)')
    parser.add_argument('--max-bytes', '-m', type=float, default=20 * 1024**3,
                        help='Maximum total artifact bytes allowed (default 20 GiB)')
    args = parser.parse_args()

    deleted_count, freed_bytes, deleted_files = cleanup_artifacts(
        base_instance_path=args.instance_path,
        ttl_minutes=args.ttl_minutes,
        max_total_bytes=int(args.max_bytes)
    )

    print(f"Deleted {deleted_count} files, freed {_human_size(freed_bytes)}")
    if deleted_files:
        print("Deleted files:")
        for p in deleted_files:
            print(" -", p)
