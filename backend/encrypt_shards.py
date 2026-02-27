import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from cryptography.fernet import Fernet

# -----------------------------
# CONFIG
# -----------------------------
SHARDS_FOLDER = "shards"
ENCRYPTED_FOLDER = "encrypted_shards"
KEY_FILE = "secret.key"

os.makedirs(ENCRYPTED_FOLDER, exist_ok=True)

# Generate a key or load from file (keep this safe!)
if os.path.exists(KEY_FILE):
    with open(KEY_FILE, "rb") as f:
        key = f.read()
else:
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as f:
        f.write(key)

fernet = Fernet(key)


def _encrypt_one(shard_file):
    """Read, encrypt, write .enc, and delete the plaintext shard."""
    shard_path = os.path.join(SHARDS_FOLDER, shard_file)

    with open(shard_path, "rb") as f:
        data = f.read()

    encrypted_data = fernet.encrypt(data)

    encrypted_path = os.path.join(ENCRYPTED_FOLDER, shard_file + ".enc")
    with open(encrypted_path, "wb") as f:
        f.write(encrypted_data)

    os.remove(shard_path)
    return shard_file


# -----------------------------
# ENCRYPT SHARDS (PARALLEL)
# -----------------------------
shards = [f for f in os.listdir(SHARDS_FOLDER) if os.path.isfile(os.path.join(SHARDS_FOLDER, f))]

if not shards:
    print("⚠ No shards found to encrypt!")
else:
    print(f"🔒 Encrypting {len(shards)} shard(s) in parallel...")
    start = time.perf_counter()

    workers = min(len(shards), os.cpu_count() or 4)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_encrypt_one, s): s for s in shards}
        for future in as_completed(futures):
            name = future.result()
            print(f"✅ Encrypted and deleted: {name}")

    elapsed = time.perf_counter() - start
    print(f"🎉 All {len(shards)} shards encrypted in {elapsed:.2f}s")
    print(f"🔑 Encryption key saved in '{KEY_FILE}' — keep this safe!")
