import os
import subprocess
import math

UPLOAD_FOLDER = "uploads"
SHARD_FOLDER = "shards"
TOTAL_SHARDS = 5

os.makedirs(SHARD_FOLDER, exist_ok=True)

def get_video_duration(file_path):
    """
    Returns video duration in seconds (float)
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(result.stdout.strip())

def shard_video(file_path):
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    output_pattern = os.path.join(SHARD_FOLDER, f"{base_name}_part%03d.mp4")

    total_duration = get_video_duration(file_path)
    shard_duration = math.ceil(total_duration / TOTAL_SHARDS)

    print(f"▶ Video duration: {total_duration:.2f}s")
    print(f"▶ Splitting into {TOTAL_SHARDS} shards (~{shard_duration}s each)")

    cmd = [
        "ffmpeg",
        "-i", file_path,

        # Video re-encode with forced keyframes
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-force_key_frames", f"expr:gte(t,n_forced*{shard_duration})",

        # Audio (if present)
        "-c:a", "copy",

        "-f", "segment",
        "-segment_time", str(shard_duration),
        "-reset_timestamps", "1",
        output_pattern
    ]

    subprocess.run(cmd, check=True)
    print(f"✔ Created exactly {TOTAL_SHARDS} shards")

def process_uploads():
    if not os.path.exists(UPLOAD_FOLDER):
        print(f"⚠ No uploads folder found: {UPLOAD_FOLDER}")
        return

    videos = [f for f in os.listdir(UPLOAD_FOLDER) if f.lower().endswith(('.mp4', '.mkv'))]
    if not videos:
        print("⚠ No videos found in uploads folder")
        return

    for video in videos:
        video_path = os.path.join(UPLOAD_FOLDER, video)
        shard_video(video_path)
        os.remove(video_path)
        print(f"🗑 Deleted original video: {video}")

    print("🏁 All videos processed")

if __name__ == "__main__":
    process_uploads()
