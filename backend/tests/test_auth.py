"""Tests for authentication module."""
import pytest
from app.auth import get_password_hash, verify_password, create_access_token, decode_token


class TestPasswordHashing:
    """Test password hashing functions."""
    
    def test_hash_password(self):
        """Test that password hashing works."""
        password = "testpassword123"
        hashed = get_password_hash(password)
        
        assert hashed != password
        assert len(hashed) > 0
    
    def test_verify_correct_password(self):
        """Test that correct password verifies."""
        password = "testpassword123"
        hashed = get_password_hash(password)
        
        assert verify_password(password, hashed) is True
    
    def test_verify_wrong_password(self):
        """Test that wrong password fails verification."""
        password = "testpassword123"
        hashed = get_password_hash(password)
        
        assert verify_password("wrongpassword", hashed) is False


class TestJWT:
    """Test JWT token functions."""
    
    def test_create_access_token(self):
        """Test token creation."""
        data = {"sub": "testuser", "user_id": "123"}
        token = create_access_token(data)
        
        assert token is not None
        assert len(token) > 0
    
    def test_decode_valid_token(self):
        """Test decoding a valid token."""
        data = {"sub": "testuser", "user_id": "123"}
        token = create_access_token(data)
        
        decoded = decode_token(token)
        
        assert decoded.username == "testuser"
        assert decoded.user_id == "123"
