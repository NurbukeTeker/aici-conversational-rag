"""Tests for LangChain + LangGraph /answer and /answer/stream endpoints."""
import json
import pytest
from unittest.mock import MagicMock, patch

from app.smalltalk import SMALLTALK_RESPONSE


def _app_available():
    try:
        from app.main import app  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _app_available(), reason="App dependencies not installed")
class TestAnswerEndpoints:
    """Test /answer and /answer/stream (LangChain + LangGraph primary)."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_smalltalk_returns_smalltalk_response_no_retrieval_llm(self, client):
        """Test 1: smalltalk -> returns SMALLTALK_RESPONSE, no retrieval/LLM."""
        with patch("app.retrieval_lc.retrieve", MagicMock(return_value=[])) as mock_retrieve:
            with patch("app.lc.chains.invoke_doc_only", MagicMock(return_value="")) as mock_llm:
                with patch("app.lc.chains.invoke_hybrid", MagicMock(return_value="")):
                    resp = client.post(
                        "/answer",
                        json={"question": "hi", "session_objects": []},
                    )
        if resp.status_code == 503:
            pytest.skip("Services not initialized in this environment")
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"].strip() == SMALLTALK_RESPONSE.strip()
        mock_retrieve.assert_not_called()
        mock_llm.assert_not_called()

    def test_missing_geometry_returns_deterministic_guard_message(self, client):
        """Test 2: missing geometry -> returns deterministic guard message."""
        with patch("app.retrieval_lc.retrieve", MagicMock(return_value=[])):
            with patch("app.lc.chains.invoke_hybrid", MagicMock(return_value="Yes.")):
                session_objects = [
                    {"layer": "Highway", "geometry": None, "type": "line"},
                    {"layer": "Plot Boundary", "geometry": None, "type": "polygon"},
                ]
                resp = client.post(
                    "/answer",
                    json={
                        "question": "Does this property front a highway?",
                        "session_objects": session_objects,
                    },
                )
        if resp.status_code == 503:
            pytest.skip("Services not initialized in this environment")
        assert resp.status_code == 200
        data = resp.json()
        answer = data["answer"]
        assert "Cannot determine" in answer or "geometric information" in answer
        assert "Highway" in answer or "Plot Boundary" in answer

    def test_followup_what_it_needs_returns_checklist(self, client):
        """Test 3: followup 'what it needs?' returns deterministic checklist."""
        with patch("app.retrieval_lc.retrieve", MagicMock(return_value=[])) as mock_retrieve:
            session_objects = [
                {"layer": "Highway", "geometry": None},
                {"layer": "Plot Boundary", "geometry": None},
            ]
            resp = client.post(
                "/answer",
                json={"question": "what it needs?", "session_objects": session_objects},
            )
        if resp.status_code == 503:
            pytest.skip("Services not initialized in this environment")
        assert resp.status_code == 200
        data = resp.json()
        assert "Highway" in data["answer"] or "Plot Boundary" in data["answer"]
        mock_retrieve.assert_not_called()

    def test_doc_only_uses_doc_only_chain(self, client):
        """Test 4: doc-only definition question -> doc_only chain."""
        mock_chunks = [
            {"id": "chunk_1", "source": "doc", "page": "1", "section": "A", "text": "A highway is a public road.", "distance": 0.1}
        ]
        with patch("app.retrieval_lc.retrieve", MagicMock(return_value=mock_chunks)):
            with patch("app.lc.chains.invoke_doc_only", MagicMock(return_value="A highway is...")) as mock_doc:
                with patch("app.lc.chains.invoke_hybrid", MagicMock(return_value="Hybrid answer.")):
                    resp = client.post(
                        "/answer",
                        json={
                            "question": "What is a highway?",
                            "session_objects": [{"layer": "Highway", "geometry": None}],
                        },
                    )
        if resp.status_code == 503:
            pytest.skip("Services not initialized in this environment")
        assert resp.status_code == 200
        data = resp.json()
        assert "highway" in (data.get("answer") or "").lower()
        mock_doc.assert_called_once()

    def test_doc_only_empty_retrieval_returns_override_message(self, client):
        """DOC_ONLY with no retrieved docs: answer is override message."""
        with patch("app.retrieval_lc.retrieve", MagicMock(return_value=[])):
            with patch("app.lc.chains.invoke_hybrid", MagicMock(return_value="Hybrid.")):
                resp = client.post(
                    "/answer",
                    json={"question": "what is definition of highway?", "session_objects": []},
                )
        if resp.status_code == 503:
            pytest.skip("Services not initialized in this environment")
        assert resp.status_code == 200
        data = resp.json()
        answer = data.get("answer", "")
        assert "No explicit definition was found" in answer
        assert "retrieved documents" in answer or "retrieved" in answer.lower()

    def test_hybrid_returns_answer(self, client):
        """Test 5: hybrid question -> retriever + hybrid chain."""
        mock_chunks = [
            {"id": "chunk_1", "source": "doc", "page": "1", "section": "A", "text": "Planning rules.", "distance": 0.1}
        ]
        with patch("app.retrieval_lc.retrieve", MagicMock(return_value=mock_chunks)) as mock_retrieve:
            with patch("app.lc.chains.invoke_hybrid", MagicMock(return_value="The extension complies.")):
                session_objects = [
                    {"layer": "Extension", "geometry": {"coordinates": [[0, 0], [1, 0], [1, 1]]}, "properties": {"name": "Ext1"}},
                    {"layer": "Plot Boundary", "geometry": {"coordinates": [[0, 0], [10, 0]]}},
                ]
                resp = client.post(
                    "/answer",
                    json={
                        "question": "Does the extension comply with regulations?",
                        "session_objects": session_objects,
                    },
                )
        if resp.status_code == 503:
            pytest.skip("Services not initialized in this environment")
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "The extension complies."
        mock_retrieve.assert_called_once()

    def test_json_only_question_returns_answer(self, client):
        """JSON-only (e.g. how many layers) returns answer, no retrieval."""
        with patch("app.retrieval_lc.retrieve", MagicMock(return_value=[])) as mock_retrieve:
            with patch("app.lc.chains.invoke_hybrid", MagicMock(return_value="There are 3 layers.")):
                session_objects = [
                    {"layer": "Highway", "geometry": None},
                    {"layer": "Plot Boundary", "geometry": None},
                    {"layer": "Walls", "geometry": None},
                ]
                resp = client.post(
                    "/answer",
                    json={
                        "question": "How many drawing layers are in the current session?",
                        "session_objects": session_objects,
                    },
                )
        if resp.status_code == 503:
            pytest.skip("Services not initialized in this environment")
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        mock_retrieve.assert_not_called()

    def test_answer_stream_streams_chunks_and_ends_with_done(self, client):
        """Test 6: /answer/stream streams chunks and ends with done payload (schema)."""
        with patch("app.retrieval_lc.retrieve", MagicMock(return_value=[
            {"id": "c1", "source": "doc", "page": "1", "section": "A", "text": "A highway is a road.", "distance": 0.1}
        ])):
            with patch("app.main.astream_doc_only") as mock_astream:
                async def _stream(*args, **kwargs):
                    for token in ["A ", "highway ", "is ", "a road."]:
                        yield token
                mock_astream.return_value = _stream()
                # TestClient does not support async streaming response iteration in same way; we get response
                resp = client.post(
                    "/answer/stream",
                    json={"question": "What is a highway?", "session_objects": []},
                )
        if resp.status_code == 503:
            pytest.skip("Services not initialized in this environment")
        assert resp.status_code == 200
        lines = [line.strip() for line in resp.text.strip().split("\n") if line.strip()]
        assert len(lines) >= 1
        # Last line must be done payload
        last = json.loads(lines[-1])
        assert last.get("t") == "done"
        assert "answer" in last
        assert "session_summary" in last


class TestGraphLcNodes:
    """Unit tests for graph_lc node logic."""

    def test_smalltalk_node_sets_guard_result(self):
        try:
            from app.graph_lc.nodes import smalltalk_node
        except ImportError as e:
            pytest.skip(f"LangGraph not installed: {e}")

        state = {"question": "hi", "session_objects": []}
        out = smalltalk_node(state)
        assert out.get("guard_result") is not None
        assert out["guard_result"].get("type") == "smalltalk"

    def test_smalltalk_node_no_guard_for_domain_question(self):
        try:
            from app.graph_lc.nodes import smalltalk_node
        except ImportError as e:
            pytest.skip(f"LangGraph not installed: {e}")

        state = {"question": "Does this property front a highway?", "session_objects": []}
        out = smalltalk_node(state)
        assert out.get("guard_result") is None

    def test_geometry_guard_node_sets_guard_for_missing_layers(self):
        try:
            from app.graph_lc.nodes import geometry_guard_node
        except ImportError as e:
            pytest.skip(f"LangGraph not installed: {e}")

        state = {
            "question": "Does this property front a highway?",
            "session_objects": [
                {"layer": "Highway", "geometry": None},
                {"layer": "Plot Boundary", "geometry": None},
            ],
        }
        out = geometry_guard_node(state)
        assert out.get("guard_result") is not None
        assert out["guard_result"].get("type") == "missing_geometry"
        assert "Highway" in out["guard_result"].get("missing_layers", [])
        assert "Plot Boundary" in out["guard_result"].get("missing_layers", [])
