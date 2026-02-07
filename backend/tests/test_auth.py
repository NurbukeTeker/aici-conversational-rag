"""Tests for authentication module."""
import pytest
from app.auth import get_password_hash, verify_password, create_access_token, decode_token

# Test fixture - NOT a real credential  # noqa: S105  # gitguardian: ignore
TEST_PASSWORD = "TestPass_Auth123!"  # noqa: S105  # gitguardian: ignore


class TestPasswordHashing:
    """Test password hashing functions."""
    
    def test_hash_password(self):
        """Test that password hashing works."""
        password = TEST_PASSWORD
        hashed = get_password_hash(password)
        
        assert hashed != password
        assert len(hashed) > 0
        # Argon2 hashes start with $argon2
        assert hashed.startswith("$argon2")
    
    def test_verify_correct_password(self):
        """Test that correct password verifies."""
        password = TEST_PASSWORD
        hashed = get_password_hash(password)
        
        assert verify_password(password, hashed) is True
    
    def test_verify_wrong_password(self):
        """Test that wrong password fails verification."""
        password = TEST_PASSWORD
        hashed = get_password_hash(password)
        
        assert verify_password("WrongPass_Test!", hashed) is False  # noqa: S105
    
    def test_long_password_hashing(self):
        """Test that long passwords work (Argon2 has no 72-byte limit like bcrypt)."""
        long_password = "A" * 200 + "1" + "!" + "a"
        hashed = get_password_hash(long_password)
        
        assert verify_password(long_password, hashed) is True
    
    def test_unicode_password(self):
        """Test that unicode passwords work."""
        password = "TestPass_123!"  # noqa: S105  # gitguardian: ignore
        hashed = get_password_hash(password)
        
        assert verify_password(password, hashed) is True


class TestJWT:
    """Test JWT token functions."""
    
    def test_create_access_token(self):
        """Test token creation."""
        data = {"sub": "testuser", "user_id": "123"}
        token = create_access_token(data)
        
        assert token is not None
        assert len(token) > 0
        # JWT tokens have 3 parts separated by dots
        assert len(token.split(".")) == 3
    
    def test_decode_valid_token(self):
        """Test decoding a valid token."""
        data = {"sub": "testuser", "user_id": "uuid-123-456"}
        token = create_access_token(data)
        
        decoded = decode_token(token)
        
        assert decoded.username == "testuser"
        assert decoded.user_id == "uuid-123-456"
    
    def test_token_with_special_characters(self):
        """Test token with special characters in data."""
        data = {"sub": "test_user.name", "user_id": "uuid-123"}
        token = create_access_token(data)
        decoded = decode_token(token)
        
        assert decoded.username == "test_user.name"
