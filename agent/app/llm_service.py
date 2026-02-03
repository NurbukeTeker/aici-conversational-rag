"""OpenAI LLM service."""
import logging
from openai import OpenAI

from .config import get_settings
from .prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)


class LLMService:
    """Service for LLM interactions via OpenAI."""
    
    def __init__(self):
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        logger.info(f"LLM service initialized with model: {self.model}")
    
    def generate_answer(
        self,
        question: str,
        session_objects: list[dict],
        session_summary: dict,
        retrieved_chunks: list[dict]
    ) -> str:
        """Generate an answer using the LLM."""
        
        user_prompt = build_user_prompt(
            question=question,
            json_objects=session_objects,
            session_summary=session_summary,
            retrieved_chunks=retrieved_chunks
        )
        
        logger.info(f"Generating answer for question: {question[:100]}...")
        logger.debug(f"User prompt length: {len(user_prompt)} chars")
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,  # Low temperature for factual accuracy
                max_tokens=2000
            )
            
            answer = response.choices[0].message.content
            logger.info(f"Generated answer of {len(answer)} chars")
            
            return answer
            
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            raise
    
    def is_available(self) -> bool:
        """Check if the LLM service is available."""
        settings = get_settings()
        return bool(settings.openai_api_key)
