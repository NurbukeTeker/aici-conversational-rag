"""Tests for Pydantic models."""
import pytest
from app.models import UserRegister, SessionObjects, QARequest

# Test fixture - NOT a real credential  # noqa: S105  # gitguardian: ignore
TEST_PASSWORD = "testpass123"  # noqa: S105  # gitguardian: ignore


class TestUserModels:
    """Test user-related models."""
    
    def test_user_register_valid(self):
        """Test valid user registration."""
        user = UserRegister(
            username="testuser",
            email="test@example.com",
            password=TEST_PASSWORD
        )
        
        assert user.username == "testuser"
        assert user.email == "test@example.com"
    
    def test_user_register_short_username(self):
        """Test that short username fails validation."""
        with pytest.raises(ValueError):
            UserRegister(
                username="ab",  # Too short (min 3)
                email="test@example.com",
                password=TEST_PASSWORD
            )
    
    def test_user_register_short_password(self):
        """Test that short password fails validation."""
        with pytest.raises(ValueError):
            UserRegister(
                username="testuser",
                email="test@example.com",
                password="12345"  # noqa: S105 - intentionally short for test
            )


class TestSessionModels:
    """Test session-related models."""
    
    def test_session_objects_empty(self):
        """Test empty session objects."""
        session = SessionObjects(objects=[])
        
        assert session.objects == []
    
    def test_session_objects_with_data(self):
        """Test session objects with data."""
        objects = [
            {"layer": "Highway", "type": "line"},
            {"layer": "Walls", "type": "polygon"}
        ]
        session = SessionObjects(objects=objects)
        
        assert len(session.objects) == 2
        assert session.objects[0].layer == "Highway"


class TestQAModels:
    """Test Q&A models."""
    
    def test_qa_request_valid(self):
        """Test valid QA request."""
        qa = QARequest(question="Does this front a highway?")
        
        assert qa.question == "Does this front a highway?"
    
    def test_qa_request_empty_question(self):
        """Test that empty question fails."""
        with pytest.raises(ValueError):
            QARequest(question="")
