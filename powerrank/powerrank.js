// ── powerrank.js — PA Milk Society Power Rankings ──

const state = {
  weeks:    [],
  activeWk: null,
  view:     "overall",   // "overall" | "whole" | "skim"
  data:     null,        // current week's JSON
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

  if (!state.weeks.length) {
    byId("preseason").hidden    = false;
    byId("mainContent").hidden  = true;
    return;
  }

  byId("preseason").hidden   = true;
  byId("mainContent").hidden = false;

  renderWeekTabs();
  bindViewTabs();

  const latest = state.weeks[state.weeks.length - 1];
  await loadWeek(latest);
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
  document.querySelectorAll(".pr-week-tab").forEach(b => {
    b.classList.toggle("active", b.dataset.id === id);
  });
}

// ── View tabs ─────────────────────────────────────────────────────────────
function bindViewTabs() {
  document.querySelectorAll(".pr-view-tab").forEach(btn => {
    btn.addEventListener("click", async () => {
      state.view = btn.dataset.view;
      document.querySelectorAll(".pr-view-tab").forEach(b => b.classList.toggle("active", b === btn));
      if (state.data) render(state.data);
    });
  });
}

// ── Load week data ─────────────────────────────────────────────────────────
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

  // Generated timestamp
  const genEl = byId("generatedAt");
  if (genEl && data.generated) {
    genEl.textContent = `Updated ${genFmt.format(new Date(data.generated))} ET`;
  }

  renderPodium(teams.slice(0, 3));
  renderTable(teams, state.view !== "overall");
}

function renderPodium(top3) {
  const [first, second, third] = top3;
  const slot = (team, cls, label) => {
    if (!team) return "";
    const delta = deltaHTML(team.delta, true);
    return `
      <div class="podium-slot ${cls}">
        <div class="podium-place">${label}</div>
        <img class="podium-logo" src="${esc(team.logo)}" alt="${esc(team.team_name)}"
             onerror="this.src='/assets/images/default_team.png'" />
        <div class="podium-name">${esc(team.team_name)}</div>
        <div class="podium-mgr">${esc(team.manager)}</div>
        <div class="podium-rec">${esc(team.wins)}-${esc(team.losses)}</div>
        <div class="podium-score">${team.score.toFixed(1)} ${delta}</div>
      </div>`;
  };

  byId("podium").innerHTML = `
    ${slot(second, "p2", "2nd")}
    ${slot(first,  "p1", "1st")}
    ${slot(third,  "p3", "3rd")}`;
}

function renderTable(teams, confView) {
  const tbody = byId("rankBody");
  tbody.innerHTML = teams.map((t, i) => {
    const rank  = confView ? (t.conf_rank ?? i + 1) : t.rank;
    const delta = deltaHTML(t.delta);
    const factorBars = buildFactorBars(t.factors);

    return `
      <tr class="${rank <= 3 ? "top-row" : ""}">
        <td class="col-rank">
          <div class="rank-cell">
            <span class="rank-num">${rank}</span>
            ${delta}
          </div>
        </td>
        <td class="col-team">
          <div class="team-cell">
            <img class="team-logo" src="${esc(t.logo)}" alt="${esc(t.team_name)}"
                 onerror="this.src='/assets/images/default_team.png'" />
            <div class="team-info">
              <div class="team-name-main">${esc(t.team_name)}</div>
              <div class="team-mgr">${esc(t.manager)}<span class="conf-badge">${esc(t.division_name)}</span></div>
            </div>
          </div>
        </td>
        <td class="col-record rec-cell">${t.wins}-${t.losses}</td>
        <td class="col-pf pf-cell">${t.pf.toFixed(1)}</td>
        <td class="col-score score-cell">${t.score.toFixed(1)}</td>
        <td class="col-bars">${factorBars}</td>
      </tr>`;
  }).join("");
}

function buildFactorBars(factors) {
  if (!factors) return "";
  const items = [
    { key: "record",     label: "Rec",  max: 40 },
    { key: "pf",         label: "PF",   max: 30 },
    { key: "efficiency", label: "Eff",  max: 20 },
    { key: "form",       label: "Frm",  max: 10 },
  ];
  return `<div class="factor-bars">${items.map(({ key, label, max }) => {
    const val = factors[key] ?? 0;
    const pct = Math.min(100, (val / max) * 100);
    return `
      <div class="fbar-row">
        <span class="fbar-label">${label}</span>
        <div class="fbar-track"><div class="fbar-fill" style="width:${pct}%"></div></div>
        <span class="fbar-val">${val.toFixed(1)}</span>
      </div>`;
  }).join("")}</div>`;
}

function deltaHTML(delta, small = false) {
  if (!delta || delta === 0) return `<span class="rank-delta delta-same">—</span>`;
  const abs = Math.abs(delta);
  const cls = delta > 0 ? "delta-up" : "delta-down";
  const sym = delta > 0 ? "↑" : "↓";
  return `<span class="rank-delta ${cls}">${sym}${abs}</span>`;
}

boot().catch(console.error);
