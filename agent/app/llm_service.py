"""OpenAI LLM service via LangChain (inference layer only)."""
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .config import get_settings
from .prompts import SYSTEM_PROMPT, build_user_prompt, build_user_prompt_doc_only

logger = logging.getLogger(__name__)


class LLMService:
    """Service for LLM interactions via LangChain ChatOpenAI."""

    def __init__(self):
        settings = get_settings()
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=0.1,  # Low temperature for factual accuracy
            max_tokens=2000,
            api_key=settings.openai_api_key,
        )
        self.model = settings.openai_model
        logger.info(f"LLM service initialized with model: {self.model}")

    def generate_answer(
        self,
        question: str,
        session_objects: list[dict],
        session_summary: dict,
        retrieved_chunks: list[dict],
        doc_only: bool = False,
    ) -> str:
        """Generate an answer using the LLM. If doc_only, prompt uses only question + chunks (no JSON/summary)."""
        if doc_only:
            user_prompt = build_user_prompt_doc_only(question=question, retrieved_chunks=retrieved_chunks)
        else:
            user_prompt = build_user_prompt(
                question=question,
                json_objects=session_objects,
                session_summary=session_summary,
                retrieved_chunks=retrieved_chunks,
            )
        logger.info(f"Generating answer for question: {question[:100]}...")
        logger.debug(f"User prompt length: {len(user_prompt)} chars")
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
        try:
            response = self.llm.invoke(messages)
            answer = response.content if hasattr(response, "content") else str(response)
            logger.info(f"Generated answer of {len(answer)} chars")
            return answer
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            raise

    async def generate_answer_stream_async(
        self,
        question: str,
        session_objects: list[dict],
        session_summary: dict,
        retrieved_chunks: list[dict],
        doc_only: bool = False,
    ):
        """
        Generate an answer with streaming (async). Yields content chunks as they arrive.
        If doc_only, prompt uses only question + chunks (no JSON/summary).
        """
        if doc_only:
            user_prompt = build_user_prompt_doc_only(question=question, retrieved_chunks=retrieved_chunks)
        else:
            user_prompt = build_user_prompt(
                question=question,
                json_objects=session_objects,
                session_summary=session_summary,
                retrieved_chunks=retrieved_chunks,
            )
        logger.info(f"Streaming answer for question: {question[:100]}...")
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
        try:
            async for chunk in self.llm.astream(messages):
                content = getattr(chunk, "content", None)
                if content:
                    yield content
        except Exception as e:
            logger.error(f"Error streaming answer: {e}")
            raise

    def is_available(self) -> bool:
        """Check if the LLM service is available."""
        settings = get_settings()
        return bool(settings.openai_api_key)
