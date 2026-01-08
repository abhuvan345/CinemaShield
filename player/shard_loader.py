import os

SHARD_DIR = "../backend/encrypted_shards"

def load_encrypted_shard(shard_id):
    path = os.path.join(SHARD_DIR, shard_id)
    with open(path, "rb") as f:
        return f.read()
