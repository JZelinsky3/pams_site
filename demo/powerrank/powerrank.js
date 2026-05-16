// ── powerrank.js — The Lakeside League Power Rankings ──

const state = {
  weeks:    [],
  activeWk: null,
  view:     "overall",
  data:     null,
};

const genFmt = new Intl.DateTimeFormat("en-US", {
  month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  timeZone: "America/New_York",
});

function byId(id) { return document.getElementById(id); }
function esc(s)   { return (s || "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;"); }

// ── Boot ──────────────────────────────────────────────────────────────────
async function boot() {
  const manifest = await fetch("./manifest.json").then(r => r.json());
  state.weeks = manifest.weeks || [];

  bindFormulaPopup();

  if (!state.weeks.length) {
    byId("preseason").hidden   = false;
    byId("mainContent").hidden = true;
    return;
  }

  byId("preseason").hidden   = true;
  byId("mainContent").hidden = false;

  renderWeekTabs();
  bindViewTabs();

  const latest = state.weeks[state.weeks.length - 1];
  await loadWeek(latest);
}

// ── Formula popup ─────────────────────────────────────────────────────────
function bindFormulaPopup() {
  const popup = byId("formulaPopup");
  if (!popup) return;
  const open     = byId("formulaBtn");
  const close    = byId("formulaClose");
  const backdrop = popup.querySelector(".formula-popup-backdrop");
  if (open)     open.addEventListener("click",    () => { popup.hidden = false; });
  if (close)    close.addEventListener("click",   () => { popup.hidden = true; });
  if (backdrop) backdrop.addEventListener("click", () => { popup.hidden = true; });
  document.addEventListener("keydown", e => { if (e.key === "Escape") popup.hidden = true; });
}

// ── Week tabs ─────────────────────────────────────────────────────────────
function renderWeekTabs() {
  const container = byId("weekTabs");
  container.innerHTML = state.weeks.map(w =>
    `<button class="pr-week-tab" data-id="${w.id}">${w.label}</button>`
  ).join("");
  container.addEventListener("click", async e => {
    const btn = e.target.closest(".pr-week-tab");
    if (!btn) return;
    const wk = state.weeks.find(x => x.id === btn.dataset.id);
    if (wk) await loadWeek(wk);
  });
}

function setActiveWeekTab(id) {
  document.querySelectorAll(".pr-week-tab").forEach(b =>
    b.classList.toggle("active", b.dataset.id === id)
  );
}

// ── View tabs ─────────────────────────────────────────────────────────────
function bindViewTabs() {
  document.querySelectorAll(".pr-view-tab").forEach(btn => {
    btn.addEventListener("click", () => {
      state.view = btn.dataset.view;
      document.querySelectorAll(".pr-view-tab").forEach(b => b.classList.toggle("active", b === btn));
      if (state.data) render(state.data);
    });
  });
}

// ── Load week ──────────────────────────────────────────────────────────────
async function loadWeek(weekMeta) {
  state.activeWk = weekMeta.id;
  setActiveWeekTab(weekMeta.id);
  const data = await fetch("./" + weekMeta.data).then(r => r.json());
  state.data = data;
  render(data);
}

// ── Render ────────────────────────────────────────────────────────────────
function render(data) {
  const teams = data[state.view] || data.overall;

  const genEl = byId("generatedAt");
  if (genEl && data.generated) {
    genEl.textContent = `Updated ${genFmt.format(new Date(data.generated))} ET`;
  }

  const titleEl = byId("rankingsTitle");
  if (titleEl) {
    titleEl.textContent = data.week === 0
      ? "Pre-Season Rankings"
      : `Week ${data.week} Rankings`;
  }

  renderPodium(teams.slice(0, 3));
  renderTable(teams, state.view !== "overall");
  renderProjections(data.overall);
  renderConferenceTables(data.whole, data.skim);
}

// ── Podium ────────────────────────────────────────────────────────────────
function renderPodium(top3) {
  const [first, second, third] = top3;

  const heroCard = t => `
    <div class="podium-hero">
      <div class="podium-hero-left">
        <div class="podium-rank-label">1st Place</div>
        <div class="podium-rank-num">I.</div>
        <div class="podium-hero-name">${esc(t.team_name)}</div>
        <div class="podium-hero-mgr">${esc(t.manager)}</div>
        <div class="podium-hero-rec">${t.wins}–${t.losses}</div>
      </div>
      <div class="podium-hero-right">
        <img class="podium-hero-logo" src="${esc(t.logo)}" alt="${esc(t.team_name)}"
             onerror="this.src='../assets/images/default_team.png'" />
        <div class="podium-hero-score">${t.score.toFixed(1)}</div>
        <div class="podium-hero-delta">${deltaHTML(t.delta)}</div>
      </div>
    </div>`;

  const runnerCard = (t, label, cls) => !t ? "" : `
    <div class="podium-runner ${cls}">
      <div class="podium-runner-top">
        <img class="podium-runner-logo" src="${esc(t.logo)}" alt="${esc(t.team_name)}"
             onerror="this.src='../assets/images/default_team.png'" />
        <div class="podium-runner-info">
          <div class="podium-runner-label">${label}</div>
          <div class="podium-runner-name">${esc(t.team_name)}</div>
          <div class="podium-runner-mgr">${esc(t.manager)}</div>
        </div>
      </div>
      <div class="podium-runner-bottom">
        <span class="podium-runner-rec">${t.wins}–${t.losses}</span>
        <span class="podium-runner-score">${t.score.toFixed(1)}</span>
      </div>
    </div>`;

  byId("podium").innerHTML = `
    ${first ? heroCard(first) : ""}
    <div class="podium-runners">
      ${runnerCard(second, "2nd Place", "p2")}
      ${runnerCard(third,  "3rd Place", "p3")}
    </div>`;
}

// ── Rankings table ────────────────────────────────────────────────────────
function renderTable(teams, confView) {
  const tbody = byId("rankBody");
  tbody.innerHTML = teams.map((t, i) => {
    const rank = confView ? (t.conf_rank ?? i + 1) : t.rank;
    return `
      <tr class="${rank <= 3 ? "top-row" : ""}">
        <td class="col-rank">
          <div class="rank-cell">
            <span class="rank-num">${rank}</span>
            ${deltaHTML(t.delta)}
          </div>
        </td>
        <td class="col-team">
          <div class="team-cell">
            <img class="team-logo" src="${esc(t.logo)}" alt="${esc(t.team_name)}"
                 onerror="this.src='../assets/images/default_team.png'" />
            <div class="team-info">
              <div class="team-name-main">${esc(t.team_name)}</div>
              <div class="team-mgr">${esc(t.manager)}${confBadge(t.division_name)}</div>
            </div>
          </div>
        </td>
        <td class="col-record rec-cell">${t.wins}-${t.losses}</td>
        <td class="col-pf pf-cell">${t.pf.toFixed(1)}</td>
        <td class="col-score score-cell">${t.score.toFixed(1)}</td>
        <td class="col-bars">${buildFactorBars(t.factors)}</td>
      </tr>`;
  }).join("");
}

function confBadge(divName) {
  if (!divName) return "";
  const cls = (divName === "Whole" || divName === "North") ? "conf-badge-whole" : "conf-badge-skim";
  return `<span class="conf-badge ${cls}">${esc(divName)}</span>`;
}

function buildFactorBars(factors) {
  if (!factors) return "";
  const isPreseason = "win_pct" in factors;
  const items = isPreseason
    ? [
        { key: "win_pct",  label: "Win%", max: 20 },
        { key: "pf_avg",   label: "PF",   max: 20 },
        { key: "recent",   label: "Rec3", max: 26 },
        { key: "pedigree", label: "Ped",  max: 34 },
      ]
    : [
        { key: "record", label: "Rec",  max: 35 },
        { key: "pf",     label: "PF",   max: 35 },
        { key: "form",   label: "Frm",  max: 15 },
        { key: "conf",   label: "Conf", max: 15 },
      ];
  return `<div class="factor-bars">${items.map(({ key, label, max }) => {
    const val = factors[key] ?? 0;
    const pct = Math.min(100, (val / max) * 100);
    return `<div class="fbar-row">
      <span class="fbar-label">${label}</span>
      <div class="fbar-track"><div class="fbar-fill" style="width:${pct}%"></div></div>
      <span class="fbar-val">${val.toFixed(1)}</span>
    </div>`;
  }).join("")}</div>`;
}

// ── Projections table ─────────────────────────────────────────────────────
function renderProjections(teams) {
  const el = byId("projBody");
  if (!el || !teams) return;
  el.innerHTML = teams.map(t => {
    const pw = t.proj_wins   !== "-" ? t.proj_wins   : null;
    const pl = t.proj_losses !== "-" ? t.proj_losses : null;
    const pp = t.playoff_pct !== "-" ? t.playoff_pct : null;
    const bp = t.bye_pct     !== "-" ? t.bye_pct     : null;
    const projWL  = pw !== null && pl !== null ? `${pw}–${pl}` : "—";
    const playStr = pp !== null ? pp + "%" : "—";
    const byeStr  = bp !== null ? bp + "%" : "—";
    const barW    = pp !== null ? Math.min(100, pp) : 0;
    const barCls  = pp >= 60 ? "bar-elite" : pp >= 50 ? "bar-good" : pp >= 38 ? "bar-mid" : "bar-low";
    return `
      <tr>
        <td class="col-team">
          <div class="team-cell">
            <img class="team-logo" src="${esc(t.logo)}" alt="${esc(t.team_name)}"
                 onerror="this.src='../assets/images/default_team.png'" />
            <div class="team-info">
              <div class="team-name-main">${esc(t.team_name)}</div>
              <div class="team-mgr">${esc(t.manager)}${confBadge(t.division_name)}</div>
            </div>
          </div>
        </td>
        <td class="proj-wl-cell">${projWL}</td>
        <td class="proj-pct-cell">
          <div class="proj-bar-wrap">
            <div class="proj-bar ${barCls}" style="width:${Math.max(0,barW)}%"></div>
          </div>
          <span class="proj-pct-val">${playStr}</span>
        </td>
        <td class="proj-bye-cell">${byeStr}</td>
      </tr>`;
  }).join("");
}

// ── Conference odds tables ─────────────────────────────────────────────────
function renderConferenceTables(whole, skim) {
  renderConfTable("confBodyWhole", whole);
  renderConfTable("confBodySkim",  skim);
}

function renderConfTable(tbodyId, teams) {
  const el = byId(tbodyId);
  if (!el || !teams) return;
  const sorted = [...teams].sort((a, b) => b.conf_win_pct - a.conf_win_pct);
  el.innerHTML = sorted.map((t, i) => {
    const cp    = t.conf_win_pct;
    const cpStr = cp + "%";
    const barW  = Math.min(100, cp || 0);
    const barCls = cp >= 30 ? "bar-elite" : cp >= 16 ? "bar-good" : "bar-low";
    return `
      <tr>
        <td class="col-rank"><span class="rank-num conf-rank-num">${i + 1}</span></td>
        <td class="col-team">
          <div class="team-cell">
            <img class="team-logo" src="${esc(t.logo)}" alt="${esc(t.team_name)}"
                 onerror="this.src='../assets/images/default_team.png'" />
            <div class="team-info">
              <div class="team-name-main">${esc(t.team_name)}</div>
              <div class="team-mgr">${esc(t.manager)}</div>
            </div>
          </div>
        </td>
        <td class="score-cell">${t.score.toFixed(1)}</td>
        <td class="proj-pct-cell">
          <div class="proj-bar-wrap">
            <div class="proj-bar ${barCls}" style="width:${barW}%"></div>
          </div>
          <span class="proj-pct-val">${cpStr}</span>
        </td>
      </tr>`;
  }).join("");
}

// ── Delta badge ───────────────────────────────────────────────────────────
function deltaHTML(delta) {
  if (!delta || delta === 0) return `<span class="rank-delta delta-same">—</span>`;
  const abs = Math.abs(delta);
  const cls = delta > 0 ? "delta-up" : "delta-down";
  const sym = delta > 0 ? "↑" : "↓";
  return `<span class="rank-delta ${cls}">${sym}${abs}</span>`;
}

boot().catch(console.error);
