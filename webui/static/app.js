/* ═══════════════════════════════════════════════════════════════════════════
   LangExtract WebUI — Frontend App
   ═══════════════════════════════════════════════════════════════════════════ */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

// ── State ────────────────────────────────────────────────────────────────────

const state = {
  endpoints: {},
  currentEndpoint: null,
  currentModel: null,
  currentProject: null,
  currentConversation: null,
  ws: null,
  streaming: false,
  streamBuffer: '',
};

// ── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  await loadEndpoints();
  await loadProjects();
  await loadConversations();
  loadSkills();
  setupEventListeners();
});

// ── API helpers ──────────────────────────────────────────────────────────────

async function api(path, opts = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  return res.json();
}

// ── Endpoints & Models ───────────────────────────────────────────────────────

async function loadEndpoints() {
  try {
    state.endpoints = await api('/endpoints');
  } catch {
    state.endpoints = {};
  }

  const sel = $('#sel-endpoint');
  sel.innerHTML = '';

  for (const [name, info] of Object.entries(state.endpoints)) {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = `${name} ${info.online ? '●' : '○'}`;
    sel.appendChild(opt);
  }

  if (sel.options.length > 0) {
    state.currentEndpoint = sel.value;
    updateEndpointStatus();
    await loadModels();
  }
}

function updateEndpointStatus() {
  const info = state.endpoints[state.currentEndpoint];
  const el = $('#endpoint-status');
  if (!info) {
    el.textContent = '';
    return;
  }
  el.textContent = info.online
    ? `● online · ${info.models.length} model${info.models.length !== 1 ? 's' : ''}`
    : '○ offline';
  el.className = `endpoint-status ${info.online ? 'online' : 'offline'}`;
  $('#footer-endpoint').textContent = state.currentEndpoint;
}

async function loadModels() {
  const info = state.endpoints[state.currentEndpoint];
  const sel = $('#sel-model');
  sel.innerHTML = '';

  const models = info?.models || [];
  for (const m of models) {
    const opt = document.createElement('option');
    opt.value = m.id;
    opt.textContent = m.name;
    sel.appendChild(opt);
  }

  if (sel.options.length > 0) {
    state.currentModel = sel.value;
  }

  updateTopbar();
}

// ── Projects ─────────────────────────────────────────────────────────────────

async function loadProjects() {
  let projects = [];
  try { projects = await api('/projects'); } catch {}

  const list = $('#project-list');
  list.innerHTML = '';

  for (const p of projects) {
    const el = document.createElement('div');
    el.className = `item ${state.currentProject === p.name ? 'active' : ''}`;
    el.innerHTML = `
      <span class="item-icon">📁</span>
      <span class="item-label">${esc(p.name)}</span>
      <span class="item-meta">${p.files}f</span>
    `;
    el.onclick = () => selectProject(p.name);
    list.appendChild(el);
  }
}

function selectProject(name) {
  state.currentProject = name;
  loadProjects();
  loadFileTree();
  updateTopbar();
}

async function createProject() {
  const name = await showPrompt('New Project', 'Project name:');
  if (!name) return;
  await api('/projects', { method: 'POST', body: { name } });
  await loadProjects();
  selectProject(name);
}

// ── Conversations ────────────────────────────────────────────────────────────

async function loadConversations() {
  let convs = [];
  try { convs = await api('/conversations'); } catch {}

  const list = $('#conversation-list');
  list.innerHTML = '';

  for (const c of convs) {
    const el = document.createElement('div');
    el.className = `item ${state.currentConversation === c.id ? 'active' : ''}`;
    el.innerHTML = `
      <span class="item-icon">💬</span>
      <span class="item-label">${esc(c.title)}</span>
      <button class="btn-delete" data-id="${c.id}">✕</button>
    `;
    el.onclick = (e) => {
      if (e.target.classList.contains('btn-delete')) {
        deleteConversation(e.target.dataset.id);
        return;
      }
      selectConversation(c.id, c);
    };
    list.appendChild(el);
  }
}

async function selectConversation(id, meta = null) {
  state.currentConversation = id;
  loadConversations();
  connectWebSocket(id);
  if (meta) {
    state.currentProject = meta.project || state.currentProject;
    $('#topbar-title').textContent = meta.title || 'Chat';
  }
  updateTopbar();
  // Reload messages from server would go here — for now we clear
  $('#messages').innerHTML = '';
  $('#welcome').classList.add('hidden');
}

async function newConversation() {
  const data = await api('/conversations', {
    method: 'POST',
    body: {
      project: state.currentProject,
      model: state.currentModel,
      endpoint: state.currentEndpoint,
      title: 'New chat',
    },
  });
  await loadConversations();
  selectConversation(data.id, { title: 'New chat', project: state.currentProject });
}

async function deleteConversation(id) {
  await api(`/conversations/${id}`, { method: 'DELETE' });
  if (state.currentConversation === id) {
    state.currentConversation = null;
    disconnectWebSocket();
    $('#messages').innerHTML = '';
    $('#welcome').classList.remove('hidden');
    $('#topbar-title').textContent = 'New chat';
  }
  loadConversations();
}

// ── WebSocket ────────────────────────────────────────────────────────────────

function connectWebSocket(cid) {
  disconnectWebSocket();

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  state.ws = new WebSocket(`${proto}//${location.host}/ws/chat/${cid}`);

  state.ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleWSMessage(data);
  };

  state.ws.onerror = () => {
    appendSystemMessage('WebSocket error — check connection');
  };

  state.ws.onclose = () => {
    state.ws = null;
  };
}

function disconnectWebSocket() {
  if (state.ws) {
    state.ws.close();
    state.ws = null;
  }
}

function handleWSMessage(data) {
  switch (data.type) {
    case 'stream_start':
      state.streaming = true;
      state.streamBuffer = '';
      appendMessage('assistant', '', true);
      $('#typing-indicator').classList.remove('hidden');
      break;

    case 'stream':
      state.streamBuffer += data.content;
      updateStreamingMessage(state.streamBuffer);
      break;

    case 'stream_end':
      state.streaming = false;
      $('#typing-indicator').classList.add('hidden');
      finalizeStreamingMessage();
      scrollToBottom();
      break;

    case 'skill_exec':
      appendSkillBlock(data.skill, data.params, null);
      break;

    case 'skill_result':
      updateLastSkillBlock(data.skill, data.result);
      break;

    case 'error':
      appendSystemMessage(data.content);
      break;
  }
}

function sendMessage(content) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    appendSystemMessage('Not connected. Create or select a conversation first.');
    return;
  }

  state.ws.send(JSON.stringify({ type: 'message', content }));
  appendMessage('user', content);
  $('#welcome').classList.add('hidden');
  scrollToBottom();
}

// ── Message rendering ────────────────────────────────────────────────────────

function appendMessage(role, content, streaming = false) {
  const container = $('#messages');
  const el = document.createElement('div');
  el.className = `message ${role}`;
  el.dataset.streaming = streaming;

  const time = new Date().toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' });

  el.innerHTML = `
    <div class="message-header">
      <span class="message-role">${role === 'user' ? '● You' : '⬡ Assistant'}</span>
      <span class="message-time">${time}</span>
    </div>
    <div class="message-content">${streaming ? '' : renderMarkdown(content)}</div>
  `;

  container.appendChild(el);
  scrollToBottom();
}

function updateStreamingMessage(content) {
  const msgs = $$('.message[data-streaming="true"]');
  const last = msgs[msgs.length - 1];
  if (!last) return;
  last.querySelector('.message-content').innerHTML = renderMarkdown(content) + '<span class="cursor">▊</span>';
  scrollToBottom();
}

function finalizeStreamingMessage() {
  const msgs = $$('.message[data-streaming="true"]');
  for (const m of msgs) {
    m.dataset.streaming = 'false';
    const cursor = m.querySelector('.cursor');
    if (cursor) cursor.remove();
    // Re-render with full markdown
    const content = m.querySelector('.message-content');
    // Add copy buttons to code blocks
    content.querySelectorAll('pre code').forEach(addCopyButton);
  }
}

function appendSystemMessage(text) {
  const container = $('#messages');
  const el = document.createElement('div');
  el.className = 'message system';
  el.style.cssText = 'padding: 8px 24px; font-size: 12px; color: var(--text-warning); font-family: var(--font-mono);';
  el.textContent = `⚠ ${text}`;
  container.appendChild(el);
  scrollToBottom();
}

function appendSkillBlock(skill, params, result) {
  const container = $('#messages');
  const el = document.createElement('div');
  el.className = 'skill-block';
  el.dataset.skill = skill;
  el.innerHTML = `
    <div class="skill-block-header">
      ⚡ ${esc(skill)} ${params ? `· ${esc(JSON.stringify(params).slice(0, 80))}` : ''}
    </div>
    <div class="skill-block-content">${result ? renderSkillResult(result) : 'Running...'}</div>
  `;
  container.appendChild(el);
  scrollToBottom();
}

function updateLastSkillBlock(skill, result) {
  const blocks = $$('.skill-block');
  const last = blocks[blocks.length - 1];
  if (!last) return;
  last.querySelector('.skill-block-content').innerHTML = renderSkillResult(result);
  scrollToBottom();
}

function renderSkillResult(result) {
  if (result.error) return `<span style="color:var(--text-error)">Error: ${esc(result.error)}</span>`;
  if (result.content) return `<pre style="margin:0;white-space:pre-wrap">${esc(result.content.slice(0, 5000))}</pre>`;
  if (result.entries) {
    return result.entries.map(e =>
      `<div style="padding:2px 0">${e.type === 'dir' ? '📁' : '📄'} ${esc(e.name)}${e.size != null ? ` <span style="color:var(--text-dim)">${formatSize(e.size)}</span>` : ''}</div>`
    ).join('');
  }
  if (result.stdout !== undefined) {
    let out = '';
    if (result.stdout) out += esc(result.stdout);
    if (result.stderr) out += `\n<span style="color:var(--text-error)">${esc(result.stderr)}</span>`;
    if (!out) out = `<span style="color:var(--text-dim)">exit ${result.returncode}</span>`;
    return `<pre style="margin:0;white-space:pre-wrap">${out}</pre>`;
  }
  if (result.matches) {
    return result.matches.length > 0
      ? result.matches.map(m => `<div>📄 ${esc(m)}</div>`).join('')
      : '<span style="color:var(--text-dim)">No matches</span>';
  }
  return `<pre style="margin:0;white-space:pre-wrap">${esc(JSON.stringify(result, null, 2))}</pre>`;
}

// ── Markdown renderer (lightweight) ──────────────────────────────────────────

function renderMarkdown(text) {
  if (!text) return '';

  // Escape HTML first
  let html = esc(text);

  // Code blocks with language
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const langLabel = lang || 'code';
    return `<pre><div class="code-header"><span>${langLabel}</span><button class="btn-copy" onclick="copyCode(this)">copy</button></div><code>${code.trim()}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // Italic
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // Headers
  html = html.replace(/^### (.+)$/gm, '<h4 style="margin:12px 0 4px;color:var(--text-primary)">$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3 style="margin:12px 0 4px;color:var(--text-primary)">$1</h3>');
  html = html.replace(/^# (.+)$/gm, '<h2 style="margin:12px 0 4px;color:var(--text-primary)">$1</h2>');

  // Blockquotes
  html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');

  // Unordered lists
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');

  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

  // Paragraphs (double newline)
  html = html.replace(/\n\n/g, '</p><p>');
  html = `<p>${html}</p>`;

  // Single newlines -> <br> (but not in pre blocks)
  html = html.replace(/(?<!<\/pre>)\n(?!<)/g, '<br>');

  // Clean up empty paragraphs
  html = html.replace(/<p><\/p>/g, '');

  return html;
}

// ── File tree ────────────────────────────────────────────────────────────────

async function loadFileTree(path = '.') {
  if (!state.currentProject) return;

  const data = await api(`/projects/${state.currentProject}/tree?path=${encodeURIComponent(path)}`);
  const tree = $('#file-tree');

  if (path === '.') tree.innerHTML = '';

  const entries = data.entries || [];
  for (const entry of entries) {
    const el = document.createElement('div');
    el.className = `tree-item ${entry.type === 'dir' ? 'dir' : ''}`;
    el.innerHTML = `
      <span class="tree-icon">${entry.type === 'dir' ? '📁' : '📄'}</span>
      <span>${esc(entry.name)}</span>
      ${entry.size != null ? `<span class="tree-size">${formatSize(entry.size)}</span>` : ''}
    `;
    el.onclick = () => {
      if (entry.type === 'dir') {
        loadFileTree(entry.path);
      } else {
        viewFile(entry.path);
      }
    };
    tree.appendChild(el);
  }
}

async function viewFile(path) {
  if (!state.currentProject) return;

  const data = await api(`/projects/${state.currentProject}/file?path=${encodeURIComponent(path)}`);
  const viewer = $('#file-viewer');
  viewer.classList.remove('hidden');
  $('#file-viewer-path').textContent = path;
  $('#file-viewer-content').querySelector('code').textContent = data.content || data.error || '';
}

// ── Skills ───────────────────────────────────────────────────────────────────

async function loadSkills() {
  let skills = {};
  try { skills = await api('/skills'); } catch {}

  const grid = $('#skills-list');
  grid.innerHTML = '';

  for (const [id, skill] of Object.entries(skills)) {
    const el = document.createElement('div');
    el.className = 'skill-item';
    el.textContent = skill.name;
    el.title = skill.description;
    el.onclick = () => executeSkillFromUI(id);
    grid.appendChild(el);
  }
}

async function executeSkillFromUI(skillId) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    appendSystemMessage('Connect to a conversation first');
    return;
  }

  let params = {};

  switch (skillId) {
    case 'file_read':
      params.path = await showPrompt('Read File', 'File path:');
      if (!params.path) return;
      break;
    case 'file_write': {
      params.path = await showPrompt('Write File', 'File path:');
      if (!params.path) return;
      params.content = await showPrompt('Write File', 'Content:');
      if (params.content == null) return;
      break;
    }
    case 'file_list':
      params.path = await showPrompt('List Files', 'Directory path:', '.');
      if (params.path == null) return;
      break;
    case 'shell':
      params.command = await showPrompt('Shell', 'Command:');
      if (!params.command) return;
      break;
    case 'search':
      params.pattern = await showPrompt('Search', 'Search pattern:');
      if (!params.pattern) return;
      break;
  }

  state.ws.send(JSON.stringify({ type: 'skill', skill: skillId, params }));
}

// ── UI helpers ───────────────────────────────────────────────────────────────

function updateTopbar() {
  const projectTag = $('#topbar-project');
  const modelTag = $('#topbar-model');
  projectTag.textContent = state.currentProject ? `📁 ${state.currentProject}` : '';
  modelTag.textContent = state.currentModel ? `🤖 ${state.currentModel}` : '';
}

function scrollToBottom() {
  const chat = $('#chat-area');
  requestAnimationFrame(() => {
    chat.scrollTop = chat.scrollHeight;
  });
}

function esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)}K`;
  return `${(bytes / 1048576).toFixed(1)}M`;
}

function addCopyButton(codeEl) {
  const pre = codeEl.closest('pre');
  if (!pre || pre.querySelector('.code-header')) return;
  // Already has one from markdown rendering
}

window.copyCode = function(btn) {
  const code = btn.closest('pre').querySelector('code');
  if (!code) return;
  navigator.clipboard.writeText(code.textContent).then(() => {
    btn.textContent = 'copied!';
    setTimeout(() => btn.textContent = 'copy', 1500);
  });
};

// ── Modal prompt ─────────────────────────────────────────────────────────────

function showPrompt(title, label, defaultVal = '') {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal">
        <h3>${esc(title)}</h3>
        <label style="font-size:12px;color:var(--text-secondary);display:block;margin-bottom:6px">${esc(label)}</label>
        <input type="text" id="modal-input" value="${esc(defaultVal)}" autofocus>
        <div class="modal-actions">
          <button class="cancel">Cancel</button>
          <button class="primary confirm">OK</button>
        </div>
      </div>
    `;

    const input = overlay.querySelector('#modal-input');
    const confirm = () => { resolve(input.value); overlay.remove(); };
    const cancel = () => { resolve(null); overlay.remove(); };

    overlay.querySelector('.confirm').onclick = confirm;
    overlay.querySelector('.cancel').onclick = cancel;
    input.onkeydown = (e) => { if (e.key === 'Enter') confirm(); if (e.key === 'Escape') cancel(); };
    overlay.onclick = (e) => { if (e.target === overlay) cancel(); };

    document.body.appendChild(overlay);
    input.focus();
    input.select();
  });
}

// ── Event listeners ──────────────────────────────────────────────────────────

function setupEventListeners() {
  // Endpoint change
  $('#sel-endpoint').onchange = async (e) => {
    state.currentEndpoint = e.target.value;
    updateEndpointStatus();
    await loadModels();
  };

  // Model change
  $('#sel-model').onchange = (e) => {
    state.currentModel = e.target.value;
    updateTopbar();
  };

  // New chat
  $('#btn-new-chat').onclick = newConversation;

  // New project
  $('#btn-new-project').onclick = createProject;

  // Toggle sidebar
  $('#btn-toggle-sidebar').onclick = () => {
    const sb = $('#sidebar');
    if (window.innerWidth <= 768) {
      sb.classList.toggle('open');
    } else {
      sb.classList.toggle('collapsed');
    }
  };

  // Toggle file panel
  $('#btn-toggle-panel').onclick = () => {
    const panel = $('#file-panel');
    panel.classList.toggle('hidden');
    if (!panel.classList.contains('hidden') && state.currentProject) {
      loadFileTree();
    }
  };

  // Close file panel
  $('#btn-close-panel').onclick = () => $('#file-panel').classList.add('hidden');
  $('#btn-close-file').onclick = () => $('#file-viewer').classList.add('hidden');

  // Input
  const input = $('#input');
  const btnSend = $('#btn-send');

  input.oninput = () => {
    btnSend.disabled = !input.value.trim();
    // Auto-resize
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 200) + 'px';
  };

  input.onkeydown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (input.value.trim() && !state.streaming) {
        doSend();
      }
    }
  };

  btnSend.onclick = () => {
    if (input.value.trim() && !state.streaming) {
      doSend();
    }
  };

  // Welcome hints
  $$('.hint').forEach(hint => {
    hint.onclick = () => {
      input.value = hint.dataset.msg;
      input.oninput();
    };
  });

  // Context clear
  $('#btn-clear-context').onclick = () => {
    $('#input-context').classList.add('hidden');
  };
}

async function doSend() {
  const input = $('#input');
  const text = input.value.trim();
  if (!text) return;

  // Auto-create conversation if needed
  if (!state.currentConversation) {
    await newConversation();
    // Small delay to let WS connect
    await new Promise(r => setTimeout(r, 300));
  }

  sendMessage(text);
  input.value = '';
  input.style.height = 'auto';
  $('#btn-send').disabled = true;
}
