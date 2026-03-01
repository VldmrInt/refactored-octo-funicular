/* ════════════════════════════════════════════════════════════
   Support WebApp — Vanilla JS SPA
   ════════════════════════════════════════════════════════════ */

'use strict';

// ── State ──────────────────────────────────────────────────────
const state = {
  token: null,
  user: null,
  currentTab: 'mine',
  tickets: [],
  currentTicket: null,
  editingTicketId: null,
  pendingFiles: [],       // for new ticket form
  chatFile: null,         // single file for chat message
};

// ── Config ─────────────────────────────────────────────────────
// Set window.SUPPORT_BASE_PATH in index.html for subpath deployments.
// Example: window.SUPPORT_BASE_PATH = '/support';
// Nginx must strip that prefix before proxying to FastAPI.
const API_BASE = (window.SUPPORT_BASE_PATH || '').replace(/\/$/, '');

const STATUS_LABELS = {
  new:         'Новое',
  in_progress: 'В работе',
  on_pause:    'На паузе',
  biz_review:  'Проверка бизнесом',
  closed:      'Закрытое',
  reopened:    'Переоткрытое',
};

const VALID_TRANSITIONS = {
  new:         ['in_progress'],
  in_progress: ['on_pause', 'biz_review', 'closed'],
  on_pause:    ['in_progress'],
  biz_review:  ['in_progress', 'closed'],
  closed:      ['reopened'],
  reopened:    ['in_progress'],
};

// ── API helpers ────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers['Authorization'] = `Bearer ${state.token}`;
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(API_BASE + path, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

async function apiGet(path) { return apiFetch(path); }
async function apiPost(path, body) {
  return apiFetch(path, { method: 'POST', body: JSON.stringify(body) });
}
async function apiPut(path, body) {
  return apiFetch(path, { method: 'PUT', body: JSON.stringify(body) });
}
async function apiPostForm(path, formData) {
  return apiFetch(path, { method: 'POST', body: formData });
}

// ── Toast ──────────────────────────────────────────────────────
function showToast(msg, duration = 2500) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), duration);
}

// ── Screen routing ─────────────────────────────────────────────
function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(`screen-${name}`).classList.add('active');
}

// ── Date formatting ────────────────────────────────────────────
function timeAgo(isoStr) {
  const dt = new Date(isoStr.endsWith('Z') ? isoStr : isoStr + 'Z');
  const diff = (Date.now() - dt.getTime()) / 1000;
  if (diff < 60) return 'только что';
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
  if (diff < 172800) return 'вчера';
  return dt.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

function formatTime(isoStr) {
  const dt = new Date(isoStr.endsWith('Z') ? isoStr : isoStr + 'Z');
  return dt.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

// ── Auth ───────────────────────────────────────────────────────
async function initAuth() {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    // Apply Telegram theme vars
    if (tg.colorScheme === 'dark') document.documentElement.style.setProperty('--card-bg', '#1c1c1e');
  }

  const initData = tg?.initData || '';

  // Handle deep link: ?startapp=ticket_42
  const startParam = tg?.initDataUnsafe?.start_param || new URLSearchParams(location.search).get('startapp') || '';

  try {
    const resp = await apiPost('/auth/telegram', { initData });
    state.token = resp.token;
    state.user = resp.user;
  } catch (e) {
    // Dev fallback: allow no-auth with mock user
    console.warn('Auth failed, using mock user:', e.message);
    state.token = 'dev';
    state.user = { id: 1, telegram_id: 0, username: 'dev', full_name: 'Dev User', role: 'admin' };
  }

  // Show/hide "All" tab based on role
  if (state.user.role === 'support' || state.user.role === 'admin') {
    document.getElementById('tab-all').style.display = '';
  }

  if (startParam.startsWith('ticket_')) {
    const tid = parseInt(startParam.replace('ticket_', ''), 10);
    if (!isNaN(tid)) {
      await openTicketById(tid);
      return;
    }
  }

  await loadTicketList();
}

// ── Ticket List ────────────────────────────────────────────────
async function loadTicketList() {
  showScreen('list');
  const container = document.getElementById('ticket-list-content');
  container.innerHTML = '<div class="loader"><div class="spinner"></div></div>';

  try {
    const params = new URLSearchParams({ filter: state.currentTab });
    const tickets = await apiGet(`/tickets?${params}`);
    state.tickets = tickets;
    renderTicketList(tickets);
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><div class="icon">⚠️</div>${e.message}</div>`;
  }
}

function renderTicketList(tickets) {
  const container = document.getElementById('ticket-list-content');
  if (!tickets.length) {
    container.innerHTML = '<div class="empty-state"><div class="icon">📭</div>Обращений нет</div>';
    return;
  }

  container.innerHTML = tickets.map(t => {
    const unassigned = !t.assigned_to;
    let cardClass = 'ticket-card';
    if (t.is_urgent && unassigned) cardClass += ' urgent-unassigned';
    else if (unassigned) cardClass += ' unassigned';

    const statusBadge = `<span class="badge-status ${t.status}">${STATUS_LABELS[t.status] || t.status}</span>`;
    const urgentBadge = t.is_urgent ? '<span class="badge-urgent">🔴 СРОЧНО</span>' : '';
    const assigneeName = (state.user.role === 'support' || state.user.role === 'admin') && t.assignee
      ? ` · ${t.assignee.full_name}` : '';

    return `
      <div class="${cardClass}" data-id="${t.id}">
        <div class="ticket-card-top">
          <span class="ticket-number">${t.number}</span>
          ${urgentBadge}
          ${statusBadge}
        </div>
        <div class="ticket-title">${escHtml(t.title)}</div>
        <div class="ticket-meta">
          @${escHtml(t.author?.username || t.author?.full_name || '—')}${assigneeName}
          · ${timeAgo(t.updated_at)}
        </div>
      </div>`;
  }).join('');

  container.querySelectorAll('.ticket-card').forEach(card => {
    card.addEventListener('click', () => openTicketById(parseInt(card.dataset.id, 10)));
  });
}

// ── Tabs ───────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.currentTab = btn.dataset.tab;
    loadTicketList();
  });
});

// ── New ticket button ──────────────────────────────────────────
document.getElementById('btn-new-ticket').addEventListener('click', () => {
  openTicketForm(null);
});

// ── Ticket Form ────────────────────────────────────────────────
function openTicketForm(ticket) {
  state.editingTicketId = ticket ? ticket.id : null;
  state.pendingFiles = [];

  document.getElementById('form-title').textContent = ticket ? 'Редактировать' : 'Новое обращение';
  document.getElementById('f-title').value = ticket?.title || '';
  document.getElementById('f-desc').value = ticket?.description || '';
  document.getElementById('f-steps').value = ticket?.steps || '';
  document.getElementById('f-url').value = ticket?.url || '';
  document.getElementById('f-urgent').checked = ticket?.is_urgent || false;
  document.getElementById('file-list').innerHTML = '';
  document.getElementById('btn-submit-ticket').textContent = ticket ? 'Сохранить' : 'Отправить';

  showScreen('form');
}

document.getElementById('btn-form-back').addEventListener('click', () => {
  if (state.editingTicketId) {
    openTicketById(state.editingTicketId);
  } else {
    loadTicketList();
  }
});

// File upload area
document.getElementById('file-upload-area').addEventListener('click', () => {
  document.getElementById('file-input').click();
});
document.getElementById('file-input').addEventListener('change', e => {
  Array.from(e.target.files).forEach(f => addPendingFile(f));
  e.target.value = '';
});

function addPendingFile(file) {
  state.pendingFiles.push(file);
  renderPendingFiles();
}

function renderPendingFiles() {
  const list = document.getElementById('file-list');
  list.innerHTML = state.pendingFiles.map((f, i) => `
    <div class="file-item">
      <span>📎 ${escHtml(f.name)} (${formatSize(f.size)})</span>
      <button class="remove" data-idx="${i}">×</button>
    </div>`).join('');
  list.querySelectorAll('.remove').forEach(btn => {
    btn.addEventListener('click', () => {
      state.pendingFiles.splice(parseInt(btn.dataset.idx, 10), 1);
      renderPendingFiles();
    });
  });
}

document.getElementById('btn-submit-ticket').addEventListener('click', async () => {
  const title = document.getElementById('f-title').value.trim();
  const desc = document.getElementById('f-desc').value.trim();
  if (!title || !desc) { showToast('Заполните обязательные поля'); return; }

  const btn = document.getElementById('btn-submit-ticket');
  btn.disabled = true;

  try {
    const body = {
      title,
      description: desc,
      steps: document.getElementById('f-steps').value.trim() || null,
      url: document.getElementById('f-url').value.trim() || null,
      is_urgent: document.getElementById('f-urgent').checked,
    };

    let ticket;
    if (state.editingTicketId) {
      ticket = await apiPut(`/tickets/${state.editingTicketId}`, body);
    } else {
      ticket = await apiPost('/tickets', body);
    }

    // Upload files
    for (const file of state.pendingFiles) {
      const fd = new FormData();
      fd.append('file', file);
      await apiPostForm(`/tickets/${ticket.id}/files`, fd).catch(e => showToast(`Файл ${file.name}: ${e.message}`));
    }

    showToast(state.editingTicketId ? 'Сохранено' : 'Обращение создано');
    await openTicketById(ticket.id);
  } catch (e) {
    showToast(e.message);
  } finally {
    btn.disabled = false;
  }
});

// ── Ticket Detail ──────────────────────────────────────────────
async function openTicketById(id) {
  showScreen('loading');
  try {
    const ticket = await apiGet(`/tickets/${id}`);
    state.currentTicket = ticket;
    renderTicketDetail(ticket);
    await loadChatMessages(id);
    showScreen('detail');
    scrollChatToBottom();
  } catch (e) {
    showToast(e.message);
    loadTicketList();
  }
}

function renderTicketDetail(t) {
  const me = state.user;
  const isAuthor = t.author.id === me.id;
  const isSupport = me.role === 'support' || me.role === 'admin';

  // Header
  document.getElementById('d-number').textContent = t.number;
  document.getElementById('d-title').textContent = t.title;
  const urgentBadge = document.getElementById('d-urgent-badge');
  urgentBadge.style.display = t.is_urgent ? '' : 'none';

  // Status badge
  const statusBadge = document.getElementById('d-status-badge');
  statusBadge.textContent = STATUS_LABELS[t.status] || t.status;
  statusBadge.className = `badge-status ${t.status}`;

  // Status dropdown (support/admin)
  const sel = document.getElementById('d-status-select');
  sel.style.display = 'none';
  if (isSupport) {
    const options = VALID_TRANSITIONS[t.status] || [];
    if (options.length) {
      sel.innerHTML = `<option value="">Сменить статус…</option>` +
        options.map(s => `<option value="${s}">${STATUS_LABELS[s]}</option>`).join('');
      sel.style.display = '';
      sel.onchange = async () => {
        const newStatus = sel.value;
        if (!newStatus) return;
        try {
          const updated = await apiPut(`/tickets/${t.id}/status`, { status: newStatus });
          state.currentTicket = updated;
          renderTicketDetail(updated);
          await loadChatMessages(updated.id);
          scrollChatToBottom();
          showToast('Статус изменён');
        } catch (e) { showToast(e.message); sel.value = ''; }
      };
    }
  }

  // Action buttons
  const actionsRow = document.getElementById('d-actions');
  actionsRow.innerHTML = '';

  // Assign button
  if (isSupport && !t.assigned_to) {
    const btn = makeBtn('Взять на себя', 'btn-action btn-assign');
    btn.onclick = async () => {
      try {
        const updated = await apiPut(`/tickets/${t.id}/assign`, {});
        state.currentTicket = updated;
        renderTicketDetail(updated);
        showToast('Обращение взято');
      } catch (e) { showToast(e.message); }
    };
    actionsRow.appendChild(btn);
  }

  // Edit button (author, status=new)
  if (isAuthor && t.status === 'new') {
    const btn = makeBtn('✏️ Редактировать', 'btn-action btn-edit');
    btn.onclick = () => openTicketForm(t);
    actionsRow.appendChild(btn);
  }

  // Close button (author, status=biz_review)
  if (isAuthor && t.status === 'biz_review') {
    const btn = makeBtn('✅ Закрыть обращение', 'btn-action btn-close');
    btn.onclick = async () => {
      try {
        const updated = await apiPut(`/tickets/${t.id}/status`, { status: 'closed' });
        state.currentTicket = updated;
        renderTicketDetail(updated);
        showToast('Обращение закрыто');
      } catch (e) { showToast(e.message); }
    };
    actionsRow.appendChild(btn);
  }

  // Reopen button (author, status=closed)
  if (isAuthor && t.status === 'closed') {
    const btn = makeBtn('🔄 Переоткрыть', 'btn-action btn-reopen');
    btn.onclick = async () => {
      try {
        const updated = await apiPut(`/tickets/${t.id}/status`, { status: 'reopened' });
        state.currentTicket = updated;
        renderTicketDetail(updated);
        showToast('Обращение переоткрыто');
      } catch (e) { showToast(e.message); }
    };
    actionsRow.appendChild(btn);
  }

  // Urgent toggle
  const canToggleUrgent = isSupport || isAuthor;
  if (canToggleUrgent) {
    const urgentBtn = makeBtn(
      t.is_urgent ? '🔕 Снять «Срочно»' : '🔴 Пометить срочным',
      t.is_urgent ? 'btn-action btn-urgent-on' : 'btn-action btn-urgent-off'
    );
    urgentBtn.onclick = async () => {
      try {
        const updated = await apiPut(`/tickets/${t.id}/urgent`, { is_urgent: !t.is_urgent });
        state.currentTicket = updated;
        renderTicketDetail(updated);
        showToast(updated.is_urgent ? 'Отмечено срочным' : '«Срочно» снято');
      } catch (e) { showToast(e.message); }
    };
    actionsRow.appendChild(urgentBtn);
  }

  // Description
  const descSec = document.getElementById('d-desc-section');
  const descEl = document.getElementById('d-desc');
  descSec.style.display = t.description ? '' : 'none';
  descEl.textContent = t.description;

  // Steps
  const stepsSec = document.getElementById('d-steps-section');
  stepsSec.style.display = t.steps ? '' : 'none';
  document.getElementById('d-steps').textContent = t.steps || '';

  // URL
  const urlSec = document.getElementById('d-url-section');
  urlSec.style.display = t.url ? '' : 'none';
  const urlEl = document.getElementById('d-url');
  urlEl.textContent = t.url || '';
  urlEl.href = t.url || '#';

  // Files
  const filesSec = document.getElementById('d-files-section');
  const filesEl = document.getElementById('d-files');
  if (t.files && t.files.length) {
    filesSec.style.display = '';
    filesEl.innerHTML = t.files.map(f => `
      <a class="file-chip" href="${API_BASE}/public/files/${encodeURIComponent(f.stored_path)}"
         target="_blank" rel="noopener">
        📎 ${escHtml(f.filename)}
      </a>`).join('');
  } else {
    filesSec.style.display = 'none';
  }

  // Author
  const author = t.author;
  const authorStr = `@${author.username || author.full_name} · ${timeAgo(t.created_at)}`;
  const assigneeStr = t.assignee
    ? (isSupport ? ` · Исполнитель: ${t.assignee.full_name}` : '') : '';
  document.getElementById('d-author').textContent = authorStr + assigneeStr;

  // Disable chat input if closed
  const chatWrap = document.getElementById('chat-input-wrap');
  const isClosed = t.status === 'closed';
  chatWrap.style.opacity = isClosed ? '0.4' : '1';
  chatWrap.style.pointerEvents = isClosed ? 'none' : '';
}

function makeBtn(text, className) {
  const btn = document.createElement('button');
  btn.textContent = text;
  btn.className = className;
  return btn;
}

document.getElementById('btn-detail-back').addEventListener('click', () => {
  loadTicketList();
});

// ── Chat ───────────────────────────────────────────────────────
async function loadChatMessages(ticketId) {
  const container = document.getElementById('chat-messages');
  container.innerHTML = '<div class="loader"><div class="spinner"></div></div>';
  try {
    const messages = await apiGet(`/tickets/${ticketId}/messages`);
    renderMessages(messages);
  } catch (e) {
    container.innerHTML = `<div class="empty-state">${e.message}</div>`;
  }
}

function renderMessages(messages) {
  const container = document.getElementById('chat-messages');
  const me = state.user;

  if (!messages.length) {
    container.innerHTML = '<div class="empty-state" style="padding:24px">Сообщений нет</div>';
    return;
  }

  container.innerHTML = messages.map(msg => {
    if (msg.sender_role === 'system') {
      return `<div class="msg-wrap system">
        <div class="msg-bubble">${escHtml(msg.text)}</div>
        <div class="msg-time">${formatTime(msg.created_at)}</div>
      </div>`;
    }

    const isMe = msg.sender_id === me.id;
    const isSupport = msg.sender_role === 'support' || msg.sender_role === 'admin';

    let wrapClass = 'msg-wrap ';
    if (isMe) wrapClass += 'me';
    else if (isSupport) wrapClass += 'support';
    else wrapClass += 'other';

    const senderLabel = isMe ? '' :
      (isSupport ? '<div class="msg-sender">Поддержка</div>' : '<div class="msg-sender">Автор</div>');

    const filesHtml = (msg.files || []).map(f =>
      `<a class="file-chip" style="margin-top:4px" href="${API_BASE}/public/files/${encodeURIComponent(f.stored_path)}"
          target="_blank" rel="noopener">📎 ${escHtml(f.filename)}</a>`
    ).join('');

    return `<div class="${wrapClass}">
      ${senderLabel}
      <div class="msg-bubble">
        ${escHtml(msg.text)}
        ${filesHtml}
      </div>
      <div class="msg-time">${formatTime(msg.created_at)}</div>
    </div>`;
  }).join('');
}

function scrollChatToBottom() {
  const container = document.getElementById('chat-messages');
  container.scrollTop = container.scrollHeight;
}

// Chat file attach
document.getElementById('chat-attach-btn').addEventListener('click', () => {
  document.getElementById('chat-file-input').click();
});
document.getElementById('chat-file-input').addEventListener('change', e => {
  const file = e.target.files[0];
  if (!file) return;
  state.chatFile = file;
  const preview = document.getElementById('chat-file-preview');
  preview.style.display = 'flex';
  preview.innerHTML = `<span>📎 ${escHtml(file.name)}</span>
    <button class="remove" id="chat-file-remove">×</button>`;
  document.getElementById('chat-file-remove').addEventListener('click', () => {
    state.chatFile = null;
    preview.style.display = 'none';
    preview.innerHTML = '';
    e.target.value = '';
  });
});

// Chat send
document.getElementById('chat-send-btn').addEventListener('click', sendChatMessage);
document.getElementById('chat-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChatMessage(); }
});

async function sendChatMessage() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text && !state.chatFile) return;
  if (!state.currentTicket) return;

  const btn = document.getElementById('chat-send-btn');
  btn.disabled = true;

  try {
    const fd = new FormData();
    fd.append('text', text || '📎 Файл');
    if (state.chatFile) fd.append('file', state.chatFile);

    await apiPostForm(`/tickets/${state.currentTicket.id}/messages`, fd);

    input.value = '';
    state.chatFile = null;
    document.getElementById('chat-file-preview').style.display = 'none';
    document.getElementById('chat-file-preview').innerHTML = '';
    document.getElementById('chat-file-input').value = '';

    await loadChatMessages(state.currentTicket.id);
    scrollChatToBottom();
  } catch (e) {
    showToast(e.message);
  } finally {
    btn.disabled = false;
  }
}

// Auto-resize chat textarea
document.getElementById('chat-input').addEventListener('input', function () {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 100) + 'px';
});

// ── Utils ──────────────────────────────────────────────────────
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

// ── Bootstrap ──────────────────────────────────────────────────
(async () => {
  try {
    await initAuth();
  } catch (e) {
    console.error('Init failed:', e);
    document.getElementById('screen-loading').innerHTML =
      `<div class="empty-state" style="height:100vh;display:flex;flex-direction:column;justify-content:center">
        <div class="icon">⚠️</div>
        <div>Ошибка загрузки: ${escHtml(e.message)}</div>
      </div>`;
  }
})();
