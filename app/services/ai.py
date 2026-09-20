"""AI Service provider abstraction."""
import asyncio
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from app.config import settings

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
        Uses asyncio.to_thread to prevent blocking the event loop during network requests.
        """
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools or []
        )

        def _call_gemini():
            return self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config
            )

        response = await asyncio.to_thread(_call_gemini)

        # Extract tool calls and text
        tool_calls = []
        if response.function_calls:
            for fc in response.function_calls:
                tool_calls.append({
                    "name": fc.name,
                    "arguments": fc.args or {}
                })

        text = response.text if response.text else None
        
        # In case the candidate content has parts
        raw_content = None
        if response.candidates and response.candidates[0].content:
            raw_content = response.candidates[0].content

        return AIResponse(
            text=text,
            tool_calls=tool_calls,
            raw_content=raw_content
        )

ai_service = AIService()

