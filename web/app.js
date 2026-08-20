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
  const mac = /Mac|iPhone|iPad/.test(navigator.userAgent);
  const mod = mac ? "⌘" : "Ctrl+";

  const ICO = {
    chev: '<svg viewBox="0 0 16 16" width="12" height="12"><path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    folder: '<svg viewBox="0 0 16 16" width="14" height="14"><path d="M2.5 4.5h4l1 1.5h6v7.5h-11z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
    file: '<svg viewBox="0 0 16 16" width="14" height="14"><path d="M4.5 2.5h5l3 3v8h-8zM9.5 2.5v3h3" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
    image: '<svg viewBox="0 0 16 16" width="14" height="14"><rect x="2.5" y="3.5" width="11" height="9" rx="1.4" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M2.8 11.2 6 8.2l2.2 2.2 2-1.8 3 2.6" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><circle cx="5.2" cy="6.2" r="0.9" fill="currentColor"/></svg>',
    go: '<svg viewBox="0 0 16 16" width="12" height="12"><path d="M6 3.5h6.5V10M12.5 3.5 3.5 12.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  };

  const IMG_EXT = /\.(png|jpe?g|gif|webp|ico)$/i;

  function readJson(key, fallback) {
    try {
      const v = JSON.parse(localStorage.getItem(key) || "null");
      return v == null ? fallback : v;
    } catch {
      return fallback;
    }
  }

  const state = {
    workspace: localStorage.getItem("fxs.workspace") || "",
    busy: false,
    demo: true,
    resume: localStorage.getItem("fxs.resume") || "last",
    perm: localStorage.getItem("fxs.perm") || (localStorage.getItem("fxs.yolo") === "0" ? "auto" : "yolo"),
    theme: localStorage.getItem("fxs.theme") || "system",
    history: readJson("fxs.history", []),
    histIdx: -1,
    abort: null,
    model: "",
    queue: [],
    lastAnswer: "",
    treeOn: localStorage.getItem("fxs.tree") !== "0",
    expanded: Object.fromEntries((readJson("fxs.expanded", []) || []).map((k) => [k, true])),
    openPath: "",
    orig: "",
    wrap: localStorage.getItem("fxs.wrap") === "1",
    treeW: parseInt(localStorage.getItem("fxs.treeW") || "0", 10) || 0,
    edW: parseInt(localStorage.getItem("fxs.edW") || "0", 10) || 0,
    treeData: null,
    edSize: 0,
  };

  function basename(p) {
    if (!p) return "project";
    const parts = p.replace(/\/+$/, "").split("/");
    return parts[parts.length - 1] || p;
  }

  function dirname(p) {
    const i = (p || "").lastIndexOf("/");
    return i <= 0 ? "" : p.slice(0, i);
  }

  function prettySize(n) {
    n = Number(n) || 0;
    if (n < 1000) return n + " B";
    if (n < 1024 * 1024) {
      const k = n / 1024;
      return (k < 10 ? k.toFixed(1) : Math.round(k)) + " KB";
    }
    return (n / 1048576).toFixed(1) + " MB";
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
    if (state.treeOn) loadTree();
  }

  function setPerm(p) {
    const next = p === "ask" || p === "auto" || p === "yolo" ? p : "yolo";
    state.perm = next;
    localStorage.setItem("fxs.perm", next);
    permBtn.textContent = next;
    permBtn.classList.toggle("on", next === "yolo");
    permBtn.title = "Permissions · " + next;
  }

  function cyclePerm() {
    const order = ["ask", "auto", "yolo"];
    setPerm(order[(order.indexOf(state.perm) + 1) % order.length]);
  }

  function newSession() {
    state.resume = "";
    localStorage.removeItem("fxs.resume");
    state.queue = [];
    state.lastAnswer = "";
    thread.innerHTML = "";
    refreshStatus();
    promptEl.focus();
  }

  function grow() {
    promptEl.style.height = "auto";
    promptEl.style.height = Math.min(promptEl.scrollHeight, 144) + "px";
  }

  function esc(s) {
    const ent = { "&": "&" + "amp;", "<": "&" + "lt;", ">": "&" + "gt;", '"': "&" + "quot;" };
    return String(s).replace(/[&<>"]/g, (c) => ent[c]);
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
        if (j === 0 || "/-_.".includes(t[j - 1])) score += 10;
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
    { id: "clear", hint: "New session" },
    { id: "new", hint: "New session" },
    { id: "resume", hint: "Pick a session" },
    { id: "compact", hint: "Summarize older turns" },
    { id: "copy", hint: "Copy last reply" },
    { id: "models", hint: "Switch model" },
    { id: "permissions", hint: "ask / auto / yolo" },
    { id: "status", hint: "Runtime" },
    { id: "usage", hint: "Local spend" },
    { id: "credits", hint: "Gateway balance" },
    { id: "doctor", hint: "Preflight" },
    { id: "files", hint: "Toggle explorer" },
    { id: "help", hint: "Commands" },
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
    $("palette-hint").textContent = pal.kind === "@"
      ? "Enter to mention  ·  Shift+Enter to open"
      : "Enter to run";
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
      const name = document.createElement("span");
      name.className = "name";
      name.innerHTML = mark(it.label, pal.query);
      li.appendChild(name);
      if (it.hint) {
        const hint = document.createElement("span");
        hint.className = "hint";
        hint.textContent = it.hint;
        li.appendChild(hint);
      }
      if (pal.kind === "@") {
        const go = document.createElement("button");
        go.type = "button";
        go.className = "pal-go";
        go.title = "Open";
        go.innerHTML = ICO.go;
        go.addEventListener("mousedown", (e) => {
          e.preventDefault();
          e.stopPropagation();
          pal.idx = i;
          pickPalette(true);
        });
        li.appendChild(go);
      }
      li.addEventListener("mousedown", (e) => {
        if (e.target.closest(".pal-go")) return;
        e.preventDefault();
        pal.idx = i;
        pickPalette(e.altKey || e.metaKey || e.shiftKey);
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
        const files = (data.files || []).map((p) => ({
          id: p, label: p, hint: "", score: fuzzy(tok.query, p),
        }));
        setPaletteItems(files);
      } catch { hidePalette(); }
    }, 70);
  }

  function pickPalette(openFileToo) {
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
    if (openFileToo) openFile(it.id);
  }

  function mention(path) {
    if (!path) return;
    const v = promptEl.value;
    const caret = promptEl.selectionStart || v.length;
    const need = caret > 0 && !/\s$/.test(v.slice(0, caret)) ? " " : "";
    const ins = need + "@" + path + " ";
    promptEl.value = v.slice(0, caret) + ins + v.slice(caret);
    const pos = caret + ins.length;
    promptEl.setSelectionRange(pos, pos);
    grow();
    promptEl.focus();
  }

  function showInfo(title, text) {
    $("info-title").textContent = title;
    $("info-body").textContent = text || "";
    $("info-dlg").showModal();
  }

  async function runCommand(id) {
    if (id === "clear" || id === "new") {
      newSession();
      return;
    }
    if (id === "copy") {
      if (state.lastAnswer) navigator.clipboard.writeText(state.lastAnswer);
      return;
    }
    if (id === "compact") {
      if (!state.workspace) return;
      send("Compact the earlier turns of this session. Keep the last few messages intact.");
      return;
    }
    if (id === "resume") {
      await loadSessions();
      sessionsDlg.showModal();
      return;
    }
    if (id === "models") { openModels(); return; }
    if (id === "permissions") { cyclePerm(); return; }
    if (id === "files") { toggleTree(); return; }
    if (id === "help") {
      showInfo("Commands", COMMANDS.map((c) => "/" + c.id + "  " + c.hint).join("\n"));
      return;
    }
    if (["status", "usage", "credits", "doctor"].includes(id)) {
      try {
        const r = await fetch("/api/fx", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ args: [id], workspace: state.workspace }),
        });
        const data = await r.json();
        showInfo("/" + id, data.text || data.error || JSON.stringify(data, null, 2));
      } catch (e) {
        showInfo("/" + id, String(e.message || e));
      }
    }
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
        b.textContent = m.label ? m.label + "  " + id : id;
        if (id === (data.current || state.model)) b.style.fontWeight = "590";
        b.addEventListener("click", async () => {
          await fetch("/api/model", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model: id }),
          });
          $("model-btn").textContent = (id.split("/")[1] || id).slice(0, 16);
          $("models-dlg").close();
          refreshStatus();
        });
        li.appendChild(b);
        list.appendChild(li);
      });
    } catch {
      list.innerHTML = "<li class='meta' style='padding:8px'>Could not load models.</li>";
    }
    $("models-dlg").showModal();
  }

  function mobile() {
    return window.matchMedia("(max-width: 860px)").matches;
  }

  function syncChrome() {
    const edOn = !$("editor").hidden;
    $("split-tree").hidden = !state.treeOn || mobile();
    $("split-ed").hidden = !edOn || mobile();
    $("veil").hidden = !(mobile() && (state.treeOn || edOn));
    $("files-btn").classList.toggle("on", state.treeOn);
  }

  function toggleTree(force) {
    state.treeOn = typeof force === "boolean" ? force : !state.treeOn;
    localStorage.setItem("fxs.tree", state.treeOn ? "1" : "0");
    $("tree").hidden = !state.treeOn;
    if (state.treeW && state.treeOn && !mobile()) $("tree").style.width = state.treeW + "px";
    syncChrome();
    if (state.treeOn) loadTree();
  }

  function persistExpanded() {
    const on = Object.keys(state.expanded).filter((k) => state.expanded[k]).slice(0, 80);
    localStorage.setItem("fxs.expanded", JSON.stringify(on));
  }

  function expandTo(rel) {
    const parts = (rel || "").split("/");
    let acc = "";
    for (let i = 0; i < parts.length - 1; i++) {
      acc = acc ? acc + "/" + parts[i] : parts[i];
      state.expanded[acc] = true;
    }
    persistExpanded();
  }

  function flatten(nodes, acc) {
    (nodes || []).forEach((n) => {
      acc.push(n);
      if (n.children) flatten(n.children, acc);
    });
    return acc;
  }

  function matchNode(node, q) {
    if (!q) return true;
    if (fuzzy(q, node.path || node.name) > 0) return true;
    return (node.children || []).some((c) => matchNode(c, q));
  }

  function fileIcon(name) {
    return IMG_EXT.test(name) ? ICO.image : ICO.file;
  }

  function treeButton(n, depth, q, flat) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "tree-item" + (n.path === state.openPath ? " on" : "") +
      (n.type === "dir" && (state.expanded[n.path] || q) ? " open" : "");
    b.style.paddingLeft = (flat ? 8 : 8 + depth * 12) + "px";
    b.tabIndex = -1;
    b.dataset.path = n.path || "";
    b.dataset.type = n.type;
    b.setAttribute("role", "treeitem");
    if (n.type === "dir") b.setAttribute("aria-expanded", state.expanded[n.path] || q ? "true" : "false");

    const chev = document.createElement("span");
    chev.className = "chev";
    chev.innerHTML = n.type === "dir" ? ICO.chev : "";
    const kind = document.createElement("span");
    kind.className = "kind";
    kind.innerHTML = n.type === "dir" ? ICO.folder : fileIcon(n.name);
    const nm = document.createElement("span");
    nm.className = "nm";
    nm.innerHTML = q ? mark(n.name, q) : esc(n.name);
    b.appendChild(chev);
    b.appendChild(kind);
    b.appendChild(nm);
    if (flat && n.path && n.path !== n.name) {
      const sub = document.createElement("span");
      sub.className = "sub";
      sub.textContent = dirname(n.path);
      b.appendChild(sub);
    }
    if (n.type === "file") {
      const at = document.createElement("span");
      at.className = "at";
      at.textContent = "@";
      at.title = "Mention";
      at.addEventListener("click", (e) => {
        e.stopPropagation();
        mention(n.path);
      });
      b.appendChild(at);
      b.draggable = true;
      b.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData("text/plain", "@" + n.path + " ");
        e.dataTransfer.effectAllowed = "copy";
      });
    }
    b.addEventListener("click", (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) {
        mention(n.path || n.name);
        return;
      }
      if (n.type === "dir") {
        if (q) {
          $("tree-q").value = "";
          expandTo(n.path + "/x");
          state.expanded[n.path] = true;
          persistExpanded();
          renderTree(n.path);
          return;
        }
        state.expanded[n.path] = !state.expanded[n.path];
        persistExpanded();
        renderTree();
      } else openFile(n.path);
    });
    return b;
  }

  function renderTree(scrollTo) {
    const host = $("tree-list");
    const q = ($("tree-q").value || "").trim();
    host.innerHTML = "";
    const data = state.treeData;
    if (!data || !(data.children || []).length) {
      const p = document.createElement("p");
      p.className = "tree-empty";
      if (!state.workspace) {
        p.appendChild(document.createTextNode("Open a folder to browse the same files the agent sees."));
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = "Open folder";
        btn.addEventListener("click", () => $("project").click());
        p.appendChild(document.createElement("br"));
        p.appendChild(btn);
      } else {
        p.textContent = "Nothing here.";
      }
      host.appendChild(p);
      $("tree-count").textContent = "";
      return;
    }

    const total = flatten(data.children || [], []).filter((n) => n.type === "file").length;
    $("tree-count").textContent = q ? "" : (total ? String(total) : "");

    if (q) {
      const rows = flatten(data.children, [])
        .map((n) => ({ n, s: fuzzy(q, n.path || n.name) }))
        .filter((x) => x.s > 0)
        .sort((a, b) => b.s - a.s || a.n.path.localeCompare(b.n.path))
        .slice(0, 80);
      rows.forEach((x) => host.appendChild(treeButton(x.n, 0, q, true)));
    } else {
      function draw(nodes, depth) {
        nodes.forEach((n) => {
          host.appendChild(treeButton(n, depth, "", false));
          if (n.type === "dir" && state.expanded[n.path] && n.children) draw(n.children, depth + 1);
        });
      }
      draw(data.children || [], 0);
    }
    if (!host.querySelector(".tree-item")) {
      const p = document.createElement("p");
      p.className = "tree-empty";
      p.textContent = "No match.";
      host.appendChild(p);
      $("tree-count").textContent = "";
    } else if (q) {
      const n = host.querySelectorAll(".tree-item").length;
      $("tree-count").textContent = String(n);
    }
    const target = scrollTo || state.openPath;
    if (target) {
      const el = [...host.querySelectorAll(".tree-item")].find((x) => x.dataset.path === target);
      if (el) el.scrollIntoView({ block: "nearest" });
    }
  }

  async function loadTree() {
    const host = $("tree-list");
    if (!state.workspace) {
      renderTree();
      return;
    }
    host.classList.add("dim");
    try {
      const data = await (await fetch("/api/tree?workspace=" + encodeURIComponent(state.workspace))).json();
      if (data.error) throw new Error(data.error);
      state.treeData = data;
      if (data.children) {
        data.children.forEach((n) => {
          if (n.type === "dir" && state.expanded[n.path] === undefined) state.expanded[n.path] = true;
        });
      }
      renderTree();
    } catch (e) {
      host.innerHTML = '<p class="tree-empty">' + esc(String(e.message || e)) + "</p>";
      $("tree-count").textContent = "";
    } finally {
      host.classList.remove("dim");
    }
  }

  function showEditor(on) {
    $("editor").hidden = !on;
    if (on && state.edW && !mobile()) $("editor").style.width = state.edW + "px";
    if (mobile()) {
      if (on) $("tree").hidden = true;
      else $("tree").hidden = !state.treeOn;
    }
    syncChrome();
  }

  function setDirty(on) {
    $("ed-dirty").hidden = !on;
    $("ed-save").hidden = !on;
    $("ed-save").textContent = "Save";
  }

  function setEdMode(mode) {
    $("ed-code").hidden = mode !== "code";
    $("ed-preview").hidden = mode !== "image";
    $("ed-note").hidden = mode !== "note";
  }

  function applyWrap() {
    $("ed-body").classList.toggle("wrap", state.wrap);
    $("ed-body").wrap = state.wrap ? "soft" : "off";
    $("ed-wrap").classList.toggle("on", state.wrap);
    $("ed-gutter").style.display = state.wrap ? "none" : "";
    localStorage.setItem("fxs.wrap", state.wrap ? "1" : "0");
  }

  function updateGutter() {
    const a = $("ed-body");
    const g = $("ed-gutter");
    if (state.wrap || $("ed-code").hidden) return;
    const n = a.value ? a.value.split("\n").length : 1;
    if ((g.dataset.n | 0) !== n) {
      let s = "";
      for (let i = 1; i <= n; i++) s += i + "\n";
      g.textContent = s;
      g.dataset.n = String(n);
    }
    g.scrollTop = a.scrollTop;
  }

  function updateLoc() {
    const a = $("ed-body");
    if ($("ed-code").hidden) {
      $("ed-loc").textContent = "";
      return;
    }
    const pos = a.selectionStart || 0;
    const up = a.value.slice(0, pos);
    const lines = up.split("\n");
    $("ed-loc").textContent = "Ln " + lines.length + ", Col " + (lines[lines.length - 1].length + 1);
    $("ed-size").textContent = prettySize(state.edSize || new Blob([a.value]).size);
  }

  function setEdTitle(rel) {
    const name = basename(rel);
    const dir = dirname(rel);
    $("ed-name").textContent = name;
    $("ed-dir").textContent = dir ? dir + "/" : "";
    $("ed-id").title = "Copy path · " + rel;
  }

  async function openFile(rel) {
    if (!rel || !state.workspace) return;
    if (!$("ed-code").hidden && !$("ed-dirty").hidden) await saveFile();
    try {
      const data = await (await fetch(
        "/api/file?workspace=" + encodeURIComponent(state.workspace) + "&path=" + encodeURIComponent(rel)
      )).json();
      if (data.error) throw new Error(data.error);
      state.openPath = data.path || rel;
      state.edSize = data.size || 0;
      setEdTitle(state.openPath);
      setDirty(false);
      showEditor(true);
      expandTo(state.openPath);
      if (data.image) {
        setEdMode("image");
        $("ed-preview").innerHTML = '<img alt="" src="/api/raw?workspace=' +
          encodeURIComponent(state.workspace) + "&path=" + encodeURIComponent(state.openPath) + '">';
        $("ed-loc").textContent = "Image";
        $("ed-size").textContent = prettySize(data.size);
      } else if (data.binary || data.too_large) {
        setEdMode("note");
        $("ed-note").textContent = data.too_large
          ? "Too large to open · " + prettySize(data.size)
          : "Binary · " + prettySize(data.size);
        $("ed-loc").textContent = "";
        $("ed-size").textContent = prettySize(data.size);
      } else {
        setEdMode("code");
        $("ed-body").value = data.content || "";
        state.orig = $("ed-body").value;
        state.edSize = new Blob([state.orig]).size;
        applyWrap();
        $("ed-body").setSelectionRange(0, 0);
        $("ed-body").scrollTop = 0;
        updateGutter();
        updateLoc();
        $("ed-body").focus();
      }
      if (!mobile()) toggleTree(true);
      renderTree(state.openPath);
    } catch (e) {
      showInfo("File", String(e.message || e));
    }
  }

  async function closeEditor() {
    if (!$("ed-code").hidden && !$("ed-dirty").hidden) await saveFile();
    showEditor(false);
    state.openPath = "";
    state.orig = "";
    setDirty(false);
    renderTree();
    promptEl.focus();
  }

  async function saveFile() {
    if (!state.openPath || $("ed-code").hidden) return;
    const content = $("ed-body").value;
    try {
      const r = await fetch("/api/file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace: state.workspace, path: state.openPath, content }),
      });
      const data = await r.json();
      if (!r.ok || data.error) throw new Error(data.error || "save failed");
      state.orig = content;
      state.edSize = data.size || new Blob([content]).size;
      setDirty(false);
      $("ed-save").textContent = "Saved";
      $("ed-save").hidden = false;
      updateLoc();
      setTimeout(() => {
        if ($("ed-body").value === state.orig) {
          $("ed-save").hidden = true;
          $("ed-save").textContent = "Save";
        }
      }, 900);
    } catch (e) {
      showInfo("Save", String(e.message || e));
    }
  }

  async function copyPath() {
    if (!state.openPath) return;
    try {
      await navigator.clipboard.writeText(state.openPath);
      const n = $("ed-name");
      const t = n.textContent;
      n.textContent = "Copied";
      setTimeout(() => { if (n.textContent === "Copied") n.textContent = t; }, 800);
    } catch { /* ignore */ }
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

  function renderUser(text) {
    return esc(text).replace(/@([A-Za-z0-9_./@+-][A-Za-z0-9_./+-]*)/g, (m, p) =>
      '<button type="button" class="mention" data-path="' + esc(p) + '">@' + esc(p) + "</button>"
    );
  }

  function decorate(el) {
    el.querySelectorAll("pre").forEach((pre) => {
      if (pre.querySelector(".copy")) return;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "copy";
      b.textContent = "Copy";
      b.addEventListener("click", () => {
        const code = pre.querySelector("code");
        navigator.clipboard.writeText((code || pre).innerText);
        b.textContent = "Copied";
        setTimeout(() => { b.textContent = "Copy"; }, 1100);
      });
      pre.appendChild(b);
    });
  }

  function addMsg(kind, text) {
    const el = document.createElement("div");
    el.className = "msg " + kind;
    if (kind === "user") el.innerHTML = renderUser(text);
    else if (kind === "tools") el.innerHTML = text;
    else {
      el.innerHTML = render(text || "");
      decorate(el);
    }
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
      if (s.default_workspace && (!state.workspace || state.workspace === "/workspace")) {
        setWorkspace(s.default_workspace);
      } else if (!state.workspace && s.workspace) {
        setWorkspace(s.workspace);
      }
      const bits = [];
      if (s.demo) bits.push('<span class="dot off"></span>demo');
      else bits.push('<span class="dot"></span>' + (s.model || "fxs"));
      if (s.model) $("model-btn").textContent = (s.model.split("/")[1] || s.model).slice(0, 18);
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
    if (!text.trim()) {
      if (state.busy) stop();
      return;
    }
    const slash = text.trim();
    if (slash.startsWith("/") && !slash.includes(" ") && !slash.includes("@")) {
      const id = slash.slice(1).toLowerCase();
      if (COMMANDS.some((c) => c.id === id)) {
        promptEl.value = "";
        grow();
        hidePalette();
        runCommand(id);
        return;
      }
    }
    if (!state.workspace) {
      folderDlg.showModal();
      folderInput.focus();
      return;
    }
    if (state.busy) {
      state.queue.push(text.trim());
      promptEl.value = "";
      grow();
      setActivity("queued · " + state.queue.length);
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
          perm: state.perm,
          yolo: state.perm === "yolo",
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
            decorate(bot);
            state.lastAnswer = acc;
          } else if (ev.type === "activity") {
            setActivity(ev.text || (state.queue.length ? "queued · " + state.queue.length : ""));
          } else if (ev.type === "tools" && ev.tools) {
            const row = addMsg("tools", ev.tools.map((t) => {
              const name = t.name || t;
              const path = t.path || "";
              return '<span class="tool"' + (path ? ' data-path="' + esc(path) + '"' : "") + ">" +
                esc(name) + (path ? " " + esc(path) : "") + "</span>";
            }).join(""));
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
      if (state.treeOn) loadTree();
      if (state.queue.length) {
        const next = state.queue.shift();
        send(next);
      }
    }
  }

  function bindSplit(el, side) {
    el.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      const startX = e.clientX;
      const pane = side === "tree" ? $("tree") : $("editor");
      const startW = pane.getBoundingClientRect().width;
      const move = (ev) => {
        const dx = ev.clientX - startX;
        if (side === "tree") {
          const w = Math.min(420, Math.max(180, startW + dx));
          pane.style.width = w + "px";
          state.treeW = w;
        } else {
          const w = Math.min(Math.floor(window.innerWidth * 0.7), Math.max(240, startW - dx));
          pane.style.width = w + "px";
          state.edW = w;
        }
      };
      const up = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        if (state.treeW) localStorage.setItem("fxs.treeW", String(state.treeW));
        if (state.edW) localStorage.setItem("fxs.edW", String(state.edW));
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    });
  }

  $("composer").addEventListener("submit", (e) => {
    e.preventDefault();
    if (state.busy) { stop(); return; }
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
        pickPalette(false);
        return;
      }
      if (e.key === "Enter" && e.shiftKey) {
        e.preventDefault();
        pickPalette(true);
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
    const metaKey = e.metaKey || e.ctrlKey;
    if (e.key === "Escape" && state.busy) stop();
    if (metaKey && e.key.toLowerCase() === "s") {
      if (!$("editor").hidden) { e.preventDefault(); saveFile(); }
    }
    if (metaKey && e.key.toLowerCase() === "b") {
      e.preventDefault();
      toggleTree();
    }
    if (metaKey && e.key.toLowerCase() === "p") {
      e.preventDefault();
      toggleTree(true);
      $("tree-q").focus();
      $("tree-q").select();
    }
  });

  thread.addEventListener("click", (e) => {
    const mentionBtn = e.target.closest(".mention");
    if (mentionBtn && mentionBtn.dataset.path) {
      openFile(mentionBtn.dataset.path);
      return;
    }
    const t = e.target.closest(".tool");
    if (!t) return;
    const path = t.dataset.path || t.textContent.trim().split(/\s+/).slice(1).join(" ");
    if (path) openFile(path);
  });

  $("files-btn").title = "Files · " + mod + "B";
  $("files-btn").addEventListener("click", () => {
    if (mobile() && !$("editor").hidden) {
      closeEditor().then(() => toggleTree(true));
      return;
    }
    toggleTree();
  });
  $("tree-q").addEventListener("input", renderTree);
  $("tree-q").addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const first = $("tree-list").querySelector(".tree-item");
      if (first) first.focus();
    } else if (e.key === "Enter") {
      e.preventDefault();
      const files = $("tree-list").querySelectorAll('.tree-item[data-type="file"]');
      if (files.length) openFile(files[0].dataset.path);
    } else if (e.key === "Escape") {
      if ($("tree-q").value) {
        $("tree-q").value = "";
        renderTree();
      } else promptEl.focus();
    }
  });
  $("tree-list").addEventListener("keydown", (e) => {
    const items = [...$("tree-list").querySelectorAll(".tree-item")];
    if (!items.length) return;
    const i = Math.max(0, items.indexOf(document.activeElement));
    if (e.key === "ArrowDown") {
      e.preventDefault();
      items[Math.min(i + 1, items.length - 1)].focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (i <= 0) $("tree-q").focus();
      else items[i - 1].focus();
    } else if (e.key === "ArrowRight") {
      const el = items[i];
      if (el && el.dataset.type === "dir" && !el.classList.contains("open")) el.click();
      else if (el && el.dataset.type === "file") openFile(el.dataset.path);
    } else if (e.key === "ArrowLeft") {
      const el = items[i];
      if (el && el.dataset.type === "dir" && el.classList.contains("open")) el.click();
    } else if (e.key === "Enter") {
      e.preventDefault();
      items[i].click();
    }
  });
  $("ed-save").addEventListener("click", saveFile);
  $("ed-close").addEventListener("click", closeEditor);
  $("ed-id").addEventListener("click", copyPath);
  $("ed-wrap").addEventListener("click", () => {
    state.wrap = !state.wrap;
    applyWrap();
    updateGutter();
  });
  $("ed-body").addEventListener("input", () => {
    setDirty($("ed-body").value !== state.orig);
    updateGutter();
    updateLoc();
  });
  $("ed-body").addEventListener("scroll", () => { $("ed-gutter").scrollTop = $("ed-body").scrollTop; });
  $("ed-body").addEventListener("keyup", updateLoc);
  $("ed-body").addEventListener("click", updateLoc);
  $("ed-body").addEventListener("keydown", (e) => {
    if (e.key === "Tab") {
      e.preventDefault();
      const a = $("ed-body");
      const s = a.selectionStart, n = a.selectionEnd;
      a.value = a.value.slice(0, s) + "  " + a.value.slice(n);
      a.selectionStart = a.selectionEnd = s + 2;
      setDirty(true);
      updateGutter();
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
  $("sessions-btn").addEventListener("click", async () => {
    await loadSessions();
    sessionsDlg.showModal();
  });
  $("new-session").addEventListener("click", (e) => {
    e.preventDefault();
    newSession();
    sessionsDlg.close();
  });
  $("new-btn").addEventListener("click", newSession);
  permBtn.addEventListener("click", cyclePerm);
  $("theme-btn").addEventListener("click", cycleTheme);
  $("model-btn").addEventListener("click", openModels);
  $("veil").addEventListener("click", () => {
    if (!$("editor").hidden) closeEditor();
    else toggleTree(false);
  });
  window.addEventListener("resize", syncChrome);
  bindSplit($("split-tree"), "tree");
  bindSplit($("split-ed"), "editor");

  $("composer").addEventListener("dragover", (e) => { e.preventDefault(); });
  $("composer").addEventListener("drop", (e) => {
    e.preventDefault();
    const text = (e.dataTransfer.getData("text/plain") || "").trim();
    const names = [...(e.dataTransfer.files || [])].map((f) => f.name).filter(Boolean);
    let extra = "";
    if (text && text.startsWith("@")) extra = text.endsWith(" ") ? text : text + " ";
    else if (names.length) extra = names.map((n) => "@" + n).join(" ") + " ";
    else if (text) extra = text + " ";
    if (!extra) return;
    promptEl.value = (promptEl.value ? promptEl.value.replace(/\s*$/, " ") : "") + extra;
    grow();
    updatePalette();
    promptEl.focus();
  });

  applyTheme();
  setPerm(state.perm);
  applyWrap();
  $("ed-wrap").title = "Line wrap";
  setWorkspace(state.workspace);
  toggleTree(state.treeOn);
  refreshStatus();
  promptEl.focus();
})();
