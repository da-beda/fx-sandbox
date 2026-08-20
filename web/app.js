(() => {
  const $ = (id) => document.getElementById(id);
  const thread = $("thread");
  const promptEl = $("prompt");
  const sendBtn = $("send");
  const projectName = $("project-name");
  const meta = $("meta");
  const folderDlg = $("folder-dlg");
  const folderInput = $("folder-input");
  const sessionsDlg = $("sessions-dlg");
  const sessionList = $("session-list");
  const modelDlg = $("model-dlg");
  const modelList = $("model-list");
  const activity = $("activity");
  const permBtn = $("perm-btn");
  const modelBtn = $("model-btn");
  const slashEl = $("slash");
  const html = document.documentElement;
  const themeMeta = document.querySelectorAll('meta[name="theme-color"]');

  const COMMANDS = [
    { cmd: "/new", hint: "Fresh session" },
    { cmd: "/resume", hint: "Continue last" },
    { cmd: "/yolo", hint: "No tool prompts" },
    { cmd: "/auto", hint: "Ask before tools" },
    { cmd: "/model", hint: "Pick a model" },
    { cmd: "/copy", hint: "Copy last reply" },
    { cmd: "/clear", hint: "Clear this view" },
  ];

  const state = {
    workspace: localStorage.getItem("fxs.workspace") || "",
    busy: false,
    demo: true,
    resume: localStorage.getItem("fxs.resume") || "last",
    yolo: localStorage.getItem("fxs.yolo") !== "0",
    theme: localStorage.getItem("fxs.theme") || "system",
    model: localStorage.getItem("fxs.model") || "zai/glm-5.2",
    history: JSON.parse(localStorage.getItem("fxs.history") || "[]"),
    histIdx: -1,
    abort: null,
    slashIdx: 0,
    lastReply: "",
  };

  function basename(p) {
    if (!p) return "project";
    const parts = p.replace(/\/+$/, "").split("/");
    return parts[parts.length - 1] || p;
  }

  function shortModel(id) {
    return (id || "").split("/").pop() || "model";
  }

  function applyTheme() {
    if (state.theme === "system") html.removeAttribute("data-theme");
    else html.setAttribute("data-theme", state.theme);
    localStorage.setItem("fxs.theme", state.theme);
    const dark = state.theme === "dark" ||
      (state.theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
    const color = dark ? "#000000" : "#f5f5f7";
    themeMeta.forEach((m) => m.setAttribute("content", color));
    $("theme-btn").title = "Theme · " + state.theme;
  }

  function cycleTheme() {
    state.theme = state.theme === "system" ? "light" : state.theme === "light" ? "dark" : "system";
    applyTheme();
  }

  function setWorkspace(p) {
    state.workspace = (p || "").trim();
    if (state.workspace) localStorage.setItem("fxs.workspace", state.workspace);
    projectName.textContent = basename(state.workspace);
    $("project").title = state.workspace || "Workspace";
  }

  function setYolo(on) {
    state.yolo = on;
    localStorage.setItem("fxs.yolo", on ? "1" : "0");
    permBtn.textContent = on ? "yolo" : "auto";
    permBtn.classList.toggle("on", on);
  }

  function setModel(id) {
    if (!id) return;
    state.model = id;
    localStorage.setItem("fxs.model", id);
    modelBtn.textContent = shortModel(id);
    modelBtn.title = id;
  }

  function grow() {
    promptEl.style.height = "auto";
    promptEl.style.height = Math.min(promptEl.scrollHeight, 144) + "px";
  }

  function esc(s) {
    return String(s).replace(/[&<>]/g, (c) => ({ "&": "&", "<": "<", ">": ">" }[c]));
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

  function addCopy(el) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "copy";
    b.title = "Copy";
    b.setAttribute("aria-label", "Copy");
    b.innerHTML = '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="5.5" y="5.5" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M10 5V3.8A1.3 1.3 0 0 0 8.7 2.5H3.8A1.3 1.3 0 0 0 2.5 3.8v4.9A1.3 1.3 0 0 0 3.8 10H5" stroke="currentColor" stroke-width="1.3"/></svg>';
    b.addEventListener("click", () => {
      const t = state.lastReply || el.innerText;
      navigator.clipboard.writeText(t).catch(() => {});
    });
    el.appendChild(b);
  }

  function addMsg(kind, text) {
    const el = document.createElement("div");
    el.className = "msg " + kind;
    if (kind === "user") el.textContent = text;
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

  function hideSlash() {
    slashEl.hidden = true;
    slashEl.innerHTML = "";
  }

  function filteredSlash() {
    const v = promptEl.value;
    if (!v.startsWith("/") || v.includes(" ") && !v.startsWith("/model ")) return [];
    const q = v.split(/\s/)[0].toLowerCase();
    return COMMANDS.filter((c) => c.cmd.startsWith(q));
  }

  function renderSlash() {
    const items = filteredSlash();
    if (!items.length) { hideSlash(); return; }
    state.slashIdx = Math.max(0, Math.min(state.slashIdx, items.length - 1));
    slashEl.hidden = false;
    slashEl.innerHTML = items.map((c, i) =>
      "<li class='" + (i === state.slashIdx ? "on" : "") + "'><button type='button' data-cmd='" +
      esc(c.cmd) + "'><span class='cmd'>" + esc(c.cmd) + "</span><span class='hint'>" +
      esc(c.hint) + "</span></button></li>"
    ).join("");
  }

  function runSlash(raw) {
    const [cmd, ...rest] = raw.trim().split(/\s+/);
    hideSlash();
    promptEl.value = "";
    grow();
    if (cmd === "/new" || cmd === "/clear") {
      state.resume = "";
      localStorage.removeItem("fxs.resume");
      thread.innerHTML = "";
      refreshStatus();
      return true;
    }
    if (cmd === "/resume") {
      state.resume = "last";
      localStorage.setItem("fxs.resume", "last");
      refreshStatus();
      return true;
    }
    if (cmd === "/yolo") { setYolo(true); return true; }
    if (cmd === "/auto") { setYolo(false); return true; }
    if (cmd === "/model") {
      if (rest[0]) setModel(rest.join(" "));
      else openModels();
      return true;
    }
    if (cmd === "/copy") {
      if (state.lastReply) navigator.clipboard.writeText(state.lastReply).catch(() => {});
      return true;
    }
    return false;
  }

  async function refreshStatus() {
    try {
      const q = state.workspace ? "?workspace=" + encodeURIComponent(state.workspace) : "";
      const s = await (await fetch("/api/status" + q)).json();
      state.demo = !!s.demo;
      if (s.model && !localStorage.getItem("fxs.model")) setModel(s.model);
      if (!state.workspace && s.workspace) setWorkspace(s.workspace);
      setModel(state.model);
      const bits = [];
      if (s.demo) bits.push('<span class="dot off"></span>demo');
      else bits.push('<span class="dot"></span>sandbox');
      if (s.key === false) bits.push("no key");
      if (!s.demo && s.docker === "idle") bits.push("docker off");
      if (state.resume === "last") bits.push("last");
      else if (state.resume) bits.push("session");
      meta.innerHTML = bits.join(" · ");
    } catch {
      meta.innerHTML = '<span class="dot warn"></span>offline';
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
      sessionList.innerHTML = "<li class='meta' style='padding:8px'>Open a folder first.</li>";
      return;
    }
    const r = await fetch("/api/sessions?workspace=" + encodeURIComponent(state.workspace));
    const data = await r.json();
    if (!data.sessions || !data.sessions.length) {
      sessionList.innerHTML = "<li class='meta' style='padding:8px'>None yet.</li>";
      return;
    }
    data.sessions.forEach((s) => {
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.type = "button";
      b.innerHTML = esc(s.title || "Session") +
        '<span class="id">' + esc(ago(s.mtime) + (s.id ? " · " + s.id.slice(0, 18) : "")) + "</span>";
      b.addEventListener("click", () => {
        state.resume = s.id || "last";
        localStorage.setItem("fxs.resume", state.resume);
        sessionsDlg.close();
        refreshStatus();
      });
      li.appendChild(b);
      sessionList.appendChild(li);
    });
  }

  async function openModels() {
    modelList.innerHTML = "";
    let models = [];
    try {
      const data = await (await fetch("/api/models")).json();
      models = data.models || [];
    } catch { models = [{ id: state.model }]; }
    if (!models.length) models = [{ id: state.model }];
    models.forEach((m) => {
      const id = m.id || m;
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.type = "button";
      b.className = id === state.model ? "on" : "";
      b.innerHTML = esc(shortModel(id)) + '<span class="id">' + esc(id) + (m.note ? " · " + m.note : "") + "</span>";
      b.addEventListener("click", () => {
        setModel(id);
        modelDlg.close();
      });
      li.appendChild(b);
      modelList.appendChild(li);
    });
    modelDlg.showModal();
  }

  async function stop() {
    try { await fetch("/api/stop", { method: "POST" }); } catch { /* ignore */ }
    if (state.abort) state.abort.abort();
  }

  async function send(text) {
    if (state.busy) { stop(); return; }
    const trimmed = (text || "").trim();
    if (!trimmed) return;
    if (trimmed.startsWith("/")) {
      if (runSlash(trimmed)) return;
    }
    if (!state.workspace) {
      folderDlg.showModal();
      folderInput.focus();
      return;
    }
    setBusy(true);
    addMsg("user", trimmed);
    promptEl.value = "";
    grow();
    hideSlash();
    state.history.unshift(trimmed);
    state.history = state.history.slice(0, 40);
    localStorage.setItem("fxs.history", JSON.stringify(state.history));
    state.histIdx = -1;
    const bot = addMsg("assistant", "");
    bot.classList.add("pending");
    let acc = "";
    const ac = new AbortController();
    state.abort = ac;
    setActivity("running");

    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ac.signal,
        body: JSON.stringify({
          prompt: trimmed,
          workspace: state.workspace,
          resume: state.resume || "last",
          yolo: state.yolo,
          model: state.model,
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
      state.lastReply = acc;
      addCopy(bot);
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
  promptEl.addEventListener("input", () => {
    grow();
    state.slashIdx = 0;
    renderSlash();
  });
  promptEl.addEventListener("keydown", (e) => {
    if (!slashEl.hidden && (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Tab" || (e.key === "Enter" && promptEl.value.startsWith("/")))) {
      const items = filteredSlash();
      if (items.length) {
        if (e.key === "ArrowDown") { state.slashIdx = (state.slashIdx + 1) % items.length; renderSlash(); e.preventDefault(); return; }
        if (e.key === "ArrowUp") { state.slashIdx = (state.slashIdx - 1 + items.length) % items.length; renderSlash(); e.preventDefault(); return; }
        if (e.key === "Tab" || e.key === "Enter") {
          const c = items[state.slashIdx];
          if (c.cmd === "/model") { promptEl.value = "/model "; hideSlash(); }
          else runSlash(c.cmd);
          e.preventDefault();
          return;
        }
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(promptEl.value);
    } else if (e.key === "Escape" && state.busy) {
      e.preventDefault();
      stop();
    } else if (e.key === "ArrowUp" && !promptEl.value && slashEl.hidden) {
      if (!state.history.length) return;
      state.histIdx = Math.min(state.histIdx + 1, state.history.length - 1);
      promptEl.value = state.history[state.histIdx] || "";
      grow();
      e.preventDefault();
    } else if (e.key === "ArrowDown" && state.histIdx >= 0 && slashEl.hidden) {
      state.histIdx -= 1;
      promptEl.value = state.histIdx < 0 ? "" : state.history[state.histIdx];
      grow();
      e.preventDefault();
    }
  });
  slashEl.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-cmd]");
    if (!b) return;
    if (b.dataset.cmd === "/model") { promptEl.value = "/model "; hideSlash(); promptEl.focus(); }
    else runSlash(b.dataset.cmd);
  });

  document.addEventListener("keydown", (e) => {
    const mod = e.metaKey || e.ctrlKey;
    if (e.key === "Escape" && state.busy) stop();
    if (mod && e.key === "n") { e.preventDefault(); runSlash("/new"); }
    if (mod && e.key === ".") { e.preventDefault(); stop(); }
    if (mod && e.key === "k") { e.preventDefault(); promptEl.value = "/"; promptEl.focus(); renderSlash(); }
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
  $("sessions-btn").addEventListener("click", async () => {
    await loadSessions();
    sessionsDlg.showModal();
  });
  $("new-session").addEventListener("click", (e) => {
    e.preventDefault();
    runSlash("/new");
    sessionsDlg.close();
  });
  permBtn.addEventListener("click", () => setYolo(!state.yolo));
  modelBtn.addEventListener("click", () => openModels());
  $("theme-btn").addEventListener("click", cycleTheme);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);

  document.querySelectorAll("dialog").forEach((d) => {
    d.addEventListener("click", (e) => { if (e.target === d) d.close(); });
  });

  applyTheme();
  setYolo(state.yolo);
  setModel(state.model);
  setWorkspace(state.workspace);
  refreshStatus();
  promptEl.focus();
})();
