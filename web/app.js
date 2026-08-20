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
  const activity = $("activity");
  const permBtn = $("perm-btn");
  const html = document.documentElement;

  const state = {
    workspace: localStorage.getItem("fxs.workspace") || "",
    busy: false,
    demo: true,
    resume: localStorage.getItem("fxs.resume") || "last",
    yolo: localStorage.getItem("fxs.yolo") !== "0",
    theme: localStorage.getItem("fxs.theme") || "system",
    history: JSON.parse(localStorage.getItem("fxs.history") || "[]"),
    histIdx: -1,
    abort: null,
    model: "",
  };

  function basename(p) {
    if (!p) return "project";
    const parts = p.replace(/\/+$/, "").split("/");
    return parts[parts.length - 1] || p;
  }

  function applyTheme() {
    if (state.theme === "system") html.removeAttribute("data-theme");
    else html.setAttribute("data-theme", state.theme);
    localStorage.setItem("fxs.theme", state.theme);
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

  function grow() {
    promptEl.style.height = "auto";
    promptEl.style.height = Math.min(promptEl.scrollHeight, 144) + "px";
  }

  function esc(s) {
    return s.replace(/[&<>]/g, (c) => ({ "&": "&", "<": "<", ">": ">" }[c]));
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

  async function refreshStatus() {
    try {
      const q = state.workspace ? "?workspace=" + encodeURIComponent(state.workspace) : "";
      const s = await (await fetch("/api/status" + q)).json();
      state.demo = !!s.demo;
      state.model = s.model || "";
      if (!state.workspace && s.workspace) setWorkspace(s.workspace);
      const bits = [];
      if (s.demo) bits.push('<span class="dot off"></span>demo');
      else bits.push('<span class="dot"></span>' + (s.model || "fxs"));
      if (s.key === false) bits.push("no key");
      if (!s.demo && s.docker === "idle") bits.push("docker off");
      if (state.resume && state.resume !== "last") bits.push("resume");
      else if (state.resume === "last") bits.push("last");
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
      b.innerHTML = (s.title || "Session") +
        '<span class="id">' + (ago(s.mtime) + (s.id ? " · " + s.id.slice(0, 12) : "")) + "</span>";
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

  async function stop() {
    try { await fetch("/api/stop", { method: "POST" }); } catch { /* ignore */ }
    if (state.abort) state.abort.abort();
  }

  async function send(text) {
    if (state.busy) { stop(); return; }
    if (!text.trim()) return;
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
    setActivity("running");

    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ac.signal,
        body: JSON.stringify({
          prompt: text,
          workspace: state.workspace,
          resume: state.resume || "last",
          yolo: state.yolo,
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
  promptEl.addEventListener("input", grow);
  promptEl.addEventListener("keydown", (e) => {
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
    if (e.key === "Escape" && state.busy) stop();
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
    state.resume = "";
    localStorage.removeItem("fxs.resume");
    thread.innerHTML = "";
    sessionsDlg.close();
    refreshStatus();
  });
  permBtn.addEventListener("click", () => setYolo(!state.yolo));
  $("theme-btn").addEventListener("click", cycleTheme);

  applyTheme();
  setYolo(state.yolo);
  setWorkspace(state.workspace);
  refreshStatus();
  promptEl.focus();
})();
