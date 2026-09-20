"""Iterative agent loop executing tool calling and reasoning."""
import asyncio
import logging
import time
from typing import Callable, Awaitable, Optional, Dict, Any

from app.config import settings
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.context import AgentContext
from app.services.ai import ai_service, AIService
from app.tools.registry import tool_registry

logger = logging.getLogger("web_agent.loop")

EventCallback = Callable[[Dict[str, Any]], Awaitable[None]]

class AgentLoop:
    """Orchestrates iterative LLM generation, tool execution, and event streaming."""

    def __init__(
        self,
        task_id: str,
        ai: Optional[AIService] = None,
        event_callback: Optional[EventCallback] = None,
        max_steps: int = settings.MAX_AGENT_STEPS,
        max_runtime_seconds: int = settings.MAX_RUNTIME_SECONDS
    ):
        self.task_id = task_id
        self.ai = ai or ai_service
        self.event_callback = event_callback
        self.max_steps = max_steps
        self.max_runtime_seconds = max_runtime_seconds
        self.context = AgentContext(system_prompt=SYSTEM_PROMPT)

    async def _emit(self, event: Dict[str, Any]) -> None:
        if self.event_callback:
            try:
                await self.event_callback(event)
            except Exception as e:
                logger.warning(f"Error emitting event for task {self.task_id}: {e}")

    async def run(self, prompt: str) -> Dict[str, Any]:
        """Executes the agent loop until completion, step limit, or timeout."""
        start_time = time.time()
        self.context.add_user_message(prompt)
        tools = [tool_registry.get_gemini_tools()]

        current_step = 0
        final_response_text = ""

        try:
            while current_step < self.max_steps:
                # Check overall task runtime limit
                elapsed = time.time() - start_time
                if elapsed > self.max_runtime_seconds:
                    raise TimeoutError(f"Task exceeded maximum runtime of {self.max_runtime_seconds} seconds")

                current_step += 1
                logger.info(f"Task {self.task_id} step {current_step}/{self.max_steps}")

                # Call AI
                try:
                    response = await self.ai.generate(
                        contents=self.context.get_contents(),
                        system_instruction=self.context.system_prompt,
                        tools=tools
                    )
                except Exception as e:
                    logger.error(f"AI generation failed on task {self.task_id}: {e}")
                    raise RuntimeError(f"AI generation error: {str(e)}")

                # Check if model made tool calls
                if response.has_tool_calls:
                    # Append assistant response containing tool calls to context
                    self.context.add_assistant_response(
                        text=response.text,
                        tool_calls=response.tool_calls,
                        raw_content=response.raw_content
                    )

                    # If model provided some thinking/text alongside tool calls, emit it
                    if response.text and response.text.strip():
                        await self._emit({
                            "type": "agent_message",
                            "content": response.text.strip(),
                            "step": current_step,
                            "is_final": False
                        })

                    # Execute each tool call
                    for tool_call in response.tool_calls:
                        tool_name = tool_call["name"]
                        args = tool_call["arguments"]

                        await self._emit({
                            "type": "tool_call",
                            "tool": tool_name,
                            "arguments": args,
                            "step": current_step
                        })

                        # Execute tool within workspace
                        tool_result = await tool_registry.execute_tool(
                            task_id=self.task_id,
                            tool_name=tool_name,
                            arguments=args
                        )

                        # Emit terminal output if python or shell
                        if tool_name in ("run_python", "run_shell"):
                            await self._emit({
                                "type": "terminal_output",
                                "tool": tool_name,
                                "command": args.get("command", ""),
                                "stdout": tool_result.get("stdout", ""),
                                "stderr": tool_result.get("stderr", ""),
                                "exit_code": tool_result.get("exit_code", 0),
                                "duration_ms": tool_result.get("duration_ms", 0),
                                "step": current_step
                            })

                        # Emit file events
                        if tool_name == "write_file" and tool_result.get("success"):
                            await self._emit({
                                "type": "file_created",
                                "path": args.get("path"),
                                "step": current_step
                            })
                        elif tool_name == "edit_file" and tool_result.get("success"):
                            await self._emit({
                                "type": "file_updated",
                                "path": args.get("path"),
                                "step": current_step
                            })

                        # Emit tool result
                        await self._emit({
                            "type": "tool_result",
                            "tool": tool_name,
                            "success": tool_result.get("success", True),
                            "result": tool_result,
                            "step": current_step
                        })

                        # Feed result back into model context
                        self.context.add_tool_result(tool_name, tool_result)

                    # Continue loop to allow model to see tool output and take next step
                    continue

                # Model returned a response without tool calls -> Task complete!
                final_response_text = response.text or "Task completed."
                self.context.add_assistant_response(
                    text=final_response_text,
                    raw_content=response.raw_content
                )

                await self._emit({
                    "type": "agent_message",
                    "content": final_response_text,
                    "step": current_step,
                    "is_final": True
                })
                break

            else:
                # Step limit reached
                final_response_text = f"Task stopped: reached maximum step limit ({self.max_steps})."
                await self._emit({
                    "type": "agent_message",
                    "content": final_response_text,
                    "step": current_step,
                    "is_final": True
                })

            return {
                "success": True,
                "steps": current_step,
                "final_response": final_response_text,
                "duration_seconds": round(time.time() - start_time, 2)
            }

        except asyncio.CancelledError:
            logger.info(f"Task {self.task_id} was cancelled.")
            await self._emit({
                "type": "task_cancelled",
                "task_id": self.task_id,
                "message": "Task execution cancelled by user."
            })
            raise

        except TimeoutError as e:
            logger.warning(f"Task {self.task_id} timed out: {e}")
            await self._emit({
                "type": "error",
                "error": str(e),
                "step": current_step
            })
            raise

        except Exception as e:
            logger.error(f"Task {self.task_id} failed with error: {e}", exc_info=True)
            await self._emit({
                "type": "error",
                "error": str(e),
                "step": current_step
            })
            raise

