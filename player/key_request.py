def request_key():
    """
    Prototype: securely load Fernet key.
    Production: this comes from authenticated KMS API.
    """
    with open("../backend/secret.key", "rb") as f:
        return f.read()
