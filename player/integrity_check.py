import hashlib

def verify_sha256(data: bytes, expected_hash: str) -> bool:
    actual_hash = hashlib.sha256(data).hexdigest()
    return actual_hash == expected_hash
