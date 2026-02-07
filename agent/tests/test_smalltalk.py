"""Unit tests for small-talk detection and answer behavior.
Verify that greetings/pleasantries get a short response with no RAG and no evidence.
"""
import pytest
from unittest.mock import MagicMock, patch

from app.smalltalk import is_smalltalk, SMALLTALK_RESPONSE, get_smalltalk_response, THANKS_RESPONSE

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


class TestGetSmalltalkResponse:
    """Test get_smalltalk_response returns appropriate response per message type."""

    def test_hi_returns_greeting_response(self):
        assert get_smalltalk_response("hi") == SMALLTALK_RESPONSE
        assert get_smalltalk_response("good morning") == SMALLTALK_RESPONSE

    def test_thanks_returns_thanks_response(self):
        assert get_smalltalk_response("thanks") == THANKS_RESPONSE
        assert get_smalltalk_response("thank you") == THANKS_RESPONSE
        assert get_smalltalk_response("thx") == THANKS_RESPONSE


@pytest.mark.skipif(not _app_available(), reason="App dependencies (e.g. pypdf) not installed")
class TestAnswerEndpointSmalltalk:
    """Test /answer returns small-talk response with empty evidence and no retrieval."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app import main
        from app.main import app
        client = TestClient(app)
        # Trigger lifespan so vector_store, reasoning_service, answer_graph are set (CI may fail here)
        try:
            resp = client.get("/health")
            if resp.status_code != 200:
                pytest.skip("App not initialized (health returned %s)" % resp.status_code)
        except Exception as e:
            pytest.skip("App not initialized: %s" % e)
        # In CI lifespan may not set globals (e.g. ChromaDB fails); /answer would return 503
        if main.vector_store is None or main.reasoning_service is None:
            pytest.skip("App services not initialized in this environment")
        return client

    def test_hi_returns_smalltalk_response(self, client):
        response = client.post(
            "/answer",
            json={"question": "hi", "session_objects": []},
        )
        if response.status_code == 503:
            pytest.skip("App returned 503 (services not ready in this environment)")
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert data["answer"].strip() == SMALLTALK_RESPONSE.strip()

    def test_hi_retrieval_not_called(self, client):
        with patch("app.retrieval_lc.retrieve", MagicMock()) as mock_retrieve:
            client.post("/answer", json={"question": "hi", "session_objects": []})
            mock_retrieve.assert_not_called()

    def test_good_morning_returns_smalltalk(self, client):
        response = client.post(
            "/answer",
            json={"question": "good morning", "session_objects": []},
        )
        if response.status_code == 503:
            pytest.skip("App returned 503 (services not ready in this environment)")
        assert response.status_code == 200
        data = response.json()
        assert data["answer"].strip() == SMALLTALK_RESPONSE.strip()

    def test_hey_property_highway_uses_normal_rag(self, client):
        """Verify domain question is NOT treated as small talk (RAG path is used)."""
        with patch("app.retrieval_lc.retrieve", MagicMock(return_value=[])) as mock_retrieve:
            with patch("app.graph_lc.nodes.invoke_hybrid", return_value="Some answer."):
                response = client.post(
                    "/answer",
                    json={
                        "question": "hey, does this property front a highway?",
                        "session_objects": [],
                    },
                )
                if response.status_code == 503:
                    pytest.skip("Services not ready")
                assert response.status_code == 200
                mock_retrieve.assert_called_once()
                data = response.json()
                assert "answer" in data
