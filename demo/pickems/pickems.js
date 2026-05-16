// ── pickems.js — The Lakeside League Pick'ems (DEMO build) ──
// No Firebase: vote bars + records modal are seeded from hardcoded data,
// submissions are client-only and reset on refresh.

const dateFmt = new Intl.DateTimeFormat("en-US", {
  weekday: "short", month: "short", day: "numeric",
  hour: "numeric", minute: "2-digit", timeZone: "America/New_York",
});

// ── DOM refs ──────────────────────────────────────────────────────────────
function byId(id) { return document.getElementById(id); }

function canonical(id) {
  const all = Array.from(document.querySelectorAll(`#${id}`));
  all.slice(1).forEach(el => el.remove());
  return all[0] || null;
}

const elTabs    = canonical("weekTabs");
const elViews   = canonical("weekViews");
const loginForm = byId("loginForm");
const elWhoami  = byId("whoami");
const logoutBtn = byId("logoutBtn");
const submitBtn = byId("submitPicks");
const submitHint = byId("submitHint");

// ── State ─────────────────────────────────────────────────────────────────
const state = {
  teams:         {},
  weeks:         [],
  activeWeekId:  null,
  currentWeekId: null,
  accounts:      [],
  user:          null,
  pending:       { picks: {}, hl: {} },
};

const recordsState = { weekVotes: {} };

// ── Boot ──────────────────────────────────────────────────────────────────
initAuthUI();
boot().catch(console.error);

async function boot() {
  const v = Date.now(); // cache-buster so JSON edits show up without a hard-refresh
  const [teamsJson, manifest, usersJson] = await Promise.all([
    fetch(`./teams.json?v=${v}`).then(r => r.json()),
    fetch(`./manifest.json?v=${v}`).then(r => r.json()),
    fetch(`./users.json?v=${v}`).then(r => r.json()),
  ]);

  state.accounts = usersJson.accounts || [];
  state.teams    = indexBy(teamsJson.teams || [], t => t.id);

  if (!(manifest.weeks || []).length) {
    showPreseason();
    return;
  }

  const now = Date.now();
  const openWeeks = [];
  for (const w of manifest.weeks) {
    const data = await fetch(`./${w.data}?v=${v}`).then(r => r.json());
    if (new Date(data.openAt).getTime() <= now) {
      openWeeks.push({ meta: w, data });
    }
  }
  openWeeks.sort((a, b) => new Date(a.data.openAt) - new Date(b.data.openAt));
  state.weeks        = openWeeks;
  state.currentWeekId = openWeeks.length ? openWeeks[openWeeks.length - 1].data.id : null;

  if (elTabs) {
    elTabs.innerHTML = openWeeks.map(w => {
      const cur = w.data.id === state.currentWeekId;
      return `<button class="pe-tab" data-week="${w.data.id}" data-current="${cur}">${w.data.label}${cur ? ' <span class="tab-sub">current</span>' : ""}</button>`;
    }).join("");
    elTabs.addEventListener("click", e => {
      const btn = e.target.closest(".pe-tab");
      if (btn) setActive(btn.dataset.week);
    });
  }

  if (elViews) {
    elViews.innerHTML = openWeeks.map(w => weekViewHTML(w.data)).join("");
  }

  if (state.currentWeekId) setActive(state.currentWeekId);

  for (const w of openWeeks) {
    await hydrateWeek(w.data);
  }

  initRecords();
}

function showPreseason() {
  if (elViews) {
    elViews.innerHTML = `
      <div class="pe-preseason">
        <h2>Season hasn't started yet</h2>
        <p>Pick'ems will appear here once Week 1 matchups are set.<br>Check back after the first Tuesday update.</p>
      </div>`;
  }
  if (submitBtn) submitBtn.hidden = true;
}

// ── Views ─────────────────────────────────────────────────────────────────
function setActive(weekId) {
  state.activeWeekId = weekId;
  // NOTE: the CSS selector is .week[data-active="true"] (literal string),
  // so we set the attribute value explicitly. toggleAttribute would write
  // an empty string and never match the selector.
  document.querySelectorAll(".pe-tab").forEach(x => {
    if (x.dataset.week === weekId) x.setAttribute("data-active", "true");
    else x.removeAttribute("data-active");
  });
  document.querySelectorAll(".week").forEach(x => {
    if (x.dataset.week === weekId) x.setAttribute("data-active", "true");
    else x.removeAttribute("data-active");
  });
  state.pending = { picks: {}, hl: {} };
  updateSubmitEnabled();
}

function weekViewHTML(w) {
  // Prefer literal display strings from the week JSON if present
  // (openLabel / revealLabel / lockLabel). Fall back to formatting
  // the ISO dates if no label is provided.
  const open   = w.openLabel   || dateFmt.format(new Date(w.openAt));
  const reveal = w.revealLabel || dateFmt.format(new Date(w.revealAt));
  const lock   = w.lockLabel   || dateFmt.format(new Date(w.lockAt));
  return `
    <section class="week" data-week="${w.id}">
      <div class="week-info">
        <span class="badge">Opens ${open}</span>
        <span class="badge">Reveals ${reveal}</span>
        <span class="badge">Locks ${lock}</span>
      </div>
      <div id="lock-msg-${w.id}" class="week-locked"></div>

      ${w.gameOfWeek ? `
        <div class="gotw-title">Game of the Week
          <span class="sub">Matchup spotlight</span>
        </div>` : ""}

      <div class="pe-grid" id="grid-${w.id}"></div>

      <div class="hl-card">
        <div class="hl-row">
          <div class="select">
            <label class="hl-label" for="hl-high-${w.id}">Highest Scorer</label>
            <select id="hl-high-${w.id}"><option value="">Select team</option></select>
          </div>
          <div class="select">
            <label class="hl-label" for="hl-low-${w.id}">Lowest Scorer</label>
            <select id="hl-low-${w.id}"><option value="">Select team</option></select>
          </div>
        </div>
        <div id="hl-reveal-${w.id}" style="margin-top:8px"></div>
      </div>
    </section>`;
}

async function hydrateWeek(w) {
  const grid = byId(`grid-${w.id}`);
  if (!grid) return;

  const now      = new Date();
  const revealAt = new Date(w.revealAt);
  const lockAt   = new Date(w.lockAt);
  const locked   = now >= lockAt;

  const lockMsg = byId(`lock-msg-${w.id}`);
  if (lockMsg) lockMsg.textContent = locked ? "Locked" : "";

  // Populate high/low selects
  const opts = w.highestLowestOptions?.length
    ? w.highestLowestOptions
    : Array.from(new Set(w.matchups.flatMap(m => [m.home, m.away])));

  const hiSel = byId(`hl-high-${w.id}`);
  const loSel = byId(`hl-low-${w.id}`);
  if (hiSel && loSel && hiSel.options.length <= 1) {
    for (const tid of opts) {
      const team = state.teams[tid];
      if (!team) continue;
      const o = new Option(team.name, tid);
      hiSel.add(o.cloneNode(true));
      loSel.add(o);
    }
  }

  // Order with game of the week first
  const order = [...w.matchups];
  if (w.gameOfWeek) {
    const idx = order.findIndex(m => m.id === w.gameOfWeek);
    if (idx > -1) order.unshift(...order.splice(idx, 1));
  }

  grid.innerHTML = order.map(m => matchHTML(w, m, locked, w.gameOfWeek === m.id)).join("");

  // Bind click handlers once
  if (!grid.dataset.bound) {
    grid.addEventListener("click", e => {
      const btn = e.target.closest(".vote-btn");
      if (!btn) return;
      if (!state.user)  { alert("Login first."); return; }
      if (locked)       { alert("Voting is locked for this week."); return; }

      const mid = btn.dataset.matchup;
      const m   = w.matchups.find(x => x.id === mid);
      if (state.user.teamId && (m.home === state.user.teamId || m.away === state.user.teamId)) {
        alert("You cannot vote on your own matchup.");
        return;
      }

      const teamId = btn.dataset.team;
      state.pending.picks[mid] = teamId;

      grid.querySelectorAll(`.match[data-mid="${mid}"] .vote-btn`).forEach(b => {
        b.dataset.picked = b.dataset.team === teamId ? "true" : "";
      });
      updateSubmitEnabled();
    });
    grid.dataset.bound = "1";
  }

  if (hiSel && !hiSel.dataset.bound) {
    hiSel.addEventListener("change", () => {
      if (!state.user) { alert("Login first."); hiSel.value = ""; return; }
      if (locked)      { alert("Voting is locked."); hiSel.value = ""; return; }
      state.pending.hl.highest = hiSel.value || undefined;
      updateSubmitEnabled();
    });
    hiSel.dataset.bound = "1";
  }
  if (loSel && !loSel.dataset.bound) {
    loSel.addEventListener("change", () => {
      if (!state.user) { alert("Login first."); loSel.value = ""; return; }
      if (locked)      { alert("Voting is locked."); loSel.value = ""; return; }
      state.pending.hl.lowest = loSel.value || undefined;
      updateSubmitEnabled();
    });
    loSel.dataset.bound = "1";
  }

  if (state.user) await loadExistingSubmission(w);

  liveTally(w, revealAt);
  updateSubmitEnabled();
}

function matchHTML(w, m, locked, isGOTW) {
  const A   = state.teams[m.home];
  const B   = state.teams[m.away];
  const recA = w.records?.[m.home] || "";
  const recB = w.records?.[m.away] || "";

  const teamBlock = (side, team, rec, isAway) => {
    const champ = team?.isChampion ? '<span title="Defending Champion">👑</span>' : "";
    const name = esc(team?.name || side);
    const recHTML = `<span class="record">${esc(rec)}</span>`;
    const nameLine = isAway
      ? `${recHTML} ${name} ${champ}`
      : `${name} ${champ} ${recHTML}`;
    const lwk = team?.last_week_points != null
      ? `<div class="lwk"><span class="lbl">LAST WK</span> <strong>${team.last_week_points.toFixed(1)}</strong></div>`
      : "";
    return `
      <div class="team" data-team="${side}">
        <div class="logo">${team ? `<img src="${esc(team.logo)}" alt="${esc(team.name)}" loading="lazy">` : ""}</div>
        <div class="meta">
          <div class="team-name">${nameLine}</div>
          <div class="manager">${esc(team?.manager || "")}</div>
          ${lwk}
        </div>
      </div>`;
  };

  // Center cell: this week's projections side-by-side with "vs" between.
  const haveProj = A?.projected_points != null && B?.projected_points != null;
  const projCell = haveProj
    ? `<div class="vs">
         <span class="vs-pts home">${A.projected_points.toFixed(1)}</span>
         <span class="vs-mid">vs</span>
         <span class="vs-pts away">${B.projected_points.toFixed(1)}</span>
       </div>`
    : `<div class="vs"><span class="vs-mid">vs</span></div>`;

  return `
    <div class="match"${isGOTW ? ' data-gotw="true"' : ""} data-mid="${m.id}">
      <div class="match-top">
        ${teamBlock(m.home, A, recA, false)}
        ${projCell}
        ${teamBlock(m.away, B, recB, true)}
      </div>
      <div class="vote">
        <div class="buttons">
          <button class="vote-btn" data-matchup="${m.id}" data-team="${m.home}">
            <span class="vote-name">${esc(A?.name || m.home)}</span>
            <span class="vote-pct" id="vp-${w.id}-${m.id}-${esc(m.home)}">—</span>
          </button>
          <button class="vote-btn" data-matchup="${m.id}" data-team="${m.away}">
            <span class="vote-name">${esc(B?.name || m.away)}</span>
            <span class="vote-pct" id="vp-${w.id}-${m.id}-${esc(m.away)}">—</span>
          </button>
        </div>
        <div class="bar2" id="bar-${w.id}-${m.id}">
          <span class="left"  id="l-${w.id}-${m.id}"></span>
          <span class="right" id="r-${w.id}-${m.id}"></span>
        </div>
      </div>
      ${winnerMark(w, m)}
    </div>`;
}

function winnerMark(w, m) {
  const win = w.winners?.[m.id];
  if (!win) return "";
  requestAnimationFrame(() => {
    const matchEl = document.querySelector(`.week[data-week="${w.id}"] .match[data-mid="${m.id}"]`);
    if (!matchEl) return;
    matchEl.dataset.winner = win;
    matchEl.querySelectorAll(".team[data-team]").forEach(t => {
      t.querySelector(".team-name")?.classList.toggle("win", t.dataset.team === win);
    });
    matchEl.querySelectorAll(`.vote-btn[data-team="${win}"]`).forEach(b => {
      b.dataset.winner = "true";
    });
  });
  return "";
}

// ── Submit ────────────────────────────────────────────────────────────────
// DEMO: validate the user filled everything in, then fake a "submitted"
// state without touching Firebase. Refreshing the page resets.
async function onSubmitPicks() {
  const w = state.weeks.find(x => x.data.id === state.activeWeekId)?.data;
  if (!w || !state.user) return;
  if (w.lockAt && new Date() >= new Date(w.lockAt)) { alert("Voting is locked for this week."); return; }

  const need = new Set(
    w.matchups
      .filter(m => !(state.user.teamId && (m.home === state.user.teamId || m.away === state.user.teamId)))
      .map(m => m.id)
  );
  const missing = [...need].filter(x => !state.pending.picks[x]);
  if (missing.length)                                          { alert(`Still need to pick ${missing.length} matchup(s).`); return; }
  if (!state.pending.hl.highest || !state.pending.hl.lowest)   { alert("Pick both Highest and Lowest scorer."); return; }

  disableWeekInputs(w.id);
  submitBtn.disabled = true;
  submitHint.textContent = "Picks submitted! (Demo — not saved)";
}

// DEMO: nothing to load — picks aren't persisted in demo mode.
async function loadExistingSubmission(_w) { /* no-op */ }

function disableWeekInputs(weekId) {
  document.querySelectorAll(`.week[data-week="${weekId}"] .vote-btn`).forEach(b => b.disabled = true);
  const hi = byId(`hl-high-${weekId}`); if (hi) hi.disabled = true;
  const lo = byId(`hl-low-${weekId}`);  if (lo) lo.disabled = true;
}

function updateSubmitEnabled() {
  const w = state.weeks.find(x => x.data.id === state.activeWeekId)?.data;
  if (!w || !state.user) {
    submitBtn.disabled = true;
    submitHint.textContent = state.user ? "" : "Login to vote";
    return;
  }
  if (new Date() >= new Date(w.lockAt)) {
    submitBtn.disabled = true; submitHint.textContent = "Locked"; return;
  }
  const need = w.matchups
    .filter(m => !(state.user.teamId && (m.home === state.user.teamId || m.away === state.user.teamId)))
    .map(m => m.id);
  const missing = need.filter(x => !state.pending.picks[x]);
  const hlOK    = !!state.pending.hl.highest && !!state.pending.hl.lowest;

  submitBtn.disabled = missing.length > 0 || !hlOK;
  submitHint.textContent = submitBtn.disabled
    ? `Pick ${missing.length} more matchup(s) + High/Low`
    : "Ready to submit";
}

// ── Live tally ─────────────────────────────────────────────────────────────
// DEMO: computes the vote bars from the same fake submissions seeded in
// initRecords (recordsState.weekVotes). No Firebase listener — these are
// synchronous reads of an in-memory dict.
function liveTally(w, revealAt) {
  const show   = new Date() >= revealAt;
  const counts = {};
  const hl     = { highest: {}, lowest: {} };

  for (const m of w.matchups) counts[m.id] = { [m.home]: 0, [m.away]: 0 };

  for (const d of Object.values(recordsState.weekVotes[w.id] || {})) {
    for (const [mid, tid] of Object.entries(d.picks || {})) {
      if (counts[mid]?.[tid] != null) counts[mid][tid]++;
    }
    for (const k of ["highest", "lowest"]) {
      if (d.hl?.[k]) hl[k][d.hl[k]] = (hl[k][d.hl[k]] || 0) + 1;
    }
  }

  for (const m of w.matchups) {
    const bar  = byId(`bar-${w.id}-${m.id}`);
    const left = byId(`l-${w.id}-${m.id}`);
    const rgt  = byId(`r-${w.id}-${m.id}`);
    const vpA  = byId(`vp-${w.id}-${m.id}-${m.home}`);
    const vpB  = byId(`vp-${w.id}-${m.id}-${m.away}`);
    if (!bar || !left || !rgt) continue;
    const a = counts[m.id][m.home], b = counts[m.id][m.away], tot = a + b;
    const pA = show && tot ? Math.round(a / tot * 100) : 50;
    const pB = 100 - pA;
    left.style.width = pA + "%";
    rgt.style.width  = pB + "%";
    if (vpA) vpA.textContent = show ? pA + "%" : "—";
    if (vpB) vpB.textContent = show ? pB + "%" : "—";
    bar.title = show
      ? `${state.teams[m.home]?.name || m.home} ${pA}% · ${state.teams[m.away]?.name || m.away} ${pB}% · ${tot} votes`
      : "Votes hidden until reveal";
  }

  const hlBox = byId(`hl-reveal-${w.id}`);
  if (hlBox) {
    if (w.hlWinners) {
      const hi = (w.hlWinners.highest || []).map(id => state.teams[id]?.name || id).join(", ") || "TBD";
      const lo = (w.hlWinners.lowest  || []).map(id => state.teams[id]?.name || id).join(", ") || "TBD";
      hlBox.innerHTML = `<span class="badge">Highest: ${hi}</span> <span class="badge">Lowest: ${lo}</span>`;
    } else if (show) {
      const hi = topKeys(hl.highest).map(id => state.teams[id]?.name || id).join(", ") || "TBD";
      const lo = topKeys(hl.lowest ).map(id => state.teams[id]?.name || id).join(", ") || "TBD";
      hlBox.innerHTML = `<span class="badge">Highest leader: ${hi}</span> <span class="badge">Lowest leader: ${lo}</span>`;
    } else {
      hlBox.innerHTML = `<span class="badge" style="color:var(--cream-mute)">Reveals ${dateFmt.format(revealAt)}</span>`;
    }
  }
}

// ── Records ────────────────────────────────────────────────────────────────
// DEMO: seed hardcoded submissions from 5 fake users so the records modal
// looks populated without a live backend. Each user's picks skip their own
// matchup (mirrors the production rule). Wins/losses are auto-calculated
// from week1.winners in renderRecords.
function initRecords() {
  const weeksWithWinners = state.weeks
    .map(w => w.data)
    .filter(w => w.winners && Object.values(w.winners).some(Boolean));

  recordsState.weekVotes["week1"] = {
    "week1_Jordan": { user: "Jordan", teamId: "jordan",
      picks: { m1: "marcus", m3: "brandon", m4: "cole",   m5: "noah",   m6: "owen" } },
    "week1_Devin":  { user: "Devin",  teamId: "devin",
      picks: { m1: "tyler",  m2: "jordan",  m4: "cole",   m5: "adam",   m6: "owen" } },
    "week1_Cole":   { user: "Cole",   teamId: "cole",
      picks: { m1: "marcus", m2: "jordan",  m3: "devin",  m5: "noah",   m6: "owen" } },
    "week1_Noah":   { user: "Noah",   teamId: "noah",
      picks: { m1: "marcus", m2: "ethan",   m3: "devin",  m4: "cole",   m6: "owen" } },
    "week1_Ryan":   { user: "Ryan",   teamId: "ryan",
      picks: { m1: "tyler",  m2: "jordan",  m3: "devin",  m4: "trevor", m5: "noah" } },
  };

  renderRecords(weeksWithWinners);
}

function renderRecords(weeks) {
  const byUser = new Map();
  for (const a of state.accounts) {
    byUser.set(a.name, { right: 0, wrong: 0, teamId: a.teamId });
  }

  for (const w of weeks) {
    const winners = w.winners || {};
    const ownMids = new Map();
    for (const m of w.matchups) {
      for (const side of [m.home, m.away]) {
        if (!ownMids.has(side)) ownMids.set(side, new Set());
        ownMids.get(side).add(m.id);
      }
    }

    for (const data of Object.values(recordsState.weekVotes[w.id] || {})) {
      const person = data.user;
      const tid    = data.teamId;
      const row    = byUser.get(person) || { right: 0, wrong: 0, teamId: tid };
      for (const [mid, pickTid] of Object.entries(data.picks || {})) {
        const winTid = winners[mid]; if (!winTid) continue;
        if ((ownMids.get(tid) || new Set()).has(mid)) continue;
        pickTid === winTid ? row.right++ : row.wrong++;
      }
      byUser.set(person, row);
    }
  }

  const rows = [...byUser.entries()].map(([name, rw]) => ({ name, ...rw }));
  rows.sort((a, b) => b.right - a.right || a.wrong - b.wrong || a.name.localeCompare(b.name));

  const list = byId("recordsList");
  if (!list) return;
  list.innerHTML = rows.map(r =>
    `<li><span class="name">${esc(r.name)}</span><span class="rw">${r.right}-${r.wrong}</span></li>`
  ).join("");
}

// Modal controls
document.addEventListener("click", e => {
  if (e.target.id === "recordsBtn")     { byId("recordsModal").hidden = false; }
  if (e.target.id === "recordsClose" || e.target.dataset.close === "1") {
    byId("recordsModal").hidden = true;
  }
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { const m = byId("recordsModal"); if (m) m.hidden = true; }
});

// ── Auth ───────────────────────────────────────────────────────────────────
function initAuthUI() {
  const saved = localStorage.getItem("pams_user");
  if (saved) { try { const u = JSON.parse(saved); if (u?.name && u?.teamId) state.user = u; } catch {} }
  updateAuthUI();

  loginForm?.addEventListener("submit", async e => {
    e.preventDefault();
    const name = (byId("username")?.value || "").trim();
    const pin  = (byId("password")?.value || "").trim();
    if (!name || !pin) return;
    const acct = state.accounts.find(a => a.name.toLowerCase() === name.toLowerCase() && a.pin === pin);
    if (!acct) { alert("Invalid name or PIN."); return; }
    state.user = { name: acct.name, teamId: acct.teamId };
    localStorage.setItem("pams_user", JSON.stringify(state.user));
    updateAuthUI();
    if (state.activeWeekId) {
      const w = state.weeks.find(x => x.data.id === state.activeWeekId)?.data;
      if (w) await hydrateWeek(w);
    }
  });

  logoutBtn?.addEventListener("click", () => {
    localStorage.removeItem("pams_user");
    state.user = null;
    updateAuthUI();
    document.querySelectorAll(".vote-btn").forEach(b => b.dataset.picked = "");
    state.pending = { picks: {}, hl: {} };
    updateSubmitEnabled();
  });

  submitBtn?.addEventListener("click", onSubmitPicks);
}

function updateAuthUI() {
  const in_ = !!state.user;
  if (loginForm)  loginForm.hidden  = in_;
  if (elWhoami)   { elWhoami.hidden = !in_; elWhoami.textContent = in_ ? `Logged in as ${state.user.name}` : ""; }
  if (logoutBtn)  logoutBtn.hidden  = !in_;
}

// ── Utilities ──────────────────────────────────────────────────────────────
function topKeys(map) {
  let top = 0, out = [];
  for (const [k, v] of Object.entries(map || {})) {
    if (v > top) { top = v; out = [k]; } else if (v === top) out.push(k);
  }
  return out;
}
function indexBy(arr, fn) { const o = {}; for (const x of arr) o[fn(x)] = x; return o; }
function esc(s) { return (s || "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;"); }
