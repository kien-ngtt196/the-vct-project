const searchInput = document.querySelector("#search-input");
const searchStatus = document.querySelector("#search-status");
const searchResults = document.querySelector("#search-results");
const profileView = document.querySelector("#profile-view");
const powerRankings = document.querySelector("#power-rankings");
const teamRankingSeason = document.querySelector("#team-ranking-season");
const playerRankingSeason = document.querySelector("#player-ranking-season");
const homeTopTeams = document.querySelector("#home-top-teams");
const homeTopPlayers = document.querySelector("#home-top-players");
const roadmapRegions = document.querySelector("#roadmap-regions");
const roadmapNote = document.querySelector("#roadmap-note");
const archiveSeason = document.querySelector("#archive-season");
const archiveStatus = document.querySelector("#archive-status");
const archiveEvents = document.querySelector("#archive-events");
const themeToggle = document.querySelector("#theme-toggle");
const themeToggleLabel = document.querySelector("#theme-toggle-label");
const themeColor = document.querySelector('meta[name="theme-color"]');
const profileDialog = document.querySelector("#profile-dialog");
const profileDialogTitle = document.querySelector("#profile-dialog-title");
const pagePanels = [...document.querySelectorAll("[data-page-panel]")];
const pageLinks = [...document.querySelectorAll("[data-view-target]")];

let searchTimer;
let searchVersion = 0;
const regions = [
  {
    key: "americas",
    name: "Americas",
    logo: "/vct-images/vlr-vct-americas-2027.png",
    source: "https://www.vlr.gg/events/?region=26",
  },
  {
    key: "emea",
    name: "EMEA",
    logo: "/vct-images/vlr-vct-emea-2027.png",
    source: "https://www.vlr.gg/events/?region=27",
  },
  {
    key: "pacific",
    name: "Pacific",
    logo: "/vct-images/vlr-vct-pacific-2027.png",
    source: "https://www.vlr.gg/events/?region=28",
  },
  {
    key: "china",
    name: "China",
    logo: "/vct-images/vlr-vct-china-2027.png",
    source: "https://www.vlr.gg/events/?region=24",
  },
];
const roadmapStages = [
  ["Open Qualifiers", "The open entry point for teams starting their regional run."],
  ["Regional Cups", "Regional events build toward international qualification."],
  ["Masters", "The strongest teams meet on the international stage."],
  ["Champions", "The season culminates in the world championship."],
];

function applyTheme(theme, persist = false) {
  const isDark = theme === "dark";
  document.documentElement.dataset.theme = isDark ? "dark" : "light";
  themeToggle.setAttribute("aria-pressed", String(isDark));
  themeToggle.setAttribute("aria-label", isDark ? "Switch to light mode" : "Switch to dark mode");
  themeToggleLabel.textContent = isDark ? "Light mode" : "Dark mode";
  themeColor.content = isDark ? "#171b1a" : "#f5f5f2";
  if (persist) {
    try {
      localStorage.setItem("vct-scout-theme", isDark ? "dark" : "light");
    } catch (error) {
      console.warn("Could not save the theme preference.", error);
    }
  }
}

applyTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
themeToggle.addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark", true);
});

function viewFromHash() {
  const hash = window.location.hash.slice(1);
  const legacyViews = {
    "power-rankings-section": "teams",
    "player-rankings-section": "players",
    directory: "players",
    "search-section": "players",
    "watchlist-section": "watchlist",
  };
  const view = legacyViews[hash] || hash;
  return pagePanels.some((panel) => panel.dataset.pagePanel === view) ? view : "home";
}

function showPage(view, scroll = true) {
  pagePanels.forEach((panel) => {
    panel.hidden = panel.dataset.pagePanel !== view;
  });
  pageLinks.forEach((link) => {
    if (link.closest(".site-nav")) {
      if (link.dataset.viewTarget === view) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
  });
  if (scroll) window.scrollTo({ top: 0, behavior: "smooth" });
  if (view === "archive") loadArchive();
}

async function loadArchive() {
  const year = archiveSeason.value;
  archiveStatus.textContent = "Loading tournaments…";
  archiveEvents.replaceChildren();
  try {
    const { events } = await getJson(`/api/events?year=${year}`);
    if (archiveSeason.value !== year) return;
    archiveStatus.textContent = `${events.length} Tier 1 events recorded for ${year}.`;
    archiveEvents.replaceChildren(...events.map((event) => {
      const item = document.createElement("li");
      const url = safeSourceUrl(event.url);
      if (url) {
        const source = document.createElement("a");
        source.href = url;
        source.textContent = event.title;
        source.target = "_blank";
        source.rel = "noopener noreferrer";
        item.append(source);
      } else {
        item.textContent = event.title;
      }
      item.append(` · ${event.matches_imported} matches imported`);
      return item;
    }));
  } catch (error) {
    if (archiveSeason.value === year) archiveStatus.textContent = error.message;
  }
}

archiveSeason.addEventListener("change", loadArchive);

pageLinks.forEach((link) => {
  link.addEventListener("click", (event) => {
    const view = link.dataset.viewTarget;
    if (!pagePanels.some((panel) => panel.dataset.pagePanel === view)) return;
    event.preventDefault();
    if (window.location.hash !== `#${view}`) {
      window.history.pushState({ view }, "", `#${view}`);
    }
    showPage(view);
  });
});
window.addEventListener("popstate", () => showPage(viewFromHash()));
const initialView = viewFromHash();
showPage(initialView, false);
if (window.location.hash !== `#${initialView}`) {
  window.history.replaceState({ view: initialView }, "", `#${initialView}`);
}

document.querySelector("#profile-dialog-close").addEventListener("click", () => profileDialog.close());
profileDialog.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.preventDefault();
    profileDialog.close();
  }
});
profileDialog.addEventListener("click", (event) => {
  if (event.target === profileDialog) profileDialog.close();
});

function safeImageUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.origin);
    if (
      url.origin === window.location.origin
      && (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/vct-images/"))
      && !url.pathname.split("/").includes("..")
    ) return url.href;
    if (url.protocol !== "https:") return null;
    if (!["vlr.gg", "www.vlr.gg", "owcdn.net"].includes(url.hostname)) return null;
    if (url.pathname.endsWith("/sil.png")) return null;
    return url.href;
  } catch {
    return null;
  }
}

function safeSourceUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || !["vlr.gg", "www.vlr.gg"].includes(url.hostname)) return null;
    return url.href;
  } catch {
    return null;
  }
}

async function getJson(path) {
  const response = await fetch(path);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status}).`);
  return payload;
}

function createValorantFallback(className) {
  const fallback = document.createElement("span");
  fallback.className = `${className} result-fallback valorant-fallback`;
  fallback.setAttribute("role", "img");
  fallback.setAttribute("aria-label", "VALORANT logo");
  const mark = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  mark.setAttribute("viewBox", "0 0 64 64");
  mark.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M6 9h19l7 19 7-19h19L39 55H25z");
  mark.append(path);
  fallback.append(mark);
  return fallback;
}

function addImage(parent, url, className, alt) {
  const safeUrl = safeImageUrl(url);
  if (safeUrl) {
    const image = document.createElement("img");
    image.className = className;
    image.src = safeUrl;
    image.alt = alt;
    image.loading = "lazy";
    image.referrerPolicy = "no-referrer";
    image.onerror = () => image.replaceWith(createValorantFallback(image.className));
    parent.append(image);
  } else {
    parent.append(createValorantFallback(className));
  }
}

function renderSearchResult(item) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "result-button";
  button.addEventListener("click", () => loadProfile(item));
  addImage(
    button,
    item.image_local_path || item.image_url,
    "result-avatar",
    `${item.name} ${item.type} image`,
  );
  const name = document.createElement("span");
  name.className = "result-name";
  name.textContent = item.name;
  const meta = document.createElement("small");
  if (item.type === "player") {
    meta.className = "result-meta";
    meta.textContent = [item.team, item.nationality].filter(Boolean).join(" · ") || "Player";
    name.append(meta);
  }
  button.append(name);
  const type = document.createElement("span");
  type.className = "result-type";
  type.textContent = item.type.toUpperCase();
  button.append(type);
  return button;
}

function makeProfileButton(id, type, name, imageUrl, meta, className, year) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.addEventListener("click", () => loadProfile({ type, id, year }));
  addImage(
    button,
    imageUrl,
    "result-avatar",
    `${name} ${type} image`,
  );
  const title = document.createElement("span");
  title.className = "result-name";
  title.textContent = name;
  if (meta) {
    const detail = document.createElement("small");
    detail.className = "result-meta";
    detail.textContent = meta;
    title.append(detail);
  }
  button.append(title);
  return button;
}

function getRegion(regionName) {
  const value = String(regionName || "").trim().toLowerCase();
  if (!value) return null;
  if (value.includes("china")) return regions[3];
  if (
    value.includes("emea")
    || value.includes("europe")
    || value.includes("africa")
    || value.includes("middle east")
    || value.includes("turkey")
    || value.includes("türkiye")
  ) return regions[1];
  if (
    value.includes("america")
    || value.includes("brazil")
    || value.includes("latam")
    || value.includes("mexico")
  ) return regions[0];
  if (
    value.includes("pacific")
    || value.includes("asia")
    || value.includes("korea")
    || value.includes("japan")
    || value.includes("oceania")
    || value.includes("vietnam")
    || value.includes("thailand")
    || value.includes("singapore")
    || value.includes("malaysia")
    || value.includes("indonesia")
    || value.includes("philippines")
  ) return regions[2];
  return null;
}

function renderHomeLeader(item, type, rank) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "home-leader-button";
  button.setAttribute("aria-label", `Open ${type} profile: ${item.name}`);
  button.addEventListener("click", () => loadProfile({ type, id: item.id, region: item.region }));

  const position = document.createElement("span");
  position.className = "home-leader-position";
  position.textContent = String(rank).padStart(2, "0");
  const image = document.createElement("span");
  image.className = "home-leader-image";
  addImage(
    image,
    item.image_local_path || item.image_url,
    "home-leader-avatar",
    `${item.name} ${type} image`,
  );
  const identity = document.createElement("span");
  identity.className = "home-leader-identity";
  const name = document.createElement("strong");
  name.textContent = item.name;
  const meta = document.createElement("small");
  if (type === "player") {
    meta.textContent = item.team || "TEAM NOT RECORDED · 2026";
    identity.append(name, meta);
  } else {
    identity.append(name);
  }

  const score = document.createElement("span");
  score.className = "home-leader-score";
  const value = document.createElement("strong");
  value.textContent = Number(item.power_score).toFixed(1);
  const label = document.createElement("small");
  label.textContent = "POWER";
  score.append(value, label);
  button.append(position, image, identity, score);
  return button;
}

function renderHomeLeaders(container, items, type, errorMessage) {
  if (!items.length) {
    const message = document.createElement("p");
    message.className = "home-leader-message";
    message.textContent = errorMessage || "No ranked entries are available.";
    container.replaceChildren(message);
    return;
  }
  container.replaceChildren(
    ...items.slice(0, 3).map((item, index) => renderHomeLeader(item, type, index + 1)),
  );
}

async function search() {
  const query = searchInput.value.trim();
  const requestVersion = ++searchVersion;
  searchResults.replaceChildren();
  if (!query) {
    searchResults.hidden = true;
    searchStatus.textContent = "Search players or teams";
    return;
  }
  searchResults.hidden = false;
  searchStatus.textContent = "Searching indexed VLR results…";
  try {
    const payload = await getJson(`/api/search?q=${encodeURIComponent(query)}&limit=20`);
    if (requestVersion !== searchVersion || query !== searchInput.value.trim()) return;
    if (!payload.results.length) {
      searchStatus.textContent = "No matching player or team in the imported data.";
      return;
    }
    searchStatus.textContent = `${payload.results.length} matching result${payload.results.length === 1 ? "" : "s"}.`;
    searchResults.replaceChildren(...payload.results.map(renderSearchResult));
  } catch (error) {
    if (requestVersion !== searchVersion || query !== searchInput.value.trim()) return;
    searchStatus.textContent = error.message;
  }
}

searchInput.addEventListener("input", () => {
  searchVersion += 1;
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(search, 250);
});
searchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    window.clearTimeout(searchTimer);
    search();
  }
});

function makeStat(label, value) {
  const wrapper = document.createElement("div");
  wrapper.className = "stat-cell";
  const number = document.createElement("strong");
  number.className = "stat-value";
  number.textContent = value;
  const title = document.createElement("span");
  title.className = "stat-label";
  title.textContent = label;
  wrapper.append(number, title);
  return wrapper;
}

function renderPlayer(player) {
  const card = document.createElement("article");
  card.className = "player-card";
  const recent = player.recent_maps || [];
  const stats = player.stats || {};
  const top = document.createElement("div");
  top.className = "card-top";
  const photo = document.createElement("div");
  photo.className = "card-photo-wrap";
  addImage(
    photo,
    player.image_local_path || player.image_url,
    "card-photo",
    `${player.name} portrait`,
  );
  const info = document.createElement("div");
  info.className = "card-top-info";
  const kicker = document.createElement("span");
  kicker.className = "card-kicker";
  kicker.textContent = player.nationality || "TIER ONE PLAYER";
  const name = document.createElement("h3");
  name.className = "card-name";
  name.textContent = player.name;
  const observedTeam = recent.find((map) => map.team)?.team;
  const team = document.createElement("span");
  team.className = "card-team";
  team.textContent = player.current_team
    ? `${player.current_team} · ${player.current_status}`
    : `${observedTeam || "Team not recorded"} · ${player.current_status}`;
  const rating = document.createElement("div");
  rating.className = "card-rating";
  rating.textContent = player.global_power
    ? `${Number(player.global_power.power_score).toFixed(1)} `
    : "— ";
  const ratingLabel = document.createElement("span");
  ratingLabel.textContent = "GLOBAL PLAYER POWER · OUT OF 100";
  rating.append(ratingLabel);
  info.append(kicker, name, team, rating);
  top.append(photo, info);

  const statsPanel = document.createElement("div");
  statsPanel.className = "card-stats";
  const kills = Number(stats.kills) || 0;
  const deaths = Number(stats.deaths) || 0;
  statsPanel.append(
    makeStat("2026 MAPS", String(stats.maps_played ?? 0)),
    makeStat("AVG ACS", stats.acs == null ? "—" : Number(stats.acs).toFixed(1)),
    makeStat("AVG RATING", stats.rating == null ? "—" : Number(stats.rating).toFixed(2)),
    makeStat("KAST %", stats.kast == null ? "—" : Number(stats.kast).toFixed(1)),
    makeStat("ADR", stats.adr == null ? "—" : Number(stats.adr).toFixed(1)),
    makeStat("K/D", deaths ? (kills / deaths).toFixed(2) : "—"),
    makeStat("KILLS", String(stats.kills ?? 0)),
    makeStat("ASSISTS", String(stats.assists ?? 0)),
    makeStat(
      "HEADSHOT %",
      stats.headshot_percentage == null
        ? "—"
        : Number(stats.headshot_percentage).toFixed(1),
    ),
    makeStat("FIRST KILLS", String(stats.first_kills ?? 0)),
  );

  const foot = document.createElement("div");
  foot.className = "card-foot";
  const sample = document.createElement("span");
  sample.textContent = `${stats.maps_played || 0} imported tier-one maps in 2026`;
  const sourceUrl = safeSourceUrl(player.source_url);
  if (sourceUrl) {
    const source = document.createElement("a");
    source.className = "source-link";
    source.href = sourceUrl;
    source.target = "_blank";
    source.rel = "noopener noreferrer";
    source.textContent = "VLR profile ↗";
    foot.append(sample, source);
  } else {
    foot.append(sample);
  }

  const disclaimer = document.createElement("p");
  disclaimer.className = "data-disclaimer";
  disclaimer.textContent = player.roster_history.length
    ? "Current status is based on the latest VLR team-profile listing. Event entries and match appearances are historical evidence, not contract records."
    : "No current VLR roster listing is available. The latest match appearance is not a confirmed current team.";

  card.append(top, statsPanel, foot, disclaimer);
  const recentTitle = document.createElement("h4");
  recentTitle.className = "subheading";
  recentTitle.textContent = "Recent map rows";
  const mapRows = document.createElement("div");
  if (recent.length) {
    recent.slice(0, 5).forEach((row) => {
      const line = document.createElement("div");
      line.className = "match-row";
      const left = document.createElement("span");
      left.textContent = `${row.map || "Map"} · ${row.team || "Team"}`;
      const right = document.createElement("small");
      right.textContent = [row.date ? new Date(row.date).toLocaleDateString() : "", row.acs ? `ACS ${row.acs}` : ""].filter(Boolean).join(" · ");
      line.append(left, right);
      mapRows.append(line);
    });
  } else {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent = "No player-stat rows have been imported for this profile yet.";
    mapRows.append(note);
  }
  card.append(recentTitle, mapRows);
  const observedHeading = document.createElement("h4");
  observedHeading.className = "subheading";
  observedHeading.textContent = "Teams seen in matches";
  card.append(observedHeading);
  if (player.observed_team_history.length) {
    player.observed_team_history.forEach((entry) => {
      const line = document.createElement("div");
      line.className = "match-row";
      const dates = document.createElement("small");
      dates.textContent = `${entry.matches} matches · ${entry.first_match ? new Date(entry.first_match).toLocaleDateString() : "date n/a"} – ${entry.last_match ? new Date(entry.last_match).toLocaleDateString() : "date n/a"}`;
      const teamButton = makeProfileButton(
        entry.team_id,
        "team",
        entry.team,
        null,
        `${entry.matches} matches`,
        "history-team-button",
      );
      line.append(teamButton, dates);
      card.append(line);
    });
  } else {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent = "No dated match appearances are recorded yet.";
    card.append(note);
  }
  if (player.roster_history.length) {
    const rosterHeading = document.createElement("h4");
    rosterHeading.className = "subheading";
    rosterHeading.textContent = "Sourced roster records";
    card.append(rosterHeading);
    player.roster_history.forEach((entry) => {
      const line = document.createElement("div");
      line.className = "match-row";
      const teamName = document.createElement("span");
      teamName.textContent = entry.team;
      const dateRange = document.createElement("small");
      dateRange.textContent = `${entry.start_date || "start unknown"} – ${entry.end_date || "end unknown"} · ${entry.status}${entry.notes ? ` · ${entry.notes}` : ""}`;
      line.append(teamName, dateRange);
      card.append(line);
    });
  }
  profileView.replaceChildren(card);
}

function renderTeam(team) {
  const wrapper = document.createElement("article");
  wrapper.className = "team-profile";
  const header = document.createElement("div");
  header.className = "team-profile-head";
  addImage(
    header,
    team.image_local_path || team.image_url,
    "team-avatar",
    `${team.name} logo`,
  );
  const heading = document.createElement("div");
  heading.className = "team-profile-heading";
  const title = document.createElement("h3");
  title.textContent = team.name;
  heading.append(title);
  header.append(heading);
  const sourceUrl = safeSourceUrl(team.source_url);
  if (sourceUrl) {
    const source = document.createElement("a");
    source.className = "source-link";
    source.href = sourceUrl;
    source.target = "_blank";
    source.rel = "noopener noreferrer";
    source.textContent = "VLR team page ↗";
    header.append(source);
  }
  wrapper.append(header);

  const seasonLabel = document.createElement("label");
  seasonLabel.textContent = "Team history season ";
  const seasonPicker = document.createElement("select");
  for (let year = 2026; year >= 2022; year -= 1) {
    seasonPicker.add(new Option(String(year), String(year)));
  }
  seasonPicker.value = String(team.year);
  seasonPicker.addEventListener("change", () => {
    loadProfile({ id: team.id, type: "team", year: seasonPicker.value });
  });
  seasonLabel.append(seasonPicker);
  wrapper.append(seasonLabel);

  if (team.stats) {
    const teamStats = document.createElement("div");
    teamStats.className = "card-stats team-stats";
    const losses = team.stats.matches_played
      - team.stats.matches_won
      - team.stats.matches_drawn;
    const mapLosses = team.stats.maps_played
      - team.stats.maps_won
      - team.stats.maps_drawn;
    teamStats.append(
      makeStat("POWER POINTS · OUT OF 100", Number(team.stats.power_score).toFixed(1)),
      makeStat("MATCH RECORD", `${team.stats.matches_won}–${losses}–${team.stats.matches_drawn}`),
      makeStat("MAP RECORD", `${team.stats.maps_won}–${mapLosses}–${team.stats.maps_drawn}`),
      makeStat("ROUND DIFF", `${team.stats.round_differential > 0 ? "+" : ""}${team.stats.round_differential}`),
      makeStat("KILLS", String(team.stats.kills)),
      makeStat("DEATHS", String(team.stats.deaths)),
      makeStat("AVG K/D", team.stats.deaths
        ? (Number(team.stats.kills) / Number(team.stats.deaths)).toFixed(2)
        : "—"),
      makeStat("EXECUTION", `${(Number(team.stats.execution_score) * 100).toFixed(1)}%`),
    );
    wrapper.append(teamStats);
  }

  const warning = document.createElement("p");
  warning.className = "team-warning";
  warning.textContent = team.current_roster.length
    ? "Current roster is sourced from the latest VLR team profile. Match appearances are shown separately."
    : "No current VLR roster listing is available. Match appearances below do not confirm a current roster.";
  wrapper.append(warning);

  const rosterHeading = document.createElement("h4");
  rosterHeading.className = "subheading";
  rosterHeading.textContent = "Current VLR roster";
  wrapper.append(rosterHeading);
  if (team.current_roster.length) {
    team.current_roster.forEach((player) => {
      const line = document.createElement("div");
      line.className = "observed-player roster-player";
      const profile = makeProfileButton(
        player.id,
        "player",
        player.name,
        player.image_local_path || player.image_url,
        player.role || "Player",
        "roster-profile-button",
      );
      line.append(profile);
      wrapper.append(line);
    });
  } else {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent = "No roster members are currently confirmed by a VLR profile.";
    wrapper.append(note);
  }

  const playerHeading = document.createElement("h4");
  playerHeading.className = "subheading";
  playerHeading.textContent = `Players observed in ${team.year} matches`;
  wrapper.append(playerHeading);
  if (team.observed_players.length) {
    team.observed_players.forEach((player) => {
      const line = document.createElement("div");
      line.className = "observed-player";
      const link = makeProfileButton(
        player.id,
        "player",
        player.name,
        player.image_local_path || player.image_url,
        null,
        "roster-profile-button",
      );
      const date = document.createElement("small");
      date.textContent = player.last_seen ? `Seen ${new Date(player.last_seen).toLocaleDateString()}` : "Date unavailable";
      line.append(link, date);
      wrapper.append(line);
    });
  } else {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent = "No match-participation records for this team yet.";
    wrapper.append(note);
  }

  const tournamentHeading = document.createElement("h4");
  tournamentHeading.className = "subheading";
  tournamentHeading.textContent = `${team.year} tournament results & prizes`;
  wrapper.append(tournamentHeading);
  if (team.tournaments.length) {
    team.tournaments.forEach((event) => {
      const item = document.createElement("div");
      item.className = "team-event-row";
      const titleLine = document.createElement("div");
      titleLine.className = "team-event-title";
      const eventUrl = safeSourceUrl(event.url);
      if (eventUrl) {
        const link = document.createElement("a");
        link.href = eventUrl;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = event.title;
        titleLine.append(link);
      } else {
        titleLine.textContent = event.title;
      }
      item.append(titleLine);
      const result = document.createElement("small");
      const losses = event.matches_played - event.matches_won - event.matches_drawn;
      result.textContent = [
        event.placement || "Placement not listed by VLR",
        `${event.matches_won}W–${losses}L–${event.matches_drawn}D`,
        event.prize_pool ? `Event pool ${event.prize_pool}` : "",
        event.prize ? `Team prize ${event.prize}` : "Team payout not listed by VLR",
      ].filter(Boolean).join(" · ");
      item.append(result);
      wrapper.append(item);
    });
  } else {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent = `No tier-one event participation is recorded for ${team.year}.`;
    wrapper.append(note);
  }

  const matchHeading = document.createElement("h4");
  matchHeading.className = "subheading";
  matchHeading.textContent = "Recent matches";
  wrapper.append(matchHeading);
  if (team.recent_matches.length) {
    team.recent_matches.forEach((match) => {
      const row = document.createElement("div");
      row.className = "match-row";
      const opponent = document.createElement("span");
      opponent.textContent = match.opponent || "Opponent unknown";
      const score = document.createElement("small");
      const date = match.date ? new Date(match.date).toLocaleDateString() : "";
      score.textContent = match.team1_score === null
        ? [match.status || "Scheduled", date, match.event].filter(Boolean).join(" · ")
        : `${match.team1_score} – ${match.team2_score}${match.won === null ? "" : match.won ? " · W" : " · L"} · ${date}${match.event ? ` · ${match.event}` : ""}`;
      row.append(opponent, score);
      wrapper.append(row);
    });
  } else {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent = "No imported results yet.";
    wrapper.append(note);
  }
  profileView.replaceChildren(wrapper);
}

async function loadProfile(item) {
  profileDialogTitle.textContent = item.type === "player" ? "Player profile" : "Team profile";
  if (!profileDialog.open) profileDialog.showModal();
  profileView.replaceChildren();
  const loading = document.createElement("p");
  loading.className = "muted";
  loading.textContent = "Loading profile…";
  profileView.append(loading);
  try {
    const kind = item.type === "player" ? "players" : "teams";
    const season = item.year ? `?year=${encodeURIComponent(item.year)}` : "";
    const details = await getJson(`/api/${kind}/${encodeURIComponent(item.id)}${season}`);
    if (item.type === "player") renderPlayer(details);
    else renderTeam(details);
  } catch (error) {
    const message = document.createElement("p");
    message.className = "team-warning";
    message.textContent = error.message;
    profileView.replaceChildren(message);
  }
}

function formatRate(rate) {
  return `${(Number(rate) * 100).toFixed(1)}%`;
}

function renderScoreMeter(container, score) {
  const value = Number(score);
  const readout = document.createElement("div");
  readout.className = "score-readout";
  const number = document.createElement("strong");
  number.textContent = value.toFixed(1);
  const unit = document.createElement("small");
  unit.textContent = "pts";
  readout.append(number, unit);

  const track = document.createElement("span");
  track.className = "score-track";
  track.setAttribute("aria-hidden", "true");
  const fill = document.createElement("span");
  fill.style.width = `${Math.max(0, Math.min(100, value))}%`;
  track.append(fill);
  container.append(readout, track);
}

function renderPowerTeam(team, rank, year) {
  const row = document.createElement("tr");
  row.className = "power-rank-row";
  const position = document.createElement("td");
  position.className = "power-rank-position";
  position.textContent = String(rank);
  const teamCell = document.createElement("td");
  const identity = makeProfileButton(
    team.id,
    "team",
    team.name,
    team.image_local_path || team.image_url,
    null,
    "rank-team-button",
    year,
  );
  identity.querySelector(".result-avatar")?.classList.replace("result-avatar", "rank-team-logo");
  identity.querySelector(".result-name")?.classList.add("power-rank-name");
  teamCell.append(identity);
  const scoreCell = document.createElement("td");
  scoreCell.className = "power-rank-score";
  renderScoreMeter(scoreCell, team.power_score);
  const achievement = team.score_breakdown;
  if (achievement) {
    scoreCell.title = `Achievement points: ${achievement.international_achievement}/40 international, ${achievement.regional_achievement}/15 regional`;
  }
  const record = document.createElement("td");
  record.className = "power-rank-record";
  const matchLosses = team.matches_played - team.matches_won - team.matches_drawn;
  record.textContent = `${team.matches_won}–${matchLosses}–${team.matches_drawn}`;
  const recent = document.createElement("td");
  recent.className = "power-rank-component";
  recent.textContent = formatRate(team.recent_performance_rate);
  const execution = document.createElement("td");
  execution.className = "power-rank-component";
  execution.textContent = formatRate(team.execution_score);
  const opponents = document.createElement("td");
  opponents.className = "power-rank-component";
  opponents.textContent = formatRate(team.opponent_strength_rate);
  row.append(position, teamCell, scoreCell, record, recent, execution, opponents);
  return row;
}

function renderPowerPlayer(player, rank) {
  const row = document.createElement("tr");
  row.className = "power-rank-row";
  const position = document.createElement("td");
  position.className = "power-rank-position";
  position.textContent = String(rank);
  const playerCell = document.createElement("td");
  const identity = makeProfileButton(
    player.id,
    "player",
    player.name,
    player.image_local_path || player.image_url,
    player.nationality,
    "rank-player-button",
  );
  identity.querySelector(".result-avatar")?.classList.replace("result-avatar", "rank-player-image");
  identity.querySelector(".result-name")?.classList.add("power-rank-name");
  playerCell.append(identity);
  const team = document.createElement("td");
  team.className = "power-rank-record";
  team.textContent = player.team || "Not recorded";
  const scoreCell = document.createElement("td");
  scoreCell.className = "power-rank-score";
  renderScoreMeter(scoreCell, player.power_score);
  const maps = document.createElement("td");
  maps.className = "power-rank-component";
  maps.textContent = String(player.maps_played);
  const rating = document.createElement("td");
  rating.className = "power-rank-component";
  rating.textContent = player.rating == null ? "—" : Number(player.rating).toFixed(2);
  const acs = document.createElement("td");
  acs.className = "power-rank-component";
  acs.textContent = player.acs == null ? "—" : Number(player.acs).toFixed(1);
  const kast = document.createElement("td");
  kast.className = "power-rank-component";
  kast.textContent = player.kast == null ? "—" : `${Number(player.kast).toFixed(1)}%`;
  const internationalMaps = document.createElement("td");
  internationalMaps.className = "power-rank-component";
  internationalMaps.textContent = String(player.international_maps);
  const internationalRating = document.createElement("td");
  internationalRating.className = "power-rank-component";
  internationalRating.textContent = player.international_rating == null
    ? "—" : Number(player.international_rating).toFixed(2);
  row.append(position, playerCell, team, scoreCell, maps, rating, internationalMaps, internationalRating, acs, kast);
  return row;
}

async function loadPowerRankings() {
  const year = teamRankingSeason.value;
  try {
    const payload = await getJson(`/api/power-rankings?year=${year}`);
    if (teamRankingSeason.value !== year) return;
    const powerTeams = payload.teams;
    if (year === "2026") {
      renderHomeLeaders(homeTopTeams, powerTeams, "team");
      document.querySelectorAll('[data-count="teams"]').forEach((counter) => {
        counter.textContent = String(powerTeams.length);
      });
    }
    powerRankings.replaceChildren(
      ...powerTeams.map((team, index) => renderPowerTeam(team, index + 1, year)),
    );
    if (!powerTeams.length) {
      const cell = powerRankings.insertRow().insertCell();
      cell.colSpan = 7;
      cell.className = "table-message";
      cell.textContent = "No eligible team results have been imported for this season.";
    }
  } catch (error) {
    if (teamRankingSeason.value !== year) return;
    if (year === "2026") renderHomeLeaders(homeTopTeams, [], "team", error.message);
    const row = document.createElement("tr");
    const message = document.createElement("td");
    message.className = "table-message";
    message.colSpan = 7;
    message.textContent = error.message;
    row.append(message);
    powerRankings.replaceChildren(row);
  }
}

async function loadPlayerRankings() {
  const year = playerRankingSeason.value;
  const tableBody = document.querySelector("#player-rankings");
  try {
    const payload = await getJson(`/api/player-power-rankings?year=${year}`);
    if (playerRankingSeason.value !== year) return;
    if (year === "2026") {
      document.querySelectorAll('[data-count="players"]').forEach((counter) => {
        counter.textContent = String(payload.players.length);
      });
      renderHomeLeaders(homeTopPlayers, payload.players, "player");
    }
    tableBody.replaceChildren(
      ...payload.players.map((player, index) => renderPowerPlayer(player, index + 1)),
    );
    if (!payload.players.length) {
      const cell = tableBody.insertRow().insertCell();
      cell.colSpan = 10;
      cell.className = "table-message";
      cell.textContent = "No players meet the five-map minimum for this season yet.";
    }
  } catch (error) {
    if (playerRankingSeason.value !== year) return;
    if (year === "2026") renderHomeLeaders(homeTopPlayers, [], "player", error.message);
    const row = document.createElement("tr");
    const message = document.createElement("td");
    message.className = "table-message";
    message.colSpan = 10;
    message.textContent = error.message;
    row.append(message);
    tableBody.replaceChildren(row);
  }
}

teamRankingSeason.addEventListener("change", loadPowerRankings);
playerRankingSeason.addEventListener("change", loadPlayerRankings);

async function loadRoadmap() {
  try {
    const data = await getJson("/api/2027");
    const events = data.events || [];
    roadmapNote.textContent = events.length
      ? `${events.length} 2027 event listing${events.length === 1 ? "" : "s"} found on VLR. Stages without a confirmed listing remain marked as unannounced.`
      : "Riot’s 2027 format preview introduces Open Qualifiers, Cups, Masters, and Champions. Exact dates and regional brackets remain subject to official listings.";
    roadmapRegions.replaceChildren(...regions.map((region) => {
      const regionCard = document.createElement("article");
      regionCard.className = "roadmap-region";
      const regionHeading = document.createElement("header");
      regionHeading.className = "roadmap-region-heading";
      addImage(regionHeading, region.logo, "roadmap-region-icon", `${region.name} VCT event logo`);
      const title = document.createElement("h3");
      title.textContent = region.name;
      const source = document.createElement("a");
      source.href = region.source;
      source.target = "_blank";
      source.rel = "noopener noreferrer";
      source.className = "roadmap-region-source";
      source.textContent = "VLR ↗";
      regionHeading.append(title, source);
      regionCard.append(regionHeading);

      const regionalEvents = events.filter((item) => getRegion(item.region)?.key === region.key);
      const qualifierEvents = regionalEvents.filter((item) => /qualif|open/i.test(item.title || ""));
      const cupEvents = regionalEvents.filter((item) =>
        !/qualif|open|masters|champions/i.test(item.title || ""));
      const globalEvents = [
        events.filter((item) => /masters/i.test(item.title || "")),
        events.filter((item) => /champions/i.test(item.title || "")),
      ];
      const stageEvents = [qualifierEvents, cupEvents, ...globalEvents];

      roadmapStages.forEach(([stageName, description], index) => {
        const stage = document.createElement("section");
        stage.className = "roadmap-stage";
        const stageHeading = document.createElement("div");
        stageHeading.className = "roadmap-stage-heading";
        const stageTitle = document.createElement("h4");
        stageTitle.textContent = stageName;
        const stageDescription = document.createElement("p");
        stageDescription.textContent = description;
        stageHeading.append(stageTitle, stageDescription);
        stage.append(stageHeading);
        const stageItems = stageEvents[index];
        if (stageItems.length) {
          stageItems.forEach((item) => {
            const event = document.createElement("article");
            event.className = "roadmap-event";
            const eventTitle = document.createElement("strong");
            const eventUrl = safeSourceUrl(item.url);
            if (eventUrl) {
              const link = document.createElement("a");
              link.href = eventUrl;
              link.target = "_blank";
              link.rel = "noopener noreferrer";
              link.textContent = item.title;
              eventTitle.append(link);
            } else {
              eventTitle.textContent = item.title;
            }
            const eventDetails = document.createElement("small");
            const dateRange = item.start_date && item.end_date
              ? `${item.start_date} – ${item.end_date}`
              : item.start_date || "";
            eventDetails.textContent = [item.status, dateRange].filter(Boolean).join(" · ")
              || "Date to be announced";
            event.append(eventTitle, eventDetails);
            stage.append(event);
          });
        } else {
          const pending = document.createElement("p");
          pending.className = "roadmap-pending";
          pending.textContent = "Awaiting a confirmed listing";
          stage.append(pending);
        }
        regionCard.append(stage);
      });
      return regionCard;
    }));
  } catch (error) {
    roadmapNote.textContent = `Unable to load 2027 event listings: ${error.message}`;
  }
}

loadPowerRankings();
loadPlayerRankings();
loadRoadmap();
