(() => {
  const $ = (id) => document.getElementById(id);
  const thread = $("thread");
  const promptEl = $("prompt");
  const sendBtn = $("send");
  const projectBtn = $("project");
  const projectName = $("project-name");
  const meta = $("meta");
  const folderDlg = $("folder-dlg");
  const folderInput = $("folder-input");
  const sessionsDlg = $("sessions-dlg");
  const sessionList = $("session-list");

  const state = {
    workspace: localStorage.getItem("fxs.workspace") || "",
    busy: false,
    demo: true,
    resume: null,
  };

  function basename(p) {
    if (!p) return "project";
    const parts = p.replace(/\/+$/, "").split("/");
    return parts[parts.length - 1] || p;
  }

  function setWorkspace(p) {
    state.workspace = (p || "").trim();
    if (state.workspace) localStorage.setItem("fxs.workspace", state.workspace);
    projectName.textContent = basename(state.workspace);
    projectBtn.title = state.workspace || "Workspace";
  }

  function grow() {
    promptEl.style.height = "auto";
    promptEl.style.height = Math.min(promptEl.scrollHeight, 144) + "px";
  }

  function addMsg(kind, text) {
    const el = document.createElement("div");
    el.className = "msg " + kind;
    if (kind === "user") el.textContent = text;
    else if (kind === "log") el.textContent = text;
    else el.innerHTML = render(text);
    thread.appendChild(el);
    thread.scrollTop = thread.scrollHeight;
    return el;
  }

  function escapeHtml(s) {
    return s.replace(/[&<>]/g, (c) => ({ "&": "&", "<": "<", ">": ">" }[c]));
  }

  function render(src) {
    const parts = [];
    const re = /```[\s\S]*?```/g;
    let last = 0;
    let m;
    while ((m = re.exec(src))) {
      parts.push(inline(src.slice(last, m.index)));
      parts.push("<pre><code>" + escapeHtml(m[0].replace(/^```[^\n]*\n?/, "").replace(/```$/, "")) + "</code></pre>");
      last = m.index + m[0].length;
    }
    parts.push(inline(src.slice(last)));
    return parts.join("");
  }

  function inline(s) {
    return escapeHtml(s)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  }

  async function refreshStatus() {
    try {
      const q = state.workspace ? "?workspace=" + encodeURIComponent(state.workspace) : "";
      const s = await (await fetch("/api/status" + q)).json();
      state.demo = !!s.demo;
      if (!state.workspace && s.workspace) setWorkspace(s.workspace);
      const bits = [];
      bits.push((s.demo ? '<span class="dot off"></span>demo' : '<span class="dot"></span>' + (s.model || "fxs")));
      if (s.key === false) bits.push("no key");
      meta.innerHTML = bits.join(" · ");
    } catch {
      meta.innerHTML = '<span class="dot off"></span>offline';
    }
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
      b.innerHTML = (s.title || "Session") + '<span class="id">' + (s.id || "") + "</span>";
      b.addEventListener("click", () => {
        state.resume = s.id;
        sessionsDlg.close();
      });
      li.appendChild(b);
      sessionList.appendChild(li);
    });
  }

  async function send(text) {
    if (state.busy || !text.trim()) return;
    if (!state.workspace) {
      folderDlg.showModal();
      folderInput.focus();
      return;
    }
    state.busy = true;
    sendBtn.disabled = true;
    addMsg("user", text);
    promptEl.value = "";
    grow();
    const bot = addMsg("assistant", "");
    bot.classList.add("pending");
    let acc = "";

    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: text,
          workspace: state.workspace,
          resume: state.resume,
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
          } else if (ev.type === "log") {
            addMsg("log", ev.text || "");
          } else if (ev.type === "error") {
            bot.classList.remove("pending");
            acc = acc || (ev.text || "failed");
            bot.innerHTML = render(acc);
          }
        }
        thread.scrollTop = thread.scrollHeight;
      }
    } catch (e) {
      bot.classList.remove("pending");
      if (!acc) bot.textContent = String(e.message || e);
    } finally {
      bot.classList.remove("pending");
      state.busy = false;
      sendBtn.disabled = false;
      promptEl.focus();
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
    }
  });

  projectBtn.addEventListener("click", () => {
    folderInput.value = state.workspace;
    folderDlg.showModal();
    folderInput.focus();
    folderInput.select();
  });
  $("folder-form").addEventListener("submit", (e) => {
    const v = e.submitter && e.submitter.value;
    if (v === "ok") setWorkspace(folderInput.value);
  });

  $("sessions-btn").addEventListener("click", async () => {
    await loadSessions();
    sessionsDlg.showModal();
  });
  $("new-session").addEventListener("click", (e) => {
    e.preventDefault();
    state.resume = null;
    thread.innerHTML = "";
    sessionsDlg.close();
  });

  setWorkspace(state.workspace);
  refreshStatus();
  promptEl.focus();
})();
