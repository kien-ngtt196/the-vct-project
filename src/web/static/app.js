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
const archiveCircuit = document.querySelector("#archive-circuit");
const archiveSearch = document.querySelector("#archive-search");
let archivedEvents = [];
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
const methodPaths = {
  trophy: "M8 3h8v5a4 4 0 0 1-8 0zm0 2H4v2a4 4 0 0 0 4 4m8-6h4v2a4 4 0 0 1-4 4m-4 1v6m-4 3h8",
  flag: "M5 21V3m0 2h13l-3 4 3 4H5",
  chart: "M4 4v16h16M8 16v-4m5 4V8m5 8V5",
  trend: "m3 17 6-6 4 3 7-8m-5 0h5v5",
  target: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 6a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  shield: "M12 3 4 6v5c0 5 4 8 8 10 4-2 8-5 8-10V6zm-4 9 3 3 5-6",
};
for (const element of document.querySelectorAll("[data-method-icon]")) {
  element.append(lineGraphic("0 0 24 24", methodPaths[element.dataset.methodIcon]));
}

function lineGraphic(viewBox, pathData) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", viewBox);
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", pathData);
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.7");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  svg.append(path);
  return svg;
}

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

function eventKind(title) {
  if (/^(?:valorant )?champions (?:20|austin)/i.test(title)) return "champions";
  if (/\bmasters\b|lock\W*in/i.test(title)) return "masters";
  return "regional";
}

function eventIcon(event) {
  const kind = event.kind || eventKind(event.title || "");
  if (kind === "champions") return ["/champions-mark.svg", event.logo_url];
  if (kind === "regional") {
    const region = getRegion(event.region) || getRegion(event.title);
    if (region?.key === "emea") return [region.logo, event.logo_url, "/vct-images/vct-mark.png"];
  }
  const fallback = kind === "masters"
    ? "/vct-images/masters-mark.png" : "/vct-images/vct-mark.png";
  return [event.logo_url, fallback];
}

function eventCard(event, detail) {
  const card = document.createElement("article");
  card.className = "event-tile";
  const kind = event.kind || eventKind(event.title);
  card.dataset.kind = kind;
  addImage(card, eventIcon(event), "event-tile-logo", "");
  const info = document.createElement("div");
  const eyebrow = document.createElement("small");
  eyebrow.className = "event-tile-label";
  eyebrow.textContent = [kind === "regional" ? event.region || "Regional" : kind, event.year, event.status]
    .filter(Boolean).join(" · ");
  const url = safeSourceUrl(event.url);
  const title = document.createElement(url ? "a" : "strong");
  if (url) {
    title.href = url;
    title.target = "_blank";
    title.rel = "noopener noreferrer";
  }
  title.className = "event-tile-title";
  title.textContent = event.title;
  const meta = document.createElement("small");
  meta.className = "event-tile-detail";
  meta.textContent = detail;
  info.append(eyebrow, title, meta);
  card.append(info);
  return card;
}

function eventDates(event) {
  const date = (value) => new Intl.DateTimeFormat("en", {
    month: "short", day: "numeric", timeZone: "UTC",
  }).format(new Date(value));
  if (!event.start_date) return "Date to be announced";
  return event.end_date && event.end_date !== event.start_date
    ? `${date(event.start_date)} – ${date(event.end_date)}` : date(event.start_date);
}

function renderArchive() {
  const term = archiveSearch.value.trim().toLowerCase();
  const circuit = archiveCircuit.value;
  const filtered = archivedEvents.filter((event) => {
    const international = eventKind(event.title) !== "regional";
    return (circuit === "all" || international === (circuit === "international"))
      && `${event.title} ${event.region || ""}`.toLowerCase().includes(term);
  });
  const matches = filtered.reduce((sum, event) => sum + event.matches_imported, 0);
  archiveStatus.textContent = `${filtered.length} of ${archivedEvents.length} events · ${matches.toLocaleString()} imported matches`;
  archiveEvents.replaceChildren(...filtered.map((event) =>
    eventCard(event, `${eventDates(event)} · ${event.matches_imported} matches imported`)
  ));
}

async function loadArchive() {
  const year = archiveSeason.value;
  archiveStatus.textContent = "Loading tournaments…";
  archiveEvents.replaceChildren();
  archivedEvents = [];
  try {
    const { events } = await getJson(`/api/events?year=${year}`);
    if (archiveSeason.value !== year) return;
    archivedEvents = events;
    renderArchive();
  } catch (error) {
    if (archiveSeason.value === year) archiveStatus.textContent = error.message;
  }
}

archiveSeason.addEventListener("change", loadArchive);
archiveCircuit.addEventListener("change", renderArchive);
archiveSearch.addEventListener("input", renderArchive);

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
      && (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/vct-images/")
        || ["/favicon.svg", "/champions-mark.svg"].includes(url.pathname))
      && !url.pathname.split("/").includes("..")
    ) return url.href;
    if (url.protocol !== "https:") return null;
    if (!["vlr.gg", "www.vlr.gg", "owcdn.net"].includes(url.hostname)) return null;
    if (/\/(sil|vlr)\.png$/i.test(url.pathname)) return null;
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
  const logo = document.createElement("img");
  logo.src = "/vct-images/vct-mark.png";
  logo.alt = "VCT logo";
  fallback.append(logo);
  return fallback;
}

// Alternate marks from Riot's VCT rankings, keyed by the original VLR logo ID.
const alternateTeamMarks = new Set([
  "5f3ca822464a3", "627403a0d9e48", "629f13085ead6", "62a411783d94d",
  "62c82049253b2", "632be7626d6d9", "632be843b7d51", "632be9976b8fe",
  "63a74624cc76a", "6466d79e1ed40", "657b2f3fcd199", "6670153fa9120",
  "667462f046618", "67d59bfc9eb2a", "6a353ee73ab25",
]);

function addImage(parent, urls, className, alt) {
  const originals = [urls].flat().map(safeImageUrl).filter(Boolean);
  const alternatives = originals.flatMap((url) => {
    const id = /(?:\/|_)([a-f0-9]{13})\.png$/.exec(new URL(url).pathname)?.[1];
    return alternateTeamMarks.has(id) ? [`/vct-images/team-marks/${id}.png`] : [];
  });
  const candidates = [...new Set([...alternatives, ...originals])];
  const safeUrl = candidates.shift();
  if (safeUrl) {
    const image = document.createElement("img");
    image.className = className;
    image.src = safeUrl;
    image.alt = alt;
    image.loading = "lazy";
    image.referrerPolicy = "no-referrer";
    image.onerror = () => {
      const nextUrl = candidates.shift();
      if (nextUrl) image.src = nextUrl;
      else image.replaceWith(createValorantFallback(image.className));
    };
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
    [item.image_local_path, item.image_url],
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
    [item.image_local_path, item.image_url],
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

function profileSection(title, ...children) {
  const section = document.createElement("section");
  section.className = "profile-section";
  const heading = document.createElement("h4");
  heading.className = "subheading";
  heading.textContent = title;
  section.append(heading, ...children);
  return section;
}

function agentStrip(agents, detailed = false) {
  const strip = document.createElement("div");
  strip.className = detailed ? "agent-strip agent-strip-detailed" : "agent-strip";
  for (const agent of agents || []) {
    const item = document.createElement("div");
    item.className = "agent-pick";
    item.title = `${agent.name} · ${agent.maps} maps`;
    addImage(item, agent.image, "agent-portrait", agent.name);
    if (detailed) {
      const label = document.createElement("strong");
      label.textContent = agent.name;
      const details = document.createElement("small");
      details.textContent = [agent.role, `${agent.maps} maps`].filter(Boolean).join(" · ");
      item.append(label, details);
    }
    strip.append(item);
  }
  if (!strip.childElementCount) strip.textContent = "—";
  return strip;
}

function trophyShelf(trophies, player = false) {
  const shelf = document.createElement("div");
  shelf.className = "profile-trophies";
  for (const event of trophies || []) {
    const prize = event.prize && !/^(?:[-–—]+|\$0|0)$/.test(event.prize.trim()) ? event.prize : "";
    const finish = { 1: "Winner", 2: "Runner-up", 3: "Third place" }[event.rank] || "Winner";
    const card = eventCard(event, [
      finish,
      player ? event.team : "",
      prize ? (player ? `Team prize ${prize}` : prize) : "",
    ].filter(Boolean).join(" · "));
    if (player) card.dataset.finish = String(event.rank);
    shelf.append(card);
  }
  if (!shelf.childElementCount) shelf.textContent = player
    ? "No verified Tier 1 podium finishes recorded yet."
    : "No verified tournament wins recorded yet.";
  return profileSection(player ? "Career achievements" : "Tournament wins", shelf);
}

const flagRegions = "ar au bd by be bm bo br bn bg kh ca co cr hr cu cz cl cn dk do eg ee fi fr de gr gt ht hk in id ir ie it jp kz kg la lv lb lt mo mk my mv mx md mn ma np nl nz no pk ps pe pl pt pr ph ro ru sa rs sg kr es lk se ch tw tr th ua gb us uz vn".split(" ");
const regionNames = new Intl.DisplayNames(["en"], { type: "region" });
const countryFlags = new Map(flagRegions.map((code) => [regionNames.of(code.toUpperCase()).toLowerCase(), code]));
for (const [name, code] of Object.entries({
  "bolivia, plurinational state of": "bo", "brunei darussalam": "bn", "czech republic": "cz",
  england: "gb-eng", "hong kong": "hk", "iran, islamic republic of": "ir",
  macao: "mo", macedonia: "mk", "moldova, republic of": "md", palestine: "ps",
  "south korea": "kr", turkey: "tr", türkiye: "tr", wales: "gb-wls",
})) countryFlags.set(name, code);

function countryLabel(nationality) {
  const label = document.createElement("span");
  label.className = "country-label";
  const code = countryFlags.get(nationality.trim().toLowerCase());
  if (code) {
    const flag = document.createElement("img");
    flag.src = `/vct-images/flags/${code}.png`;
    flag.alt = "";
    flag.loading = "lazy";
    flag.onerror = () => flag.remove();
    label.append(flag);
  }
  label.append(nationality);
  return label;
}

const competitiveMaps = new Set("summit corrode abyss sunset lotus pearl fracture breeze icebox ascent split haven bind".split(" "));

function mapTile(rawMap) {
  const name = (rawMap || "Map unavailable").replace(/\s+(?:PICK|DECIDER)\s*$/i, "").trim();
  const tile = document.createElement("span");
  tile.className = "map-tile";
  const slug = name.toLowerCase();
  if (competitiveMaps.has(slug)) {
    const art = document.createElement("img");
    art.src = `/vct-images/maps/${slug}.jpg`;
    art.alt = "";
    art.loading = "lazy";
    art.onerror = () => art.remove();
    tile.append(art);
  }
  const label = document.createElement("strong");
  label.textContent = name;
  tile.append(label);
  return tile;
}

function matchTeam(name, urls) {
  const team = document.createElement("span");
  team.className = "match-team";
  addImage(team, urls, "match-team-logo", "");
  team.append(name || "Team unavailable");
  return team;
}

function matchCard(match, ownTeam, mapResult = false) {
  const link = safeSourceUrl(match.match_url);
  const card = document.createElement(link ? "a" : "article");
  card.className = "profile-match";
  if (link) {
    card.href = link;
    card.target = "_blank";
    card.rel = "noopener noreferrer";
  }
  const event = document.createElement("span");
  event.className = "profile-match-event";
  addImage(event, eventIcon({ title: match.event, logo_url: match.event_logo_url }), "match-team-logo", "");
  event.append(match.event || "Event unavailable");
  const matchup = document.createElement("span");
  matchup.className = "profile-matchup";
  const score = document.createElement("strong");
  score.className = "profile-match-score";
  const { team_score: left, opponent_score: right } = match;
  score.textContent = left == null || right == null ? "—" : `${left} : ${right}`;
  if (left != null && right != null && left !== right) {
    score.dataset.result = left > right ? "win" : "loss";
    score.setAttribute("aria-label", `${left > right ? "Win" : "Loss"}, ${left} to ${right}`);
  }
  matchup.append(ownTeam, score, matchTeam(match.opponent, [match.opponent_logo_local_path, match.opponent_logo_url]));
  const date = document.createElement("span");
  date.className = "profile-match-date";
  if (match.date) date.textContent = new Date(match.date).toLocaleDateString(undefined, {
    month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
  });
  card.append(event, matchup, date);
  const detail = document.createElement("div");
  detail.className = "profile-match-detail";
  if (mapResult) {
    const performance = document.createElement("div");
    performance.className = "match-performance";
    performance.append(makeStat("RATING", metric(match.rating, 2)), makeStat("ACS", metric(match.acs, 0)));
    if (match.agent_portrait?.image) {
      const agent = document.createElement("span");
      agent.title = match.agent_portrait.name;
      addImage(agent, match.agent_portrait.image, "agent-portrait", match.agent_portrait.name);
      detail.append(agent);
    }
    detail.prepend(mapTile(match.map));
    detail.append(performance);
  } else {
    detail.append(...(match.maps || []).map(mapTile));
  }
  if (detail.childElementCount) card.append(detail);
  return card;
}

function renderPlayer(player) {
  const card = document.createElement("article");
  card.className = "player-card formline-player";
  const stats = player.stats || {};
  const header = document.createElement("header");
  header.className = "player-identity";
  addImage(header, [player.image_local_path, player.image_url], "player-identity-photo", `${player.name} portrait`);
  const identity = document.createElement("div");
  const name = document.createElement("h3");
  name.className = "card-name";
  name.textContent = player.name;
  const title = document.createElement("div");
  title.className = "player-identity-title";
  title.append(name);
  const observed = player.recent_maps.find((row) => row.team);
  const useCurrent = player.year === 2026 && player.current_team;
  const teamName = useCurrent ? player.current_team : observed?.team;
  if (teamName) {
    const logos = useCurrent
      ? [player.current_team_logo_local_path, player.current_team_logo_url]
      : [observed.team_logo_local_path, observed.team_logo_url];
    const team = document.createElement("span");
    team.className = "player-identity-team";
    addImage(team, logos, "identity-team-logo", "");
    team.append(teamName);
    title.append(team);
  }
  const badges = document.createElement("div");
  badges.className = "player-identity-badges";
  const role = document.createElement("span");
  role.className = "profile-role";
  role.textContent = player.role || "Role unclassified";
  badges.append(role);
  if (player.nationality) badges.append(countryLabel(player.nationality));
  identity.append(title, badges);
  header.append(identity, makeStat("POWER", metric(player.global_power?.power_score, 1)));
  const overview = document.createElement("div");
  overview.className = "card-stats";
  const kd = stats.deaths ? stats.kills / stats.deaths : null;
  overview.append(
    makeStat("MAPS", String(stats.maps_played ?? 0)),
    makeStat("RATING", metric(stats.rating, 2)),
    makeStat("ACS", metric(stats.acs, 1)),
    makeStat("ADR", metric(stats.adr, 1)),
    makeStat("KAST", metric(stats.kast, 1, "%")),
    makeStat("HS", metric(stats.headshot_percentage, 1, "%")),
    makeStat("K/D", metric(kd, 2)),
  );

  const history = document.createElement("div");
  history.className = "player-history";
  for (const entry of player.observed_team_history) {
    history.append(makeProfileButton(
      entry.team_id, "team", entry.team, [entry.image_local_path, entry.image_url],
      entry.years.join(" · "), "history-team-button", entry.years.at(-1),
    ));
  }
  if (!history.childElementCount) history.textContent = "No dated team appearances recorded.";
  const maps = document.createElement("div");
  maps.className = "profile-match-list";
  for (const row of player.recent_maps.slice(0, 5)) {
    maps.append(matchCard(row, matchTeam(row.team, [row.team_logo_local_path, row.team_logo_url]), true));
  }
  if (!maps.childElementCount) maps.textContent = "No maps imported for this season.";
  card.append(
    header,
    profileSection("Season stats", overview),
    trophyShelf(player.achievements || player.trophies, true),
    profileSection("Most-played agents", agentStrip(player.top_agents, true)),
    profileSection("Team history · recorded appearances", history),
    profileSection("Recent maps", maps),
  );
  profileView.replaceChildren(card);
}

function metric(value, digits, suffix = "") {
  return value == null ? "—" : `${Number(value).toFixed(digits)}${suffix}`;
}

function renderTeam(team) {
  const wrapper = document.createElement("article");
  wrapper.className = "team-profile";
  const header = document.createElement("div");
  header.className = "team-profile-head";
  addImage(
    header,
    [team.image_local_path, team.image_url],
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
        [player.image_local_path, player.image_url],
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
        [player.image_local_path, player.image_url],
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

  wrapper.append(trophyShelf(team.trophies));

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
    const matches = document.createElement("div");
    matches.className = "profile-match-list";
    team.recent_matches.forEach((match) => {
      matches.append(matchCard(match, matchTeam(team.name, [team.image_local_path, team.image_url])));
    });
    wrapper.append(matches);
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

function renderPowerTeam(team, rank, year, internationalSlots) {
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
    [team.image_local_path, team.image_url],
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
  const events = team.achievement_events || [];
  const results = new Map(events.map((event) => [String(event.event_id), event]));
  row.append(position, teamCell, scoreCell, record,
    achievementCell(internationalSlots.map((slot) => {
      const result = results.get(String(slot.id));
      return { ...result, ...slot, absent: !result };
    }), true),
    achievementCell(events.filter((event) => event.kind === "regional" && event.placement
      && !internationalSlots.some((slot) => String(slot.id) === String(event.event_id)))));
  return row;
}

const ordinalRules = new Intl.PluralRules("en", { type: "ordinal" });
const ordinalSuffix = { one: "st", two: "nd", few: "rd", other: "th" };

function achievementCell(events, international = false) {
  const achievements = document.createElement("td");
  const badges = document.createElement("div");
  badges.className = "achievement-badges";
  if (international) badges.classList.add("international-slots");
  for (const event of events) {
    const region = event.kind === "regional" ? getRegion(event.region) || getRegion(event.title) : null;
    const band = event.placement_band?.map((rank) => `${rank}${ordinalSuffix[ordinalRules.select(rank)]}`);
    const placement = event.absent ? "–" : band ? [...new Set(band)].join("–") : event.placement || "Unverified";
    const badge = document.createElement("span");
    badge.className = "achievement-badge";
    const medal = /^(1|2|3)(?:st|nd|rd)?$/.exec(event.placement || "")?.[1];
    if (medal) badge.dataset.medal = medal;
    if (event.absent) badge.dataset.absent = "true";
    const outcome = event.absent ? "No recorded appearance" : `${band ? "Inferred finish range " : ""}${placement}`;
    badge.title = `${event.title} · ${outcome}`;
    const icons = event.kind === "masters" && !/lock\W*in/i.test(event.title) ? ["/vct-images/masters-mark.png", ...eventIcon(event)]
      : region ? [region.logo, ...eventIcon(event)] : eventIcon(event);
    addImage(badge, icons,
      "achievement-icon", region ? `VCT ${region.name}` : event.title);
    badge.append(placement);
    badges.append(badge);
  }
  if (!badges.childElementCount) badges.textContent = "—";
  achievements.append(badges);
  return achievements;
}

function renderPowerPlayer(player, rank, year) {
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
    [player.image_local_path, player.image_url],
    null,
    "rank-player-button",
    year,
  );
  identity.querySelector(".result-avatar")?.classList.replace("result-avatar", "rank-player-image");
  identity.querySelector(".result-name")?.classList.add("power-rank-name");
  if (player.nationality) identity.querySelector(".result-name").append(countryLabel(player.nationality));
  playerCell.append(identity);
  const team = document.createElement("td");
  if (player.team_id && player.team) {
    team.append(makeProfileButton(player.team_id, "team", player.team,
      [player.team_logo_local_path, player.team_logo_url], null, "player-ranking-team", year));
  } else {
    team.textContent = player.team || "Not recorded";
  }
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
  const role = document.createElement("td");
  role.className = "player-role";
  role.textContent = player.role || "—";
  role.title = Object.entries(player.role_maps || {}).map(([name, count]) => `${name}: ${count} maps`).join(" · ");
  const agents = document.createElement("td");
  agents.append(agentStrip(player.top_agents));
  const headshots = document.createElement("td");
  headshots.className = "power-rank-component";
  headshots.textContent = metric(player.headshot_percentage, 1, "%");
  const kd = document.createElement("td");
  kd.className = "power-rank-component";
  kd.textContent = metric(player.kd, 2);
  row.append(position, playerCell, team, role, agents, scoreCell, maps, rating, headshots, kd, acs, kast);
  return row;
}

function renderRegionalStrength(scores, year) {
  const grid = document.querySelector("#region-strength-scores");
  grid.replaceChildren(...regions.map((region) => {
    const row = document.createElement("div");
    row.className = "region-strength-item";
    addImage(row, region.logo, "region-strength-logo", "");
    const label = document.createElement("span");
    label.textContent = region.name;
    const score = scores[region.key];
    const value = document.createElement("strong");
    value.textContent = score ? metric(score.score, 1, " pts") : "—";
    if (score) value.title = `${score.matches} international series · score out of 100`;
    row.append(label, value);
    return row;
  }));
  grid.setAttribute("aria-label", `Regional strength for ${year}`);
}

async function loadPowerRankings() {
  const year = teamRankingSeason.value;
  const strengthGrid = document.querySelector("#region-strength-scores");
  strengthGrid.textContent = "Loading scores…";
  try {
    const payload = await getJson(`/api/power-rankings?year=${year}`);
    if (teamRankingSeason.value !== year) return;
    renderRegionalStrength(payload.regional_strength || {}, year);
    const powerTeams = payload.teams;
    const events = payload.international_events || [];
    const masters = events.filter((event) => eventKind(event.title) === "masters");
    const internationalSlots = [
      { title: "Masters 1", ...masters[0], kind: "masters" },
      { title: "Masters 2", ...masters[1], kind: "masters" },
      { title: "Champions", ...events.find((event) => eventKind(event.title) === "champions"), kind: "champions" },
    ];
    if (year === "2026") {
      renderHomeLeaders(homeTopTeams, powerTeams, "team");
      document.querySelectorAll('[data-count="teams"]').forEach((counter) => {
        counter.textContent = String(powerTeams.length);
      });
    }
    powerRankings.replaceChildren(
      ...powerTeams.map((team, index) => renderPowerTeam(team, index + 1, year, internationalSlots)),
    );
    if (!powerTeams.length) {
      const cell = powerRankings.insertRow().insertCell();
      cell.colSpan = 6;
      cell.className = "table-message";
      cell.textContent = "No eligible team results have been imported for this season.";
    }
  } catch (error) {
    if (teamRankingSeason.value !== year) return;
    strengthGrid.textContent = "Regional scores unavailable.";
    if (year === "2026") renderHomeLeaders(homeTopTeams, [], "team", error.message);
    const row = document.createElement("tr");
    const message = document.createElement("td");
    message.className = "table-message";
    message.colSpan = 6;
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
      ...payload.players.map((player, index) => renderPowerPlayer(player, index + 1, year)),
    );
    if (!payload.players.length) {
      const cell = tableBody.insertRow().insertCell();
      cell.colSpan = 12;
      cell.className = "table-message";
      cell.textContent = "No players meet the five-map minimum for this season yet.";
    }
  } catch (error) {
    if (playerRankingSeason.value !== year) return;
    if (year === "2026") renderHomeLeaders(homeTopPlayers, [], "player", error.message);
    const row = document.createElement("tr");
    const message = document.createElement("td");
    message.className = "table-message";
    message.colSpan = 12;
    message.textContent = error.message;
    row.append(message);
    tableBody.replaceChildren(row);
  }
}

teamRankingSeason.addEventListener("change", loadPowerRankings);
playerRankingSeason.addEventListener("change", loadPlayerRankings);

async function loadRoadmap() {
  try {
    const { events } = await getJson("/api/2027");
    roadmapNote.textContent = "Four regional circuits feed three international stops. Dates reflect imported listings.";
    const lanes = document.createElement("div");
    lanes.className = "circuit-lanes";
    for (const region of regions) {
      const lane = document.createElement("section");
      lane.className = "circuit-lane";
      const label = document.createElement("h3");
      label.textContent = region.name;
      addImage(lane, region.logo, "circuit-logo", "");
      lane.append(label);
      const eventsForRegion = events.filter((event) =>
        eventKind(event.title) === "regional" && getRegion(event.region)?.key === region.key
      );
      const phases = document.createElement("small");
      phases.textContent = "Opens · Kickoff · Cups";
      lane.append(phases);
      if (eventsForRegion.length) {
        const details = document.createElement("details");
        const summary = document.createElement("summary");
        summary.textContent = `${eventsForRegion.length} listed events`;
        details.append(summary, ...eventsForRegion.map((event) => eventCard(event, eventDates(event))));
        lane.append(details);
      }
      lanes.append(lane);
    }
    const junction = lineGraphic("0 0 400 34", "M50 0v11h300V0M150 0v11m100-11v11m-50 0v23");
    junction.setAttribute("preserveAspectRatio", "none");
    junction.classList.add("circuit-junction");
    const finals = document.createElement("section");
    finals.className = "circuit-finals";
    const heading = document.createElement("h3");
    heading.textContent = "International circuit";
    const stages = document.createElement("div");
    stages.className = "circuit-stages";
    for (const [title, matches] of [
      ["Masters Seoul", /masters.*seoul/i],
      ["Masters Valencia", /masters.*valencia/i],
      ["Champions Austin", /^(?:valorant )?champions (?:20|austin)/i],
    ]) {
      const listed = events.find((event) => matches.test(event.title));
      const event = { ...listed, title };
      stages.append(eventCard(event, listed ? eventDates(listed) : "Dates unavailable in archive"));
    }
    finals.append(heading, stages);
    roadmapRegions.replaceChildren(lanes, junction, finals);
  } catch (error) {
    roadmapNote.textContent = `Unable to load 2027 event listings: ${error.message}`;
  }
}

loadPowerRankings();
loadPlayerRankings();
loadRoadmap();
