# Web Agent v1

An autonomous coding agent powered by Google Gemini, FastAPI, WebSockets, and a responsive dark developer dashboard.

The agent works in an isolated workspace per task, executing iterative loops with real tool calling (file inspection, editing, Python execution, and shell commands).

---

## 1. Architecture Overview

```
Browser (Vanilla JS + Responsive Dark UI)
   │
   ├── REST API (Create / Cancel / Query Tasks)
   │
   └── WebSocket (/ws/tasks/{task_id})
          │
          ▼
      FastAPI (Uvicorn)
          │
          ▼
      Task Manager (Async worker queue + In-memory state + JSON persistence)
          │
          ▼
      Agent Loop (Iterative step loop up to MAX_AGENT_STEPS)
          │
          ├── AI Provider (Google Gemini API via google-genai)
          │
          └── Tool Registry (Safe isolated execution)
                  │
                  ├── File tools: list_files, read_file, write_file, edit_file
                  ├── Python execution: run_python (subprocess)
                  └── Shell execution: run_shell (subprocess)
```

### Key Behaviors
- **Iterative Decision Loop**: The model decides next actions dynamically. Tools are executed, results fed back to the context, and the model observes outputs and self-corrects until final completion.
- **Detached Lifecycle**: Background tasks run independently of browser connection. If a WebSocket disconnects, the task continues. When reconnected, current state and event stream are restored.
- **Workspace Isolation**: Each task operates in `data/workspaces/<task_id>/`. Path traversal attempts (e.g. `../../`) are strictly blocked.
- **Subprocess Safety**: Python and shell tools run in isolated subprocesses with execution timeouts, output truncation, and process tree termination on cancellation.

---

## 2. API Reference

### Health Check
- `GET /health`
  - Response: `{"status": "ok"}`

### REST API
- `POST /api/tasks`
  - Body: `{"prompt": "Create a FastAPI hello world project"}`
  - Response: `{"task_id": "a8f21c", "status": "queued"}`
- `GET /api/tasks`
  - Returns list of all task summaries.
- `GET /api/tasks/{task_id}`
  - Returns full task state, step count, final response, and recorded events.
- `POST /api/tasks/{task_id}/cancel`
  - Requests immediate task cancellation and kills running subprocesses.

### WebSocket
- `GET /ws/tasks/{task_id}`
  - Streams real-time JSON events:
    - `task_sync`: Initial payload restoring previous task state on connect/reconnect.
    - `task_status`: Status transitions (`running`, `completed`, `cancelled`, `failed`, `timeout`).
    - `agent_message`: Model reasoning and final response text.
    - `tool_call`: Tool invocation with arguments.
    - `tool_result`: Tool execution results.
    - `terminal_output`: Live command, stdout, stderr, exit code, and duration.
    - `file_created` / `file_updated`: File activity notifications.
    - `task_completed` / `task_cancelled` / `error`.

---

## 3. Tool System

| Tool | Parameters | Description |
|---|---|---|
| `list_files` | `path="."` | List directory contents within workspace. |
| `read_file` | `path` | Safely read file content within workspace. |
| `write_file` | `path`, `content` | Write content to a file; creates parent dirs. |
| `edit_file` | `path`, `old_text`, `new_text` | Replace exact substring in existing file. |
| `run_python` | `command` | Execute Python script inside workspace subprocess. |
| `run_shell` | `command` | Execute shell command inside workspace subprocess. |

---

## 4. Environment Variables

Configure via `.env` (use `.env.example` as a template):

```env
APP_ENV=production
HOST=127.0.0.1
PORT=8000

GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

MAX_CONCURRENT_TASKS=3
MAX_AGENT_STEPS=30
MAX_RUNTIME_SECONDS=600
MAX_TOOL_OUTPUT_BYTES=100000

WORKSPACE_ROOT=./data/workspaces
TASK_ROOT=./data/tasks
```

---

## 5. Local Setup & Development

1. **Clone repository**:
   ```bash
   git clone https://github.com/Saiky988/Agent.git
   cd Agent
   ```

2. **Create Python virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Or venv\Scripts\activate on Windows
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Setup environment**:
   ```bash
   cp .env.example .env
   # Add your GEMINI_API_KEY into .env
   ```

5. **Start server**:
   ```bash
   python main.py
   # Or: uvicorn app.main:app --reload --port 8000
   ```

6. Open `http://localhost:8000` in browser.

---

## 6. Production Deployment

### Production Architecture
```
User -> Cloudflare HTTPS (:443) -> Nginx Reverse Proxy (:80 / :443) -> Uvicorn (127.0.0.1:8000) -> FastAPI
```

### Nginx Configuration
```nginx
server {
    listen 80;
    listen 443 ssl;
    server_name agent.sayraa.xyz;

    ssl_certificate /etc/ssl/certs/agent-selfsigned.crt;
    ssl_certificate_key /etc/ssl/private/agent-selfsigned.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

### Systemd Service (`/etc/systemd/system/web-agent.service`)
```ini
[Unit]
Description=Web Agent v1 Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/var/www/web-agent
EnvironmentFile=/var/www/web-agent/.env
ExecStart=/var/www/web-agent/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## 7. Security Considerations

- **Path Traversal Protection**: All paths resolve strictly relative to the task's directory. Any attempt to use `../` outside the task workspace raises a `WorkspaceError`.
- **Environment Scrubbing**: Process execution scrubs sensitive environment variables (`GEMINI_API_KEY`, SSH credentials) so spawned commands cannot leak secrets.
- **Zero Secret Commits**: `.gitignore` strictly ignores `.env`, keys, credentials, task data, and logs.
- **Execution Limits**: Hard limits on command runtime, output size, and step counts protect against infinite loops and resource exhaustion.

---

## 8. Limitations & Future Roadmap

- **Containerization**: v1 isolates workspaces via filesystem paths and subprocess cwd; v2 can introduce rootless Docker or gVisor sandbox containers.
- **Persistence**: v1 uses JSON file storage for lightweight simplicity; future versions can add PostgreSQL for high-scale multi-user history.
- **Authentication**: v1 is built as a single-tenant internal developer tool; auth (OAuth2/JWT) can be layered as needed.

