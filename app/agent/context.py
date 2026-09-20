"""Context manager for the agent conversation loop."""
from typing import List, Dict, Any, Optional
from google.genai import types

class AgentContext:
    """Maintains message and tool call history for an agent execution session."""

    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt
        self.contents: List[types.Content] = []
        self.history: List[Dict[str, Any]] = []

    def add_user_message(self, text: str) -> None:
        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=text)]
        )
        self.contents.append(content)
        self.history.append({
            "role": "user",
            "content": text
        })

    def add_assistant_response(
        self,
        text: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        raw_content: Optional[types.Content] = None
    ) -> None:
        if raw_content:
            self.contents.append(raw_content)
        elif text:
            self.contents.append(
                types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=text)]
                )
            )

        entry: Dict[str, Any] = {"role": "assistant"}
        if text:
            entry["content"] = text
        if tool_calls:
            entry["tool_calls"] = tool_calls
        self.history.append(entry)

    def add_tool_result(self, tool_name: str, result: Dict[str, Any]) -> None:
        # Construct function response part for Gemini
        part = types.Part.from_function_response(
            name=tool_name,
            response={"result": result}
        )
        self.contents.append(
            types.Content(
                role="tool",
                parts=[part]
            )
        )
        self.history.append({
            "role": "tool",
            "name": tool_name,
            "result": result
        })

    def get_contents(self) -> List[types.Content]:
        return self.contents

