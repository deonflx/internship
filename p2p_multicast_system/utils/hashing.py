import hashlib

def generate_hash(value: str) -> str:
    """
    Generates a SHA-256 hash for a given string value.
    This hash is used to check the consistency of peer metadata.
    """
    return hashlib.sha256(value.encode()).hexdigest()
