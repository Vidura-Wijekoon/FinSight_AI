"""
Tests for FinSight AI — Encryption Module
"""
import os
import tempfile
from pathlib import Path

import pytest
from cryptography.fernet import InvalidToken

from src.security.encryption import (
    decrypt_bytes,
    encrypt_and_save,
    encrypt_bytes,
    generate_key,
    load_and_decrypt,
    load_key,
)


@pytest.fixture
def tmp_key_path(tmp_path):
    return str(tmp_path / "keys" / "secret.key")


@pytest.fixture
def fernet_key(tmp_key_path):
    generate_key(tmp_key_path)
    return load_key(tmp_key_path)


class TestGenerateKey:
    def test_creates_key_file(self, tmp_key_path):
        generate_key(tmp_key_path)
        assert Path(tmp_key_path).exists()

    def test_does_not_overwrite_existing_key(self, tmp_key_path):
        generate_key(tmp_key_path)
        original = Path(tmp_key_path).read_bytes()
        generate_key(tmp_key_path)  # Should be a no-op
        assert Path(tmp_key_path).read_bytes() == original

    def test_key_is_valid_fernet_key(self, tmp_key_path):
        generate_key(tmp_key_path)
        from cryptography.fernet import Fernet
        key = Path(tmp_key_path).read_bytes()
        # Should not raise
        Fernet(key)


class TestEncryptDecrypt:
    def test_roundtrip_bytes(self, fernet_key):
        original = b"Secret financial data: Q4 revenue $1.2B"
        ciphertext = encrypt_bytes(original, fernet_key)
        assert ciphertext != original
        assert decrypt_bytes(ciphertext, fernet_key) == original

    def test_encrypt_empty_data(self, fernet_key):
        ciphertext = encrypt_bytes(b"", fernet_key)
        assert decrypt_bytes(ciphertext, fernet_key) == b""

    def test_wrong_key_raises(self, fernet_key):
        from cryptography.fernet import Fernet
        wrong_key = Fernet.generate_key()
        ciphertext = encrypt_bytes(b"sensitive data", fernet_key)
        with pytest.raises(InvalidToken):
            decrypt_bytes(ciphertext, wrong_key)

    def test_large_payload(self, fernet_key):
        large_data = b"X" * (5 * 1024 * 1024)  # 5 MB
        ciphertext = encrypt_bytes(large_data, fernet_key)
        assert decrypt_bytes(ciphertext, fernet_key) == large_data


class TestFileOperations:
    def test_encrypt_and_save_creates_file(self, tmp_path, fernet_key):
        dest = tmp_path / "test.enc"
        data = b"financial document content"
        returned = encrypt_and_save(data, dest, fernet_key)
        assert returned == dest
        assert dest.exists()

    def test_load_and_decrypt_roundtrip(self, tmp_path, fernet_key):
        dest = tmp_path / "test.enc"
        original = b"10-K filing data for FY2024"
        encrypt_and_save(original, dest, fernet_key)
        recovered = load_and_decrypt(dest, fernet_key)
        assert recovered == original

    def test_load_missing_file_raises(self, tmp_path, fernet_key):
        with pytest.raises(FileNotFoundError):
            load_and_decrypt(tmp_path / "missing.enc", fernet_key)
