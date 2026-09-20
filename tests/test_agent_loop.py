"""Integration test running a real agent loop with Gemini API."""
import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.agent.loop import AgentLoop

async def test_live_agent():
    print("Testing live Gemini Agent loop with tool calling...")
    task_id = "test_live_agent_1"

    events = []
    async def on_event(ev):
        events.append(ev)
        ev_type = ev.get("type")
        if ev_type == "tool_call":
            print(f"  -> Tool Call: {ev.get('tool')}({ev.get('arguments')})")
        elif ev_type == "tool_result":
            print(f"  <- Tool Result: {ev.get('tool')} success={ev.get('success')}")
        elif ev_type == "terminal_output":
            print(f"  [Terminal] {ev.get('command')}: exit={ev.get('exit_code')}, stdout={repr(ev.get('stdout')[:60])}")
        elif ev_type == "agent_message":
            print(f"  [Agent Message] is_final={ev.get('is_final')}: {ev.get('content')[:80]}...")

    agent = AgentLoop(task_id=task_id, event_callback=on_event, max_steps=10)
    prompt = "Create a small Python script named hello.py that prints 'Hello from Web Agent', run it, and verify the output."

    result = await agent.run(prompt)
    print("\nResult:", result)
    assert result["success"]
    assert any(ev.get("type") == "tool_call" and ev.get("tool") == "write_file" for ev in events)
    assert any(ev.get("type") == "tool_call" and ev.get("tool") in ("run_python", "run_shell") for ev in events)
    print("\nLive Gemini agent loop verification PASSED! [SUCCESS]")

if __name__ == "__main__":
    asyncio.run(test_live_agent())

