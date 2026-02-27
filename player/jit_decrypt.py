from cryptography.fernet import Fernet

def decrypt_shard(encrypted_data, key):
    """
    Decrypt a shard using Fernet.
    Decrypted data exists only in memory.
    """
    fernet = Fernet(key)
    return fernet.decrypt(encrypted_data)
