(() => {
  const $ = (id) => document.getElementById(id);
  const thread = $("thread");
  const promptEl = $("prompt");
  const sendBtn = $("send");
  const projectName = $("project-name");
  const folderDlg = $("folder-dlg");
  const folderInput = $("folder-input");
  const sessionsDlg = $("sessions-dlg");
  const sessionList = $("session-list");
  const activity = $("activity");
  const menu = $("menu");
  const more = $("more");
  const html = document.documentElement;
  const PERMS = ["ask", "auto", "yolo"];

  const state = {
    workspace: localStorage.getItem("fxs.workspace") || "",
    busy: false,
    demo: true,
    resume: localStorage.getItem("fxs.resume") || "last",
    perm: localStorage.getItem("fxs.perm") || "yolo",
    theme: localStorage.getItem("fxs.theme") || "system",
    history: JSON.parse(localStorage.getItem("fxs.history") || "[]"),
    histIdx: -1,
    abort: null,
    model: "",
  };
  if (localStorage.getItem("fxs.yolo") === "0" && !localStorage.getItem("fxs.perm")) {
    state.perm = "auto";
  }

  function basename(p) {
    if (!p) return "project";
    const parts = p.replace(/\/+$/, "").split("/");
    return parts[parts.length - 1] || p;
  }

  function shortModel(id) {
    if (!id) return "Model";
    return (id.split("/")[1] || id).slice(0, 18);
  }

  function applyTheme() {
    if (state.theme === "system") html.removeAttribute("data-theme");
    else html.setAttribute("data-theme", state.theme);
    localStorage.setItem("fxs.theme", state.theme);
    $("menu-theme").textContent = "Theme · " + state.theme;
  }

  function cycleTheme() {
    state.theme = state.theme === "system" ? "light" : state.theme === "light" ? "dark" : "system";
    applyTheme();
  }

  function setWorkspace(p) {
    state.workspace = (p || "").trim();
    if (state.workspace) localStorage.setItem("fxs.workspace", state.workspace);
    projectName.textContent = basename(state.workspace);
    $("project").title = state.workspace || "Folder";
  }

  function setPerm(p) {
    state.perm = PERMS.includes(p) ? p : "yolo";
    localStorage.setItem("fxs.perm", state.perm);
    $("menu-perm").textContent = state.perm[0].toUpperCase() + state.perm.slice(1);
  }

  function cyclePerm() {
    setPerm(PERMS[(PERMS.indexOf(state.perm) + 1) % PERMS.length]);
  }

  function grow() {
    promptEl.style.height = "auto";
    promptEl.style.height = Math.min(promptEl.scrollHeight, 144) + "px";
  }

  const ENT = {
    "&": "&" + "amp;",
    "<": "&" + "lt;",
    ">": "&" + "gt;",
    '"': "&" + "quot;",
    "'": "&#39;",
  };
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ENT[c]);
  }

  function fuzzy(query, text) {
    const q = (query || "").toLowerCase();
    const t = (text || "").toLowerCase();
    if (!q) return 1;
    const hit = t.indexOf(q);
    if (hit >= 0) return 2000 - hit - (t.length - q.length);
    let i = 0, score = 0, last = -2;
    for (let j = 0; j < t.length && i < q.length; j++) {
      if (t[j] === q[i]) {
        score += j === last + 1 ? 6 : 1;
        if (j === 0 || "/-._".includes(t[j - 1])) score += 10;
        last = j;
        i++;
      }
    }
    return i === q.length ? score : 0;
  }

  function mark(text, query) {
    const q = (query || "").toLowerCase();
    if (!q) return esc(text);
    const t = text.toLowerCase();
    const hit = t.indexOf(q);
    if (hit >= 0) {
      return esc(text.slice(0, hit)) + "<b>" + esc(text.slice(hit, hit + q.length)) + "</b>" +
        esc(text.slice(hit + q.length));
    }
    let i = 0, out = "";
    for (let j = 0; j < text.length; j++) {
      if (i < q.length && t[j] === q[i]) {
        out += "<b>" + esc(text[j]) + "</b>";
        i++;
      } else out += esc(text[j]);
    }
    return out;
  }

  const COMMANDS = [
    { id: "new", hint: "New session" },
    { id: "resume", hint: "Sessions" },
    { id: "models", hint: "Switch model" },
    { id: "permissions", hint: "ask / auto / yolo" },
    { id: "status", hint: "Runtime" },
    { id: "usage", hint: "Local spend" },
    { id: "credits", hint: "Balance" },
    { id: "doctor", hint: "Preflight" },
  ];

  const palette = $("palette");
  const paletteList = $("palette-list");
  let pal = { open: false, kind: "", items: [], idx: 0, start: 0, query: "", timer: 0 };

  function tokenAt() {
    const caret = promptEl.selectionStart || 0;
    const left = promptEl.value.slice(0, caret);
    const m = left.match(/(^|[\s])(\/|@)([^\s]*)$/);
    if (!m) return null;
    return { kind: m[2], query: m[3], start: caret - m[3].length - 1, caret };
  }

  function hidePalette() {
    pal.open = false;
    pal.items = [];
    palette.hidden = true;
    paletteList.innerHTML = "";
  }

  function renderPalette() {
    paletteList.innerHTML = "";
    if (!pal.items.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = pal.kind === "@" ? "No files" : "No commands";
      paletteList.appendChild(li);
      palette.hidden = false;
      pal.open = true;
      return;
    }
    pal.items.forEach((it, i) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", i === pal.idx ? "true" : "false");
      li.innerHTML = '<span class="name">' + mark(it.label, pal.query) + "</span>" +
        (it.hint ? '<span class="hint">' + esc(it.hint) + "</span>" : "");
      li.addEventListener("mousedown", (e) => {
        e.preventDefault();
        pal.idx = i;
        pickPalette();
      });
      paletteList.appendChild(li);
    });
    palette.hidden = false;
    pal.open = true;
    const sel = paletteList.children[pal.idx];
    if (sel && sel.scrollIntoView) sel.scrollIntoView({ block: "nearest" });
  }

  function setPaletteItems(items) {
    pal.items = items;
    pal.idx = 0;
    renderPalette();
  }

  async function updatePalette() {
    const tok = tokenAt();
    if (!tok) { hidePalette(); return; }
    pal.kind = tok.kind;
    pal.query = tok.query;
    pal.start = tok.start;
    if (tok.kind === "/") {
      const rows = COMMANDS
        .map((c) => ({ ...c, label: "/" + c.id, score: fuzzy(tok.query, c.id + " " + c.hint) }))
        .filter((c) => !tok.query || c.score > 0)
        .sort((a, b) => b.score - a.score);
      setPaletteItems(rows);
      return;
    }
    if (!state.workspace) { hidePalette(); return; }
    clearTimeout(pal.timer);
    pal.timer = setTimeout(async () => {
      try {
        const r = await fetch("/api/files?workspace=" + encodeURIComponent(state.workspace) +
          "&q=" + encodeURIComponent(tok.query));
        const data = await r.json();
        setPaletteItems((data.files || []).map((p) => ({ id: p, label: p, hint: "" })));
      } catch { hidePalette(); }
    }, 70);
  }

  function pickPalette() {
    const it = pal.items[pal.idx];
    if (!it) { hidePalette(); return; }
    if (pal.kind === "/") {
      hidePalette();
      promptEl.value = "";
      grow();
      runCommand(it.id);
      return;
    }
    const v = promptEl.value;
    const caret = promptEl.selectionStart || 0;
    const next = v.slice(0, pal.start) + "@" + it.id + " " + v.slice(caret);
    promptEl.value = next;
    const pos = pal.start + it.id.length + 2;
    promptEl.setSelectionRange(pos, pos);
    hidePalette();
    grow();
    promptEl.focus();
  }

  function render(src) {
    const parts = [];
    const re = /```[\s\S]*?```/g;
    let last = 0, m;
    while ((m = re.exec(src))) {
      parts.push(inline(src.slice(last, m.index)));
      parts.push("<pre><code>" + esc(m[0].replace(/^```[^\n]*\n?/, "").replace(/```$/, "")) + "</code></pre>");
      last = m.index + m[0].length;
    }
    parts.push(inline(src.slice(last)));
    return parts.join("");
  }

  function inline(s) {
    return esc(s)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\n/g, "<br>");
  }

  function addMsg(kind, text) {
    const el = document.createElement("div");
    el.className = "msg " + kind;
    if (kind === "user" || kind === "sys") el.textContent = text;
    else if (kind === "tools") el.innerHTML = text;
    else el.innerHTML = render(text || "");
    thread.appendChild(el);
    thread.scrollTop = thread.scrollHeight;
    return el;
  }

  function setBusy(on) {
    state.busy = on;
    sendBtn.classList.toggle("busy", on);
    sendBtn.setAttribute("aria-label", on ? "Stop" : "Send");
  }

  function setActivity(t) {
    activity.hidden = !t;
    activity.textContent = t || "";
  }

  function hideMenu() {
    menu.hidden = true;
    more.setAttribute("aria-expanded", "false");
  }

  function toggleMenu() {
    const open = menu.hidden;
    menu.hidden = !open;
    more.setAttribute("aria-expanded", open ? "true" : "false");
  }

  async function refreshStatus() {
    try {
      const q = state.workspace ? "?workspace=" + encodeURIComponent(state.workspace) : "";
      const s = await (await fetch("/api/status" + q)).json();
      state.demo = !!s.demo;
      state.model = s.model || "";
      if (!state.workspace && s.workspace) setWorkspace(s.workspace);
      $("menu-model").textContent = shortModel(state.model);
      const dot = $("dot");
      dot.className = "dot" + (s.demo ? " off" : s.key === false || s.docker === "idle" ? " warn" : "");
    } catch {
      $("dot").className = "dot warn";
    }
  }

  function ago(ts) {
    if (!ts) return "";
    const s = Math.max(0, (Date.now() / 1000) - ts);
    if (s < 60) return "now";
    if (s < 3600) return Math.floor(s / 60) + "m";
    if (s < 86400) return Math.floor(s / 3600) + "h";
    return Math.floor(s / 86400) + "d";
  }

  async function loadSessions() {
    sessionList.innerHTML = "";
    if (!state.workspace) {
      sessionList.innerHTML = "<li class='id' style='padding:8px'>Open a folder first.</li>";
      return;
    }
    const r = await fetch("/api/sessions?workspace=" + encodeURIComponent(state.workspace));
    const data = await r.json();
    if (!data.sessions || !data.sessions.length) {
      sessionList.innerHTML = "<li class='id' style='padding:8px'>None yet.</li>";
      return;
    }
    data.sessions.forEach((s) => {
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.type = "button";
      b.innerHTML = esc(s.title || "Session") +
        '<span class="id">' + esc(ago(s.mtime) + (s.id ? " · " + s.id.slice(0, 12) : "")) + "</span>";
      b.addEventListener("click", () => {
        state.resume = s.id || "last";
        localStorage.setItem("fxs.resume", state.resume);
        sessionsDlg.close();
      });
      li.appendChild(b);
      sessionList.appendChild(li);
    });
  }

  function newSession() {
    state.resume = "";
    localStorage.removeItem("fxs.resume");
    thread.innerHTML = "";
    refreshStatus();
  }

  async function openModels() {
    const list = $("model-list");
    list.innerHTML = "";
    try {
      const data = await (await fetch("/api/models")).json();
      (data.models || []).forEach((m) => {
        const id = m.id || m;
        const li = document.createElement("li");
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = m.label || id;
        if (id === (data.current || state.model)) b.style.fontWeight = "590";
        b.addEventListener("click", async () => {
          await fetch("/api/model", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model: id }),
          });
          state.model = id;
          $("menu-model").textContent = shortModel(id);
          $("models-dlg").close();
        });
        li.appendChild(b);
        list.appendChild(li);
      });
    } catch {
      list.innerHTML = "<li class='id' style='padding:8px'>Could not load models.</li>";
    }
    $("models-dlg").showModal();
  }

  async function runCommand(id) {
    if (id === "clear" || id === "new") { newSession(); return; }
    if (id === "resume") { await loadSessions(); sessionsDlg.showModal(); return; }
    if (id === "models") { openModels(); return; }
    if (id === "permissions") { cyclePerm(); addMsg("sys", state.perm); return; }
    try {
      const r = await fetch("/api/fx", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ args: [id], workspace: state.workspace, perm: state.perm }),
      });
      const data = await r.json();
      addMsg("sys", (data.text || data.error || "").trim() || ("/" + id));
    } catch (e) {
      addMsg("sys", String(e.message || e));
    }
  }

  async function stop() {
    try { await fetch("/api/stop", { method: "POST" }); } catch { /* ignore */ }
    if (state.abort) state.abort.abort();
  }

  async function send(text) {
    if (state.busy) { stop(); return; }
    if (!text.trim()) return;
    const slash = text.trim();
    if (slash.startsWith("/") && !slash.includes(" ") && !slash.includes("@")) {
      const id = slash.slice(1).toLowerCase();
      if (COMMANDS.some((c) => c.id === id) || id === "clear") {
        promptEl.value = "";
        grow();
        runCommand(id);
        return;
      }
    }
    if (!state.workspace) {
      folderDlg.showModal();
      folderInput.focus();
      return;
    }
    setBusy(true);
    addMsg("user", text);
    promptEl.value = "";
    grow();
    state.history.unshift(text);
    state.history = state.history.slice(0, 40);
    localStorage.setItem("fxs.history", JSON.stringify(state.history));
    state.histIdx = -1;
    const bot = addMsg("assistant", "");
    bot.classList.add("pending");
    let acc = "";
    const ac = new AbortController();
    state.abort = ac;
    setActivity("…");

    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ac.signal,
        body: JSON.stringify({
          prompt: text,
          workspace: state.workspace,
          resume: state.resume || "last",
          perm: state.perm,
        }),
      });
      if (!res.ok || !res.body) throw new Error("request failed");
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const chunks = buf.split("\n\n");
        buf = chunks.pop() || "";
        for (const c of chunks) {
          const line = c.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          let ev;
          try { ev = JSON.parse(line.slice(5).trim()); } catch { continue; }
          if (ev.type === "token") {
            acc += ev.text || "";
            bot.classList.remove("pending");
            bot.innerHTML = render(acc);
          } else if (ev.type === "activity") {
            setActivity(ev.text || "");
          } else if (ev.type === "tools" && ev.tools) {
            const row = addMsg("tools", ev.tools.map((t) =>
              '<span class="tool">' + esc(t.name || t) + "</span>").join(""));
            thread.insertBefore(row, bot);
          } else if (ev.type === "session" && ev.id) {
            state.resume = ev.id;
            localStorage.setItem("fxs.resume", ev.id);
          } else if (ev.type === "model" && ev.id) {
            state.model = ev.id;
            $("menu-model").textContent = shortModel(ev.id);
          } else if (ev.type === "error") {
            bot.classList.add("err");
            if (!acc) acc = ev.text || "failed";
            bot.innerHTML = render(acc);
          }
        }
        thread.scrollTop = thread.scrollHeight;
      }
    } catch (e) {
      if (e.name !== "AbortError" && !acc) {
        bot.classList.add("err");
        bot.textContent = String(e.message || e);
      }
    } finally {
      bot.classList.remove("pending");
      setBusy(false);
      setActivity("");
      state.abort = null;
      promptEl.focus();
      refreshStatus();
    }
  }

  $("composer").addEventListener("submit", (e) => {
    e.preventDefault();
    send(promptEl.value);
  });
  promptEl.addEventListener("input", () => { grow(); updatePalette(); });
  promptEl.addEventListener("keydown", (e) => {
    if (pal.open) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        pal.idx = Math.min(pal.idx + 1, pal.items.length - 1);
        renderPalette();
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        pal.idx = Math.max(pal.idx - 1, 0);
        renderPalette();
        return;
      }
      if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
        e.preventDefault();
        pickPalette();
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        hidePalette();
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(promptEl.value);
    } else if (e.key === "Escape" && state.busy) {
      e.preventDefault();
      stop();
    } else if (e.key === "ArrowUp" && !promptEl.value) {
      if (!state.history.length) return;
      state.histIdx = Math.min(state.histIdx + 1, state.history.length - 1);
      promptEl.value = state.history[state.histIdx] || "";
      grow();
      e.preventDefault();
    } else if (e.key === "ArrowDown" && state.histIdx >= 0) {
      state.histIdx -= 1;
      promptEl.value = state.histIdx < 0 ? "" : state.history[state.histIdx];
      grow();
      e.preventDefault();
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (!menu.hidden) { hideMenu(); return; }
      if (state.busy) stop();
    }
  });
  document.addEventListener("click", (e) => {
    if (!menu.hidden && !menu.contains(e.target) && e.target !== more && !more.contains(e.target)) {
      hideMenu();
    }
  });

  $("project").addEventListener("click", () => {
    folderInput.value = state.workspace;
    folderDlg.showModal();
    folderInput.focus();
    folderInput.select();
  });
  $("folder-form").addEventListener("submit", (e) => {
    if (e.submitter && e.submitter.value === "ok") {
      setWorkspace(folderInput.value);
      state.resume = "last";
      refreshStatus();
    }
  });
  $("new-session").addEventListener("click", (e) => {
    e.preventDefault();
    newSession();
    sessionsDlg.close();
  });
  more.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleMenu();
  });
  menu.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    hideMenu();
    const act = btn.getAttribute("data-act");
    if (act === "new") newSession();
    else if (act === "sessions") { await loadSessions(); sessionsDlg.showModal(); }
    else if (act === "model") openModels();
    else if (act === "perm") cyclePerm();
    else if (act === "theme") cycleTheme();
  });

  applyTheme();
  setPerm(state.perm);
  setWorkspace(state.workspace);
  refreshStatus();
  promptEl.focus();
})();
