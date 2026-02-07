"""
Acceptance tests: routing, retrieval, and answer behavior.

1) JSON_ONLY: no retrieval
2) DOC_ONLY: retrieval called, answer from docs
3) HYBRID (missing geometry): guard message
"""
import pytest
from unittest.mock import MagicMock, patch


def _app_available():
    try:
        from app.main import app  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _app_available(), reason="App dependencies not installed")
class TestAcceptanceJsonOnly:
    """JSON_ONLY: retrieval NOT called."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_how_many_layers_json_only_no_retrieval(self, client):
        """Q: How many drawing layers present? -> JSON_ONLY, no retrieval."""
        with patch("app.retrieval_lc.retrieve", MagicMock(return_value=[])) as mock_retrieve:
            with patch("app.graph_lc.nodes.invoke_hybrid", MagicMock(return_value="There are 5 layers.")):
                session_objects = [
                    {"layer": "Highway", "type": "line"},
                    {"layer": "Plot Boundary", "type": "polygon"},
                ]
                resp = client.post(
                    "/answer",
                    json={"question": "How many drawing layers are present?", "session_objects": session_objects},
                )
        if resp.status_code == 503:
            pytest.skip("Services not initialized")
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        mock_retrieve.assert_not_called()


@pytest.mark.skipif(not _app_available(), reason="App dependencies not installed")
class TestAcceptanceDocOnly:
    """DOC_ONLY: retrieval called, answer from docs."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_definition_of_highway_retrieval_called(self, client):
        """Q: What is the definition of a highway? -> DOC_ONLY, retrieval called."""
        highway_chunk = {
            "id": "doc_001_1_0001",
            "source": "Permitted Development.pdf",
            "page": "1",
            "section": "Interpretation",
            "text": "Highway – is a public right of way.",
            "distance": 0.1,
        }
        with patch("app.retrieval_lc.retrieve", MagicMock(return_value=[highway_chunk])) as mock_retrieve:
            with patch("app.graph_lc.nodes.invoke_doc_only", MagicMock(return_value="A highway is a public right of way.")):
                resp = client.post(
                    "/answer",
                    json={"question": "What is the definition of a highway?", "session_objects": []},
                )
        if resp.status_code == 503:
            pytest.skip("Services not initialized")
        assert resp.status_code == 200
        mock_retrieve.assert_called_once()

    def test_definition_no_chunks_override_message(self, client):
        """When no chunks retrieved: answer says no definition found."""
        with patch("app.retrieval_lc.retrieve", MagicMock(return_value=[])):
            resp = client.post(
                "/answer",
                json={"question": "What is the definition of a highway?", "session_objects": []},
            )
        if resp.status_code == 503:
            pytest.skip("Services not initialized")
        assert resp.status_code == 200
        data = resp.json()
        assert "No explicit definition was found" in data["answer"]


@pytest.mark.skipif(not _app_available(), reason="App dependencies not installed")
class TestAcceptanceHybridMissingGeometry:
    """HYBRID with missing geometry: deterministic guard."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_front_highway_missing_geometry_guard(self, client):
        """Q: Does this property front a highway? (missing geometry) -> guard message."""
        with patch("app.retrieval_lc.retrieve", MagicMock(return_value=[])):
            session_objects = [
                {"layer": "Highway", "geometry": None, "type": "line"},
                {"layer": "Plot Boundary", "geometry": None, "type": "polygon"},
            ]
            resp = client.post(
                "/answer",
                json={"question": "Does this property front a highway?", "session_objects": session_objects},
            )
        if resp.status_code == 503:
            pytest.skip("Services not initialized")
        assert resp.status_code == 200
        data = resp.json()
        assert "Cannot determine" in data["answer"] or "geometric information" in data["answer"]
