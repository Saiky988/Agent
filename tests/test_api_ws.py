"""Test FastAPI REST and WebSocket endpoints."""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app

def test_endpoints():
    client = TestClient(app)
    
    # 1. Test health
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
    print("  [OK] /health returned 200 ok")

    # 2. Test create task
    res = client.post("/api/tasks", json={"prompt": "Test hello world task"})
    assert res.status_code == 201
    data = res.json()
    task_id = data["task_id"]
    assert task_id
    assert data["status"] == "queued"
    print(f"  [OK] POST /api/tasks created task {task_id}")

    # 3. Test list tasks
    res = client.get("/api/tasks")
    assert res.status_code == 200
    assert any(t["task_id"] == task_id for t in res.json()["tasks"])
    print("  [OK] GET /api/tasks includes new task")

    # 4. Test WebSocket connect & sync
    with client.websocket_connect(f"/ws/tasks/{task_id}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "task_sync"
        assert msg["task_id"] == task_id
        print("  [OK] WebSocket connected and received initial task_sync event")

    # 5. Test cancel
    res = client.post(f"/api/tasks/{task_id}/cancel")
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"
    print(f"  [OK] POST /api/tasks/{task_id}/cancel succeeded")

    print("\nAPI and WebSocket integration test PASSED! [SUCCESS]")

if __name__ == "__main__":
    test_endpoints()

