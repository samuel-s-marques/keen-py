import os
import shutil
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import ConfigManager


def test_encryption_decryption():
    print("=== Testing Secure API Key Encryption/Decryption ===")
    test_db_dir = os.path.expanduser("~/.keen_test_encryption_tmp")
    if os.path.exists(test_db_dir):
        shutil.rmtree(test_db_dir)

    config_db_path = "~/.keen_test_encryption_tmp/config.db"
    config = ConfigManager(config_db_path)

    # 1. Initially it should not have a master password
    assert not config.has_master_password()
    assert not config.has_api_keys()
    assert not config.is_unlocked()

    # 2. Try getting API keys before unlocking - should return None or empty
    assert config.get_api_key("hunter_io") is None
    assert len(config.get_all_api_keys()) == 0

    # 3. Setup master password
    password = "MySecureMasterPassword123!"
    success = config.unlock(password)
    assert success
    assert config.is_unlocked()
    assert config.has_master_password()

    # 4. Save API keys and retrieve them
    config.set_api_key("hunter_io", "secret_hunter_key_abc123")
    config.set_api_key("apilayer", "apilayer_secret_xyz")
    assert config.has_api_keys()

    assert config.get_api_key("hunter_io") == "secret_hunter_key_abc123"
    assert config.get_api_key("apilayer") == "apilayer_secret_xyz"

    all_keys = config.get_all_api_keys()
    assert len(all_keys) == 2
    assert any(k["service"] == "hunter_io" and k["api_key"] == "secret_hunter_key_abc123" for k in all_keys)

    # Close DB connection to release file lock and lock config
    config.lock()
    config.conn.close()

    # 5. Open new ConfigManager instance mimicking a new shell session
    config2 = ConfigManager(config_db_path)
    assert not config2.is_unlocked()
    assert config2.has_master_password()
    assert config2.has_api_keys()

    # Try retrieving keys while locked
    assert config2.get_api_key("hunter_io") is None

    # Try unlocking with wrong password
    unlocked = config2.unlock("wrong_password")
    assert not unlocked
    assert not config2.is_unlocked()

    # Try unlocking with correct password
    unlocked = config2.unlock(password)
    assert unlocked
    assert config2.is_unlocked()

    # Retrieve keys after unlock
    assert config2.get_api_key("hunter_io") == "secret_hunter_key_abc123"
    assert config2.get_api_key("apilayer") == "apilayer_secret_xyz"

    # Delete a key
    config2.delete_api_key("hunter_io")
    assert config2.get_api_key("hunter_io") is None
    assert config2.get_api_key("apilayer") == "apilayer_secret_xyz"

    config2.conn.close()
    shutil.rmtree(test_db_dir)
    print("\n[OK] ENCRYPTION, DECRYPTION AND MASTER PASSWORD FLOW PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    try:
        test_encryption_decryption()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
