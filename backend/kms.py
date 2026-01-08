import secrets
import json
from datetime import datetime, timedelta

# Example manifest file
MANIFEST_FILE = "manifest.json"

# In-memory key store (for demo; in real world, use secure DB)
KEY_STORE = {}

def generate_temp_key(shard_id, theatre_id, valid_minutes=120):
    """Generate a temporary AES key for a shard"""
    key = secrets.token_hex(32)  # 256-bit key in hex
    expires_at = datetime.utcnow() + timedelta(minutes=valid_minutes)
    
    # Store the key info
    KEY_STORE[shard_id] = {
        "key": key,
        "theatre_id": theatre_id,
        "expires_at": expires_at
    }
    return key

def validate_key(shard_id, theatre_id, key):
    """Check if a key is valid for the shard"""
    info = KEY_STORE.get(shard_id)
    if not info:
        return False, "Key does not exist"
    
    now = datetime.utcnow()
    if info["theatre_id"] != theatre_id:
        return False, "Invalid theatre ID"
    if now > info["expires_at"]:
        return False, "Key expired"
    if info["key"] != key:
        return False, "Invalid key"
    
    return True, "Key valid"

def load_manifest():
    """Load shard info from manifest"""
    with open(MANIFEST_FILE, "r") as f:
        return json.load(f)

if __name__ == "__main__":
    manifest = load_manifest()
    theatre_id = manifest["theatre_id"]
    
    # Generate keys for all shards
    for shard in manifest["shards"]:
        shard_id = shard["id"]
        key = generate_temp_key(shard_id, theatre_id)
        print(f"Shard: {shard_id} | Theatre: {theatre_id} | Key: {key}")

    # Example validation
    sample_shard = manifest["shards"][0]["id"]
    sample_key = KEY_STORE[sample_shard]["key"]
    valid, msg = validate_key(sample_shard, theatre_id, sample_key)
    print(f"Validation for {sample_shard}: {valid}, {msg}")
