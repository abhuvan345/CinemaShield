import os
import json
import hashlib
from datetime import datetime, timedelta

# Folder where encrypted shards are stored
SHARDS_FOLDER = "encrypted_shards"

# Output manifest file
MANIFEST_FILE = "manifest.json"

# Example theatre ID and playback window
THEATRE_ID = "THEATRE_001"
PLAYBACK_START = datetime.utcnow()
PLAYBACK_END = PLAYBACK_START + timedelta(hours=2)  # 2 hours window

def sha256_file(filepath):
    """Compute SHA-256 hash of a file"""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()

def generate_manifest():
    if not os.path.exists(SHARDS_FOLDER):
        print(f"⚠ Folder '{SHARDS_FOLDER}' does not exist!")
        return

    shards = [f for f in os.listdir(SHARDS_FOLDER) if os.path.isfile(os.path.join(SHARDS_FOLDER, f))]
    if not shards:
        print(f"⚠ No encrypted shards found in '{SHARDS_FOLDER}'!")
    
    manifest_data = {
        "created_at": datetime.utcnow().isoformat() + "Z",
        "theatre_id": THEATRE_ID,
        "playback_window": {
            "start": PLAYBACK_START.isoformat() + "Z",
            "end": PLAYBACK_END.isoformat() + "Z"
        },
        "shards": []
    }

    for shard_file in sorted(shards):
        shard_path = os.path.join(SHARDS_FOLDER, shard_file)
        shard_hash = sha256_file(shard_path)
        manifest_data["shards"].append({
            "id": shard_file,
            "sha256": shard_hash
        })

    with open(MANIFEST_FILE, "w") as f:
        json.dump(manifest_data, f, indent=4)

    print(f"✅ Manifest generated: {MANIFEST_FILE}")
    print(f"Total shards: {len(manifest_data['shards'])}")

if __name__ == "__main__":
    generate_manifest()
