"use strict";

/* ===== Constants ===== */
const ROUTES = {
  adviser:      { label: "Career adviser", working: "Looking up learning paths…",
                  icon: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14Zm0 0A2.5 2.5 0 0 0 6.5 22H20v-5"/>' },
  search:       { label: "Web search", working: "Searching the web…",
                  icon: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>' },
  crawl:        { label: "Page reader", working: "Scanning and reading the page…",
                  icon: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>' },
  conversation: { label: "Chat", working: "Thinking…",
                  icon: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z"/>' },
};
const FEATURE_LABELS = { adviser: "Knowledge base", search: "Web search", crawl: "Crawler", url_scan: "URL scan" };
const STORAGE_KEY = "lla.threads.v1";
const ACTIVE_KEY = "lla.active.v1";
const TOKEN_KEY = "lla.token.v1";
const MAX_THREADS = 50;
const LOGO = '<svg viewBox="0 0 24 24"><path d="M12 3 2 8l10 5 8-4v6h2V8L12 3Zm-6 9.2V16c0 1.7 2.7 3 6 3s6-1.3 6-3v-3.8l-6 3-6-3Z"/></svg>';
const TRASH = '<svg viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>';
const LINK = '<svg viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/></svg>';

/* ===== DOM ===== */
const $ = (sel) => document.querySelector(sel);
const el = {
  sidebar: $("#sidebar"), scrim: $("#scrim"), threadList: $("#threadList"),
  newChat: $("#newChat"), openSidebar: $("#openSidebar"), closeSidebar: $("#closeSidebar"),
  themeToggle: $("#themeToggle"), clearChat: $("#clearChat"), threadTitle: $("#threadTitle"),
  chat: $("#chat"), welcome: $("#welcome"), messages: $("#messages"),
  composer: $("#composer"), input: $("#input"), sendBtn: $("#sendBtn"),
  statusDot: $("#status .dot"), statusModel: $("#statusModel"), features: $("#features"),
  template: $("#messageTemplate"),
  login: $("#login"), loginForm: $("#loginForm"), loginPassword: $("#loginPassword"),
  loginError: $("#loginError"), loginBtn: $("#loginBtn"),
};

/* ===== Storage (per-browser convenience; the app works without it) ===== */
const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch (_) { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* quota or disabled */ }
  },
};

/* ===== State ===== */
const state = {
  threads: store.get(STORAGE_KEY, []),
  activeId: store.get(ACTIVE_KEY, null),
  controller: null, // AbortController of the in-flight request
  token: store.get(TOKEN_KEY, null), // bearer token when the server requires a password
};

const uid = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random()).replace(/-/g, "");
const activeThread = () => state.threads.find((t) => t.id === state.activeId) || null;
const busy = () => state.controller !== null;

function persist() {
  state.threads.sort((a, b) => b.updatedAt - a.updatedAt);
  state.threads = state.threads.slice(0, MAX_THREADS);
  store.set(STORAGE_KEY, state.threads);
  store.set(ACTIVE_KEY, state.activeId);
}

/* ===== API ===== */
async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(path, { ...options, headers });
  if (res.status === 401) showLogin();
  return res;
}

async function errorDetail(res) {
  try { return (await res.json()).detail || `HTTP ${res.status}`; } catch (_) { return `HTTP ${res.status}`; }
}

/* ===== Login ===== */
function showLogin(message = "") {
  state.token = null;
  store.set(TOKEN_KEY, null);
  el.loginError.textContent = message;
  el.login.hidden = false;
  el.loginPassword.focus();
}

async function submitLogin(e) {
  e.preventDefault();
  el.loginBtn.disabled = true;
  el.loginError.textContent = "";
  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: el.loginPassword.value }),
    });
    if (!res.ok) { el.loginError.textContent = await errorDetail(res); return; }
    state.token = (await res.json()).token;
    store.set(TOKEN_KEY, state.token);
    el.loginPassword.value = "";
    el.login.hidden = true;
    el.input.focus();
  } catch (_) {
    el.loginError.textContent = "Could not reach the server.";
  } finally {
    el.loginBtn.disabled = false;
  }
}

/* ===== Markdown ===== */
const hasMarkdown = typeof marked !== "undefined" && typeof DOMPurify !== "undefined";
if (hasMarkdown) {
  marked.setOptions({ gfm: true, breaks: true });
  DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A") { node.setAttribute("target", "_blank"); node.setAttribute("rel", "noopener noreferrer"); }
  });
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function renderMarkdown(target, text, { final = false } = {}) {
  target.innerHTML = hasMarkdown ? DOMPurify.sanitize(marked.parse(text)) : escapeHtml(text).replace(/\n/g, "<br>");
  if (!final) return;
  target.querySelectorAll("pre code").forEach((code) => {
    if (typeof hljs !== "undefined") hljs.highlightElement(code);
    const btn = document.createElement("button");
    btn.className = "code-copy";
    btn.type = "button";
    btn.textContent = "Copy";
    btn.addEventListener("click", () => copyText(code.innerText, btn));
    code.parentElement.appendChild(btn);
  });
}

/* ===== Helpers ===== */
let toastTimer;
function toast(message) {
  let node = $(".toast");
  if (!node) { node = document.createElement("div"); node.className = "toast"; document.body.appendChild(node); }
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("show"), 1800);
}

async function copyText(text, button) {
  try {
    await navigator.clipboard.writeText(text);
    if (button) {
      const label = button.querySelector("span") || button;
      const old = label.textContent;
      label.textContent = "Copied";
      setTimeout(() => (label.textContent = old), 1400);
    } else {
      toast("Copied to clipboard");
    }
  } catch (_) {
    toast("Could not access the clipboard");
  }
}

function hostOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch (_) { return url; }
}

function nearBottom() {
  const c = el.chat;
  return c.scrollHeight - c.scrollTop - c.clientHeight < 120;
}

function scrollToBottom(force = false) {
  if (force || nearBottom()) el.chat.scrollTop = el.chat.scrollHeight;
}

/** Run a DOM update and keep the view pinned to the bottom if it was there before. */
function keepPinned(update) {
  const pinned = nearBottom();
  update();
  if (pinned) scrollToBottom(true);
}

/* ===== Message rendering ===== */
function routeBadge(route) {
  const r = ROUTES[route];
  if (!r) return "";
  return `<span class="route" data-route="${route}"><svg viewBox="0 0 24 24">${r.icon}</svg>${r.label}</span>`;
}

function setMeta(node, route) {
  node.querySelector(".msg-meta").innerHTML = `<span class="who">Assistant</span>${routeBadge(route)}`;
}

function setSources(node, sources = []) {
  const box = node.querySelector(".sources");
  box.innerHTML = "";
  const seen = new Set();
  for (const s of sources) {
    if (!s || !s.url || seen.has(s.url) || !/^https?:\/\//i.test(s.url)) continue;
    seen.add(s.url);
    const a = document.createElement("a");
    a.className = "source";
    a.href = s.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.title = `${s.title || ""}\n${s.url}`.trim();
    a.innerHTML = `${LINK}<span></span>`;
    a.querySelector("span").textContent = s.title && s.title !== s.url ? s.title : hostOf(s.url);
    box.appendChild(a);
  }
}

function setThinking(node, label) {
  node.querySelector(".bubble").innerHTML =
    `<span class="thinking"><span class="thinking-dots"><i></i><i></i><i></i></span><span></span></span>`;
  node.querySelector(".thinking span:last-child").textContent = label;
}

function createMessageNode(msg) {
  const node = el.template.content.firstElementChild.cloneNode(true);
  node.classList.add(msg.role);
  if (msg.error) node.classList.add("error");
  const bubble = node.querySelector(".bubble");

  if (msg.role === "user") {
    bubble.textContent = msg.content;
  } else {
    node.querySelector(".avatar").innerHTML = LOGO;
    setMeta(node, msg.route);
    if (msg.error) bubble.textContent = msg.content;
    else renderMarkdown(bubble, msg.content, { final: true });
    setSources(node, msg.sources);
  }
  node.querySelector(".copy").addEventListener("click", (e) => copyText(msg.content, e.currentTarget));
  return node;
}

function renderThread() {
  const thread = activeThread();
  el.messages.innerHTML = "";
  const messages = thread ? thread.messages : [];
  el.welcome.hidden = messages.length > 0;
  el.threadTitle.textContent = thread && messages.length ? thread.title : "New chat";
  el.clearChat.hidden = !messages.length;
  for (const msg of messages) el.messages.appendChild(createMessageNode(msg));
  scrollToBottom(true);
}

function renderThreadList() {
  el.threadList.innerHTML = "";
  const threads = state.threads.filter((t) => t.messages.length);
  if (!threads.length) {
    el.threadList.innerHTML = '<div class="thread-empty">No conversations yet</div>';
    return;
  }
  for (const t of threads) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "thread" + (t.id === state.activeId ? " active" : "");
    item.innerHTML = `<span class="thread-title"></span><span class="icon-btn thread-del" role="button" aria-label="Delete chat" title="Delete">${TRASH}</span>`;
    item.querySelector(".thread-title").textContent = t.title;
    item.addEventListener("click", (e) => {
      if (e.target.closest(".thread-del")) deleteThread(t.id);
      else selectThread(t.id);
    });
    el.threadList.appendChild(item);
  }
}

/* ===== Thread actions ===== */
function newThread() {
  if (busy()) return;
  const current = activeThread();
  if (current && !current.messages.length) { el.input.focus(); closeSidebar(); return; }
  const thread = { id: uid(), title: "New chat", messages: [], updatedAt: Date.now() };
  state.threads.unshift(thread);
  state.activeId = thread.id;
  persist();
  renderThreadList();
  renderThread();
  closeSidebar();
  el.input.focus();
}

function selectThread(id) {
  if (busy() || id === state.activeId) { closeSidebar(); return; }
  state.activeId = id;
  persist();
  renderThreadList();
  renderThread();
  closeSidebar();
}

function deleteThread(id) {
  if (busy() && id === state.activeId) return;
  const thread = state.threads.find((t) => t.id === id);
  if (!thread || !confirm(`Delete "${thread.title}"?`)) return;
  api(`/api/threads/${encodeURIComponent(id)}`, { method: "DELETE" }).catch(() => {});
  state.threads = state.threads.filter((t) => t.id !== id);
  if (state.activeId === id) state.activeId = null;
  persist();
  ensureActiveThread();
  renderThreadList();
  renderThread();
}

function ensureActiveThread() {
  if (activeThread()) return;
  const empty = state.threads.find((t) => !t.messages.length);
  const thread = empty || { id: uid(), title: "New chat", messages: [], updatedAt: Date.now() };
  if (!empty) state.threads.unshift(thread);
  state.activeId = thread.id;
  persist();
}

/* ===== Chat ===== */
function parseSSE(buffer, onEvent) {
  const parts = buffer.split("\n\n");
  const rest = parts.pop();
  for (const part of parts) {
    let event = "message", data = "";
    for (const line of part.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (data) {
      try { onEvent(event, JSON.parse(data)); } catch (e) { console.warn("Bad SSE payload", e); }
    }
  }
  return rest;
}

async function sendMessage(text) {
  text = text.trim();
  if (!text || busy()) return;

  ensureActiveThread();
  const thread = activeThread();
  const userMsg = { role: "user", content: text };
  if (!thread.messages.length) thread.title = text.length > 60 ? text.slice(0, 57) + "…" : text;
  thread.messages.push(userMsg);
  thread.updatedAt = Date.now();
  persist();

  el.welcome.hidden = true;
  el.clearChat.hidden = false;
  el.threadTitle.textContent = thread.title;
  el.messages.appendChild(createMessageNode(userMsg));
  renderThreadList();

  // Placeholder assistant message, filled as events stream in
  const reply = { role: "assistant", content: "", route: null, sources: [] };
  const node = el.template.content.firstElementChild.cloneNode(true);
  node.classList.add("assistant", "streaming");
  node.querySelector(".avatar").innerHTML = LOGO;
  setMeta(node, null);
  setThinking(node, "Routing your message…");
  el.messages.appendChild(node);
  scrollToBottom(true);

  const bubble = node.querySelector(".bubble");
  let streamed = "";
  let frame = 0;
  const paint = () => {
    frame = 0;
    keepPinned(() => renderMarkdown(bubble, streamed));
  };

  setBusy(new AbortController());
  try {
    const res = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, thread_id: thread.id }),
      signal: state.controller.signal,
    });
    if (res.status === 401 || res.status === 429) {
      const detail = res.status === 401 ? "Please log in, then send your message again." : await errorDetail(res);
      throw Object.assign(new Error(detail), { userFacing: true });
    }
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer = parseSSE(buffer + decoder.decode(value, { stream: true }), (event, data) => {
        if (event === "route") {
          reply.route = data.route;
          setMeta(node, data.route);
          if (!streamed) keepPinned(() => setThinking(node, (ROUTES[data.route] || ROUTES.conversation).working));
        } else if (event === "token") {
          streamed += data.text;
          if (!frame) frame = requestAnimationFrame(paint);
        } else if (event === "final") {
          reply.content = data.content;
          reply.sources = data.sources || [];
        } else if (event === "error") {
          reply.error = true;
          reply.content = data.message || "Something went wrong.";
        }
      });
    }
  } catch (err) {
    if (err.name === "AbortError") {
      reply.content = (streamed || reply.content) + "\n\n*— stopped —*";
    } else {
      reply.error = true;
      reply.content = err.userFacing
        ? err.message
        : "Could not reach the server. Make sure the backend is running, then try again.";
      if (!err.userFacing) console.error(err);
    }
  } finally {
    if (frame) cancelAnimationFrame(frame);
    setBusy(null);
  }

  if (!reply.content) reply.content = streamed || "_(No response)_";
  keepPinned(() => {
    node.classList.remove("streaming");
    if (reply.error) {
      node.classList.add("error");
      bubble.textContent = reply.content;
    } else {
      renderMarkdown(bubble, reply.content, { final: true });
      setSources(node, reply.sources);
    }
  });
  node.querySelector(".copy").addEventListener("click", (e) => copyText(reply.content, e.currentTarget));

  thread.messages.push(reply);
  thread.updatedAt = Date.now();
  persist();
}

function setBusy(controller) {
  state.controller = controller;
  el.sendBtn.classList.toggle("busy", !!controller);
  el.sendBtn.setAttribute("aria-label", controller ? "Stop" : "Send");
  updateSendState();
  if (!controller) el.input.focus();
}

function updateSendState() {
  el.sendBtn.disabled = !busy() && !el.input.value.trim();
}

function autoGrow() {
  el.input.style.height = "auto";
  el.input.style.height = Math.min(el.input.scrollHeight, 200) + "px";
}

/* ===== Health ===== */
async function loadHealth() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    if (data.auth_required && !state.token) showLogin();
    el.statusDot.dataset.state = "ok";
    el.statusModel.textContent = data.model.split(/[\\/]/).pop();
    el.statusModel.title = data.model;
    el.features.innerHTML = Object.entries(data.features)
      .map(([k, on]) => `<span class="feature ${on ? "on" : "off"}" title="${on ? "Configured" : "Not configured"}">${FEATURE_LABELS[k] || k}</span>`)
      .join("");
  } catch (_) {
    el.statusDot.dataset.state = "error";
    el.statusModel.textContent = "Backend offline";
    el.features.innerHTML = "";
  }
}

/* ===== Sidebar & theme ===== */
function openSidebar() { el.sidebar.classList.add("open"); el.scrim.classList.add("show"); }
function closeSidebar() { el.sidebar.classList.remove("open"); el.scrim.classList.remove("show"); }

function toggleTheme() {
  const root = document.documentElement;
  const current = root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = current === "dark" ? "light" : "dark";
  root.dataset.theme = next;
  try { localStorage.setItem("theme", next); } catch (_) {}
}

/* ===== Events ===== */
el.composer.addEventListener("submit", (e) => {
  e.preventDefault();
  if (busy()) { state.controller.abort(); return; }
  const text = el.input.value;
  el.input.value = "";
  autoGrow();
  updateSendState();
  sendMessage(text);
});
el.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    if (!busy()) el.composer.requestSubmit();
  }
});
el.input.addEventListener("input", () => { autoGrow(); updateSendState(); });
document.querySelectorAll(".suggestion").forEach((btn) =>
  btn.addEventListener("click", () => sendMessage(btn.dataset.prompt)));
el.newChat.addEventListener("click", newThread);
el.clearChat.addEventListener("click", () => state.activeId && deleteThread(state.activeId));
el.openSidebar.addEventListener("click", openSidebar);
el.closeSidebar.addEventListener("click", closeSidebar);
el.scrim.addEventListener("click", closeSidebar);
el.themeToggle.addEventListener("click", toggleTheme);
el.loginForm.addEventListener("submit", submitLogin);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeSidebar();
});

/* ===== Init ===== */
ensureActiveThread();
renderThreadList();
renderThread();
loadHealth();
el.input.focus();
