import os
import json
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger("EncryptionHelper")

# Retrieve encryption keys
ENCRYPTION_KEYS = {}
CURRENT_VERSION = "v1"

keys_env = os.getenv("SECRET_ENCRYPTION_KEYS")
if keys_env:
    try:
        # Expected format: JSON map {"v1": "key1", "v2": "key2"} or comma-separated list of keys
        if keys_env.strip().startswith("{"):
            ENCRYPTION_KEYS = json.loads(keys_env)
            # Find the highest version key as current
            sorted_versions = sorted(ENCRYPTION_KEYS.keys())
            if sorted_versions:
                CURRENT_VERSION = sorted_versions[-1]
        else:
            # Comma-separated list: key1,key2
            parts = [k.strip() for k in keys_env.split(",") if k.strip()]
            for idx, key in enumerate(parts):
                version = f"v{idx+1}"
                ENCRYPTION_KEYS[version] = key
            CURRENT_VERSION = f"v{len(parts)}"
    except Exception as e:
        logger.error(f"Failed to parse SECRET_ENCRYPTION_KEYS: {str(e)}")

# Fallback to single key env
if not ENCRYPTION_KEYS:
    single_key = os.getenv("SECRET_ENCRYPTION_KEY")
    if not single_key:
        single_key = Fernet.generate_key().decode()
        logger.warning(f"No secret keys found. Using temporary key: {single_key}")
    ENCRYPTION_KEYS = {"v1": single_key}
    CURRENT_VERSION = "v1"

class EncryptionHelper:
    _ciphers = {}

    @classmethod
    def get_cipher(cls, version="v1"):
        if version not in cls._ciphers:
            key = ENCRYPTION_KEYS.get(version)
            if not key:
                return None
            try:
                cls._ciphers[version] = Fernet(key.encode())
            except Exception as e:
                logger.error(f"Failed to initialize Fernet cipher for {version}: {str(e)}")
                return None
        return cls._ciphers.get(version)

    @classmethod
    def encrypt_value(cls, val):
        if val is None:
            return None
        cipher = cls.get_cipher(CURRENT_VERSION)
        if not cipher:
            return str(val)
        try:
            ciphertext = cipher.encrypt(str(val).encode()).decode()
            return f"{CURRENT_VERSION}:{ciphertext}"
        except Exception as e:
            logger.error(f"Encryption failed: {str(e)}")
            return str(val)

    @classmethod
    def decrypt_value(cls, encrypted_str):
        if not encrypted_str or not isinstance(encrypted_str, str):
            return encrypted_str
        
        # Check if the value starts with a key version prefix (e.g. "v2:")
        version = "v1"
        ciphertext = encrypted_str
        if ":" in encrypted_str:
            parts = encrypted_str.split(":", 1)
            if parts[0].startswith("v") and parts[0][1:].isdigit():
                version = parts[0]
                ciphertext = parts[1]

        cipher = cls.get_cipher(version)
        if not cipher:
            return encrypted_str
        try:
            return cipher.decrypt(ciphertext.encode()).decode()
        except Exception:
            # Fallback: Try to decrypt using default v1 key in case prefix matched coincidentally
            default_cipher = cls.get_cipher("v1")
            if default_cipher and cipher != default_cipher:
                try:
                    return default_cipher.decrypt(encrypted_str.encode()).decode()
                except Exception:
                    pass
            return encrypted_str

    @classmethod
    def process_sensitive_fields(cls, answers, sensitive_fields, action="encrypt"):
        """
        Encrypts or decrypts sensitive fields in place.
        """
        processed = dict(answers)
        for field in sensitive_fields:
            if field in processed:
                val = processed[field]
                if action == "encrypt":
                    processed[field] = cls.encrypt_value(val)
                elif action == "decrypt":
                    processed[field] = cls.decrypt_value(val)
        return processed
