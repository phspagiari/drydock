/* drydock board — polls /api/state and renders the queue. No dependencies. */

const POLL_MS = 4000;

const SECTIONS = [
  ["blocked",   "Blocked — needs you",  "copy the command → run it in a new terminal"],
  ["delivered", "Ready for review",     "review the PR, then archive or reject"],
  ["active",    "In flight",            "executors working"],
  ["inbox",     "Inbox",                "waiting for the orchestrator"],
  ["archive",   "Archive",              "most recent first"],
];

/* Whitelisted so an arbitrary verdict string can never become a class name. */
const VERDICT_CLASS = {
  ship: "ship", fix: "fix", flag: "flag",
  reject: "reject", rejected: "reject",
};

const el = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(
  /[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let prev = {};          // id -> "<state>:<mtime>", for change flashing
let firstRender = true;
let latestFiles = {};   // id -> allowed file names, so an open drawer stays current
let drawer = { id: null, file: null };

/* ------------------------------------------------------------------ render */

function age(mtime, nowEpoch) {
  const hours = (nowEpoch - mtime) / 3600;
  if (hours < 1) return Math.max(0, Math.round(hours * 60)) + "m";
  if (hours < 48) return Math.round(hours) + "h";
  return (hours / 24).toFixed(1) + "d";
}

function commandFor(item, state) {
  if (state === "blocked") return `claude "/drydock:spec unblock ${item.id}"`;
  if (state === "delivered") return `claude "/drydock:review ${item.id}"`;
  return "";
}

function linkFor(item, state) {
  if (!item.url) return "";
  const label = state === "delivered"
    ? (item.kind === "pr" ? "open PR" : "open report")
    : item.url;
  return `<a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(label)}</a>`;
}

function card(item, state, nowEpoch) {
  const cmd = commandFor(item, state);
  const link = linkFor(item, state);
  const hours = (nowEpoch - item.mtime) / 3600;

  const verdict = item.review
    ? `<span class="badge ${VERDICT_CLASS[item.review] || ""}">${esc(item.review)}</span>`
    : "";
  const gist = item.gist
    ? `<div class="gist${item.gist.startsWith("waiting on:") ? " waiting" : ""}">${esc(item.gist)}</div>`
    : "";
  const act = (cmd || link)
    ? `<div class="act">${cmd
        ? `<code>${esc(cmd)}</code><button class="copy" data-cmd="${esc(cmd)}">copy</button>`
        : ""}${link}</div>`
    : "";

  return `<article class="card" id="c-${esc(item.id)}" data-id="${esc(item.id)}"
    data-state="${esc(state)}" tabindex="0" role="button"
    aria-label="Open files for ${esc(item.id)}">
    <div class="row">
      <span class="pill">${esc(item.track)}</span>
      <code class="id">${esc(item.id)}</code>
      ${verdict}
      <span class="age${hours >= 24 && state !== "archive" ? " old" : ""}">${age(item.mtime, nowEpoch)}</span>
    </div>
    <div class="title">${esc(item.title)}</div>
    ${gist}${act}
  </article>`;
}

function render(state) {
  const nowEpoch = state.now_epoch || Math.floor(Date.now() / 1000);

  el("sections").innerHTML = SECTIONS.map(([key, name, hint]) => {
    const rows = state[key] || [];
    const body = rows.length
      ? rows.map((item) => card(item, key, nowEpoch)).join("")
      : `<div class="empty">nothing here</div>`;
    return `<section>
      <div class="sec-head">
        <h2>${name}</h2>
        <span class="count${rows.length ? "" : " zero"}">${rows.length}</span>
        <span class="hint">${hint}</span>
      </div>${body}
    </section>`;
  }).join("");

  latestFiles = {};
  const seen = {};
  for (const [key, rows] of Object.entries(state)) {
    if (!Array.isArray(rows)) continue;
    for (const item of rows) {
      latestFiles[item.id] = item.files || [];
      const stamp = key + ":" + item.mtime;
      seen[item.id] = stamp;
      if (!firstRender && prev[item.id] !== undefined && prev[item.id] !== stamp) {
        const node = el("c-" + item.id);
        if (node) node.classList.add("flash");
      }
    }
  }
  prev = seen;
  firstRender = false;

  const blocked = (state.blocked || []).length;
  const ready = (state.delivered || []).length;
  document.title = (blocked ? `${blocked}⚠ ` : "") + (ready ? `${ready}✓ ` : "") + "drydock board";

  el("repo").textContent = state.repo || "";
  if (drawer.id) syncDrawerTabs();
}

/* -------------------------------------------------------------------- poll */

async function tick() {
  let state;
  try {
    const res = await fetch("/api/state", { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    state = await res.json();
  } catch (err) {
    el("status").classList.add("off");
    el("stamp").textContent = "offline";
    el("banner").hidden = false;
    return;
  }
  el("status").classList.remove("off");
  el("stamp").textContent = "live · " + state.now;
  el("banner").hidden = true;
  render(state);
}

/* ------------------------------------------------------------------ drawer */

function syncDrawerTabs() {
  const files = latestFiles[drawer.id] || [];
  el("drawer-tabs").innerHTML = files.length
    ? files.map((f) => `<button class="tab${f === drawer.file ? " active" : ""}" data-file="${esc(f)}">${esc(f)}</button>`).join("")
    : `<span class="empty">no readable files</span>`;
}

async function openDrawer(id) {
  drawer.id = id;
  const files = latestFiles[id] || [];
  drawer.file = files.includes("QUESTION.md") ? "QUESTION.md" : (files[0] || null);
  el("drawer-title").textContent = id;
  el("drawer-file").textContent = files.length ? "loading…" : "This item has no readable files yet.";
  el("drawer").hidden = false;
  el("scrim").hidden = false;
  syncDrawerTabs();
  if (drawer.file) await showFile(drawer.file);
  el("drawer").querySelector("button")?.focus();
}

function closeDrawer() {
  drawer = { id: null, file: null };
  el("drawer").hidden = true;
  el("scrim").hidden = true;
}

async function showFile(name) {
  drawer.file = name;
  syncDrawerTabs();
  const target = el("drawer-file");
  try {
    const res = await fetch(
      `/api/file?id=${encodeURIComponent(drawer.id)}&name=${encodeURIComponent(name)}`,
      { cache: "no-store" });
    target.textContent = res.ok ? await res.text() : "not found";
  } catch (err) {
    target.textContent = "could not load — server unreachable";
  }
}

/* ------------------------------------------------------------------ events */

function copyToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text);
  }
  return new Promise((resolve, reject) => {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand && document.execCommand("copy");
    document.body.removeChild(ta);
    ok ? resolve() : reject(new Error("copy failed"));
  });
}

/* One delegated listener: inline handlers break as soon as markup is re-rendered. */
document.addEventListener("click", (e) => {
  const copyBtn = e.target.closest("button.copy");
  if (copyBtn) {
    e.stopPropagation();
    const settle = (cls, label) => {
      copyBtn.classList.add(cls);
      copyBtn.textContent = label;
      setTimeout(() => { copyBtn.classList.remove(cls); copyBtn.textContent = "copy"; }, 1500);
    };
    copyToClipboard(copyBtn.dataset.cmd).then(
      () => settle("done", "copied"),
      () => settle("failed", "copy failed"));
    return;
  }

  const tab = e.target.closest("button.tab");
  if (tab) { showFile(tab.dataset.file); return; }

  if (e.target.closest("[data-close]") || e.target.closest("#scrim")) { closeDrawer(); return; }
  if (e.target.closest("#drawer")) return;
  if (e.target.closest("a")) return;   // links navigate; no drawer

  const c = e.target.closest(".card");
  if (c) openDrawer(c.dataset.id);
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && drawer.id) { closeDrawer(); return; }
  const c = e.target.closest && e.target.closest(".card");
  if (c && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openDrawer(c.dataset.id); }
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) tick();
});

tick();
setInterval(tick, POLL_MS);
