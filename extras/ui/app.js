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
  const railEl = $("rail");
  const railList = $("rail-list");
  const railQ = $("rail-q");
  const veil = $("veil");
  const treeEl = $("tree");
  const treeQ = $("tree-q");
  const edBody = $("ed-body");
  const edGutter = $("ed-gutter");
  const PERMS = ["ask", "auto", "yolo"];
  const THEMES = ["system", "light", "dark"];
  const PERM_HINT = {
    ask: "Prompt before each tool",
    auto: "Allow reads; prompt for writes",
    yolo: "Allow all tools",
  };
  const SET_PAGES = {
    provider: "Provider",
    model: "Model",
    sessions: "Sessions",
    diag: "Diagnostics",
  };
  const ICO = {
    chev: '<svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M3.2 1.6 7 5 3.2 8.4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    folder: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2.5 4.2A1.2 1.2 0 0 1 3.7 3h2.4l1.2 1.5h5.2A1.2 1.2 0 0 1 13.7 5.7v6.1A1.2 1.2 0 0 1 12.5 13H3.7A1.2 1.2 0 0 1 2.5 11.8V4.2Z" stroke="currentColor" stroke-width="1.3"/></svg>',
    file: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M5 2.5h4.2L13 6.3V13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1Z" stroke="currentColor" stroke-width="1.3"/><path d="M9.2 2.5V6.2H13" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
    image: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2.5" y="3.5" width="11" height="9" rx="1.4" stroke="currentColor" stroke-width="1.3"/><path d="m4.5 10.5 2.2-2.4 2 2.1 1.3-1.2 1.5 1.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6" cy="6.4" r="0.8" fill="currentColor"/></svg>',
    more: '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><circle cx="3.5" cy="8" r="1.2"/><circle cx="8" cy="8" r="1.2"/><circle cx="12.5" cy="8" r="1.2"/></svg>',
  };
  const STEP_ICO = {
    read: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path fill-rule="evenodd" d="M7 3h6.2L18 7.8V11h-1.8V8.6H12V4.8H7A1.2 1.2 0 0 0 5.8 6v12A1.2 1.2 0 0 0 7 19.2h4.2V21H7A3 3 0 0 1 4 18V6a3 3 0 0 1 3-3zm9.75 9.2a4.05 4.05 0 1 1-2.86 6.92l-2 2 1.27 1.27 2-2A4.05 4.05 0 0 1 16.75 12.2zm0 1.8a2.25 2.25 0 1 0 0 4.5 2.25 2.25 0 0 0 0-4.5z"/></svg>',
    write: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M4.8 16.7 15.4 6.1l2.5 2.5-10.6 10.6H4.8v-2.5zm12.2-12.3 1.3-1.3a1.4 1.4 0 0 1 2 2l-1.3 1.3-2-2z"/></svg>',
    search: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path fill-rule="evenodd" d="M10.8 3a7.8 7.8 0 0 1 6.17 12.57l3.73 3.73-1.41 1.41-3.73-3.73A7.8 7.8 0 1 1 10.8 3zm0 1.8a6 6 0 1 0 0 12 6 6 0 0 0 0-12z"/></svg>',
    explore: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path fill-rule="evenodd" d="M10.8 3a7.8 7.8 0 0 1 6.17 12.57l3.73 3.73-1.41 1.41-3.73-3.73A7.8 7.8 0 1 1 10.8 3zm0 1.8a6 6 0 1 0 0 12 6 6 0 0 0 0-12z"/></svg>',
    run: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path fill-rule="evenodd" d="M6.2 3.5h11.6A2.7 2.7 0 0 1 20.5 6.2v11.6a2.7 2.7 0 0 1-2.7 2.7H6.2a2.7 2.7 0 0 1-2.7-2.7V6.2A2.7 2.7 0 0 1 6.2 3.5zM5.3 6.2c0-.5.4-.9.9-.9h11.6c.5 0 .9.4.9.9v11.6c0 .5-.4.9-.9.9H6.2a.9.9 0 0 1-.9-.9V6.2z"/><path d="M8.2 8.4 11.8 12 8.2 15.6l-1.3-1.3 2.1-2.3-2.1-2.3L8.2 8.4zm5.2 5.2h4.2v-1.8h-4.2v1.8z"/></svg>',
    web: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path fill-rule="evenodd" d="M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18zm0 1.8c-1.66 1.86-2.66 4.1-2.86 6.5h5.72C14.66 8.9 13.66 6.66 12 4.8zM6.3 11.3c.22-2.5 1.32-4.8 3.02-6.6A7.18 7.18 0 0 0 4.82 11.3H6.3zm11.4 0h1.48A7.18 7.18 0 0 0 14.68 4.7c1.7 1.8 2.8 4.1 3.02 6.6zM4.82 12.7A7.18 7.18 0 0 0 9.32 19.3c-1.7-1.8-2.8-4.1-3.02-6.6H4.82zm3.5 0c.2 2.4 1.2 4.64 2.86 6.5 1.66-1.86 2.66-4.1 2.86-6.5H8.32zm6.86 0c-.22 2.5-1.32 4.8-3.02 6.6a7.18 7.18 0 0 0 4.5-6.6h-1.48z"/></svg>',
    retry: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3.2a8.8 8.8 0 1 1-8.1 5.6l1.7.7A7 7 0 1 0 12 5.2V8l4-4-4-4v3.2z"/></svg>',
    list: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M9.2 4 11 6.2h6.4A2.4 2.4 0 0 1 19.8 8.6v8.8a2.4 2.4 0 0 1-2.4 2.4H6.6A2.4 2.4 0 0 1 4.2 17.4V6.4A2.4 2.4 0 0 1 6.6 4h2.6z"/></svg>',
    delete: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M9.2 3.4h5.6l.8 1.6h4.2v1.8H4.2V5h4.2l.8-1.6zM6.4 8.4h11.2l-.8 11.2a2 2 0 0 1-2 1.8H9.2a2 2 0 0 1-2-1.8L6.4 8.4z"/></svg>',
    ok: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="m9.2 16.2-4-4 1.6-1.6 2.4 2.4 7.2-7.2 1.6 1.6-8.8 8.8z"/></svg>',
    agent: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18zm0 6.2a2.8 2.8 0 1 0 .1 5.6 2.8 2.8 0 0 0-.1-5.6z"/></svg>',
    image: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M6.6 3.6h10.8A2.6 2.6 0 0 1 20 6.2v11.6a2.6 2.6 0 0 1-2.6 2.6H6.6A2.6 2.6 0 0 1 4 17.8V6.2A2.6 2.6 0 0 1 6.6 3.6zm8.6 3.8a1.5 1.5 0 1 0 .1 3 1.5 1.5 0 0 0-.1-3zM5.8 16.4 9.4 12.8l8 8c.3-.2.6-.4.8-.7l-9-9-3.4 3.4v2.9z"/></svg>',
    skill: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M7.4 3.2a3.6 3.6 0 1 1 0 7.2 3.6 3.6 0 0 1 0-7.2zm9.6 1.4 2.2 3.8h-4.4l2.2-3.8zM6.6 13.2h2.4A2.4 2.4 0 0 1 11.4 15.6v2.4A2.4 2.4 0 0 1 9 20.4H6.6A2.4 2.4 0 0 1 4.2 18v-2.4A2.4 2.4 0 0 1 6.6 13.2zm10.4.2a3.4 3.4 0 1 1 0 6.8 3.4 3.4 0 0 1 0-6.8z"/></svg>',
    status: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3.2A5.2 5.2 0 0 1 17.2 9.8c0 1.8-.9 3.2-2.3 4.2v1.6H9.1v-1.6A5.2 5.2 0 0 1 12 3.2zM9.4 17.2h5.2v1.2H9.4v-1.2zm.8 2.2h3.6V21h-3.6v-1.6z"/></svg>',
    tool: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="m7.2 14.2 7.4-7.4 2.2 2.2-7.4 7.4H7.2v-2.2zm8.2-9.6 1.5-1.5a1.5 1.5 0 0 1 2.1 2.1l-1.5 1.5-2.1-2.1zM5 17.2h5.2V21H5v-3.8z"/></svg>',
    chev: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M6.4 9.2 12 14.8l5.6-5.6 1.4 1.4-7 7-7-7 1.4-1.4z"/></svg>',
  };
  const LIVE_DOTS = '<span class="dots" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></span>';
  const GROUPABLE = new Set(["read", "write", "search", "web", "list", "delete", "tool", "image", "skill"]);
  const EXPLORE = new Set(["read", "search"]);
  const IMG_EXT = /\.(png|jpe?g|webp|gif)$/i;
  const MD_EXT = /\.(md|markdown|mdown|mdx)$/i;

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
    filesOn: localStorage.getItem("fxs.filesOn") === "1",
    expanded: new Set(JSON.parse(localStorage.getItem("fxs.expanded") || "[]")),
    tree: [],
    treeCursor: "",
    openPath: "",
    orig: "",
    wrap: localStorage.getItem("fxs.wrap") !== "0",
    mdPreview: localStorage.getItem("fxs.mdPreview") !== "0",
    filesW: clampW(parseInt(localStorage.getItem("fxs.filesW") || "340", 10)),
    editing: false,
    status: null,
    kind: "",
    provider: "",
    providerLabel: "",
    api: "auto",
    settingsOn: false,
    settingsPage: "",
    models: [],
    sessionCount: 0,
    railOn: localStorage.getItem("fxs.railOn") === "1",
    sessions: [],
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

  function hasChat() {
    return !!thread.querySelector(".msg.user, .msg.assistant");
  }

  function applyWrap() {
    filesEl.classList.toggle("wrap", state.wrap);
    $("ed-wrap").classList.toggle("on", state.wrap);
    edBody.setAttribute("wrap", state.wrap ? "soft" : "off");
    localStorage.setItem("fxs.wrap", state.wrap ? "1" : "0");
  }

  function hoverMorph() {
    return window.matchMedia("(hover: hover) and (pointer: fine)").matches;
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
    loadSessions();
  }

  function setPerm(p) {
    state.perm = PERMS.includes(p) ? p : "yolo";
    localStorage.setItem("fxs.perm", state.perm);
    document.querySelectorAll("#perm-seg [data-perm]").forEach((b) => {
      b.classList.toggle("on", b.getAttribute("data-perm") === state.perm);
    });
    const hint = $("perm-hint");
    if (hint) hint.textContent = PERM_HINT[state.perm] || "";
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

  function isMd(path) {
    return MD_EXT.test(path || "");
  }

  function resolveMdPath(url) {
    url = String(url || "").trim();
    let path = url.split("#")[0].split("?")[0].replace(/\\/g, "/");
    if (!path || /^(https?:|data:|mailto:|javascript:|vbscript:)/i.test(path)) return "";
    const rooted = path.startsWith("/");
    path = path.replace(/^\.\//, "").replace(/^\/+/, "");
    const dir = (state.openPath || "").replace(/\/[^/]*$/, "");
    const joined = (!rooted && dir) ? dir + "/" + path : path;
    const out = [];
    for (const part of joined.split("/")) {
      if (!part || part === ".") continue;
      if (part === "..") {
        if (!out.length) return "";
        out.pop();
        continue;
      }
      out.push(part);
    }
    return out.join("/");
  }

  function mdUrl(url, img) {
    url = String(url || "").trim();
    if (/^https?:/i.test(url)) return url;
    if (img && /^data:image\/(png|jpe?g|gif|webp)[;,]/i.test(url)) return url;
    const path = resolveMdPath(url);
    if (img && state.workspace && path) {
      return "/api/file?raw=1&workspace=" + encodeURIComponent(state.workspace) +
        "&path=" + encodeURIComponent(path);
    }
    return "";
  }

  function mdLink(url, inner, title) {
    url = String(url || "").trim();
    const t = title ? ' title="' + esc(title) + '"' : "";
    if (/^(https?:|mailto:)/i.test(url)) {
      return '<a href="' + esc(url) + '" target="_blank" rel="noopener"' + t + ">" + inner + "</a>";
    }
    if (url.startsWith("#")) return '<a href="' + esc(url) + '"' + t + ">" + inner + "</a>";
    const path = resolveMdPath(url);
    if (!path) return inner;
    return '<a href="#"' + t + ' data-path="' + esc(path) + '">' + inner + "</a>";
  }

  function mdInline(s) {
    const stash = [];
    const hold = (html) => {
      stash.push(html);
      return "\0" + (stash.length - 1) + "\0";
    };
    s = String(s || "");
    s = s.replace(/!\[([^\]]*)\]\((?:<)?([^)\s>]+)(?:>)?(?:\s+"([^"]*)")?\)/g,
      (_, alt, url, title) => hold('<img src="' + esc(mdUrl(url, true)) + '" alt="' + esc(alt) + '"' +
        (title ? ' title="' + esc(title) + '"' : "") + ">"));
    s = s.replace(/\[([^\]]+)\]\((?:<)?([^)\s>]+)(?:>)?(?:\s+"([^"]*)")?\)/g,
      (_, text, url, title) => hold(mdLink(url, mdInline(text), title)));
    s = s.replace(/<(https?:\/\/[^>\s]+)>/g, (_, url) => hold(mdLink(url, esc(url))));
    s = s.replace(/`([^`]+)`/g, (_, code) => hold("<code>" + esc(code) + "</code>"));
    s = esc(s);
    s = s.replace(/~~([^~]+)~~/g, "<del>$1</del>");
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/__([^_]+)__/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^\w*])\*([^*\n]+)\*([^\w*]|$)/g, "$1<em>$2</em>$3");
    s = s.replace(/(^|[^\w_])_([^_\n]+)_([^\w_]|$)/g, "$1<em>$2</em>$3");
    s = s.replace(/\0(\d+)\0/g, (_, n) => stash[+n] || "");
    return s;
  }

  function mdToHtml(src) {
    src = String(src ?? "").replace(/\r\n?/g, "\n").replace(/\t/g, "    ");
    if (!src.trim()) return "";
    const held = [];
    const hold = (html) => {
      held.push(html);
      return "\n\n%%" + (held.length - 1) + "%%\n\n";
    };
    src = src.replace(/^ {0,3}(`{3,}|~{3,})([^\n]*)\n([\s\S]*?)^ {0,3}\1[ \t]*$/gm,
      (_, _t, info, body) => {
        const lang = (info || "").trim().split(/\s+/)[0];
        return hold("<pre><code" + (lang ? ' class="lang-' + esc(lang) + '"' : "") + ">" +
          esc(body.replace(/\n$/, "")) + "</code></pre>");
      });
    const lines = src.split("\n");
    const out = [];
    let i = 0;
    const LI = /^( *)([-*+]|\d+[.)])(?: +\[([ xX])\])? +(.*)$/;
    const SEP = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/;
    const TROW = /^\s*\|.*\|\s*$/;
    const HR = /^ {0,3}([-*_])(?: *\1){2,} *$/;
    const ATX = /^ {0,3}(#{1,6}) +(.+?)(?: +#*)? *$/;
    const restore = (s) => s.replace(/%%(\d+)%%/g, (_, n) => held[+n] || "");

    function peek(n) { return lines[i + n] || ""; }
    function blank(line) { return !String(line || "").trim(); }

    function takeQuote() {
      const inner = [];
      while (i < lines.length && /^ {0,3}>/.test(lines[i])) {
        inner.push(lines[i].replace(/^ {0,3}> ?/, ""));
        i++;
      }
      return "<blockquote>" + mdToHtml(inner.join("\n")) + "</blockquote>";
    }

    function takeTable() {
      const header = lines[i].trim().replace(/^\|/, "").replace(/\|$/, "");
      const alignLine = peek(1);
      const aligns = alignLine.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => {
        const t = c.trim();
        if (t.startsWith(":") && t.endsWith(":")) return "center";
        if (t.endsWith(":")) return "right";
        return "left";
      });
      i += 2;
      const rows = [];
      while (i < lines.length && TROW.test(lines[i]) && !SEP.test(lines[i])) {
        rows.push(lines[i].trim().replace(/^\|/, "").replace(/\|$/, ""));
        i++;
      }
      const split = (row) => row.split("|").map((c) => c.trim());
      const cells = (row, tag) => split(row).map((c, n) => {
        const a = aligns[n] && aligns[n] !== "left" ? ' style="text-align:' + aligns[n] + '"' : "";
        return "<" + tag + a + ">" + mdInline(c) + "</" + tag + ">";
      }).join("");
      let html = "<table><thead><tr>" + cells(header, "th") + "</tr></thead>";
      if (rows.length) {
        html += "<tbody>" + rows.map((r) => "<tr>" + cells(r, "td") + "</tr>").join("") + "</tbody>";
      }
      return html + "</table>";
    }

    function takeList() {
      const first = LI.exec(lines[i]);
      const base = first[1].length;
      const ordered = /\d/.test(first[2]);
      const items = [];
      while (i < lines.length) {
        const m = LI.exec(lines[i]);
        if (!m || m[1].length !== base || /\d/.test(m[2]) !== ordered) {
          if (blank(lines[i]) && i + 1 < lines.length && LI.test(lines[i + 1]) &&
              LI.exec(lines[i + 1])[1].length >= base) {
            i++;
            continue;
          }
          break;
        }
        const item = { check: m[3], chunks: [m[4]] };
        i++;
        while (i < lines.length) {
          if (blank(lines[i])) {
            if (i + 1 < lines.length && (LI.test(lines[i + 1]) ||
                lines[i + 1].startsWith(" ".repeat(base + 2)))) {
              item.chunks.push("");
              i++;
              continue;
            }
            break;
          }
          const n = LI.exec(lines[i]);
          if (n) {
            if (n[1].length > base) { item.chunks.push(lines[i]); i++; continue; }
            break;
          }
          if (lines[i].startsWith(" ".repeat(base + 1))) {
            item.chunks.push(lines[i].slice(Math.min(lines[i].length, base + 2)));
            i++;
            continue;
          }
          break;
        }
        items.push(item);
      }
      const tag = ordered ? "ol" : "ul";
      const body = items.map((it) => {
        const inner = mdToHtml(it.chunks.join("\n")).replace(/^<p>([\s\S]*)<\/p>$/, "$1");
        if (it.check != null) {
          const ck = /x/i.test(it.check) ? " checked" : "";
          return '<li class="task"><input type="checkbox" disabled' + ck + ">" + inner + "</li>";
        }
        return "<li>" + inner + "</li>";
      }).join("");
      return "<" + tag + ">" + body + "</" + tag + ">";
    }

    while (i < lines.length) {
      const line = lines[i];
      if (blank(line)) { i++; continue; }
      const token = line.trim();
      if (/^%%\d+%%$/.test(token)) { out.push(token); i++; continue; }
      const atx = ATX.exec(line);
      if (atx) {
        const lv = atx[1].length;
        out.push("<h" + lv + ">" + mdInline(atx[2]) + "</h" + lv + ">");
        i++;
        continue;
      }
      if (HR.test(line) && !TROW.test(line)) { out.push("<hr>"); i++; continue; }
      if (TROW.test(line) && SEP.test(peek(1))) { out.push(takeTable()); continue; }
      if (/^ {0,3}>/.test(line)) { out.push(takeQuote()); continue; }
      if (LI.test(line)) { out.push(takeList()); continue; }
      if (/^ {0,3}=+$/.test(peek(1)) && line.trim()) {
        out.push("<h1>" + mdInline(line.trim()) + "</h1>");
        i += 2;
        continue;
      }
      if (/^ {0,3}-+$/.test(peek(1)) && line.trim() && !TROW.test(line)) {
        out.push("<h2>" + mdInline(line.trim()) + "</h2>");
        i += 2;
        continue;
      }
      const buf = [line];
      i++;
      while (i < lines.length && !blank(lines[i]) && !ATX.test(lines[i]) &&
             !HR.test(lines[i]) && !LI.test(lines[i]) && !/^ {0,3}>/.test(lines[i]) &&
             !/^%%\d+%%$/.test(lines[i].trim()) &&
             !(TROW.test(lines[i]) && SEP.test(peek(1)))) {
        if (/^ {0,3}(=+|-+)$/.test(lines[i])) break;
        buf.push(lines[i]);
        i++;
      }
      out.push("<p>" + mdInline(buf.join(" ").replace(/ +/g, " ").trim()) + "</p>");
    }
    return restore(out.join(""));
  }

  function applyMdView() {
    const md = isMd(state.openPath) && state.kind === "text";
    const preview = md && state.mdPreview;
    const btn = $("ed-md");
    btn.hidden = !md;
    btn.classList.toggle("on", preview);
    btn.setAttribute("aria-label", preview ? "Source" : "Preview");
    btn.title = preview ? "Source" : "Preview";
    $("ed-wrap").hidden = preview || state.kind !== "text";
    if (preview) {
      $("ed-md-view").innerHTML = mdToHtml(edBody.value);
      $("ed-md-view").hidden = false;
      $("ed-img").hidden = true;
      $("ed-preview").classList.add("has-md");
      $("ed-preview").hidden = false;
      $("ed-code").hidden = true;
      $("ed-loc").textContent = "Markdown";
    } else {
      $("ed-md-view").hidden = true;
      $("ed-md-view").innerHTML = "";
      $("ed-preview").classList.remove("has-md");
      if (state.kind !== "image") $("ed-preview").hidden = true;
    }
    localStorage.setItem("fxs.mdPreview", state.mdPreview ? "1" : "0");
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

  function applySideWidth() {
    const w = state.filesW + "px";
    filesEl.style.setProperty("--files-w", w);
    settings.style.setProperty("--files-w", w);
  }

  function updateVeil() {
    veil.hidden = !(mobile() && ((state.filesOn && !state.editing) || state.settingsOn || state.railOn));
  }

  function hideSettings() {
    if (!state.settingsOn) return;
    commitFolder();
    state.settingsOn = false;
    state.settingsPage = "";
    settings.hidden = true;
    settings.classList.remove("paging");
    $("settings-home").inert = false;
    $("settings-page").inert = true;
    $("more").classList.remove("on");
    $("more").setAttribute("aria-expanded", "false");
    updateVeil();
  }

  async function showFiles(on) {
    if (!on && state.editing) {
      if (!(await maybeSave())) return;
    }
    if (on) hideSettings();
    state.filesOn = !!on;
    if (!mobile()) localStorage.setItem("fxs.filesOn", on ? "1" : "0");
    filesEl.hidden = !on;
    document.body.classList.toggle("files-on", on);
    $("files-btn").classList.toggle("on", on);
    $("files-btn").setAttribute("aria-expanded", on ? "true" : "false");
    applySideWidth();
    updateVeil();
    if (on) {
      applyWrap();
      if (!state.tree.length) loadTree();
      else renderTree();
      findSync();
    } else {
      showEditor(false);
      if (!state.settingsOn && !hasChat()) closeChrome();
    }
  }

  function toggleFiles() {
    showFiles(!state.filesOn);
  }

  function findOpen() {
    $("explorer").classList.add("finding");
    $("tree-find").setAttribute("aria-expanded", "true");
    requestAnimationFrame(() => {
      treeQ.focus();
      treeQ.select();
    });
  }

  function findClose() {
    if ((treeQ.value || "").trim()) return;
    $("explorer").classList.remove("finding");
    $("tree-find").setAttribute("aria-expanded", "false");
  }

  function findSync() {
    if ((treeQ.value || "").trim()) {
      $("explorer").classList.add("finding");
      $("tree-find").setAttribute("aria-expanded", "true");
    } else {
      $("explorer").classList.remove("finding");
      $("tree-find").setAttribute("aria-expanded", "false");
    }
  }

  function showEditor(on) {
    state.editing = !!on;
    filesEl.classList.toggle("editing", on);
    updateVeil();
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
      state.kind = data.kind || "";
      $("ed-name").textContent = data.name || basename(path);
      $("ed-name").title = path;
      $("ed-meta").textContent = prettySize(data.size);
      $("ed-preview").hidden = true;
      $("ed-preview").classList.remove("has-md");
      $("ed-md-view").hidden = true;
      $("ed-md-view").innerHTML = "";
      $("ed-img").hidden = false;
      $("ed-note").hidden = true;
      $("ed-code").hidden = true;
      edBody.value = "";
      state.orig = "";
      $("ed-save").hidden = true;
      $("ed-dot").hidden = true;
      $("ed-md").hidden = true;
      $("ed-wrap").hidden = true;
      if (data.kind === "image") {
        $("ed-img").src = data.src;
        $("ed-img").alt = path;
        $("ed-preview").hidden = false;
        $("ed-loc").textContent = "";
      } else if (data.kind === "text") {
        edBody.value = data.text || "";
        state.orig = edBody.value;
        $("ed-code").hidden = false;
        $("ed-wrap").hidden = false;
        updateGutter();
        applyMdView();
      } else {
        $("ed-note").hidden = false;
        $("ed-note").textContent = "This file can’t be edited here.";
        $("ed-loc").textContent = "";
      }
      showEditor(true);
      reveal(path);
      if (data.kind === "text" && !(isMd(path) && state.mdPreview)) {
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
      $("ed-md").hidden = true;
      $("ed-wrap").hidden = true;
      $("ed-note").textContent = String(e.message || e);
      $("ed-name").textContent = basename(path);
      showEditor(true);
    }
  }

  async function closeEditor() {
    if (!(await maybeSave())) return;
    state.openPath = "";
    state.orig = "";
    state.kind = "";
    showEditor(false);
    const sel = treeEl.querySelector(".tree-item.on") || treeEl.querySelector(".tree-item");
    if (sel) sel.focus();
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
    const dirty = state.kind === "text" && edBody.value !== state.orig;
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
    { id: "settings", hint: "Provider, model, look" },
    { id: "provider", hint: "Vercel, xAI, Ollama" },
    { id: "models", hint: "Switch model" },
    { id: "permissions", hint: "Ask, auto, yolo" },
    { id: "resume", hint: "Past sessions" },
    { id: "debug", hint: "Diagnostics" },
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
    return m + "m " + (s % 60) + "s";
  }

  function clip(s, n) {
    s = String(s || "").replace(/\s+/g, " ").trim();
    return s.length <= n ? s : s.slice(0, Math.max(0, n - 1)) + "…";
  }

  function stepItems(el) {
    try { return JSON.parse(el.dataset.items || "[]"); } catch { return []; }
  }

  function itemFrom(step) {
    return {
      label: step.label || "",
      path: step.path || "",
      detail: step.detail || "",
      kind: step.kind || "status",
      status: step.status || "ok",
    };
  }

  function itemCaption(it) {
    if (it.path) {
      const parts = String(it.path).split("/").filter(Boolean);
      return parts[parts.length - 1] || it.path;
    }
    return clip(String(it.detail || it.label || "").replace(
      /^(Ran command|Running command|Ran|Read|Reading|Edited|Explored|Loaded|Viewed|Listed|Listing)\s+/i, ""), 56);
  }

  function normPath(p) {
    return String(p || "").replace(/\\/g, "/").replace(/^\.\//, "").replace(/\/$/, "");
  }

  function samePath(a, b) {
    a = normPath(a);
    b = normPath(b);
    if (!a || !b) return false;
    return a === b || a.endsWith("/" + b) || b.endsWith("/" + a);
  }

  function itemKey(it) {
    const ident = normPath(it.path || it.detail || "");
    if (!ident) return "";
    return (it.kind || "") + ":" + ident;
  }

  function counted(verb, n, one, many) {
    return verb + ' <span class="num">' + n + "</span> " + (n === 1 ? one : many);
  }

  function countBit(n, one, many) {
    return '<span class="num">' + n + "</span> " + (n === 1 ? one : many);
  }

  function batchKind(items) {
    const hasFile = items.some((it) => it.kind === "read");
    const hasSearch = items.some((it) => it.kind === "search");
    if (hasFile && hasSearch) return "explore";
    if (hasSearch && !hasFile) return "search";
    if (items.length && items.every((it) => it.kind === "list")) return "list";
    if (hasFile) return "read";
    return (items[0] && items[0].kind) || "status";
  }

  function groupStatus(items, incoming) {
    if (incoming && incoming.status === "running") return "running";
    if (items.some((it) => it.status === "running")) return "running";
    return "ok";
  }

  function canMerge(row, step) {
    if (!row || row.classList.contains("live")) return false;
    const k = step.kind || "";
    const rk = row.dataset.kind;
    if (!k || k === "run" || rk === "run") return false;
    if (k === "retry" || rk === "retry") return false;
    if ((EXPLORE.has(k) || k === "explore") && (EXPLORE.has(rk) || rk === "explore")) return true;
    return rk === k && GROUPABLE.has(k);
  }

  const PROGRESS_RE = [
    [/^(reading|read)\b\s*(.*)$/i, "read"],
    [/^(listing|listed|list)\b\s*(.*)$/i, "list"],
    [/^(writing|wrote|write|editing|edited|edit)\b\s*(.*)$/i, "write"],
    [/^(running|ran|executing)\b(?:\s+command)?\s*(.*)$/i, "run"],
    [/^(searching|searched|search|grepping|grep)\b\s*(.*)$/i, "search"],
    [/^(fetching|fetched|fetch|converting|converted)\b\s*(.*)$/i, "web"],
    [/^(loading|loaded)\s+(?:skill\s+)?(.*)$/i, "skill"],
    [/^(viewing|viewed)\b\s*(.*)$/i, "image"],
  ];

  function stripGlyphs(s) {
    return String(s || "").replace(/^[^\p{L}\p{N}.\/~]+/u, "").trim();
  }

  function looksPath(s) {
    s = String(s || "").trim().replace(/^["']|["']$/g, "");
    if (!s) return "";
    if (s === "." || s === "./") return ".";
    if (/\s/.test(s) && s.indexOf("/") < 0) return "";
    if (/[\/.\\]/.test(s) || /^[\w.@-]+$/.test(s)) return s;
    return "";
  }

  function normalizeStep(step) {
    if (!step) return null;
    let kind = step.kind || "";
    let label = stripGlyphs(step.label || "");
    let detail = step.detail || "";
    let path = step.path || "";
    let status = step.status || "";
    if ((kind === "ok" || kind === "status" || kind === "retry") && /recovered/i.test(label + " " + detail)) return null;
    const raw = stripGlyphs([label, detail].filter(Boolean).join(" "));
    if (/recovered/i.test(raw) && /attempt|succeed/i.test(raw)) return null;
    if (kind === "status" || kind === "tool" || kind === "ok" || !kind) {
      for (const [re, k] of PROGRESS_RE) {
        const m = raw.match(re);
        if (!m) continue;
        kind = k;
        const rest = (m[2] || "").trim();
        if (!path) path = looksPath(rest);
        if (!detail) detail = rest;
        if (!status || status === "ok") status = /ing$/i.test(m[1]) && !rest ? "running" : (status || "ok");
        break;
      }
    }
    if (!kind || kind === "status") return null;
    if (!label && !path && !detail && kind !== "retry") return null;
    return Object.assign({}, step, { kind, label, detail, path, status: status || step.status || "ok" });
  }

  function formatLab(step, n, items) {
    const kind = step.kind || "status";
    const status = step.status || "";
    const first = (items && items[0]) || {};
    const snippet = clip(first.detail || step.detail || "", 48);
    if (kind === "run") {
      const cmd = snippet.replace(/^(Ran command|Running command|Ran)\s+/i, "");
      const verb = status === "running" ? "Running command" : "Ran command";
      return { verb, det: cmd, aria: verb + (cmd ? " " + cmd : "") };
    }
    if (kind === "explore") {
      const files = (items || []).filter((it) => it.kind === "read").length;
      const searches = (items || []).filter((it) => it.kind === "search").length;
      const bits = [];
      const raw = [];
      if (files) { bits.push(countBit(files, "file", "files")); raw.push(files + (files === 1 ? " file" : " files")); }
      if (searches) { bits.push(countBit(searches, "search", "searches")); raw.push(searches + (searches === 1 ? " search" : " searches")); }
      return { verb: "Explored", detHtml: bits.join(", "), aria: "Explored " + raw.join(", ") };
    }
    if (kind === "read") return { verb: counted("Read", n, "file", "files"), aria: "Read " + n + (n === 1 ? " file" : " files") };
    if (kind === "write") return { verb: counted("Edited", n, "file", "files"), aria: "Edited " + n + (n === 1 ? " file" : " files") };
    if (kind === "search") return { verb: counted("Ran", n, "search", "searches"), aria: "Ran " + n + (n === 1 ? " search" : " searches") };
    if (kind === "web") {
      const url = snippet.replace(/^(Fetched|Fetching|Converted|Converting)\s+/i, "");
      return { verb: counted("Fetched", n, "page", "pages"), det: n === 1 ? url : "", aria: "Fetched " + n + (n === 1 ? " page" : " pages") };
    }
    if (kind === "list") return { verb: counted("Listed", n, "folder", "folders"), aria: "Listed " + n + (n === 1 ? " folder" : " folders") };
    if (kind === "delete") return { verb: counted("Deleted", n, "file", "files"), aria: "Deleted " + n + (n === 1 ? " file" : " files") };
    if (kind === "skill") return { verb: counted("Loaded", n, "skill", "skills"), aria: "Loaded " + n + (n === 1 ? " skill" : " skills") };
    if (kind === "image") return { verb: counted("Viewed", n, "image", "images"), aria: "Viewed " + n + (n === 1 ? " image" : " images") };
    if (kind === "tool") return { verb: counted("Used", n, "tool", "tools"), aria: "Used " + n + (n === 1 ? " tool" : " tools") };
    let verb = esc(step.label || "");
    if (kind === "retry" && step.detail) verb += ' <span class="num">' + esc(step.detail) + "</span>";
    return { verb: verb || "Working", det: "", aria: step.label || "Working" };
  }

  function paintStep(el, step, items) {
    items = (items || stepItems(el)).filter((it) => it.path || it.detail || it.label);
    if (!items.length) items = [itemFrom(step)];
    let kind = step.kind || el.dataset.kind || "status";
    if (items.some((it) => it.kind === "read" || it.kind === "search")) kind = batchKind(items);
    const status = step.status != null ? step.status : (el.dataset.status || "");
    const n = items.length;
    const open = el.classList.contains("open");
    el.dataset.kind = kind;
    el.dataset.status = status;
    el.dataset.n = String(n);
    el.dataset.items = JSON.stringify(items);
    if (step.id) el.dataset.id = step.id;
    const path = n === 1 ? (step.path || items[0].path) : "";
    if (path) el.dataset.path = path;
    else el.removeAttribute("data-path");
    el.className = "step"
      + (status === "running" ? " running" : "")
      + (status === "warn" ? " warn" : "")
      + (status === "ok" ? " ok" : "")
      + (n > 1 || items.some((it) => it.path || it.detail) ? " fold" : "")
      + (open ? " open" : "");
    const ico = STEP_ICO[kind] || (status === "ok" ? STEP_ICO.ok : STEP_ICO.status);
    const lab = formatLab({ kind, status, label: step.label, detail: step.detail, path: step.path }, n, items);
    const kids = items.map((it) => {
      const cap = esc(itemCaption(it));
      if (!cap) return "";
      if (it.path) {
        return '<button type="button" class="kid" data-path="' + esc(it.path) + '">' + cap + "</button>";
      }
      return '<div class="kid">' + cap + "</div>";
    }).join("");
    const exp = open ? "true" : "false";
    const shimmer = status === "running" ? " shimmer" : "";
    el.innerHTML =
      '<div class="spine">' +
        '<button type="button" class="ico-btn" aria-expanded="' + exp + '" aria-label="' + esc(lab.aria) + '">' +
          '<span class="ico-face ico-kind" aria-hidden="true">' + ico + "</span>" +
          '<span class="ico-face ico-chev" aria-hidden="true">' + STEP_ICO.chev + "</span>" +
        "</button>" +
      "</div>" +
      '<button type="button" class="hit" aria-expanded="' + exp + '">' +
        '<span class="lab">' +
          '<span class="verb' + shimmer + '">' + lab.verb + "</span>" +
          (lab.detHtml ? '<span class="det">' + lab.detHtml + "</span>" :
            (lab.det ? '<span class="det">' + esc(lab.det) + "</span>" : "")) +
        "</span>" +
      "</button>" +
      '<div class="kids">' + kids + "</div>";
  }

  function startTrail() {
    const trail = document.createElement("div");
    trail.className = "trail";
    trail.setAttribute("aria-live", "polite");
    thread.appendChild(trail);
    const live = document.createElement("div");
    live.className = "step live running";
    live.innerHTML = '<div class="spine">' + LIVE_DOTS + "</div>" +
      '<span class="lab"><span class="verb">Working for</span><span class="num"> 0s</span></span>';
    trail.appendChild(live);
    const t0 = Date.now();
    const iv = setInterval(() => {
      const num = live.querySelector(".num");
      if (num) num.textContent = " " + fmtElapsed(Date.now() - t0);
    }, 1000);
    function solids() {
      return [...trail.querySelectorAll(":scope > .step:not(.live)")];
    }
    function place(el) {
      trail.insertBefore(el, live);
    }
    function apply(row, step, items) {
      paintStep(row, { kind: batchKind(items), status: groupStatus(items, step), label: step.label, detail: step.detail, path: step.path, id: step.id }, items);
    }
    return {
      el: trail,
      push(raw) {
        const step = normalizeStep(raw);
        if (!step) return;
        const item = itemFrom(step);
        const empty = !item.path && !item.detail;
        if (step.id) {
          const existing = trail.querySelector('.step[data-id="' + CSS.escape(String(step.id)) + '"]');
          if (existing) {
            const items = empty ? stepItems(existing) : [item];
            apply(existing, step, items);
            return;
          }
        }
        const rows = solids();
        const last = rows[rows.length - 1];
        const key = itemKey(item);
        for (let i = rows.length - 1; i >= 0; i--) {
          const items = stepItems(rows[i]);
          const ix = items.findIndex((it) => {
            if (key && itemKey(it) === key) return true;
            if (item.path && (samePath(it.path, item.path) || samePath(it.detail, item.path))) return true;
            if (item.detail && (samePath(it.path, item.detail) || it.detail === item.detail)) return true;
            return false;
          });
          if (ix < 0) continue;
          items[ix] = Object.assign({}, items[ix], item, {
            path: items[ix].path || item.path,
            detail: items[ix].detail || item.detail,
          });
          apply(rows[i], step, items);
          return;
        }
        if (empty) {
          const same = last && last.dataset.kind === step.kind ? last
            : [...rows].reverse().find((r) => r.dataset.kind === step.kind);
          if (same) {
            apply(same, step, stepItems(same));
            return;
          }
        }
        if (last && canMerge(last, step)) {
          const items = stepItems(last);
          items.push(item);
          apply(last, step, items);
          return;
        }
        const row = document.createElement("div");
        paintStep(row, step, empty ? [] : [item]);
        place(row);
      },
      stop(ok) {
        clearInterval(iv);
        const spent = fmtElapsed(Date.now() - t0);
        solids().forEach((el) => {
          if (el.dataset.kind === "retry") {
            if (ok !== false) el.remove();
            return;
          }
          if (!el.classList.contains("running")) return;
          const items = stepItems(el).map((it) => Object.assign({}, it, { status: "ok" }));
          const verb = (el.querySelector(".verb") || {}).textContent || "";
          paintStep(el, { kind: el.dataset.kind, status: "ok", label: verb }, items);
        });
        if (ok === false) {
          live.className = "step live warn";
          live.innerHTML = '<div class="spine"><span class="ico-face ico-kind" aria-hidden="true">' +
            STEP_ICO.retry + "</span></div>" +
            '<span class="lab"><span class="verb">Stopped</span><span class="num"> · ' + spent + "</span></span>";
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
      state.status = s;
      state.live = s.live !== false;
      state.model = s.model || state.model;
      const def = s.default_workspace || s.workspace;
      if (def && (!state.workspace || state.workspace === "/workspace") && def !== state.workspace) {
        setWorkspace(def);
      }
      if (state.modelLabel) $("model-val").textContent = state.modelLabel;
      else $("model-val").textContent = modelName(state.model) || "—";
      paintDiagnostics(s);
      paintHome();
    } catch {
      state.status = null;
      paintDiagnostics(null);
    }
  }

  function paintHome() {
    const p = (state.status && state.status.provider) || {};
    const pv = $("provider-val");
    if (pv) {
      pv.textContent = p.label || state.providerLabel || "Vercel";
      const need = !!(state.status && state.status.key === false && p.url);
      pv.classList.toggle("warn", need);
      if (need) pv.textContent = (p.label || "Provider") + " · key";
    }
    const mv = $("model-val");
    if (mv) mv.textContent = state.modelLabel || modelName(state.model) || "—";
    const hint = $("perm-hint");
    if (hint) hint.textContent = PERM_HINT[state.perm] || "";
    const sv = $("sessions-val");
    if (sv) {
      if (!state.workspace) sv.textContent = "—";
      else if (!state.sessionCount) sv.textContent = "None";
      else sv.textContent = String(state.sessionCount);
    }
  }

  function paintDiagnostics(s) {
    const set = (id, v) => { const el = $(id); if (el) el.textContent = v; };
    if (!s) {
      set("diag-backend", "unreachable");
      set("diag-model", "—");
      set("diag-provider", "—");
      set("diag-api", "—");
      set("diag-session", state.resume || "—");
      set("diag-docker", "—");
      set("diag-bins", "—");
      paintHome();
      return;
    }
    set("diag-backend", s.backend || "—");
    set("diag-model", s.model || state.model || "—");
    const p = s.provider || {};
    set("diag-provider", p.url || p.label || "Vercel AI Gateway");
    if (p.vercel || !p.url) {
      set("diag-api", "Vercel");
    } else if (p.api === "auto" && p.effective_api && p.effective_api !== p.api) {
      set("diag-api", "auto → " + p.effective_api);
    } else {
      set("diag-api", p.effective_api || p.api || "—");
    }
    state.provider = p.id || "";
    state.providerLabel = p.label || "";
    state.api = p.api && p.api !== "vercel" ? p.api : "auto";
    paintApi(p);
    paintKeyRow(p, s.key);
    paintPplxRow(p);
    const urlRow = $("provider-url-row");
    if (urlRow) {
      urlRow.hidden = !p.url || p.id !== "custom";
      if (p.url && $("provider-url")) $("provider-url").value = p.url;
    }
    set("diag-session", state.resume && state.resume !== "last" ? state.resume : "last");
    set("diag-docker", s.docker || "—");
    const bins = [];
    if (s.fx) bins.push("fx");
    if (s.fxs) bins.push("fxs");
    set("diag-bins", bins.join(" · ") || "none");
    paintHome();
  }

  function flashCopy(id) {
    const el = $(id);
    if (!el) return;
    const prev = el.textContent;
    el.textContent = "Copied";
    setTimeout(() => { el.textContent = prev; }, 900);
  }

  async function copyText(text, ackId) {
    try {
      await navigator.clipboard.writeText(text);
      flashCopy(ackId);
    } catch { /* ignore */ }
  }

  function diagnosticsText() {
    const s = state.status || {};
    return [
      "fxs",
      "backend: " + (s.backend || "unknown"),
      "model: " + (s.model || state.model || "—"),
      "provider: " + ((s.provider && (s.provider.url || s.provider.label)) || "—"),
      "api: " + ((s.provider && (s.provider.effective_api || s.provider.api)) || "—"),
      "key: " + (s.key === true ? "set" : s.key === false ? "missing" : "—"),
      "workspace: " + (state.workspace || "—"),
      "session: " + (state.resume || "—"),
      "docker: " + (s.docker || "—"),
      "fx: " + (s.fx ? "yes" : "no"),
      "fxs: " + (s.fxs ? "yes" : "no"),
    ].join("\n") + "\n";
  }

  function chatText() {
    return [...thread.querySelectorAll(".msg")].map((el) => {
      const kind = el.classList.contains("user") ? "user"
        : el.classList.contains("assistant") ? "assistant"
        : "sys";
      return kind.toUpperCase() + "\n" + (el.innerText || "").trim();
    }).filter((b) => b.split("\n")[1]).join("\n\n");
  }

  function ago(ts) {
    if (!ts) return "";
    const s = Math.max(0, (Date.now() / 1000) - ts);
    if (s < 60) return "now";
    if (s < 3600) return Math.floor(s / 60) + "m";
    if (s < 86400) return Math.floor(s / 3600) + "h";
    return Math.floor(s / 86400) + "d";
  }

  function sessionBucket(ts) {
    if (!ts) return "Older";
    const day = (d) => Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
    const n = day(new Date());
    const t = day(new Date(ts * 1000));
    const days = Math.round((n - t) / 86400000);
    if (days <= 0) return "Today";
    if (days === 1) return "Yesterday";
    if (days < 7) return "This week";
    if (days < 31) return "This month";
    return "Older";
  }

  function fuzzyHit(q, text) {
    q = (q || "").trim().toLowerCase();
    if (!q) return true;
    const t = (text || "").toLowerCase();
    if (t.includes(q)) return true;
    let i = 0;
    for (const ch of t) {
      if (ch === q[i]) i++;
      if (i === q.length) return true;
    }
    return false;
  }

  const railTip = $("rail-tip");
  const railMenu = $("rail-menu");
  let tipTimer = 0;
  let menuSession = null;

  function hideRailTip() {
    clearTimeout(tipTimer);
    if (railTip) railTip.hidden = true;
  }

  function showRailTip(btn) {
    hideRailTip();
    if (!btn || state.railOn || mobile() || !hoverMorph() || !railTip) return;
    const label = btn.getAttribute("data-tip");
    if (!label) return;
    tipTimer = setTimeout(() => {
      const r = btn.getBoundingClientRect();
      railTip.textContent = label;
      railTip.hidden = false;
      railTip.style.top = (r.top + r.height / 2) + "px";
      railTip.style.left = (Math.round(r.right) + 12) + "px";
    }, 180);
  }

  function hideRailMenu() {
    if (!railMenu) return;
    railMenu.hidden = true;
    menuSession = null;
    const del = railMenu.querySelector("[data-act]");
    if (del) {
      del.setAttribute("data-act", "delete");
      del.textContent = "Delete";
    }
  }

  function openRailMenu(btn, s) {
    if (!railMenu) return;
    if (menuSession && menuSession.id === s.id && !railMenu.hidden) {
      hideRailMenu();
      return;
    }
    menuSession = s;
    const del = railMenu.querySelector("[data-act]");
    if (del) {
      del.setAttribute("data-act", "delete");
      del.textContent = "Delete";
    }
    railMenu.hidden = false;
    const r = btn.getBoundingClientRect();
    const w = railMenu.offsetWidth || 148;
    const h = railMenu.offsetHeight || 40;
    let left = r.right - w;
    let top = r.bottom + 4;
    if (left < 8) left = 8;
    if (left + w > window.innerWidth - 8) left = window.innerWidth - w - 8;
    if (top + h > window.innerHeight - 8) top = r.top - h - 4;
    railMenu.style.left = left + "px";
    railMenu.style.top = top + "px";
  }

  function syncChromeA11y() {
    const brand = $("brand");
    const welcome = document.body.classList.contains("welcome");
    const docked = !welcome && hoverMorph();
    if (docked) {
      brand.setAttribute("aria-label", state.railOn ? "Close sessions" : "Sessions");
      brand.setAttribute("aria-expanded", state.railOn ? "true" : "false");
      brand.setAttribute("aria-controls", "rail");
    } else {
      brand.setAttribute("aria-label", "fxs");
      brand.removeAttribute("aria-expanded");
      brand.removeAttribute("aria-controls");
    }
    if (railEl) {
      railEl.toggleAttribute("inert", !state.railOn);
      railEl.setAttribute("aria-hidden", state.railOn ? "false" : "true");
    }
  }

  function showRail(on) {
    state.railOn = !!on;
    if (!mobile()) localStorage.setItem("fxs.railOn", on ? "1" : "0");
    document.body.classList.toggle("rail-on", on);
    $("rail-toggle").setAttribute("aria-expanded", on ? "true" : "false");
    $("sessions-btn").classList.toggle("on", on);
    $("sessions-btn").setAttribute("aria-expanded", on ? "true" : "false");
    hideRailTip();
    hideRailMenu();
    updateVeil();
    syncChromeA11y();
    if (on) loadSessions();
  }

  function toggleRail() {
    showRail(!state.railOn);
  }

  function focusFind() {
    if (mobile() && state.filesOn) showFiles(false);
    showRail(true);
    requestAnimationFrame(() => {
      if (!railQ) return;
      railQ.focus();
      railQ.select();
    });
  }

  function renderRailList() {
    if (!railList) return;
    hideRailMenu();
    railList.innerHTML = "";
    const q = railQ ? railQ.value : "";
    if (!state.workspace) {
      railList.innerHTML = "<p class='rail-empty'>Open a folder in Settings.</p>";
      return;
    }
    const rows = state.sessions.filter((s) => fuzzyHit(q, s.title || s.id || ""));
    if (!rows.length) {
      railList.innerHTML = "<p class='rail-empty'>" + (q ? "No matches." : "Nothing yet.") + "</p>";
      return;
    }
    const order = ["Today", "Yesterday", "This week", "This month", "Older"];
    const groups = new Map(order.map((k) => [k, []]));
    rows.forEach((s) => {
      const k = sessionBucket(s.mtime);
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(s);
    });
    order.forEach((k) => {
      const items = groups.get(k) || [];
      if (!items.length) return;
      const wrap = document.createElement("div");
      wrap.className = "rail-group";
      const lab = document.createElement("span");
      lab.className = "rail-label";
      lab.textContent = k;
      wrap.appendChild(lab);
      items.forEach((s) => wrap.appendChild(sessionButton(s, q)));
      railList.appendChild(wrap);
    });
  }

  function sessionButton(s, q) {
    const row = document.createElement("div");
    row.className = "rail-item" + (s.id && s.id === state.resume ? " on" : "");
    row.dataset.id = s.id || "";
    const hit = document.createElement("button");
    hit.type = "button";
    hit.className = "rail-hit";
    const title = s.title || "Untitled";
    hit.innerHTML = "<span class='ttl'>" + (q ? mark(title, q) : esc(title)) + "</span>";
    hit.title = title;
    hit.addEventListener("click", () => openSession(s));
    const more = document.createElement("button");
    more.type = "button";
    more.className = "rail-more";
    more.setAttribute("aria-label", "Session actions");
    more.innerHTML = ICO.more;
    more.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      openRailMenu(more, s);
    });
    row.append(hit, more);
    return row;
  }

  async function openSession(s) {
    if (!s || !s.id) return;
    hideRailMenu();
    state.resume = s.id;
    localStorage.setItem("fxs.resume", s.id);
    thread.innerHTML = "";
    openChrome();
    renderRailList();
    if (mobile()) showRail(false);
    try {
      const r = await fetch("/api/session?workspace=" + encodeURIComponent(state.workspace) +
        "&id=" + encodeURIComponent(s.id));
      const data = await r.json();
      if (r.ok && Array.isArray(data.messages) && data.messages.length) {
        thread.innerHTML = "";
        data.messages.forEach((m) => {
          const role = m.role === "user" ? "user" : m.role === "system" ? "sys" : "assistant";
          const text = m.content || m.text || "";
          if (text) addMsg(role, text);
        });
      }
    } catch { /* empty thread is fine */ }
    promptEl.focus();
  }

  async function deleteSession(s) {
    if (!s || !s.id || !state.workspace) return;
    hideRailMenu();
    try {
      await fetch("/api/session?workspace=" + encodeURIComponent(state.workspace) +
        "&id=" + encodeURIComponent(s.id), { method: "DELETE" });
    } catch { /* ignore */ }
    if (state.resume === s.id) {
      state.resume = "";
      localStorage.removeItem("fxs.resume");
      thread.innerHTML = "";
      closeChrome();
    }
    await loadSessions();
  }

  async function loadSessions() {
    sessionList.innerHTML = "";
    if (!state.workspace) {
      state.sessionCount = 0;
      state.sessions = [];
      paintHome();
      sessionList.innerHTML = "<li class='empty-note'>Open a folder first.</li>";
      renderRailList();
      return;
    }
    try {
      const r = await fetch("/api/sessions?workspace=" + encodeURIComponent(state.workspace));
      const data = await r.json();
      const sessions = data.sessions || [];
      state.sessions = sessions;
      state.sessionCount = sessions.length;
      paintHome();
      if (!sessions.length) {
        sessionList.innerHTML = "<li class='empty-note'>None yet.</li>";
      } else {
        sessions.forEach((s) => {
          sessionList.appendChild(choiceItem({
            title: s.title || "Session",
            sub: ago(s.mtime) + (s.id ? " · " + s.id.slice(0, 8) : ""),
            on: !!(s.id && s.id === state.resume),
            onClick: () => {
              openSession(s);
              showSettings(false);
            },
          }));
        });
      }
    } catch {
      state.sessions = [];
      sessionList.innerHTML = "<li class='empty-note'>Could not load sessions.</li>";
    }
    renderRailList();
  }

  function newSession() {
    hideRailMenu();
    state.resume = "";
    localStorage.removeItem("fxs.resume");
    thread.innerHTML = "";
    closeChrome();
    renderRailList();
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
    if (reduced || !brand || !dock || !hoverMorph()) {
      body.classList.toggle("welcome", wantWelcome);
      syncChromeA11y();
      playMark();
      return;
    }
    const firstB = brand.getBoundingClientRect();
    const firstD = dock.getBoundingClientRect();
    body.classList.toggle("welcome", wantWelcome);
    syncChromeA11y();
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

  async function showSettings(on, opts) {
    if (!on) {
      hideSettings();
      if (!state.filesOn && !hasChat()) closeChrome();
      return;
    }
    if (state.filesOn) {
      if (state.editing && !(await maybeSave())) return;
      state.filesOn = false;
      localStorage.setItem("fxs.filesOn", "0");
      filesEl.hidden = true;
      document.body.classList.remove("files-on");
      $("files-btn").classList.remove("on");
      $("files-btn").setAttribute("aria-expanded", "false");
      showEditor(false);
    }
    state.settingsOn = true;
    settings.hidden = false;
    $("more").classList.add("on");
    $("more").setAttribute("aria-expanded", "true");
    applySideWidth();
    updateVeil();
    folderInput.value = state.workspace;
    setPerm(state.perm);
    applyTheme();
    paintHome();
    const page = opts && opts.page;
    if (page) openPage(page);
    else closePage();
    loadModels();
    loadSessions();
    refreshStatus();
    if (!page && !state.workspace) {
      requestAnimationFrame(() => folderInput.focus());
    }
  }

  function closePage() {
    const was = state.settingsPage;
    state.settingsPage = "";
    settings.classList.remove("paging");
    $("settings-home").inert = false;
    $("settings-page").inert = true;
    ["provider", "model", "sessions", "diag"].forEach((p) => {
      const el = $("page-" + p);
      if (el) el.hidden = true;
    });
    const rows = {
      provider: "provider-row",
      model: "model-row",
      sessions: "sessions-row",
      diag: "diag-row",
    };
    const row = was && $(rows[was]);
    if (row && state.settingsOn) row.focus();
  }

  function openPage(id) {
    if (!SET_PAGES[id]) return;
    state.settingsPage = id;
    settings.classList.add("paging");
    $("settings-home").inert = true;
    $("settings-page").inert = false;
    $("settings-page-title").textContent = SET_PAGES[id];
    ["provider", "model", "sessions", "diag"].forEach((p) => {
      const el = $("page-" + p);
      if (el) el.hidden = p !== id;
    });
    if (id === "provider") {
      const known = (state.status && state.status.provider && state.status.provider.providers) || [];
      paintProviders(known);
      paintApi((state.status && state.status.provider) || {});
    }
    if (id === "model") {
      const q = $("model-q");
      if (q) q.value = "";
      if (state.models.length) paintModelList("");
      else loadModels();
    }
    if (id === "sessions") loadSessions();
    requestAnimationFrame(() => {
      if (id === "model") {
        const q = $("model-q");
        if (q) q.focus();
      } else if (id === "provider") {
        const keyRow = $("key-row");
        if (keyRow && !keyRow.hidden && $("key-input")) $("key-input").focus();
        else {
          const on = $("provider-list") && $("provider-list").querySelector(".choice-row.on");
          if (on) on.focus();
        }
      }
    });
  }

  function choiceItem({ title, sub, on, onClick }) {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.type = "button";
    b.className = "choice-row" + (on ? " on" : "");
    const main = document.createElement("span");
    main.className = "choice-main";
    const t = document.createElement("span");
    t.className = "choice-title";
    t.textContent = title;
    main.appendChild(t);
    if (sub) {
      const s = document.createElement("span");
      s.className = "choice-sub";
      s.textContent = sub;
      main.appendChild(s);
    }
    b.appendChild(main);
    const ck = document.createElement("span");
    ck.className = "choice-check";
    ck.innerHTML = STEP_ICO.ok;
    ck.setAttribute("aria-hidden", "true");
    b.appendChild(ck);
    b.addEventListener("click", onClick);
    li.appendChild(b);
    return li;
  }

  function hostOf(url) {
    try { return new URL(url).host; } catch { return url || ""; }
  }

  function pendingKey() {
    const inp = $("key-input");
    return (inp && inp.value.trim()) || "";
  }

  function paintKeyRow(p, hasKey) {
    const keyRow = $("key-row");
    if (!keyRow) return;
    const cloud = !!(p && p.url && p.id !== "ollama" && p.id !== "lmstudio");
    keyRow.hidden = !cloud;
    const hint = $("key-hint");
    if (hint) {
      hint.textContent = hasKey
        ? "Key is saved on this machine. Paste a new one to replace."
        : "Save, Enter, or switch protocol. Kept on this machine, not in the project.";
    }
  }

  function paintPplxRow(p) {
    const hint = $("pplx-hint");
    if (!hint) return;
    if (p && p.perplexity) {
      hint.textContent = "Perplexity key is saved. Search uses it even on OpenRouter. Paste a new one to replace.";
    } else if (p && p.vercel) {
      hint.textContent = "On Vercel, web search already uses AI Gateway. Optional pplx- key is used if you switch providers.";
    } else if (p && p.id === "openrouter") {
      hint.textContent = p.gateway_search
        ? "Vercel search needs a card on that account, so search uses OpenRouter instead. Optional pplx- for Perplexity."
        : "Search uses OpenRouter. Paste pplx- or vck_ to prefer those.";
    } else if (p && p.gateway_search) {
      hint.textContent = "Search uses your Vercel key via AI Gateway (that account needs a card). Paste pplx- to search without Vercel billing.";
    } else {
      hint.textContent = "pplx- or vck_ key. Used when the chat provider is not Vercel. Kept on this machine.";
    }
  }

  async function savePplxKey(key) {
    key = String(key || "").trim();
    if (!key) return null;
    const r = await fetch("/api/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, kind: "perplexity" }),
    });
    const data = await r.json();
    if (data.error) throw new Error(data.error);
    const inp = $("pplx-input");
    if (inp) inp.value = "";
    if (data.warn) addMsg("sys", data.warn);
    paintPplxRow(data);
    paintHome();
    await refreshStatus();
    return data;
  }

  async function saveKey(key) {
    key = String(key || "").trim();
    if (!key) return null;
    const r = await fetch("/api/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key }),
    });
    const data = await r.json();
    if (data.error) throw new Error(data.error);
    const inp = $("key-input");
    if (inp) inp.value = "";
    if (data.provider) {
      state.provider = data.provider;
      if (data.label) state.providerLabel = data.label;
    }
    if (data.model) {
      state.model = data.model;
      state.modelLabel = modelName(data.model) || data.model;
    }
    if (data.warn) addMsg("sys", data.warn);
    if (state.settingsPage === "provider") {
      if (data.providers) paintProviders(data.providers);
      paintApi(data);
      paintKeyRow(data, data.key);
      paintPplxRow(data);
    }
    paintHome();
    await loadModels();
    await refreshStatus();
    return data;
  }

  async function setProvider(id, url) {
    const body = { provider: url || id };
    const pending = pendingKey();
    if (pending) body.key = pending;
    const r = await fetch("/api/provider", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    if (data.error) throw new Error(data.error);
    if (pending && $("key-input")) $("key-input").value = "";
    state.provider = data.id || id;
    state.providerLabel = data.label || id;
    if (data.model) {
      state.model = data.model;
      state.modelLabel = modelName(data.model) || data.model;
    }
    if (data.warn) addMsg("sys", data.warn);
    if (state.settingsPage === "provider") {
      paintProviders(data.providers || []);
    }
    paintApi(data);
    paintKeyRow(data, data.key);
    paintPplxRow(data);
    const inp = $("key-input");
    if (data.needs_key && inp) {
      const keyRow = $("key-row");
      keyRow && keyRow.scrollIntoView({ block: "nearest" });
      inp.focus();
    }
    paintHome();
    await loadModels();
    await refreshStatus();
    return data;
  }

  function paintApi(p) {
    const row = $("api-row");
    if (!row) return;
    const vercel = !p || p.vercel || !p.url || p.api === "vercel";
    row.hidden = vercel;
    const mode = vercel || !p.api ? "auto" : p.api;
    state.api = mode;
    document.querySelectorAll("#api-seg [data-api]").forEach((b) => {
      b.classList.toggle("on", b.getAttribute("data-api") === mode);
    });
    const hint = $("api-hint");
    if (hint) {
      if (vercel) hint.textContent = "";
      else if (mode === "chat") hint.textContent = "Chat Completions";
      else if (mode === "responses") hint.textContent = "Responses — reasoning and tools, not stored";
      else if (p.effective_api === "responses") hint.textContent = "Auto — Responses on this host";
      else hint.textContent = "Auto — Chat Completions on this host";
    }
  }

  async function setApi(mode) {
    const body = { api: mode };
    if (state.provider === "custom") {
      const url = $("provider-url") && $("provider-url").value.trim();
      body.provider = url || state.providerLabel || "custom";
    } else if (state.provider) {
      body.provider = state.provider;
    }
    const pending = pendingKey();
    if (pending) body.key = pending;
    const r = await fetch("/api/provider", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    if (data.error) throw new Error(data.error);
    if (pending && $("key-input")) $("key-input").value = "";
    if (data.id) {
      state.provider = data.id;
      if (data.label) state.providerLabel = data.label;
    }
    if (data.warn) addMsg("sys", data.warn);
    paintApi(data);
    paintKeyRow(data, data.key);
    await refreshStatus();
    return data;
  }

  function paintProviders(list) {
    const el = $("provider-list");
    if (!el) return;
    el.innerHTML = "";
    (list || []).forEach((p) => {
      el.appendChild(choiceItem({
        title: p.label,
        sub: p.url ? hostOf(p.url) : "Default",
        on: p.id === state.provider || (!state.provider && p.id === "vercel"),
        onClick: async (ev) => {
          const btn = ev.currentTarget;
          el.querySelectorAll(".choice-row").forEach((b) => b.classList.toggle("on", b === btn));
          try {
            await setProvider(p.id, p.url);
          } catch (e) {
            addMsg("sys", String(e.message || e));
            const known = (state.status && state.status.provider && state.status.provider.providers) || list;
            paintProviders(known);
          }
        },
      }));
    });
    el.appendChild(choiceItem({
      title: "Custom URL",
      sub: "Any OpenAI-compatible /v1",
      on: state.provider === "custom",
      onClick: () => {
        const row = $("provider-url-row");
        if (row) row.hidden = false;
        $("provider-url").focus();
      },
    }));
    const selected = el.querySelector(".choice-row.on");
    if (selected) selected.scrollIntoView({ block: "nearest" });
  }

  function paintModelList(query) {
    const list = $("model-list");
    if (!list) return;
    list.innerHTML = "";
    const q = (query || "").trim().toLowerCase();
    const items = (state.models || []).filter((m) => {
      const id = String(m.id || m);
      const label = String(m.label || id);
      if (!q) return true;
      return id.toLowerCase().includes(q) || label.toLowerCase().includes(q);
    });
    if (!items.length) {
      list.innerHTML = "<li class='empty-note'>" + (q ? "No matches." : "No models.") + "</li>";
      return;
    }
    items.forEach((m) => {
      const id = m.id || m;
      const label = m.label || id;
      list.appendChild(choiceItem({
        title: label,
        sub: label !== id ? id : "",
        on: id === state.model,
        onClick: async () => {
          await fetch("/api/model", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model: id }),
          });
          state.model = id;
          state.modelLabel = label;
          paintHome();
          closePage();
        },
      }));
    });
    const selected = list.querySelector(".choice-row.on");
    if (selected) selected.scrollIntoView({ block: "nearest" });
  }

  async function loadModels() {
    try {
      const data = await (await fetch("/api/models")).json();
      state.models = data.models || [];
      const current = data.current || state.model;
      if (current) state.model = current;
      const cur = state.models.find((m) => (m.id || m) === current);
      if (cur && cur.label) state.modelLabel = cur.label;
      paintHome();
      if (state.settingsPage === "model") {
        paintModelList(($("model-q") && $("model-q").value) || "");
      }
    } catch {
      if (state.settingsPage === "model") {
        $("model-list").innerHTML = "<li class='empty-note'>Could not load models.</li>";
      }
    }
  }

  async function openSettings(opts) {
    showSettings(true, opts);
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
    if (id === "settings") { openSettings(); return; }
    if (id === "resume") { showRail(true); return; }
    if (id === "debug" || id === "advanced") { openSettings({ page: "diag" }); return; }
    if (id === "models") { openSettings({ page: "model" }); return; }
    if (id === "provider") { openSettings({ page: "provider" }); return; }
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
          resume: state.resume || "",
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
            loadSessions();
          } else if (ev.type === "model" && ev.id) {
            state.model = ev.id;
            paintHome();
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
      if (state.settingsPage) { closePage(); return; }
      if (state.settingsOn) { showSettings(false); return; }
      if (pal.open) { hidePalette(); return; }
      if (railMenu && !railMenu.hidden) { hideRailMenu(); return; }
      if (state.editing) { closeEditor(); return; }
      if ($("explorer").classList.contains("finding")) {
        if (treeQ.value) {
          treeQ.value = "";
          renderTree();
        } else {
          findClose();
          treeQ.blur();
        }
        return;
      }
      if (state.filesOn) { showFiles(false); return; }
      if (state.railOn) { showRail(false); return; }
      if (state.busy) stop();
      return;
    }
    if (mod && e.key === ",") {
      e.preventDefault();
      if (state.settingsOn) showSettings(false);
      else openSettings();
    }
    if (!mod && e.key === "?" && !e.repeat) {
      const tag = (document.activeElement && document.activeElement.tagName) || "";
      if (tag !== "INPUT" && tag !== "TEXTAREA") {
        e.preventDefault();
        openSettings({ page: "diag" });
      }
    }
    if (mod && e.key.toLowerCase() === "n") {
      e.preventDefault();
      newSession();
    }
    if (mod && e.key.toLowerCase() === "b") {
      e.preventDefault();
      toggleFiles();
    }
    if (mod && e.key.toLowerCase() === "l") {
      e.preventDefault();
      toggleRail();
    }
    if (mod && e.key.toLowerCase() === "f") {
      if (state.railOn) {
        e.preventDefault();
        focusFind();
      }
    }
    if (mod && e.key.toLowerCase() === "s") {
      if (state.editing && state.kind === "text") {
        e.preventDefault();
        saveFile();
      }
    }
    if (mod && e.key.toLowerCase() === "p") {
      e.preventDefault();
      showFiles(true).then(() => findOpen());
    }
    if (!mod && state.filesOn && !state.editing && document.activeElement !== promptEl &&
        document.activeElement !== treeQ && document.activeElement !== folderInput &&
        document.activeElement !== edBody && !state.settingsOn) {
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
    const kid = e.target.closest(".kid[data-path]");
    if (kid) {
      const path = kid.getAttribute("data-path");
      if (path) openFile(path);
      return;
    }
    const fold = e.target.closest(".step.fold");
    if (fold && fold.closest(".trail")) {
      const open = fold.classList.toggle("open");
      fold.querySelectorAll("[aria-expanded]").forEach((b) => {
        b.setAttribute("aria-expanded", open ? "true" : "false");
      });
      return;
    }
    const t = e.target.closest("[data-path]");
    if (!t) return;
    const path = t.getAttribute("data-path");
    if (path) openFile(path);
  });

  $("more").addEventListener("click", () => {
    if (state.settingsOn) showSettings(false);
    else openSettings();
  });
  $("new-btn").addEventListener("click", newSession);
  $("rail-new").addEventListener("click", newSession);
  $("rail-toggle").addEventListener("click", toggleRail);
  $("sessions-btn").addEventListener("click", toggleRail);
  $("brand").addEventListener("click", () => {
    if (document.body.classList.contains("welcome")) return;
    if (!hoverMorph()) return;
    toggleRail();
  });
  $("rail-close").addEventListener("click", () => showRail(false));
  $("files-btn").addEventListener("click", toggleFiles);
  $("files-close").addEventListener("click", () => showFiles(false));
  $("settings-close").addEventListener("click", () => showSettings(false));
  $("settings-page-close").addEventListener("click", () => showSettings(false));
  $("settings-back").addEventListener("click", () => closePage());
  $("provider-row").addEventListener("click", () => openPage("provider"));
  $("model-row").addEventListener("click", () => openPage("model"));
  $("sessions-row").addEventListener("click", () => openPage("sessions"));
  $("diag-row").addEventListener("click", () => openPage("diag"));
  const modelQ = $("model-q");
  if (modelQ) {
    modelQ.addEventListener("input", () => paintModelList(modelQ.value));
    modelQ.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowDown") return;
      const first = $("model-list") && $("model-list").querySelector(".choice-row");
      if (!first) return;
      e.preventDefault();
      first.focus();
    });
  }
  const copyDiag = $("copy-diag");
  if (copyDiag) copyDiag.addEventListener("click", () => copyText(diagnosticsText(), "copy-diag"));
  const copyChat = $("copy-chat");
  if (copyChat) copyChat.addEventListener("click", () => copyText(chatText() || "No chat yet.", "copy-chat"));
  veil.addEventListener("click", () => {
    if (state.settingsOn) showSettings(false);
    else if (state.filesOn) showFiles(false);
    if (state.railOn && mobile()) showRail(false);
  });
  $("sessions-btn").addEventListener("mouseenter", () => showRailTip($("sessions-btn")));
  $("sessions-btn").addEventListener("mouseleave", hideRailTip);
  $("sessions-btn").addEventListener("focus", () => showRailTip($("sessions-btn")));
  $("sessions-btn").addEventListener("blur", hideRailTip);
  railEl.querySelectorAll("[data-tip]").forEach((btn) => {
    btn.addEventListener("mouseenter", () => showRailTip(btn));
    btn.addEventListener("mouseleave", hideRailTip);
    btn.addEventListener("focus", () => showRailTip(btn));
    btn.addEventListener("blur", hideRailTip);
  });
  if (railMenu) {
    railMenu.addEventListener("click", (e) => {
      const act = e.target.closest("[data-act]");
      if (!act || !menuSession) return;
      const kind = act.getAttribute("data-act");
      if (kind === "delete") {
        act.setAttribute("data-act", "confirm");
        act.textContent = "Delete chat?";
        return;
      }
      if (kind === "confirm") deleteSession(menuSession);
    });
  }
  document.addEventListener("pointerdown", (e) => {
    if (!railMenu || railMenu.hidden) return;
    if (railMenu.contains(e.target) || e.target.closest(".rail-more")) return;
    hideRailMenu();
  });

  (function edgeSwipe() {
    let swipe = null;
    document.addEventListener("touchstart", (e) => {
      if (e.touches.length !== 1) { swipe = null; return; }
      const t = e.touches[0];
      const fromEdge = t.clientX <= 28;
      if (!fromEdge && !state.railOn) return;
      swipe = { x: t.clientX, y: t.clientY, fromEdge, rail: state.railOn };
    }, { passive: true });
    document.addEventListener("touchend", (e) => {
      if (!swipe) return;
      const s = swipe;
      swipe = null;
      const t = e.changedTouches[0];
      if (!t) return;
      const dx = t.clientX - s.x;
      const dy = t.clientY - s.y;
      if (Math.abs(dx) < 56 || Math.abs(dx) < Math.abs(dy) * 1.15) return;
      if (s.fromEdge && dx > 0) showRail(true);
      else if (s.rail && dx < 0) showRail(false);
    }, { passive: true });
    document.addEventListener("touchcancel", () => { swipe = null; }, { passive: true });
  })();
  if (railQ) {
    railQ.addEventListener("input", renderRailList);
    railQ.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (railQ.value) { railQ.value = ""; renderRailList(); e.stopPropagation(); }
        else if (mobile()) showRail(false);
      } else if (e.key === "ArrowDown") {
        const first = railList && railList.querySelector(".rail-hit");
        if (first) { e.preventDefault(); first.focus(); }
      }
    });
  }
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
  $("ed-md").addEventListener("click", () => {
    state.mdPreview = !state.mdPreview;
    if (!state.mdPreview) {
      $("ed-code").hidden = false;
      $("ed-preview").hidden = true;
      $("ed-preview").classList.remove("has-md");
      $("ed-md-view").hidden = true;
      applyMdView();
      updateGutter();
      updateLoc();
      edBody.focus({ preventScroll: true });
    } else {
      applyMdView();
    }
  });
  $("ed-md-view").addEventListener("click", (e) => {
    const t = e.target.closest("[data-path]");
    if (!t) return;
    e.preventDefault();
    const path = t.getAttribute("data-path");
    if (path) openFile(path);
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
  $("tree-find").addEventListener("click", findOpen);
  treeQ.addEventListener("input", renderTree);
  treeQ.addEventListener("focus", () => {
    $("explorer").classList.add("finding");
    $("tree-find").setAttribute("aria-expanded", "true");
  });
  treeQ.addEventListener("blur", () => { setTimeout(findClose, 0); });
  treeQ.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      if (treeQ.value) { treeQ.value = ""; renderTree(); }
      else { findClose(); treeQ.blur(); }
    }
  });
  folderInput.addEventListener("change", commitFolder);
  folderInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); commitFolder(); }
  });
  $("provider-url").addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const url = $("provider-url").value.trim();
    if (!url) return;
    try {
      await setProvider("custom", url);
      const known = (state.status && state.status.provider && state.status.provider.providers) || [];
      paintProviders(known);
    } catch (err) {
      addMsg("sys", String(err.message || err));
    }
  });
  const keyInput = $("key-input");
  if (keyInput) {
    keyInput.addEventListener("keydown", async (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      try {
        await saveKey(keyInput.value);
      } catch (err) {
        addMsg("sys", String(err.message || err));
      }
    });
  }
  const keySave = $("key-save");
  if (keySave) {
    keySave.addEventListener("click", async () => {
      try {
        await saveKey(pendingKey());
      } catch (err) {
        addMsg("sys", String(err.message || err));
      }
    });
  }
  const pplxInput = $("pplx-input");
  if (pplxInput) {
    pplxInput.addEventListener("keydown", async (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      try {
        await savePplxKey(pplxInput.value);
      } catch (err) {
        addMsg("sys", String(err.message || err));
      }
    });
  }
  const pplxSave = $("pplx-save");
  if (pplxSave) {
    pplxSave.addEventListener("click", async () => {
      const v = pplxInput ? pplxInput.value : "";
      try {
        await savePplxKey(v);
      } catch (err) {
        addMsg("sys", String(err.message || err));
      }
    });
  }
  const apiSeg = $("api-seg");
  if (apiSeg) {
    apiSeg.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-api]");
      if (!b) return;
      try {
        await setApi(b.getAttribute("data-api"));
      } catch (err) {
        addMsg("sys", String(err.message || err));
      }
    });
  }
  $("perm-seg").addEventListener("click", (e) => {
    const b = e.target.closest("[data-perm]");
    if (b) setPerm(b.getAttribute("data-perm"));
  });
  $("theme-seg").addEventListener("click", (e) => {
    const b = e.target.closest("[data-theme]");
    if (b) { state.theme = b.getAttribute("data-theme"); applyTheme(); }
  });

  function bindSplit(el) {
    const h = document.createElement("div");
    h.className = "split";
    el.appendChild(h);
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
      applySideWidth();
    });
    function end() {
      if (!down) return;
      down = false;
      localStorage.setItem("fxs.filesW", String(state.filesW));
    }
    h.addEventListener("pointerup", end);
    h.addEventListener("pointercancel", end);
  }
  bindSplit(filesEl);
  bindSplit(settings);

  function bindChoiceNav(id) {
    const el = $(id);
    if (!el) return;
    el.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const rows = [...el.querySelectorAll(".choice-row")];
      if (!rows.length) return;
      e.preventDefault();
      const i = rows.indexOf(document.activeElement);
      const next = e.key === "ArrowDown"
        ? rows[i < 0 ? 0 : Math.min(rows.length - 1, i + 1)]
        : rows[i < 0 ? rows.length - 1 : Math.max(0, i - 1)];
      next.focus();
    });
  }
  bindChoiceNav("provider-list");
  bindChoiceNav("model-list");
  bindChoiceNav("session-list");

  applyTheme();
  setPerm(state.perm);
  setWorkspace(state.workspace);
  applyWrap();
  applySideWidth();
  grow();
  refreshStatus();
  if (mobile()) showFiles(false);
  else if (state.filesOn) showFiles(true);
  showRail(!mobile() && state.railOn);
  window.matchMedia("(max-width: 840px)").addEventListener("change", () => {
    if (mobile()) {
      if (state.railOn) showRail(false);
      if (state.filesOn) showFiles(false);
      if (state.settingsOn) showSettings(false);
    } else {
      if (localStorage.getItem("fxs.filesOn") === "1") showFiles(true);
      showRail(localStorage.getItem("fxs.railOn") === "1");
    }
    updateVeil();
  });
  window.addEventListener("resize", updateVeil);
  promptEl.focus();
  const brand = $("brand");
  if (brand) {
    brand.addEventListener("pointerenter", () => {
      if (document.body.classList.contains("welcome")) playMark();
    });
    brand.addEventListener("click", () => {
      if (document.body.classList.contains("welcome")) playMark();
    });
  }
  requestAnimationFrame(() => setTimeout(playMark, 280));
})();
