(() => {
  const $ = (id) => document.getElementById(id);
  const thread = $("thread");
  const promptEl = $("prompt");
  const sendBtn = $("send");
  const settings = $("settings");
  const folderInput = $("folder-input");
  const sessionList = $("session-list");
  const html = document.documentElement;
  const filesEl = $("files");
  const veil = $("veil");
  const treeEl = $("tree");
  const treeQ = $("tree-q");
  const edBody = $("ed-body");
  const edGutter = $("ed-gutter");
  const PERMS = ["ask", "auto", "yolo"];
  const THEMES = ["system", "light", "dark"];
  const ICO = {
    chev: '<svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M3.2 1.6 7 5 3.2 8.4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    folder: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2.5 4.2A1.2 1.2 0 0 1 3.7 3h2.4l1.2 1.5h5.2A1.2 1.2 0 0 1 13.7 5.7v6.1A1.2 1.2 0 0 1 12.5 13H3.7A1.2 1.2 0 0 1 2.5 11.8V4.2Z" stroke="currentColor" stroke-width="1.3"/></svg>',
    file: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M5 2.5h4.2L13 6.3V13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1Z" stroke="currentColor" stroke-width="1.3"/><path d="M9.2 2.5V6.2H13" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
    image: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2.5" y="3.5" width="11" height="9" rx="1.4" stroke="currentColor" stroke-width="1.3"/><path d="m4.5 10.5 2.2-2.4 2 2.1 1.3-1.2 1.5 1.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6" cy="6.4" r="0.8" fill="currentColor"/></svg>',
  };
  const STEP_ICO = {
    read: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M5 2.5h4.2L13 6.3V13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1Z" stroke="currentColor" stroke-width="1.3"/><path d="M9.2 2.5V6.2H13" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
    write: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M3.5 12.5 11.2 4.8a1.2 1.2 0 0 1 1.7 1.7L5.2 14.2H3.5v-1.7Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="m10.4 4.1 1.5 1.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
    search: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="7" cy="7" r="4.2" stroke="currentColor" stroke-width="1.3"/><path d="m10.2 10.2 3 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
    run: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2.5" y="3.2" width="11" height="9.6" rx="1.6" stroke="currentColor" stroke-width="1.3"/><path d="m6 6.2 3 1.8-3 1.8V6.2Z" fill="currentColor"/></svg>',
    web: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5.2" stroke="currentColor" stroke-width="1.3"/><path d="M3 8h10M8 3c1.6 1.8 2.4 3.6 2.4 5S9.6 11.2 8 13C6.4 11.2 5.6 9.4 5.6 8S6.4 4.8 8 3Z" stroke="currentColor" stroke-width="1.2"/></svg>',
    retry: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5.2" stroke="currentColor" stroke-width="1.3"/><path d="M8 5.2V8l1.8 1.2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    list: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2.5 4.2A1.2 1.2 0 0 1 3.7 3h2.4l1.2 1.5h5.2A1.2 1.2 0 0 1 13.7 5.7v6.1A1.2 1.2 0 0 1 12.5 13H3.7A1.2 1.2 0 0 1 2.5 11.8V4.2Z" stroke="currentColor" stroke-width="1.3"/></svg>',
    delete: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M3.5 4.5h9M6.2 4.5V3.4A.9.9 0 0 1 7.1 2.5h1.8a.9.9 0 0 1 .9.9v1.1M12.2 4.5l-.5 8.1a1 1 0 0 1-1 1H5.3a1 1 0 0 1-1-1l-.5-8.1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
    ok: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="m3.8 8.2 2.8 2.8 5.6-6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    agent: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5.2" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="1.2" fill="currentColor"/></svg>',
    image: ICO.image,
    skill: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="m8 2.5 1.5 4.1H14L10.8 9.2l1.4 4.3L8 10.8 3.8 13.5l1.4-4.3L2 6.6h4.5L8 2.5Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>',
    status: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5.2" stroke="currentColor" stroke-width="1.3"/></svg>',
    tool: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4 11.5 11.5 4M6.5 4H4v2.5M9.5 12H12V9.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  };
  const GROUP_NOUN = {
    read: ["file", "files"], write: ["file", "files"], search: ["search", "searches"],
    run: ["command", "commands"], web: ["page", "pages"], list: ["folder", "folders"],
    delete: ["file", "files"], tool: ["tool", "tools"],
  };
  const IMG_EXT = /\.(png|jpe?g|webp|gif)$/i;

  const state = {
    workspace: localStorage.getItem("fxs.workspace") || "",
    busy: false,
    live: false,
    resume: localStorage.getItem("fxs.resume") || "last",
    perm: localStorage.getItem("fxs.perm") || "yolo",
    theme: localStorage.getItem("fxs.theme") || "system",
    history: JSON.parse(localStorage.getItem("fxs.history") || "[]"),
    histIdx: -1,
    abort: null,
    model: "",
    modelLabel: "",
    filesOn: (() => {
      const v = localStorage.getItem("fxs.filesOn");
      if (v === "1") return true;
      if (v === "0") return false;
      return !window.matchMedia("(max-width: 720px)").matches;
    })(),
    expanded: new Set(JSON.parse(localStorage.getItem("fxs.expanded") || "[]")),
    tree: [],
    treeCursor: "",
    openPath: "",
    orig: "",
    wrap: localStorage.getItem("fxs.wrap") !== "0",
    filesW: clampW(parseInt(localStorage.getItem("fxs.filesW") || "340", 10)),
    editing: false,
  };
  if (localStorage.getItem("fxs.yolo") === "0" && !localStorage.getItem("fxs.perm")) {
    state.perm = "auto";
  }

  function clampW(n) {
    if (!Number.isFinite(n)) return 340;
    return Math.min(720, Math.max(280, n));
  }

  function mobile() {
    return window.matchMedia("(max-width: 840px)").matches;
  }

  function applyWrap() {
    filesEl.classList.toggle("wrap", state.wrap);
    $("ed-wrap").classList.toggle("on", state.wrap);
    edBody.setAttribute("wrap", state.wrap ? "soft" : "off");
    localStorage.setItem("fxs.wrap", state.wrap ? "1" : "0");
  }

  function basename(p) {
    if (!p) return "fxs";
    const parts = p.replace(/\/+$/, "").split("/");
    return parts[parts.length - 1] || p;
  }

  function modelName(id) {
    if (state.modelLabel && (!id || id === state.model)) return state.modelLabel;
    if (!id) return "";
    return id.split("/")[1] || id;
  }

  function prettySize(n) {
    n = Number(n) || 0;
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(n < 10 * 1024 ? 1 : 0) + " KB";
    return (n / (1024 * 1024)).toFixed(1) + " MB";
  }

  function setThemeMeta() {
    const dark = html.getAttribute("data-theme") === "dark" ||
      (!html.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
    document.querySelectorAll('meta[name="theme-color"]').forEach((m) => {
      m.content = dark ? "#000000" : "#f5f5f7";
    });
  }

  function applyTheme() {
    if (state.theme === "system") html.removeAttribute("data-theme");
    else html.setAttribute("data-theme", state.theme);
    localStorage.setItem("fxs.theme", state.theme);
    document.querySelectorAll("#theme-seg [data-theme]").forEach((b) => {
      b.classList.toggle("on", b.getAttribute("data-theme") === state.theme);
    });
    setThemeMeta();
  }

  function persistExpanded() {
    localStorage.setItem("fxs.expanded", JSON.stringify([...state.expanded].slice(0, 80)));
  }

  function setWorkspace(p) {
    state.workspace = (p || "").trim();
    if (state.workspace) localStorage.setItem("fxs.workspace", state.workspace);
    document.title = basename(state.workspace) || "fxs";
    folderInput.value = state.workspace;
    if (state.filesOn) loadTree();
  }

  function setPerm(p) {
    state.perm = PERMS.includes(p) ? p : "yolo";
    localStorage.setItem("fxs.perm", state.perm);
    document.querySelectorAll("#perm-seg [data-perm]").forEach((b) => {
      b.classList.toggle("on", b.getAttribute("data-perm") === state.perm);
    });
  }

  function grow() {
    promptEl.style.height = "auto";
    promptEl.style.height = Math.min(promptEl.scrollHeight, 144) + "px";
    sendBtn.classList.toggle("idle", !state.busy && !promptEl.value.trim());
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

  function flatten(nodes, acc) {
    (nodes || []).forEach((n) => {
      acc.push(n);
      if (n.children) flatten(n.children, acc);
    });
    return acc;
  }

  async function showFiles(on) {
    if (!on && state.editing) {
      if (!(await maybeSave())) return;
    }
    state.filesOn = !!on;
    localStorage.setItem("fxs.filesOn", on ? "1" : "0");
    filesEl.hidden = !on;
    veil.hidden = !(on && mobile() && !state.editing);
    document.body.classList.toggle("files-on", on);
    $("files-btn").classList.toggle("on", on);
    $("files-btn").setAttribute("aria-expanded", on ? "true" : "false");
    filesEl.style.setProperty("--files-w", state.filesW + "px");
    if (on) {
      applyWrap();
      if (!state.tree.length) loadTree();
      else renderTree();
    } else {
      showEditor(false);
    }
  }

  function toggleFiles() {
    showFiles(!state.filesOn);
  }

  function showEditor(on) {
    state.editing = !!on;
    filesEl.classList.toggle("editing", on);
    veil.hidden = !(state.filesOn && mobile() && !on);
    if (!on) {
      document.querySelectorAll(".tree-item.on").forEach((el) => el.classList.remove("on"));
    } else {
      applyWrap();
    }
  }

  async function loadTree() {
    if (!state.workspace) {
      treeEl.innerHTML = '<div class="tree-empty">Open a folder first.</div>';
      return;
    }
    try {
      const r = await fetch("/api/tree?workspace=" + encodeURIComponent(state.workspace));
      const data = await r.json();
      state.tree = data.tree || [];
      renderTree();
    } catch {
      treeEl.innerHTML = '<div class="tree-empty">Could not load files.</div>';
    }
  }

  function renderTree() {
    const q = (treeQ.value || "").trim();
    treeEl.innerHTML = "";
    if (!state.tree.length) {
      treeEl.innerHTML = '<div class="tree-empty">Nothing here.</div>';
      return;
    }
    if (q) {
      const hits = flatten(state.tree, [])
        .filter((n) => n.type === "file")
        .map((n) => ({ n, score: fuzzy(q, n.path) }))
        .filter((x) => x.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, 80);
      if (!hits.length) {
        treeEl.innerHTML = '<div class="tree-empty">No match.</div>';
        return;
      }
      hits.forEach((x) => treeEl.appendChild(fileRow(x.n, 0, q, true)));
      return;
    }
    (function walk(nodes, depth) {
      nodes.forEach((n) => {
        if (n.type === "dir") {
          const open = state.expanded.has(n.path);
          treeEl.appendChild(dirRow(n, depth, open));
          if (open && n.children) walk(n.children, depth + 1);
        } else {
          treeEl.appendChild(fileRow(n, depth, "", false));
        }
      });
    })(state.tree, 0);
  }

  function dirRow(n, depth, open) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "tree-item" + (open ? " open" : "");
    b.style.setProperty("--d", String(depth));
    b.dataset.path = n.path;
    b.dataset.type = "dir";
    b.setAttribute("role", "treeitem");
    b.setAttribute("aria-expanded", open ? "true" : "false");
    b.innerHTML = '<span class="chev">' + ICO.chev + '</span><span class="kind">' + ICO.folder +
      '</span><span class="nm">' + esc(n.name) + "</span>";
    b.addEventListener("click", () => {
      if (state.expanded.has(n.path)) state.expanded.delete(n.path);
      else state.expanded.add(n.path);
      persistExpanded();
      state.treeCursor = n.path;
      renderTree();
    });
    return b;
  }

  function fileRow(n, depth, q, filtered) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "tree-item" + (n.path === state.openPath ? " on" : "");
    b.style.setProperty("--d", String(depth));
    b.dataset.path = n.path;
    b.dataset.type = "file";
    b.setAttribute("role", "treeitem");
    b.draggable = true;
    const icon = IMG_EXT.test(n.path) ? ICO.image : ICO.file;
    const nameHtml = q ? mark(n.name, q) : esc(n.name);
    b.innerHTML = '<span class="chev"></span><span class="kind">' + icon +
      '</span><span class="nm">' + nameHtml + "</span>" +
      (filtered && n.path !== n.name ? '<span class="hint">' + esc(n.path) + "</span>" : "") +
      (n.size != null ? '<span class="sz">' + prettySize(n.size) + "</span>" : "");
    b.addEventListener("click", (e) => {
      state.treeCursor = n.path;
      if (e.shiftKey) { mention(n.path); return; }
      openFile(n.path);
    });
    b.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", "@" + n.path + " ");
      e.dataTransfer.effectAllowed = "copy";
    });
    return b;
  }

  function mention(path) {
    const v = promptEl.value;
    const caret = promptEl.selectionStart || v.length;
    const ins = "@" + path + " ";
    promptEl.value = v.slice(0, caret) + ins + v.slice(caret);
    const pos = caret + ins.length;
    promptEl.setSelectionRange(pos, pos);
    grow();
    promptEl.focus();
  }

  function reveal(path) {
    const parts = path.split("/");
    let acc = "";
    for (let i = 0; i < parts.length - 1; i++) {
      acc = acc ? acc + "/" + parts[i] : parts[i];
      state.expanded.add(acc);
    }
    persistExpanded();
    state.treeCursor = path;
    renderTree();
    const el = [...treeEl.querySelectorAll(".tree-item")].find((n) => n.dataset.path === path);
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
  }

  async function maybeSave() {
    if (!state.openPath || edBody.value === state.orig) return true;
    return saveFile();
  }

  async function openFile(path) {
    if (!path || !state.workspace) return;
    if (!(await maybeSave())) return;
    if (!state.filesOn) showFiles(true);
    try {
      const r = await fetch("/api/file?workspace=" + encodeURIComponent(state.workspace) +
        "&path=" + encodeURIComponent(path));
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "failed");
      state.openPath = path;
      $("ed-name").textContent = data.name || basename(path);
      $("ed-name").title = path;
      $("ed-meta").textContent = prettySize(data.size);
      $("ed-preview").hidden = true;
      $("ed-note").hidden = true;
      $("ed-code").hidden = true;
      edBody.value = "";
      state.orig = "";
      $("ed-save").hidden = true;
      $("ed-dot").hidden = true;
      if (data.kind === "image") {
        $("ed-img").src = data.src;
        $("ed-img").alt = path;
        $("ed-preview").hidden = false;
        $("ed-loc").textContent = "";
      } else if (data.kind === "text") {
        edBody.value = data.text || "";
        state.orig = edBody.value;
        $("ed-code").hidden = false;
        updateGutter();
      } else {
        $("ed-note").hidden = false;
        $("ed-note").textContent = "This file can’t be edited here.";
        $("ed-loc").textContent = "";
      }
      showEditor(true);
      reveal(path);
      if (data.kind === "text") {
        const pin = () => {
          edBody.focus({ preventScroll: true });
          edBody.setSelectionRange(0, 0);
          edBody.scrollTop = 0;
          edGutter.scrollTop = 0;
          updateLoc();
        };
        pin();
        requestAnimationFrame(() => {
          pin();
          requestAnimationFrame(pin);
        });
      }
    } catch (e) {
      $("ed-note").hidden = false;
      $("ed-code").hidden = true;
      $("ed-preview").hidden = true;
      $("ed-note").textContent = String(e.message || e);
      $("ed-name").textContent = basename(path);
      showEditor(true);
    }
  }

  async function closeEditor() {
    if (!(await maybeSave())) return;
    state.openPath = "";
    state.orig = "";
    showEditor(false);
    treeQ.focus();
  }

  async function saveFile() {
    if (!state.openPath || !state.workspace) return false;
    const btn = $("ed-save");
    try {
      const r = await fetch("/api/file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workspace: state.workspace,
          path: state.openPath,
          text: edBody.value,
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "save failed");
      state.orig = edBody.value;
      $("ed-dot").hidden = true;
      btn.hidden = false;
      btn.textContent = "Saved";
      if (data.size != null) $("ed-meta").textContent = prettySize(data.size);
      setTimeout(() => {
        if (edBody.value === state.orig) {
          btn.hidden = true;
          btn.textContent = "Save";
        }
      }, 900);
      return true;
    } catch (e) {
      btn.hidden = false;
      btn.textContent = "Retry";
      $("ed-meta").textContent = String(e.message || e);
      return false;
    }
  }

  function syncDirty() {
    const dirty = edBody.value !== state.orig && !$("ed-code").hidden;
    $("ed-dot").hidden = !dirty;
    if (dirty) {
      $("ed-save").hidden = false;
      $("ed-save").textContent = "Save";
    } else if ($("ed-save").textContent === "Save") {
      $("ed-save").hidden = true;
    }
  }

  function updateGutter() {
    const n = Math.max(1, edBody.value.split("\n").length);
    let s = "1";
    for (let i = 2; i <= n; i++) s += "\n" + i;
    edGutter.textContent = s;
  }

  function updateLoc() {
    const v = edBody.value;
    const i = edBody.selectionStart || 0;
    const line = v.slice(0, i).split("\n").length;
    const last = v.lastIndexOf("\n", i - 1);
    const col = i - last;
    $("ed-loc").textContent = "Ln " + line + "  Col " + col;
  }

  function pathFromChip(name) {
    const m = String(name || "").match(/([\w./-]+\.[A-Za-z0-9]{1,12})\s*$/);
    return m ? m[1] : "";
  }

  const COMMANDS = [
    { id: "new", hint: "New chat" },
    { id: "files", hint: "Workspace" },
    { id: "settings", hint: "Folder, model, mode" },
    { id: "models", hint: "Switch model" },
    { id: "permissions", hint: "Ask, auto, yolo" },
    { id: "resume", hint: "Sessions" },
    { id: "status", hint: "Runtime" },
    { id: "usage", hint: "Spend" },
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
        pickPalette(e.shiftKey);
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
        setPaletteItems((data.files || []).map((p) => ({ id: p, label: p, hint: "open ⇧" })));
      } catch { hidePalette(); }
    }, 70);
  }

  function pickPalette(open) {
    const it = pal.items[pal.idx];
    if (!it) { hidePalette(); return; }
    if (pal.kind === "/") {
      hidePalette();
      promptEl.value = "";
      grow();
      runCommand(it.id);
      return;
    }
    if (open) {
      hidePalette();
      openFile(it.id);
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
      .replace(/^#{1,6}\s+(.*)$/gm, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/@([\w./-]+\.[A-Za-z0-9]{1,12})/g,
        '<button type="button" class="mention" data-path="$1">@$1</button>')
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

  function fmtElapsed(ms) {
    const s = Math.max(0, Math.round(ms / 1000));
    if (s < 60) return s + "s";
    const m = Math.floor(s / 60);
    const r = s % 60;
    return m + "m " + String(r).padStart(2, "0") + "s";
  }

  function groupLabel(kind, n) {
    const pair = GROUP_NOUN[kind] || ["step", "steps"];
    const noun = n === 1 ? pair[0] : pair[1];
    const verb = { read: "Read", write: "Edited", search: "Searched", run: "Ran",
      web: "Fetched", list: "Listed", delete: "Deleted" }[kind] || "Used";
    return verb + " " + n + " " + noun;
  }

  function paintStep(el, step) {
    const kind = step.kind || "status";
    const ico = STEP_ICO[kind] || (step.status === "ok" ? STEP_ICO.ok : STEP_ICO.status);
    el.className = "step" + (step.status === "running" ? " running" : "") +
      (step.status === "warn" ? " warn" : "") + (step.status === "ok" ? " ok" : "");
    el.dataset.kind = kind;
    el.dataset.status = step.status || "";
    if (step.id) el.dataset.id = step.id;
    if (step.path) el.dataset.path = step.path;
    else el.removeAttribute("data-path");
    const tag = step.path ? "button" : "div";
    if (el.tagName.toLowerCase() !== tag) {
      /* keep as div; button type set below */
    }
    if (step.path) el.setAttribute("type", "button");
    const text = (step.label || "") +
      (kind === "retry" && step.detail ? " · " + step.detail : "");
    el.innerHTML = '<span class="ico" aria-hidden="true">' + ico + "</span>" +
      '<span class="lab">' + esc(text) + "</span>";
  }

  function startTrail() {
    const trail = document.createElement("div");
    trail.className = "trail";
    trail.setAttribute("aria-live", "polite");
    thread.appendChild(trail);
    const live = document.createElement("div");
    live.className = "step live running";
    live.innerHTML = '<span class="ico pulse" aria-hidden="true"></span>' +
      '<span class="lab">Working · 0s</span>';
    trail.appendChild(live);
    const t0 = Date.now();
    const iv = setInterval(() => {
      const lab = live.querySelector(".lab");
      if (lab) lab.textContent = "Working · " + fmtElapsed(Date.now() - t0);
    }, 1000);
    function place(el) {
      trail.insertBefore(el, live);
    }
    return {
      el: trail,
      push(step) {
        if (!step || !step.label) return;
        if (step.id) {
          const existing = trail.querySelector('.step[data-id="' + step.id + '"]');
          if (existing) { paintStep(existing, step); return; }
        }
        if (step.status === "ok") {
          const rows = [...trail.querySelectorAll(".step:not(.live)")];
          const last = rows[rows.length - 1];
          if (last && last.dataset.kind === step.kind && last.dataset.status === "ok" && !step.id) {
            const n = (parseInt(last.dataset.n || "1", 10) + 1);
            last.dataset.n = String(n);
            const lab = last.querySelector(".lab");
            if (lab) lab.innerHTML = esc(groupLabel(step.kind, n));
            if (step.path) last.dataset.path = step.path;
            return;
          }
        }
        const row = document.createElement(step.path ? "button" : "div");
        if (step.path) row.type = "button";
        row.dataset.n = "1";
        paintStep(row, step);
        place(row);
      },
      stop(ok) {
        clearInterval(iv);
        const spent = fmtElapsed(Date.now() - t0);
        if (ok === false) {
          live.className = "step live warn";
          live.innerHTML = '<span class="ico" aria-hidden="true">' + STEP_ICO.retry + "</span>" +
            '<span class="lab">Stopped · ' + spent + "</span>";
        } else {
          live.remove();
        }
        if (!trail.querySelector(".step")) trail.remove();
      },
    };
  }

  function toolsHtml(tools) {
    return tools.map((t) => {
      const name = t.name || t;
      const path = pathFromChip(name);
      if (path) {
        return '<button type="button" class="tool" data-path="' + esc(path) + '">' +
          esc(name) + "</button>";
      }
      return '<span class="tool">' + esc(name) + "</span>";
    }).join("");
  }

  function setBusy(on) {
    state.busy = on;
    sendBtn.classList.toggle("busy", on);
    sendBtn.classList.toggle("idle", !on && !promptEl.value.trim());
    sendBtn.setAttribute("aria-label", on ? "Stop" : "Send");
  }

  async function refreshStatus() {
    try {
      const q = state.workspace ? "?workspace=" + encodeURIComponent(state.workspace) : "";
      const s = await (await fetch("/api/status" + q)).json();
      state.live = s.live !== false;
      state.model = s.model || state.model;
      const def = s.default_workspace || s.workspace;
      if (def && (!state.workspace || state.workspace === "/workspace") && def !== state.workspace) {
        setWorkspace(def);
      }
      if (state.modelLabel) $("model-val").textContent = state.modelLabel;
      else $("model-val").textContent = modelName(state.model) || "—";
      const agent = $("agent-val");
      if (agent) {
        if (!state.live) agent.textContent = "Local";
        else if (s.key === false) agent.textContent = "No key";
        else if (s.backend === "native") agent.textContent = "Native";
        else agent.textContent = "Ready";
        agent.classList.toggle("warn", state.live && s.key === false);
      }
    } catch {
      const agent = $("agent-val");
      if (agent) {
        agent.textContent = "Unreachable";
        agent.classList.add("warn");
      }
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
      sessionList.innerHTML = "<li class='empty-note'>Open a folder first.</li>";
      return;
    }
    try {
      const r = await fetch("/api/sessions?workspace=" + encodeURIComponent(state.workspace));
      const data = await r.json();
      if (!data.sessions || !data.sessions.length) {
        sessionList.innerHTML = "<li class='empty-note'>None yet.</li>";
        return;
      }
      data.sessions.forEach((s) => {
        const li = document.createElement("li");
        const b = document.createElement("button");
        b.type = "button";
        b.innerHTML = esc(s.title || "Session") +
          '<span class="id">' + esc(ago(s.mtime) + (s.id ? " · " + s.id.slice(0, 8) : "")) + "</span>";
        b.addEventListener("click", () => {
          state.resume = s.id || "last";
          localStorage.setItem("fxs.resume", state.resume);
          settings.close();
        });
        li.appendChild(b);
        sessionList.appendChild(li);
      });
    } catch {
      sessionList.innerHTML = "<li class='empty-note'>Could not load sessions.</li>";
    }
  }

  function newSession() {
    state.resume = "";
    localStorage.removeItem("fxs.resume");
    thread.innerHTML = "";
    closeChrome();
    promptEl.focus();
  }

  function playMark() {
    const mark = document.querySelector(".brand .mark");
    if (!mark) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    mark.querySelectorAll(".shimmer-band").forEach((el) => {
      el.classList.remove("is-playing");
      void el.getBoundingClientRect();
      el.classList.add("is-playing");
    });
  }

  let chromeAnims = [];
  function morphChrome(open) {
    const body = document.body;
    const wantWelcome = !open;
    if (body.classList.contains("welcome") === wantWelcome) {
      if (wantWelcome) playMark();
      return;
    }
    const brand = $("brand");
    const dock = document.querySelector(".dock");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    chromeAnims.forEach((a) => { try { a.cancel(); } catch { /* ignore */ } });
    chromeAnims = [];
    if (reduced || !brand || !dock) {
      body.classList.toggle("welcome", wantWelcome);
      playMark();
      return;
    }
    const firstB = brand.getBoundingClientRect();
    const firstD = dock.getBoundingClientRect();
    body.classList.toggle("welcome", wantWelcome);
    const lastB = brand.getBoundingClientRect();
    const lastD = dock.getBoundingClientRect();
    const bx = firstB.left - lastB.left;
    const by = firstB.top - lastB.top;
    const sx = lastB.width ? firstB.width / lastB.width : 1;
    const sy = lastB.height ? firstB.height / lastB.height : 1;
    const dx = firstD.left - lastD.left;
    const dy = firstD.top - lastD.top;
    const ease = "cubic-bezier(0.32, 0.72, 0, 1)";
    const bAnim = brand.animate(
      [
        { transform: `translate(${bx}px, ${by}px) scale(${sx}, ${sy})` },
        { transform: "none" },
      ],
      { duration: 460, easing: ease, fill: "both" }
    );
    const dAnim = dock.animate(
      [
        { transform: `translate(${dx}px, ${dy}px)` },
        { transform: "none" },
      ],
      { duration: 520, easing: ease, delay: 20, fill: "both" }
    );
    chromeAnims = [bAnim, dAnim];
    const done = () => {
      chromeAnims = [];
      playMark();
    };
    Promise.all([bAnim.finished, dAnim.finished]).then(done).catch(done);
  }
  function openChrome() { morphChrome(true); }
  function closeChrome() { morphChrome(false); }

  async function loadModels() {
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
        b.classList.toggle("on", id === (data.current || state.model));
        if (id === (data.current || state.model) && m.label) {
          state.modelLabel = m.label;
          $("model-val").textContent = m.label;
        }
        b.addEventListener("click", async () => {
          await fetch("/api/model", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model: id }),
          });
          state.model = id;
          state.modelLabel = m.label || modelName(id);
          $("model-val").textContent = state.modelLabel;
          list.hidden = true;
          loadModels();
        });
        li.appendChild(b);
        list.appendChild(li);
      });
    } catch {
      list.innerHTML = "<li class='empty-note'>Could not load models.</li>";
    }
  }

  async function openSettings() {
    folderInput.value = state.workspace;
    $("model-list").hidden = true;
    $("model-val").textContent = modelName(state.model) || "—";
    setPerm(state.perm);
    applyTheme();
    await loadModels();
    await Promise.all([loadSessions(), refreshStatus()]);
    if (!settings.open) settings.showModal();
    folderInput.focus();
  }

  function commitFolder() {
    const next = folderInput.value.trim();
    if (next && next !== state.workspace) {
      setWorkspace(next);
      state.resume = "last";
      refreshStatus();
    }
  }

  async function runCommand(id) {
    if (id === "clear" || id === "new") { newSession(); return; }
    if (id === "files") { showFiles(true); return; }
    if (id === "settings" || id === "resume") { openSettings(); return; }
    if (id === "models") {
      await openSettings();
      $("model-list").hidden = false;
      return;
    }
    if (id === "permissions") {
      setPerm(PERMS[(PERMS.indexOf(state.perm) + 1) % PERMS.length]);
      addMsg("sys", state.perm);
      return;
    }
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
      openSettings();
      return;
    }
    openChrome();
    setBusy(true);
    addMsg("user", text);
    promptEl.value = "";
    grow();
    state.history.unshift(text);
    state.history = state.history.slice(0, 40);
    localStorage.setItem("fxs.history", JSON.stringify(state.history));
    state.histIdx = -1;
    const trail = startTrail();
    const bot = addMsg("assistant", "");
    bot.hidden = true;
    bot.classList.add("pending");
    let acc = "";
    let failed = false;
    const ac = new AbortController();
    state.abort = ac;

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
            bot.hidden = false;
            bot.classList.remove("pending");
            bot.innerHTML = render(acc);
          } else if (ev.type === "step") {
            trail.push(ev);
          } else if (ev.type === "activity" && ev.text) {
            trail.push({ kind: "status", label: String(ev.text).slice(-80), status: "running" });
          } else if (ev.type === "tools" && ev.tools) {
            ev.tools.forEach((t) => trail.push({
              kind: "tool",
              label: t.name || t,
              path: pathFromChip(t.name || t),
              status: "ok",
            }));
          } else if (ev.type === "session" && ev.id) {
            state.resume = ev.id;
            localStorage.setItem("fxs.resume", ev.id);
          } else if (ev.type === "model" && ev.id) {
            state.model = ev.id;
            $("model-val").textContent = modelName(ev.id);
          } else if (ev.type === "error") {
            failed = true;
            bot.hidden = false;
            bot.classList.add("err");
            if (!acc) acc = ev.text || "failed";
            bot.innerHTML = render(acc);
          }
        }
        thread.scrollTop = thread.scrollHeight;
      }
    } catch (e) {
      if (e.name !== "AbortError" && !acc) {
        failed = true;
        bot.hidden = false;
        bot.classList.add("err");
        bot.textContent = String(e.message || e);
      }
    } finally {
      trail.stop(!failed && !!acc);
      bot.classList.remove("pending");
      if (!acc && bot.hidden) bot.remove();
      setBusy(false);
      state.abort = null;
      promptEl.focus();
      refreshStatus();
      if (state.filesOn) loadTree();
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
        pickPalette(false);
        return;
      }
      if (e.key === "Enter" && e.shiftKey && pal.kind === "@") {
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
  promptEl.addEventListener("dragover", (e) => e.preventDefault());
  promptEl.addEventListener("drop", (e) => {
    const t = e.dataTransfer.getData("text/plain");
    if (!t) return;
    e.preventDefault();
    mention(t.replace(/^@/, "").trim());
  });

  document.addEventListener("keydown", (e) => {
    const mod = e.metaKey || e.ctrlKey;
    if (e.key === "Escape") {
      if (settings.open) { settings.close(); return; }
      if (pal.open) { hidePalette(); return; }
      if (state.editing) { closeEditor(); return; }
      if (state.filesOn) { showFiles(false); return; }
      if (state.busy) stop();
      return;
    }
    if (mod && e.key === ",") {
      e.preventDefault();
      openSettings();
    }
    if (mod && e.key.toLowerCase() === "n") {
      e.preventDefault();
      newSession();
    }
    if (mod && e.key.toLowerCase() === "b") {
      e.preventDefault();
      toggleFiles();
    }
    if (mod && e.key.toLowerCase() === "s") {
      if (state.editing && !$("ed-code").hidden) {
        e.preventDefault();
        saveFile();
      }
    }
    if (mod && e.key.toLowerCase() === "p") {
      e.preventDefault();
      showFiles(true);
      treeQ.focus();
      treeQ.select();
    }
    if (!mod && state.filesOn && !state.editing && document.activeElement !== promptEl &&
        document.activeElement !== treeQ && document.activeElement !== folderInput &&
        document.activeElement !== edBody) {
      const items = [...treeEl.querySelectorAll(".tree-item")];
      if (!items.length) return;
      const idx = items.findIndex((el) => el.dataset.path === state.treeCursor);
      if (e.key === "ArrowDown") {
        e.preventDefault();
        const next = items[Math.min(items.length - 1, Math.max(0, idx) + 1)] || items[0];
        state.treeCursor = next.dataset.path;
        items.forEach((el) => el.classList.toggle("on", el === next));
        next.scrollIntoView({ block: "nearest" });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const prev = items[Math.max(0, (idx < 0 ? 0 : idx) - 1)];
        state.treeCursor = prev.dataset.path;
        items.forEach((el) => el.classList.toggle("on", el === prev));
        prev.scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter" && idx >= 0) {
        e.preventDefault();
        items[idx].click();
      } else if (e.key === "ArrowRight" && idx >= 0 && items[idx].dataset.type === "dir") {
        state.expanded.add(items[idx].dataset.path);
        persistExpanded();
        renderTree();
      } else if (e.key === "ArrowLeft" && idx >= 0 && items[idx].dataset.type === "dir") {
        state.expanded.delete(items[idx].dataset.path);
        persistExpanded();
        renderTree();
      }
    }
  });

  thread.addEventListener("click", (e) => {
    const t = e.target.closest("[data-path]");
    if (!t) return;
    const path = t.getAttribute("data-path");
    if (path) openFile(path);
  });

  $("more").addEventListener("click", openSettings);
  $("new-btn").addEventListener("click", newSession);
  $("files-btn").addEventListener("click", toggleFiles);
  $("files-close").addEventListener("click", () => showFiles(false));
  $("settings-close").addEventListener("click", () => settings.close());
  veil.addEventListener("click", () => showFiles(false));
  $("ed-back").addEventListener("click", closeEditor);
  $("ed-save").addEventListener("click", saveFile);
  $("ed-name").addEventListener("click", async () => {
    if (!state.openPath) return;
    try {
      await navigator.clipboard.writeText(state.openPath);
      const prev = $("ed-name").textContent;
      $("ed-name").textContent = "Copied";
      setTimeout(() => { $("ed-name").textContent = prev; }, 800);
    } catch { /* ignore */ }
  });
  $("ed-wrap").addEventListener("click", () => {
    state.wrap = !state.wrap;
    applyWrap();
  });
  edBody.addEventListener("input", () => { updateGutter(); syncDirty(); });
  edBody.addEventListener("scroll", () => { edGutter.scrollTop = edBody.scrollTop; });
  edBody.addEventListener("keyup", updateLoc);
  edBody.addEventListener("click", updateLoc);
  if (window.ResizeObserver) {
    new ResizeObserver(() => {
      if ($("ed-code").hidden) return;
      edGutter.scrollTop = edBody.scrollTop;
    }).observe(edBody);
  }
  window.addEventListener("resize", () => {
    veil.hidden = !(state.filesOn && mobile() && !state.editing);
  });
  edBody.addEventListener("keydown", (e) => {
    if (e.key === "Tab") {
      e.preventDefault();
      const s = edBody.selectionStart;
      const v = edBody.value;
      edBody.value = v.slice(0, s) + "  " + v.slice(edBody.selectionEnd);
      edBody.setSelectionRange(s + 2, s + 2);
      updateGutter();
      syncDirty();
    }
  });
  treeQ.addEventListener("input", renderTree);
  treeQ.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (treeQ.value) { treeQ.value = ""; renderTree(); e.stopPropagation(); }
    }
  });
  folderInput.addEventListener("change", commitFolder);
  folderInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); commitFolder(); }
  });
  $("model-row").addEventListener("click", () => {
    const list = $("model-list");
    list.hidden = !list.hidden;
  });
  $("perm-seg").addEventListener("click", (e) => {
    const b = e.target.closest("[data-perm]");
    if (b) setPerm(b.getAttribute("data-perm"));
  });
  $("theme-seg").addEventListener("click", (e) => {
    const b = e.target.closest("[data-theme]");
    if (b) { state.theme = b.getAttribute("data-theme"); applyTheme(); }
  });
  settings.addEventListener("close", commitFolder);

  (function splitHandle() {
    const h = document.createElement("div");
    h.className = "split";
    filesEl.appendChild(h);
    let startX = 0, startW = 0, down = false;
    h.addEventListener("pointerdown", (e) => {
      down = true;
      startX = e.clientX;
      startW = state.filesW;
      h.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    h.addEventListener("pointermove", (e) => {
      if (!down) return;
      state.filesW = clampW(startW + (startX - e.clientX));
      filesEl.style.setProperty("--files-w", state.filesW + "px");
    });
    function end() {
      if (!down) return;
      down = false;
      localStorage.setItem("fxs.filesW", String(state.filesW));
    }
    h.addEventListener("pointerup", end);
    h.addEventListener("pointercancel", end);
  })();

  applyTheme();
  setPerm(state.perm);
  setWorkspace(state.workspace);
  applyWrap();
  filesEl.style.setProperty("--files-w", state.filesW + "px");
  grow();
  refreshStatus();
  if (state.filesOn) showFiles(true);
  window.matchMedia("(max-width: 840px)").addEventListener("change", () => {
    veil.hidden = !(state.filesOn && mobile() && !state.editing);
  });
  promptEl.focus();
  const brand = $("brand");
  if (brand) {
    brand.addEventListener("pointerenter", playMark);
    brand.addEventListener("click", playMark);
  }
  requestAnimationFrame(() => setTimeout(playMark, 280));
})();
