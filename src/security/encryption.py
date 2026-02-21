"""
FinSight AI — Fernet Encryption Module
Handles symmetric encryption/decryption of document binaries at rest.
Key is stored in keys/secret.key (gitignored).
"""
import os
from pathlib import Path

from cryptography.fernet import Fernet


def generate_key(key_path: str) -> None:
    """Generate and save a new Fernet key if one does not already exist."""
    path = Path(key_path)
    if path.exists():
        return  # Never overwrite an existing key

    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    path.write_bytes(key)
    # Restrict permissions — owner read/write only (POSIX)
    try:
        os.chmod(path, 0o600)
    except AttributeError:
        pass  # Windows — skip chmod


def load_key(key_path: str) -> bytes:
    """Load the Fernet encryption key from disk."""
    path = Path(key_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Encryption key not found at '{key_path}'. "
            "Run generate_key() during app startup."
        )
    return path.read_bytes()


def get_fernet(key: bytes) -> Fernet:
    """Return a Fernet instance for the given key bytes."""
    return Fernet(key)


def encrypt_bytes(data: bytes, key: bytes) -> bytes:
    """Encrypt raw bytes and return ciphertext token."""
    fernet = get_fernet(key)
    return fernet.encrypt(data)


def decrypt_bytes(token: bytes, key: bytes) -> bytes:
    """Decrypt a Fernet ciphertext token back to plaintext bytes."""
    fernet = get_fernet(key)
    return fernet.decrypt(token)


def encrypt_and_save(data: bytes, dest: Path, key: bytes) -> Path:
    """Encrypt data and write ciphertext to dest path. Returns dest."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    ciphertext = encrypt_bytes(data, key)
    dest.write_bytes(ciphertext)
    return dest


def load_and_decrypt(path: Path, key: bytes) -> bytes:
    """Read ciphertext from path and return decrypted plaintext bytes."""
    if not path.exists():
        raise FileNotFoundError(f"Encrypted file not found: {path}")
    ciphertext = path.read_bytes()
    return decrypt_bytes(ciphertext, key)
