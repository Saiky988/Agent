/**
 * Web Agent v1 - Frontend Application
 */

const state = {
  tasks: [],
  activeTaskId: null,
  socket: null,
  connected: false,
  activeMobileTab: 'agent-view',
  step: 0,
  isNearBottomActivity: true,
  isNearBottomTerminal: true,
  renderedEventIds: new Set()
};

// DOM Elements
const elements = {
  connDot: document.getElementById('conn-dot'),
  connText: document.getElementById('conn-text'),
  taskIndicator: document.getElementById('task-indicator'),
  headerTaskId: document.getElementById('header-task-id'),
  headerTaskStatus: document.getElementById('header-task-status'),
  taskList: document.getElementById('task-list'),
  taskListEmpty: document.getElementById('task-list-empty'),
  btnNewTask: document.getElementById('btn-new-task'),
  activityScroll: document.getElementById('activity-scroll'),
  messagesContainer: document.getElementById('messages-container'),
  emptyState: document.getElementById('empty-state'),
  stepCounter: document.getElementById('step-counter'),
  terminalBody: document.getElementById('terminal-body'),
  terminalStream: document.getElementById('terminal-stream'),
  terminalPlaceholder: document.getElementById('terminal-placeholder'),
  btnClearTerminal: document.getElementById('btn-clear-terminal'),
  composerInput: document.getElementById('composer-input'),
  btnSend: document.getElementById('btn-send-task'),
  btnStop: document.getElementById('btn-stop-task'),
  mobileTabs: document.getElementById('mobile-tabs'),
  tasksSidebar: document.getElementById('tasks-sidebar'),
  mobileTasksToggle: document.getElementById('mobile-tasks-toggle'),
  agentView: document.getElementById('agent-view'),
  terminalView: document.getElementById('terminal-view')
};

// ======================== API Functions ======================== //

async function apiFetchTasks() {
  try {
    const res = await fetch('/api/tasks');
    if (!res.ok) throw new Error('Failed to fetch tasks');
    const data = await res.json();
    state.tasks = data.tasks || [];
    renderTaskList();
  } catch (err) {
    console.error('apiFetchTasks error:', err);
  }
}

async function apiCreateTask(prompt) {
  try {
    setComposerLoading(true);
    const res = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt })
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || 'Failed to create task');
    }
    const data = await res.json();
    await apiFetchTasks();
    await selectTask(data.task_id);
  } catch (err) {
    alert(`Error creating task: ${err.message}`);
  } finally {
    setComposerLoading(false);
  }
}

async function apiCancelTask(taskId) {
  if (!taskId) return;
  try {
    elements.btnStop.disabled = true;
    const res = await fetch(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to cancel task');
  } catch (err) {
    console.error('apiCancelTask error:', err);
  }
}

async function apiGetTask(taskId) {
  const res = await fetch(`/api/tasks/${taskId}`);
  if (!res.ok) throw new Error(`Task ${taskId} not found`);
  return await res.json();
}

// ======================== WebSocket ======================== //

function connectWebSocket(taskId) {
  if (state.socket) {
    state.socket.close();
    state.socket = null;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/tasks/${taskId}`;
  
  updateConnectionStatus('connecting');

  const ws = new WebSocket(wsUrl);
  state.socket = ws;

  ws.onopen = () => {
    if (state.socket === ws) {
      state.connected = true;
      updateConnectionStatus('connected');
    }
  };

  ws.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data);
      handleWebSocketEvent(event);
    } catch (err) {
      console.error('Error parsing WS message:', err);
    }
  };

  ws.onclose = () => {
    if (state.socket === ws) {
      state.connected = false;
      updateConnectionStatus('disconnected');
    }
  };

  ws.onerror = (err) => {
    console.warn('WebSocket error:', err);
    updateConnectionStatus('disconnected');
  };
}

function updateConnectionStatus(status) {
  elements.connDot.className = `status-dot ${status}`;
  if (status === 'connected') {
    elements.connText.textContent = 'Connected';
  } else if (status === 'connecting') {
    elements.connText.textContent = 'Connecting...';
  } else {
    elements.connText.textContent = 'Disconnected';
  }
}

function handleWebSocketEvent(event) {
  const type = event.type;

  if (type === 'task_sync') {
    // Initial task hydration
    updateTaskHeader(event.task_id, event.status);
    updateStepCounter(event.current_step || 0);
    clearActivity();
    clearTerminal();

    if (event.prompt) {
      renderUserMessage(event.prompt);
    }

    if (event.events && Array.isArray(event.events)) {
      for (const ev of event.events) {
        processSingleEvent(ev);
      }
    }

    if (event.status === 'running') {
      elements.btnStop.style.display = 'inline-flex';
      elements.btnStop.disabled = false;
    } else {
      elements.btnStop.style.display = 'none';
    }
    return;
  }

  processSingleEvent(event);
}

function processSingleEvent(event) {
  const type = event.type;

  if (event.step !== undefined) {
    updateStepCounter(event.step);
  }

  switch (type) {
    case 'task_status':
      updateTaskHeader(state.activeTaskId, event.status);
      if (event.status === 'running') {
        elements.btnStop.style.display = 'inline-flex';
        elements.btnStop.disabled = false;
      } else {
        elements.btnStop.style.display = 'none';
      }
      apiFetchTasks();
      break;

    case 'agent_message':
      renderAgentMessage(event.content, event.is_final);
      break;

    case 'tool_call':
      renderToolCall(event.tool, event.arguments, event.step);
      break;

    case 'tool_result':
      updateToolResult(event.tool, event.success, event.result, event.step);
      break;

    case 'terminal_output':
      renderTerminalOutput(event);
      break;

    case 'file_created':
      renderFileNotification('Created', event.path);
      break;

    case 'file_updated':
      renderFileNotification('Updated', event.path);
      break;

    case 'task_completed':
      updateTaskHeader(state.activeTaskId, 'completed');
      elements.btnStop.style.display = 'none';
      apiFetchTasks();
      break;

    case 'task_cancelled':
      updateTaskHeader(state.activeTaskId, 'cancelled');
      elements.btnStop.style.display = 'none';
      renderFileNotification('Cancelled', 'Task was stopped by user');
      apiFetchTasks();
      break;

    case 'error':
      renderErrorNotification(event.error);
      break;
  }
}

// ======================== Rendering ======================== //

function renderTaskList() {
  elements.taskList.innerHTML = '';
  if (state.tasks.length === 0) {
    elements.taskListEmpty.style.display = 'block';
    return;
  }
  elements.taskListEmpty.style.display = 'none';

  state.tasks.forEach((t) => {
    const item = document.createElement('div');
    item.className = `task-item ${t.task_id === state.activeTaskId ? 'active' : ''}`;
    item.onclick = () => {
      selectTask(t.task_id);
      if (window.innerWidth <= 768) {
        elements.tasksSidebar.classList.remove('open');
      }
    };

    item.innerHTML = `
      <div class="task-item-top">
        <span class="task-item-id">#${t.task_id}</span>
        <span class="status-pill status-${t.status}">${t.status}</span>
      </div>
      <div class="task-item-prompt" title="${escapeHtml(t.user_prompt)}">${escapeHtml(t.user_prompt)}</div>
    `;
    elements.taskList.appendChild(item);
  });
}

function updateTaskHeader(taskId, status) {
  if (!taskId) {
    elements.taskIndicator.style.display = 'none';
    return;
  }
  elements.taskIndicator.style.display = 'flex';
  elements.headerTaskId.textContent = `#${taskId}`;
  elements.headerTaskStatus.className = `status-pill status-${status}`;
  elements.headerTaskStatus.textContent = status;
}

function updateStepCounter(step) {
  state.step = step;
  elements.stepCounter.textContent = `Step: ${step}`;
}

function clearActivity() {
  elements.messagesContainer.innerHTML = '';
  elements.emptyState.style.display = 'none';
}

function renderUserMessage(text) {
  elements.emptyState.style.display = 'none';
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble user-message';
  bubble.innerHTML = `
    <div class="message-title">User Prompt</div>
    <div class="agent-message-content">${escapeHtml(text)}</div>
  `;
  elements.messagesContainer.appendChild(bubble);
  scrollActivityToBottom();
}

function renderAgentMessage(content, isFinal) {
  elements.emptyState.style.display = 'none';
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble agent-message';
  bubble.innerHTML = `
    <div class="message-title">${isFinal ? 'Final Answer' : 'Agent Thought'}</div>
    <div class="agent-message-content">${escapeHtml(content)}</div>
  `;
  elements.messagesContainer.appendChild(bubble);
  scrollActivityToBottom();
}

function renderToolCall(toolName, args, step) {
  elements.emptyState.style.display = 'none';
  const card = document.createElement('div');
  card.className = 'tool-card';
  card.id = `tool-step-${step}-${toolName}`;

  card.innerHTML = `
    <div class="tool-card-header" onclick="toggleToolCard(this)">
      <div class="tool-card-title">
        <span class="tool-badge">⚙ ${escapeHtml(toolName)}</span>
        <span>${escapeHtml(formatToolTitle(toolName, args))}</span>
      </div>
      <span style="font-size: 10px; color: var(--text-dim);">▼</span>
    </div>
    <div class="tool-card-args">${escapeHtml(JSON.stringify(args, null, 2))}</div>
    <div class="tool-card-result">Executing...</div>
  `;

  elements.messagesContainer.appendChild(card);
  scrollActivityToBottom();
}

function updateToolResult(toolName, success, result, step) {
  const card = document.getElementById(`tool-step-${step}-${toolName}`);
  if (!card) return;

  const resultDiv = card.querySelector('.tool-card-result');
  if (resultDiv) {
    resultDiv.className = `tool-card-result ${success ? 'success' : 'error'}`;
    resultDiv.textContent = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
  }
}

function formatToolTitle(toolName, args) {
  if (toolName === 'run_python' || toolName === 'run_shell') {
    return args.command || '';
  }
  if (toolName === 'read_file' || toolName === 'write_file' || toolName === 'edit_file') {
    return args.path || '';
  }
  if (toolName === 'list_files') {
    return args.path || '.';
  }
  return '';
}

function toggleToolCard(header) {
  const card = header.parentElement;
  const args = card.querySelector('.tool-card-args');
  const res = card.querySelector('.tool-card-result');
  const isHidden = args.style.display === 'none';
  args.style.display = isHidden ? 'block' : 'none';
  res.style.display = isHidden ? 'block' : 'none';
}

function renderFileNotification(action, path) {
  const note = document.createElement('div');
  note.style.margin = '4px 0';
  note.innerHTML = `
    <span class="file-event-badge">📄 ${action}: <strong>${escapeHtml(path)}</strong></span>
  `;
  elements.messagesContainer.appendChild(note);
  scrollActivityToBottom();
}

function renderErrorNotification(err) {
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.style.borderLeft = '3px solid var(--color-danger)';
  bubble.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
  bubble.innerHTML = `
    <div class="message-title" style="color: var(--color-danger);">Error</div>
    <div class="agent-message-content">${escapeHtml(err)}</div>
  `;
  elements.messagesContainer.appendChild(bubble);
  scrollActivityToBottom();
}

// ======================== Terminal ======================== //

function renderTerminalOutput(event) {
  elements.terminalPlaceholder.style.display = 'none';

  const entry = document.createElement('div');
  entry.className = 'terminal-entry';

  let html = `<div class="terminal-cmd">${escapeHtml(event.command || event.tool)}</div>`;
  if (event.stdout) {
    html += `<div class="terminal-stdout">${escapeHtml(event.stdout)}</div>`;
  }
  if (event.stderr) {
    html += `<div class="terminal-stderr">${escapeHtml(event.stderr)}</div>`;
  }
  html += `<div class="terminal-meta">Exit code: ${event.exit_code} | Duration: ${event.duration_ms}ms</div>`;

  entry.innerHTML = html;
  elements.terminalStream.appendChild(entry);
  scrollTerminalToBottom();
}

function clearTerminal() {
  elements.terminalStream.innerHTML = '';
  elements.terminalPlaceholder.style.display = 'block';
}

// ======================== UI Actions ======================== //

async function selectTask(taskId) {
  state.activeTaskId = taskId;
  renderTaskList();
  connectWebSocket(taskId);

  try {
    const task = await apiGetTask(taskId);
    updateTaskHeader(task.task_id, task.status);
    updateStepCounter(task.current_step);
  } catch (err) {
    console.error('Error loading task:', err);
  }
}

function resetToNewTask() {
  state.activeTaskId = null;
  if (state.socket) {
    state.socket.close();
    state.socket = null;
  }
  updateConnectionStatus('disconnected');
  updateTaskHeader(null, null);
  updateStepCounter(0);
  clearActivity();
  clearTerminal();
  elements.emptyState.style.display = 'block';
  elements.btnStop.style.display = 'none';
  renderTaskList();
  elements.composerInput.focus();
}

function setComposerLoading(loading) {
  elements.btnSend.disabled = loading;
  elements.composerInput.disabled = loading;
}

function scrollActivityToBottom() {
  if (state.isNearBottomActivity) {
    elements.activityScroll.scrollTop = elements.activityScroll.scrollHeight;
  }
}

function scrollTerminalToBottom() {
  if (state.isNearBottomTerminal) {
    elements.terminalBody.scrollTop = elements.terminalBody.scrollHeight;
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ======================== Event Listeners ======================== //

// Composer submit
function handleComposerSubmit() {
  const prompt = elements.composerInput.value.trim();
  if (!prompt) return;
  elements.composerInput.value = '';
  elements.composerInput.style.height = 'auto';
  apiCreateTask(prompt);
}

elements.btnSend.addEventListener('click', handleComposerSubmit);

elements.composerInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleComposerSubmit();
  }
});

elements.composerInput.addEventListener('input', () => {
  elements.composerInput.style.height = 'auto';
  elements.composerInput.style.height = `${Math.min(elements.composerInput.scrollHeight, 120)}px`;
});

// Stop task
elements.btnStop.addEventListener('click', () => {
  if (state.activeTaskId) {
    apiCancelTask(state.activeTaskId);
  }
});

// New task button
elements.btnNewTask.addEventListener('click', resetToNewTask);

// Clear terminal button
elements.btnClearTerminal.addEventListener('click', clearTerminal);

// Prompt chip clicks
document.querySelectorAll('.prompt-chip').forEach((btn) => {
  btn.addEventListener('click', () => {
    const prompt = btn.getAttribute('data-prompt');
    elements.composerInput.value = prompt;
    elements.composerInput.focus();
  });
});

// Mobile task toggle
elements.mobileTasksToggle.addEventListener('click', () => {
  elements.tasksSidebar.classList.toggle('open');
});

// Mobile tabs switcher
if (elements.mobileTabs) {
  elements.mobileTabs.querySelectorAll('.mobile-tab-btn').forEach((tabBtn) => {
    tabBtn.addEventListener('click', () => {
      elements.mobileTabs.querySelectorAll('.mobile-tab-btn').forEach((b) => b.classList.remove('active'));
      tabBtn.classList.add('active');

      const target = tabBtn.getAttribute('data-tab');
      if (target === 'tasks-drawer') {
        elements.tasksSidebar.classList.add('open');
      } else if (target === 'agent-view') {
        elements.tasksSidebar.classList.remove('open');
        elements.agentView.classList.add('active-mobile-view');
        elements.terminalView.classList.remove('active-mobile-view');
      } else if (target === 'terminal-view') {
        elements.tasksSidebar.classList.remove('open');
        elements.terminalView.classList.add('active-mobile-view');
        elements.agentView.classList.remove('active-mobile-view');
      }
    });
  });
}

// Track scroll positions
elements.activityScroll.addEventListener('scroll', () => {
  const el = elements.activityScroll;
  state.isNearBottomActivity = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
});

elements.terminalBody.addEventListener('scroll', () => {
  const el = elements.terminalBody;
  state.isNearBottomTerminal = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
});

// Initial load
window.addEventListener('DOMContentLoaded', () => {
  if (window.innerWidth <= 768) {
    elements.agentView.classList.add('active-mobile-view');
  }
  apiFetchTasks();
});

