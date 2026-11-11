// Codebase Onboarding Agent - frontend controller
const $ = (sel) => document.querySelector(sel);
const api = (path, opts) => fetch(path, opts).then(async (r) => {
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
});

let REPORT = null;

// ---------- animated starfield ----------
(function stars() {
  const c = $("#stars");
  const ctx = c.getContext("2d");
  let pts = [];
  function resize() {
    c.width = window.innerWidth;
    c.height = window.innerHeight;
    pts = Array.from({ length: Math.min(160, (c.width * c.height) / 9000) }, () => ({
      x: Math.random() * c.width,
      y: Math.random() * c.height,
      z: Math.random() * 0.8 + 0.2,
      s: Math.random() * 1.6 + 0.3,
    }));
  }
  function tick() {
    ctx.clearRect(0, 0, c.width, c.height);
    for (const p of pts) {
      p.y += p.z * 0.25;
      if (p.y > c.height) { p.y = 0; p.x = Math.random() * c.width; }
      ctx.globalAlpha = p.z;
      ctx.fillStyle = p.z > 0.7 ? "#fcbf49" : "#f77f00";
      ctx.fillRect(p.x, p.y, p.s, p.s);
    }
    requestAnimationFrame(tick);
  }
  window.addEventListener("resize", resize);
  resize();
  tick();
})();

// ---------- color scale for difficulty (palette: navy -> yellow -> orange -> red) ----------
function heatColor(v) {
  v = Math.max(0, Math.min(100, Number(v) || 0));
  const stops = [
    [0, [0, 48, 73]],      // #003049 navy  (easy)
    [40, [252, 191, 73]],  // #fcbf49 yellow
    [70, [247, 127, 0]],   // #f77f00 orange
    [100, [214, 40, 40]],  // #d62828 red   (hard)
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
    setChip("#chip-groq-2", "Groq", s.has_groq);
    setChip("#chip-tavily-2", "Tavily", s.has_tavily);
  } catch (_) {}
}
function setChip(sel, label, on) {
  const el = $(sel);
  if (!el) return;
  el.textContent = `${label}: ${on ? "on" : "off"}`;
  el.classList.toggle("on", on);
  el.classList.toggle("off", !on);
}

// ---------- view switching ----------
function showDashboard() {
  $("#launch-view").classList.add("gone");
  const dash = $("#dashboard");
  dash.hidden = false;
  requestAnimationFrame(() => dash.classList.add("show"));
}
function showLaunch() {
  const dash = $("#dashboard");
  dash.classList.remove("show");
  dash.hidden = true;
  $("#launch-view").classList.remove("gone");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ---------- analyze ----------
async function analyze(source) {
  const btn = $("#analyze-btn");
  const status = $("#status");
  btn.disabled = true;
  btn.querySelector(".btn-label").textContent = "Analyzing";
  btn.querySelector(".spinner").hidden = false;
  status.className = "status";
  status.textContent = "Cloning + reading git history + scoring modules… (first clone can take a bit)";
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

// ---------- render ----------
function renderDashboard() {
  $("#repo-name").textContent = REPORT.name || "Repository";
  $("#repo-sub").textContent = `${REPORT.total_files} files · ${REPORT.total_commits} commits analyzed`;
  renderStats();
  renderHeatmap();
  $("#tour").innerHTML = "";
  $("#tour-summary").textContent = "Generate an ordered path through the codebase, easiest-first.";
  $("#chat").innerHTML = "";
  addBot("Repository loaded. Ask me how it works, or build a guided tour above.");
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
    `<div class="stat"><div class="num">${num}</div><div class="lbl">${lbl}</div></div>`
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
    <span class="bar-track">
      <span class="bar-fill" style="width:${v}%;background:linear-gradient(90deg, ${col}, ${col});box-shadow:0 0 10px ${col}99"></span>
    </span>
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
    <div class="muted" style="font-size:12px;font-family:'JetBrains Mono',monospace">
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
  btn.textContent = "Building…";
  $("#tour-summary").textContent = "Designing an onboarding path…";
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
        ${s.watch_out ? `<div class="t-watch">⚠ ${escapeHtml(s.watch_out)}</div>` : ""}`;
      ol.appendChild(li);
    });
  } catch (e) {
    $("#tour-summary").textContent = "Error: " + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Rebuild tour";
  }
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

// ---------- inline markdown (input is already HTML-escaped) ----------
function formatInline(safe) {
  // model sometimes emits literal <br> tags inside cells
  safe = safe.replace(/&lt;br\s*\/?&gt;/gi, "<br>");

  // stash tokens so later passes don't double-process them
  const tokens = [];
  const stash = (html) => { tokens.push(html); return `\u0000${tokens.length - 1}\u0000`; };

  // inline code
  safe = safe.replace(/`([^`]+)`/g, (_m, c) => stash(`<code>${c}</code>`));
  // markdown links [label](url)
  safe = safe.replace(/\[([^\]]+)\]\((https?:[^\s)]+)\)/g,
    (_m, label, url) => stash(`<a href="${url}" target="_blank" rel="noopener">${label}</a>`));
  // bare URLs (escaped & is fine inside href)
  safe = safe.replace(/(https?:\/\/[^\s<>()"']+)/g,
    (url) => stash(`<a href="${url}" target="_blank" rel="noopener">${url}</a>`));
  // file:line citations like path/file.py:12-40
  safe = safe.replace(/([\w./-]+\.\w+:\d+(?:-\d+)?)/g, (m) => stash(`<span class="cite">${m}</span>`));

  // bold then italic
  safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  safe = safe.replace(/(^|[^*\w])\*(?!\s)([^*]+?)\*(?!\w)/g, "$1<em>$2</em>");

  // restore stashed tokens
  safe = safe.replace(/\u0000(\d+)\u0000/g, (_m, i) => tokens[+i]);
  return safe;
}

// ---------- block-level markdown renderer ----------
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

    // fenced code block
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

    // table
    if (line.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const header = splitRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "") {
        rows.push(splitRow(lines[i]));
        i++;
      }
      const th = header.map((c) => `<th>${formatInline(escapeHtml(c))}</th>`).join("");
      const trs = rows.map((r) => {
        const tds = header.map((_, c) => `<td>${formatInline(escapeHtml(r[c] || ""))}</td>`).join("");
        return `<tr>${tds}</tr>`;
      }).join("");
      out.push(`<div class="md-table-wrap"><table class="md-table"><thead><tr>${th}</tr></thead><tbody>${trs}</tbody></table></div>`);
      continue;
    }

    // heading
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      const lvl = h[1].length;
      out.push(`<h${lvl} class="md-h md-h${lvl}">${formatInline(escapeHtml(h[2]))}</h${lvl}>`);
      i++;
      continue;
    }

    // blockquote
    if (/^\s*>\s?/.test(line)) {
      const quote = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) { quote.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
      out.push(`<blockquote class="md-quote">${formatInline(escapeHtml(quote.join(" ")))}</blockquote>`);
      continue;
    }

    // unordered list
    if (/^\s*[-*+]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*+]\s+/, "")); i++; }
      out.push(`<ul class="md-list">${items.map((t) => `<li>${formatInline(escapeHtml(t))}</li>`).join("")}</ul>`);
      continue;
    }

    // ordered list
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*\d+[.)]\s+/, "")); i++; }
      out.push(`<ol class="md-list">${items.map((t) => `<li>${formatInline(escapeHtml(t))}</li>`).join("")}</ol>`);
      continue;
    }

    // horizontal rule
    if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) { out.push('<hr class="md-hr" />'); i++; continue; }

    // blank
    if (line.trim() === "") { i++; continue; }

    // paragraph
    const para = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^\s*```/.test(lines[i]) &&
      !/^(#{1,6})\s+/.test(lines[i]) &&
      !/^\s*[-*+]\s+/.test(lines[i]) &&
      !/^\s*\d+[.)]\s+/.test(lines[i]) &&
      !/^\s*>\s?/.test(lines[i]) &&
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

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// ---------- wire up ----------
$("#analyze-btn").addEventListener("click", () => {
  const src = $("#source").value.trim();
  if (src) analyze(src);
});
$("#source").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("#analyze-btn").click();
});
document.querySelectorAll(".sample").forEach((b) =>
  b.addEventListener("click", () => {
    $("#source").value = b.dataset.src;
    analyze(b.dataset.src);
  })
);
$("#new-analysis").addEventListener("click", showLaunch);
$("#tour-btn").addEventListener("click", buildTour);
$("#chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("#question").value.trim();
  if (q) { ask(q); $("#question").value = ""; }
});

refreshStatus();
