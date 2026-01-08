import os
import subprocess
import tempfile
from manifest_reader import load_manifest
from shard_loader import load_encrypted_shard
from key_request import request_key
from jit_decrypt import decrypt_shard
from integrity_check import verify_sha256


THEATRE_ID = "THEATRE_001"


def verify_all_shards(manifest):
    """
    Verify integrity of all encrypted shards BEFORE playback.
    If any shard is tampered, playback is blocked.
    """
    print(">>> Verifying integrity of all shards...")
    for shard in manifest["shards"]:
        shard_id = shard["id"]
        expected_hash = shard["sha256"]

        encrypted = load_encrypted_shard(shard_id)
        if not verify_sha256(encrypted, expected_hash):
            print(f"❌ Integrity check FAILED for {shard_id}")
            return False

    print("✅ All shards passed integrity verification")
    return True


def play_secure_tempfile():
    print(">>> Secure theatre player started")

    manifest = load_manifest()

    # 1️⃣ Verify integrity first
    for shard in manifest["shards"]:
        encrypted = load_encrypted_shard(shard["id"])
        if not verify_sha256(encrypted, shard["sha256"]):
            print("❌ Integrity check failed:", shard["id"])
            return

    key = request_key()

    # 2️⃣ Create temp folder for decrypted shards
    with tempfile.TemporaryDirectory() as tmpdir:
        decrypted_files = []

        # 3️⃣ Decrypt each shard to temp file
        for idx, shard in enumerate(manifest["shards"]):
            encrypted = load_encrypted_shard(shard["id"])
            decrypted = decrypt_shard(encrypted, key)

            shard_path = os.path.join(tmpdir, f"dec_{idx}.mp4")
            with open(shard_path, "wb") as f:
                f.write(decrypted)

            decrypted_files.append(shard_path)
            del decrypted

        # 4️⃣ Create concat list
        concat_file = os.path.join(tmpdir, "list.txt")
        with open(concat_file, "w") as f:
            for path in decrypted_files:
                f.write(f"file '{path}'\n")

        # 5️⃣ Re-mux correctly and play
        output_path = os.path.join(tmpdir, "final.mp4")
        subprocess.run([
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            output_path
        ], check=True)

        subprocess.run([
            "ffplay",
            "-autoexit",
            "-loglevel", "quiet",
            output_path
        ])

    print(">>> Playback finished, all temp files deleted")

if __name__ == "__main__":
    play_secure_tempfile()
