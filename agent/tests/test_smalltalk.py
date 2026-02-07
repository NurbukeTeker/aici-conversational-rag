"""Unit tests for small-talk detection and answer behavior.
Verify that greetings/pleasantries get a short response with no RAG and no evidence.
"""
import pytest
from unittest.mock import MagicMock, patch

from app.smalltalk import is_smalltalk, SMALLTALK_RESPONSE

# Optional: run endpoint tests only when app can be loaded (full deps available)
def _app_available():
    try:
        from app.main import app  # noqa: F401
        return True
    except Exception:
        return False


class TestSmalltalkDetector:
    """Test is_smalltalk() detection rules."""

    def test_hi_is_smalltalk(self):
        assert is_smalltalk("hi") is True
        assert is_smalltalk("Hi") is True
        assert is_smalltalk("  hi  ") is True

    def test_good_morning_is_smalltalk(self):
        assert is_smalltalk("good morning") is True
        assert is_smalltalk("Good Morning") is True
        assert is_smalltalk("good morning!") is True

    def test_hey_property_highway_not_smalltalk(self):
        """Greeting combined with domain question must NOT be treated as small talk."""
        assert is_smalltalk("hey, does this property front a highway?") is False

    def test_too_many_words_not_smalltalk(self):
        assert is_smalltalk("hi there how are you doing today") is False

    def test_domain_keyword_blocks_smalltalk(self):
        assert is_smalltalk("hi property") is False
        assert is_smalltalk("hello planning") is False
        assert is_smalltalk("thanks layer") is False

    def test_other_greetings(self):
        assert is_smalltalk("hello") is True
        assert is_smalltalk("hey") is True
        assert is_smalltalk("thanks") is True
        assert is_smalltalk("thank you") is True
        assert is_smalltalk("how are you") is True


@pytest.mark.skipif(not _app_available(), reason="App dependencies (e.g. pypdf) not installed")
class TestAnswerEndpointSmalltalk:
    """Test /answer returns small-talk response with empty evidence and no retrieval."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_hi_returns_smalltalk_response_and_empty_evidence(self, client):
        response = client.post(
            "/answer",
            json={"question": "hi", "session_objects": []},
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert data["answer"].strip() == SMALLTALK_RESPONSE.strip()
        assert "evidence" in data
        assert data["evidence"]["document_chunks"] == []
        assert data["evidence"].get("session_objects") is None

    def test_hi_retrieval_not_called(self, client):
        from app import main
        with patch.object(main.vector_store, "search", MagicMock()) as mock_search:
            client.post(
                "/answer",
                json={"question": "hi", "session_objects": []},
            )
            mock_search.assert_not_called()

    def test_good_morning_returns_smalltalk_and_empty_evidence(self, client):
        response = client.post(
            "/answer",
            json={"question": "good morning", "session_objects": []},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["answer"].strip() == SMALLTALK_RESPONSE.strip()
        assert data["evidence"]["document_chunks"] == []
        assert data["evidence"].get("session_objects") is None

    def test_hey_property_highway_uses_normal_rag(self, client):
        """Verify domain question is NOT treated as small talk (RAG path is used)."""
        from app import main
        with patch.object(main.vector_store, "search", MagicMock(return_value=[])) as mock_search:
            # Mock LLM so we don't call real API
            with patch.object(main.llm_service, "generate_answer", return_value="Some answer."):
                response = client.post(
                    "/answer",
                    json={
                        "question": "hey, does this property front a highway?",
                        "session_objects": [],
                    },
                )
                assert response.status_code == 200
                # Retrieval should have been called (normal RAG path)
                mock_search.assert_called_once()
                data = response.json()
                # Evidence structure present (may be empty if no chunks)
                assert "evidence" in data
                assert "document_chunks" in data["evidence"]
