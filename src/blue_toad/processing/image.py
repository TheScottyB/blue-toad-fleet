import hashlib

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def validate_image_bytes(data: bytes, *, min_bytes: int = 32, max_bytes: int = 40_000_000) -> str:
    if not min_bytes <= len(data) <= max_bytes:
        raise ValueError(f"image byte length {len(data)} outside {min_bytes}..{max_bytes}")
    return sha256_bytes(data)
