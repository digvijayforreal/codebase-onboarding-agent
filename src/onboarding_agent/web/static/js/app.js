// Codebase Onboarding Agent - frontend controller
const $ = (sel) => document.querySelector(sel);
const api = (path, opts) => fetch(path, opts).then(async (r) => {
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
});

let REPORT = null;
let FLOW_SEL = null;

// ---------- difficulty colour scale (cool -> warm) ----------
function heatColor(v) {
  v = Math.max(0, Math.min(100, Number(v) || 0));
  const stops = [
    [0, [45, 170, 140]],   // teal  (easy)
    [40, [240, 190, 70]],  // amber
    [70, [238, 140, 45]],  // orange
    [100, [214, 65, 65]],  // red   (hard)
  ];
  let a = stops[0], b = stops[stops.length - 1];
  for (let i = 0; i < stops.length - 1; i++) {
    if (v >= stops[i][0] && v <= stops[i + 1][0]) { a = stops[i]; b = stops[i + 1]; break; }
  }
  const t = (v - a[0]) / (b[0] - a[0] || 1);
  const rgb = a[1].map((ch, i) => Math.round(ch + (b[1][i] - ch) * t));
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}

// ---------- status chips ----------
async function refreshStatus() {
  try {
    const s = await api("/api/status");
    setChip("#chip-groq", "Groq", s.has_groq);
    setChip("#chip-tavily", "Tavily", s.has_tavily);
  } catch (_) {}
}
function setChip(sel, label, on) {
  const el = $(sel);
  if (!el) return;
  el.textContent = `${label} ${on ? "on" : "off"}`;
  el.classList.toggle("on", on);
  el.classList.toggle("off", !on);
}

// ---------- view switching ----------
function showDashboard() {
  $("#launch-view").classList.add("gone");
  const dash = $("#dashboard");
  dash.hidden = false;
  requestAnimationFrame(() => dash.classList.add("show"));
  $("#nav-workflow").disabled = false;
  $("#nav-ask").disabled = false;
  setNav("analyze");
}
function showLaunch() {
  closeModal();
  const dash = $("#dashboard");
  dash.classList.remove("show");
  dash.hidden = true;
  $("#launch-view").classList.remove("gone");
  setNav("analyze");
}
function setNav(name) {
  document.querySelectorAll(".nav-item").forEach((b) =>
    b.classList.toggle("active", b.dataset.nav === name)
  );
}

// ---------- modals ----------
function openModal(name) {
  const ov = $("#overlay");
  ov.hidden = false;
  document.querySelectorAll(".modal").forEach((m) => m.classList.remove("show"));
  $("#modal-" + name).classList.add("show");
  requestAnimationFrame(() => ov.classList.add("open"));
  if (name === "chat") setTimeout(() => $("#question").focus(), 60);
}
function closeModal() {
  const ov = $("#overlay");
  if (ov.hidden) return;
  ov.classList.remove("open");
  setTimeout(() => { ov.hidden = true; }, 240);
  setNav("analyze");
}

// ---------- analyze ----------
async function analyze(source) {
  const btn = $("#analyze-btn");
  const status = $("#status");
  btn.disabled = true;
  btn.querySelector(".btn-label").textContent = "Analyzing";
  btn.querySelector(".spinner").hidden = false;
  status.className = "status";
  status.textContent = "Cloning, reading git history, scoring modules. First clone can take a bit.";
  try {
    REPORT = await api("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source }),
    });
    status.className = "status ok";
    status.textContent = `Analyzed ${REPORT.name}: ${REPORT.total_files} files, ${REPORT.total_commits} commits.`;
    renderDashboard();
    showDashboard();
  } catch (e) {
    status.className = "status err";
    status.textContent = "Error: " + e.message;
  } finally {
    btn.disabled = false;
    btn.querySelector(".btn-label").textContent = "Analyze";
    btn.querySelector(".spinner").hidden = true;
  }
}

// ---------- render dashboard ----------
function renderDashboard() {
  $("#repo-name").textContent = REPORT.name || "Repository";
  $("#repo-sub").textContent = `${REPORT.total_files} files, ${REPORT.total_commits} commits analyzed`;
  renderStats();
  renderHeatmap();
  renderFlow();
  $("#tour").innerHTML = "";
  $("#tour-summary").textContent = "Generate an ordered path through the codebase, easiest first.";
  $("#chat").innerHTML = "";
  addBot("Repository loaded. Ask me how it works, or build a guided tour.");
}

function renderStats() {
  const langs = Object.entries(REPORT.languages).sort((a, b) => b[1] - a[1]);
  const topLang = langs.length ? langs[0][0] : "—";
  const hardest = REPORT.files[0];
  const stats = [
    ["Files", REPORT.total_files],
    ["Commits", REPORT.total_commits],
    ["Top language", topLang],
    ["Hardest score", hardest ? hardest.difficulty_score : "—"],
  ];
  $("#stats").innerHTML = stats.map(([lbl, num]) =>
    `<div class="stat glass"><div class="num">${num}</div><div class="lbl">${lbl}</div></div>`
  ).join("");
}

function renderHeatmap() {
  const wrap = $("#heatmap");
  wrap.innerHTML = "";
  REPORT.files.forEach((f, i) => {
    const t = document.createElement("div");
    t.className = "tile";
    t.style.background = heatColor(f.difficulty_score);
    t.title = `${f.path} — difficulty ${f.difficulty_score}`;
    t.addEventListener("click", () => selectFile(i, t));
    t.addEventListener("mouseenter", () => showDetail(f));
    wrap.appendChild(t);
  });
  if (REPORT.files[0]) showDetail(REPORT.files[0]);
}

function selectFile(i, tile) {
  document.querySelectorAll(".tile.active").forEach((e) => e.classList.remove("active"));
  tile.classList.add("active");
  showDetail(REPORT.files[i]);
}

function bar(label, value) {
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  const col = heatColor(v);
  return `<div class="bar-row">
    <span class="bar-label">${label}</span>
    <span class="bar-track"><span class="bar-fill" style="width:${v}%;background:${col}"></span></span>
    <span class="bar-val">${value}</span>
  </div>`;
}

function showDetail(f) {
  $("#detail-title").textContent = f.path.split("/").pop();
  $("#detail").innerHTML = `
    <div class="path">${escapeHtml(f.path)}</div>
    <div class="bars">
      ${bar("Difficulty", f.difficulty_score)}
      ${bar("Complexity", f.complexity_score)}
      ${bar("Instability", f.instability_score)}
      ${bar("Hotspot", f.hotspot_forecast)}
      ${bar("Centrality", f.centrality)}
    </div>
    <div class="muted meta">
      ${escapeHtml(f.language)} · ${f.nloc} LOC · ${f.functions} fns · worst CCN ${f.max_ccn}
      · ${f.commits} commits · ${f.authors} authors · ${f.bugfix_commits} fixes
    </div>
    <ul class="reasons">${f.reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
  `;
}

// ---------- tour ----------
async function buildTour() {
  const btn = $("#tour-btn");
  btn.disabled = true;
  btn.textContent = "Building";
  $("#tour-summary").textContent = "Designing an onboarding path.";
  try {
    const tour = await api("/api/tour", { method: "POST" });
    $("#tour-summary").textContent = tour.summary || "";
    const ol = $("#tour");
    ol.innerHTML = "";
    (tour.steps || []).forEach((s, i) => {
      const li = document.createElement("li");
      li.style.animationDelay = `${i * 0.06}s`;
      li.innerHTML = `
        <div class="t-title">${escapeHtml(s.title || s.path)}</div>
        <div class="t-path">${escapeHtml(s.path || "")}</div>
        <div class="t-why">${escapeHtml(s.why || "")}</div>
        ${s.watch_out ? `<div class="t-watch">Heads up: ${escapeHtml(s.watch_out)}</div>` : ""}`;
      ol.appendChild(li);
    });
  } catch (e) {
    $("#tour-summary").textContent = "Error: " + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Rebuild tour";
  }
}

// ================= workflow: staged request pipeline =================
function renderFlow() {
  const pipe = $("#flow-pipe");
  const g = (REPORT && REPORT.graph) || { nodes: [], edges: [] };
  FLOW_SEL = null;
  if (!g.nodes.length) {
    pipe.innerHTML = "";
    $("#flow-explain").textContent =
      "No import relationships were detected, so there is no flow to chart for this repo.";
    $("#flow-caption").textContent = "";
    return;
  }

  const starts = g.nodes.filter((n) => n.in_degree === 0);
  const ends = g.nodes.filter((n) => n.out_degree === 0);
  const names = (arr) => arr.slice(0, 3).map((n) => n.label).join(", ") + (arr.length > 3 ? "…" : "");
  $("#flow-explain").innerHTML =
    `Read it top to bottom. It is the journey a request takes through the code. ` +
    `It <strong>starts</strong> at the entry points` +
    (starts.length ? ` (<em>${escapeHtml(names(starts))}</em>)` : "") +
    `, where input first arrives, then each stage hands work down to the next, ` +
    `finishing at the <strong>foundation</strong> modules` +
    (ends.length ? ` (<em>${escapeHtml(names(ends))}</em>)` : "") +
    ` that everything is built on.`;

  const maxLayer = Math.max(0, ...g.nodes.map((n) => n.layer || 0));
  const stages = [];
  for (let L = maxLayer; L >= 0; L--) {
    const nodes = g.nodes.filter((n) => (n.layer || 0) === L).sort((a, b) => b.difficulty - a.difficulty);
    if (nodes.length) stages.push(nodes);
  }

  pipe.innerHTML = stages.map((nodes, i) => {
    const role = i === 0
      ? "Entry — where execution starts and input arrives"
      : i === stages.length - 1
        ? "Foundation — shared data, models and config everything relies on"
        : `Processing step ${i} — work happens here`;
    const chips = nodes.map((n) =>
      `<button class="pipe-node" data-id="${escAttr(n.id)}" style="--c:${heatColor(n.difficulty)}">
        <span class="pn-name">${escapeHtml(n.label)}</span>
        <span class="pn-lang">${escapeHtml(n.language || "")}</span>
      </button>`).join("");
    const conn = i < stages.length - 1 ? '<div class="stage-conn"></div>' : "";
    return `<div class="stage">
        <div class="stage-head"><span class="stage-num">${i + 1}</span><span class="stage-role">${role}</span></div>
        <div class="stage-nodes">${chips}</div>
      </div>${conn}`;
  }).join("");

  pipe.querySelectorAll(".pipe-node").forEach((b) =>
    b.addEventListener("click", () => selectFlowNode(b.dataset.id))
  );
}

function selectFlowNode(id) {
  FLOW_SEL = FLOW_SEL === id ? null : id;
  const edges = (REPORT.graph && REPORT.graph.edges) || [];
  const uses = new Set(edges.filter((e) => e.source === FLOW_SEL).map((e) => e.target));
  const usedBy = new Set(edges.filter((e) => e.target === FLOW_SEL).map((e) => e.source));

  document.querySelectorAll(".pipe-node").forEach((n) => {
    const nid = n.dataset.id;
    n.classList.toggle("sel", !!FLOW_SEL && nid === FLOW_SEL);
    n.classList.toggle("rel", !!FLOW_SEL && (uses.has(nid) || usedBy.has(nid)));
    n.classList.toggle("fade", !!FLOW_SEL && nid !== FLOW_SEL && !uses.has(nid) && !usedBy.has(nid));
  });

  const cap = $("#flow-caption");
  if (!FLOW_SEL) {
    cap.className = "flow-caption muted";
    cap.textContent = "Click any file to see what feeds into it and what it feeds.";
    return;
  }
  const name = id.split("/").pop();
  const role = usedBy.size === 0 ? "an entry point, execution can start here"
    : uses.size === 0 ? "a foundation module, lots of things build on it"
    : "a middle step that passes work along";
  const chips = (set) => set.size
    ? [...set].map((p) => `<button class="flow-chip" data-path="${escAttr(p)}">${escapeHtml(p.split("/").pop())}</button>`).join("")
    : '<span class="muted">nothing</span>';

  cap.className = "flow-caption";
  cap.innerHTML =
    `<div class="cap-title"><code>${escapeHtml(name)}</code> is ${role}.</div>
     <div class="cap-row"><span class="cap-lbl">uses</span> <span class="cap-chips">${chips(uses)}</span></div>
     <div class="cap-row"><span class="cap-lbl">used by</span> <span class="cap-chips">${chips(usedBy)}</span></div>`;
  cap.querySelectorAll(".flow-chip").forEach((b) =>
    b.addEventListener("click", () => selectFlowNode(b.dataset.path))
  );
}

// ---------- chat ----------
function addMsg(text, who) {
  const el = document.createElement("div");
  el.className = "msg " + who;
  el.innerHTML = who === "bot" ? formatBot(text) : escapeHtml(text);
  $("#chat").appendChild(el);
  $("#chat").scrollTop = $("#chat").scrollHeight;
  return el;
}
const addBot = (t) => addMsg(t, "bot");

function formatInline(safe) {
  safe = safe.replace(/&lt;br\s*\/?&gt;/gi, "<br>");
  const tokens = [];
  const stash = (html) => { tokens.push(html); return `\u0000${tokens.length - 1}\u0000`; };
  safe = safe.replace(/`([^`]+)`/g, (_m, c) => stash(`<code>${c}</code>`));
  safe = safe.replace(/\[([^\]]+)\]\((https?:[^\s)]+)\)/g,
    (_m, label, url) => stash(`<a href="${url}" target="_blank" rel="noopener">${label}</a>`));
  safe = safe.replace(/(https?:\/\/[^\s<>()"']+)/g,
    (url) => stash(`<a href="${url}" target="_blank" rel="noopener">${url}</a>`));
  safe = safe.replace(/([\w./-]+\.\w+:\d+(?:-\d+)?)/g, (m) => stash(`<span class="cite">${m}</span>`));
  safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  safe = safe.replace(/(^|[^*\w])\*(?!\s)([^*]+?)\*(?!\w)/g, "$1<em>$2</em>");
  safe = safe.replace(/\u0000(\d+)\u0000/g, (_m, i) => tokens[+i]);
  return safe;
}

function formatBot(text) {
  const lines = (text || "").replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let i = 0;
  const isTableSep = (s) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$/.test(s);
  const splitRow = (s) => {
    let r = s.trim();
    if (r.startsWith("|")) r = r.slice(1);
    if (r.endsWith("|")) r = r.slice(0, -1);
    return r.split("|").map((c) => c.trim());
  };

  while (i < lines.length) {
    const line = lines[i];
    const fence = line.match(/^\s*```(\w*)\s*$/);
    if (fence) {
      const code = [];
      i++;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) { code.push(lines[i]); i++; }
      i++;
      const lang = fence[1] ? ` data-lang="${escapeHtml(fence[1])}"` : "";
      out.push(`<pre class="md-code"${lang}><code>${escapeHtml(code.join("\n"))}</code></pre>`);
      continue;
    }
    if (line.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const header = splitRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "") { rows.push(splitRow(lines[i])); i++; }
      const th = header.map((c) => `<th>${formatInline(escapeHtml(c))}</th>`).join("");
      const trs = rows.map((r) => `<tr>${header.map((_, c) => `<td>${formatInline(escapeHtml(r[c] || ""))}</td>`).join("")}</tr>`).join("");
      out.push(`<div class="md-table-wrap"><table class="md-table"><thead><tr>${th}</tr></thead><tbody>${trs}</tbody></table></div>`);
      continue;
    }
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) { out.push(`<h${h[1].length} class="md-h md-h${h[1].length}">${formatInline(escapeHtml(h[2]))}</h${h[1].length}>`); i++; continue; }
    if (/^\s*>\s?/.test(line)) {
      const quote = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) { quote.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
      out.push(`<blockquote class="md-quote">${formatInline(escapeHtml(quote.join(" ")))}</blockquote>`);
      continue;
    }
    if (/^\s*[-*+]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*+]\s+/, "")); i++; }
      out.push(`<ul class="md-list">${items.map((t) => `<li>${formatInline(escapeHtml(t))}</li>`).join("")}</ul>`);
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*\d+[.)]\s+/, "")); i++; }
      out.push(`<ol class="md-list">${items.map((t) => `<li>${formatInline(escapeHtml(t))}</li>`).join("")}</ol>`);
      continue;
    }
    if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) { out.push('<hr class="md-hr" />'); i++; continue; }
    if (line.trim() === "") { i++; continue; }
    const para = [];
    while (i < lines.length && lines[i].trim() !== "" && !/^\s*```/.test(lines[i]) &&
      !/^(#{1,6})\s+/.test(lines[i]) && !/^\s*[-*+]\s+/.test(lines[i]) &&
      !/^\s*\d+[.)]\s+/.test(lines[i]) && !/^\s*>\s?/.test(lines[i]) &&
      !(lines[i].includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1]))
    ) { para.push(lines[i]); i++; }
    out.push(`<p class="md-p">${formatInline(escapeHtml(para.join("\n"))).replace(/\n/g, "<br>")}</p>`);
  }
  return out.join("");
}

async function ask(q) {
  addMsg(q, "user");
  const thinking = addMsg("", "bot");
  thinking.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>';
  try {
    const res = await api("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
    thinking.innerHTML = formatBot(res.answer || "(no answer)");
  } catch (e) {
    thinking.innerHTML = formatBot("Error: " + e.message);
  }
  $("#chat").scrollTop = $("#chat").scrollHeight;
}

// ---------- helpers ----------
function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function escAttr(s) { return (s || "").replace(/"/g, "&quot;"); }

// ---------- wire up ----------
$("#analyze-btn").addEventListener("click", () => {
  const src = $("#source").value.trim();
  if (src) analyze(src);
});
$("#source").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#analyze-btn").click(); });
document.querySelectorAll(".sample").forEach((b) =>
  b.addEventListener("click", () => { $("#source").value = b.dataset.src; analyze(b.dataset.src); })
);
$("#new-analysis").addEventListener("click", showLaunch);
$("#tour-btn").addEventListener("click", buildTour);

// sidebar nav
document.querySelectorAll(".nav-item").forEach((b) =>
  b.addEventListener("click", () => {
    const nav = b.dataset.nav;
    if (b.disabled) return;
    if (nav === "analyze") { showLaunch(); }
    else if (nav === "workflow") { setNav("workflow"); openModal("workflow"); }
    else if (nav === "ask") { setNav("ask"); openModal("chat"); }
  })
);

// modal close handlers
$("#overlay").addEventListener("click", (e) => { if (e.target === $("#overlay")) closeModal(); });
document.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", closeModal));
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

$("#chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("#question").value.trim();
  if (q) { ask(q); $("#question").value = ""; }
});

refreshStatus();
