"""AI Service provider abstraction with automatic retry and model fallback."""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from app.config import settings

logger = logging.getLogger("web_agent.ai")

# Fallback models in priority order if the primary model suffers high demand (503) or rate limits (429)
FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]

class AIResponse:
    """Standardized AI response across providers."""
    def __init__(
        self,
        text: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        raw_content: Any = None
    ):
        self.text = text
        self.tool_calls = tool_calls or []
        self.raw_content = raw_content

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

class AIService:
    """Provider-agnostic interface for generating AI completions."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        self._client: Optional[genai.Client] = None
        if self.api_key:
            self._client = genai.Client(api_key=self.api_key)

    @property
    def client(self) -> genai.Client:
        if not self._client:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def generate(
        self,
        contents: List[types.Content],
        system_instruction: Optional[str] = None,
        tools: Optional[List[types.Tool]] = None
    ) -> AIResponse:
        """
        Sends contents to the Gemini model and returns a standardized AIResponse.
        Includes automatic retry and fallback to secondary models if Google experiences high demand (503) or rate limit (429).
        """
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools or []
        )

        candidate_models = [self.model]
        for fb in FALLBACK_MODELS:
            if fb != self.model:
                candidate_models.append(fb)

        last_error = None

        for model_to_try in candidate_models:
            for attempt in range(2):
                try:
                    def _call():
                        return self.client.models.generate_content(
                            model=model_to_try,
                            contents=contents,
                            config=config
                        )

                    response = await asyncio.to_thread(_call)

                    # Extract tool calls and text
                    tool_calls = []
                    if response.function_calls:
                        for fc in response.function_calls:
                            tool_calls.append({
                                "name": fc.name,
                                "arguments": fc.args or {}
                            })

                    text = response.text if response.text else None
                    
                    raw_content = None
                    if response.candidates and response.candidates[0].content:
                        raw_content = response.candidates[0].content

                    return AIResponse(
                        text=text,
                        tool_calls=tool_calls,
                        raw_content=raw_content
                    )

                except Exception as e:
                    err_str = str(e)
                    last_error = e
                    if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        logger.warning(
                            f"Model {model_to_try} returned high demand/quota error (attempt {attempt + 1}/2): {e}. Retrying/falling back..."
                        )
                        await asyncio.sleep(1.5)
                        continue
                    else:
                        raise e

            logger.info(f"Switching to fallback model after {model_to_try} was unavailable/rate limited...")

        raise last_error or RuntimeError("All AI models failed to respond")

ai_service = AIService()
