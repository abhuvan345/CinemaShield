import os
import subprocess
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

UPLOAD_FOLDER = "uploads"
SHARD_FOLDER = "shards"

SHARD_SIZE_MB = 8                          # Target size per shard (MB)
SHARD_SIZE_BYTES = SHARD_SIZE_MB * 1024 * 1024
MIN_SHARDS = 2                             # Never fewer than 2 shards

os.makedirs(SHARD_FOLDER, exist_ok=True)


def calculate_shards(file_path):
    """
    Each shard targets ~8 MB.  E.g. a 200 MB file → 25 shards.
    More shards = more encrypted fragments an attacker must collect.
    """
    file_size = os.path.getsize(file_path)
    return max(MIN_SHARDS, math.ceil(file_size / SHARD_SIZE_BYTES))


def get_video_duration(file_path):
    """Returns video duration in seconds (float)."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(result.stdout.strip())


def _extract_shard(file_path, index, start_time, duration, output_path):
    """
    Extract a single shard using input-seeking + stream copy.
    -ss before -i uses keyframe-level seeking (near-instant for any offset).
    """
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),          # input seek — fast, uses index
        "-i", file_path,
        "-t", str(duration),              # limit length
        "-c", "copy",                     # no re-encode
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def shard_video(file_path):
    """
    Split video into shards by running N parallel FFmpeg processes.
    Each process input-seeks to its offset and stream-copies its segment,
    so all shards are written simultaneously — much faster than sequential.
    """
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    num_shards = calculate_shards(file_path)

    total_duration = get_video_duration(file_path)
    shard_duration = math.ceil(total_duration / num_shards)

    start = time.perf_counter()
    file_mb = os.path.getsize(file_path) / (1024 * 1024)
    print(f"▶ Video duration: {total_duration:.2f}s | Size: {file_mb:.1f} MB")
    print(f"▶ Splitting into {num_shards} shards (~{shard_duration}s each) in parallel")

    # Build list of (index, start, duration, output) for each shard
    tasks = []
    for i in range(num_shards):
        ss = i * shard_duration
        if ss >= total_duration:
            break
        dur = min(shard_duration, total_duration - ss)
        out = os.path.join(SHARD_FOLDER, f"{base_name}_part{i:03d}.mp4")
        tasks.append((i, ss, dur, out))

    # Run all FFmpeg processes in parallel
    workers = min(len(tasks), os.cpu_count() or 4)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_extract_shard, file_path, idx, ss, dur, out): idx
            for idx, ss, dur, out in tasks
        }
        for future in as_completed(futures):
            future.result()  # propagate exceptions

    elapsed = time.perf_counter() - start
    print(f"✔ Created {len(tasks)} shards in {elapsed:.2f}s")


def _process_single(video_path):
    """Process one video: shard then delete original."""
    shard_video(video_path)
    os.remove(video_path)
    print(f"🗑 Deleted original video: {os.path.basename(video_path)}")


def process_uploads():
    if not os.path.exists(UPLOAD_FOLDER):
        print(f"⚠ No uploads folder found: {UPLOAD_FOLDER}")
        return

    videos = [f for f in os.listdir(UPLOAD_FOLDER) if f.lower().endswith(('.mp4', '.mkv'))]
    if not videos:
        print("⚠ No videos found in uploads folder")
        return

    paths = [os.path.join(UPLOAD_FOLDER, v) for v in videos]

    if len(paths) == 1:
        _process_single(paths[0])
    else:
        # Process multiple videos in parallel
        workers = min(len(paths), os.cpu_count() or 4)
        print(f"▶ Processing {len(paths)} videos with {workers} workers")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_process_single, p): p for p in paths}
            for future in as_completed(futures):
                future.result()  # propagate exceptions

    print("🏁 All videos processed")


if __name__ == "__main__":
    process_uploads()
