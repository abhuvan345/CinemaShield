import os
from cryptography.fernet import Fernet

# -----------------------------
# CONFIG
# -----------------------------
SHARDS_FOLDER = "shards"
ENCRYPTED_FOLDER = "encrypted_shards"

# Create encrypted folder if it doesn't exist
os.makedirs(ENCRYPTED_FOLDER, exist_ok=True)

# Generate a key or load from file (keep this safe!)
KEY_FILE = "secret.key"

if os.path.exists(KEY_FILE):
    with open(KEY_FILE, "rb") as f:
        key = f.read()
else:
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as f:
        f.write(key)

fernet = Fernet(key)

# -----------------------------
# ENCRYPT SHARDS
# -----------------------------
shards = [f for f in os.listdir(SHARDS_FOLDER) if os.path.isfile(os.path.join(SHARDS_FOLDER, f))]

if not shards:
    print("⚠ No shards found to encrypt!")
else:
    print(f"🔒 Encrypting {len(shards)} shard(s)...")

for shard_file in shards:
    shard_path = os.path.join(SHARDS_FOLDER, shard_file)
    
    # Read plaintext shard
    with open(shard_path, "rb") as f:
        data = f.read()
    
    # Encrypt
    encrypted_data = fernet.encrypt(data)
    
    # Write encrypted shard
    encrypted_path = os.path.join(ENCRYPTED_FOLDER, shard_file + ".enc")
    with open(encrypted_path, "wb") as f:
        f.write(encrypted_data)
    
    # Delete plaintext shard
    os.remove(shard_path)
    print(f"✅ Encrypted and deleted: {shard_file}")

print(f"🎉 All shards encrypted. Encrypted files stored in '{ENCRYPTED_FOLDER}'")
print(f"🔑 Encryption key saved in '{KEY_FILE}' — keep this safe!")
