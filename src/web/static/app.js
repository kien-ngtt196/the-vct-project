const searchInput = document.querySelector("#search-input");
const searchStatus = document.querySelector("#search-status");
const searchResults = document.querySelector("#search-results");
const profileView = document.querySelector("#profile-view");
const powerForm = document.querySelector("#power-form");
const powerResult = document.querySelector("#power-result");
const powerRankings = document.querySelector("#power-rankings");
const futureMessage = document.querySelector("#future-message");
const futureEvents = document.querySelector("#future-events");
const heroImage = document.querySelector("#hero-scout-image");
const heroImagePlaceholder = document.querySelector("#hero-image-placeholder");
const heroScoutName = document.querySelector("#hero-scout-name");
const heroScoutTeam = document.querySelector("#hero-scout-team");
const heroScoutScore = document.querySelector("#hero-scout-score");
const heroScoutSource = document.querySelector("#hero-scout-source");
const heroScoutOpen = document.querySelector("#hero-scout-open");

let searchTimer;
let searchVersion = 0;
let powerTeams = [];
let heroPlayer = null;

function safeImageUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.origin);
    if (
      url.origin === window.location.origin
      && url.pathname.startsWith("/assets/")
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

function renderHeroScout(player) {
  heroPlayer = player;
  heroScoutName.textContent = player.name;
  heroScoutTeam.textContent = player.team || "TEAM NOT RECORDED · 2026";
  heroScoutScore.textContent = Number(player.power_score).toFixed(1);
  heroScoutOpen.disabled = false;

  const imageUrl = safeImageUrl(player.image_local_path || player.image_url);
  heroImage.hidden = !imageUrl;
  heroImagePlaceholder.hidden = Boolean(imageUrl);
  if (imageUrl) {
    heroImage.alt = `${player.name} portrait`;
    heroImage.src = imageUrl;
    heroImage.onerror = () => {
      heroImage.hidden = true;
      heroImagePlaceholder.hidden = false;
    };
  }

  const sourceUrl = safeSourceUrl(player.source_url);
  heroScoutSource.hidden = !sourceUrl;
  if (sourceUrl) heroScoutSource.href = sourceUrl;
}

heroScoutOpen.addEventListener("click", () => {
  if (heroPlayer) loadProfile({ type: "player", id: heroPlayer.id });
});

async function getJson(path) {
  const response = await fetch(path);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status}).`);
  return payload;
}

function addImage(parent, url, className, alt, fallbackText) {
  const safeUrl = safeImageUrl(url);
  if (safeUrl) {
    const image = document.createElement("img");
    image.className = className;
    image.src = safeUrl;
    image.alt = alt;
    image.loading = "lazy";
    image.referrerPolicy = "no-referrer";
    image.onerror = () => {
      const fallback = document.createElement("span");
      fallback.className = `${className} result-fallback`;
      fallback.textContent = fallbackText;
      image.replaceWith(fallback);
    };
    parent.append(image);
  } else {
    const fallback = document.createElement("span");
    fallback.className = `${className} result-fallback`;
    fallback.textContent = fallbackText;
    parent.append(fallback);
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
    item.name.slice(0, 1).toUpperCase(),
  );
  const name = document.createElement("span");
  name.className = "result-name";
  name.textContent = item.name;
  const meta = document.createElement("small");
  meta.className = "result-meta";
  meta.textContent = item.type === "player"
    ? [item.team, item.nationality].filter(Boolean).join(" · ") || "Player"
    : "VCT team";
  name.append(meta);
  button.append(name);
  const type = document.createElement("span");
  type.className = "result-type";
  type.textContent = item.type.toUpperCase();
  button.append(type);
  return button;
}

function makeProfileButton(id, type, name, imageUrl, meta, className) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.addEventListener("click", () => loadProfile({ type, id }));
  addImage(
    button,
    imageUrl,
    "result-avatar",
    `${name} ${type} image`,
    name.slice(0, 1).toUpperCase(),
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

async function search() {
  const query = searchInput.value.trim();
  const requestVersion = ++searchVersion;
  searchResults.replaceChildren();
  if (!query) {
    searchStatus.textContent = "Search VCT tier-one players and teams.";
    return;
  }
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
    player.name.slice(0, 1).toUpperCase(),
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
  ratingLabel.textContent = "GLOBAL PLAYER POWER · LEADER = 100";
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
    team.name.slice(0, 1).toUpperCase(),
  );
  const title = document.createElement("h3");
  title.textContent = team.name;
  header.append(title);
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
      makeStat("POWER · LEADER = 100", Number(team.stats.power_score).toFixed(1)),
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
  playerHeading.textContent = "Players observed in 2026 matches";
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
  tournamentHeading.textContent = "2026 tournament results & prizes";
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
    note.textContent = "No tier-one event participation is recorded for 2026.";
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
  profileView.replaceChildren();
  const loading = document.createElement("p");
  loading.className = "muted";
  loading.textContent = "Loading profile…";
  profileView.append(loading);
  try {
    const kind = item.type === "player" ? "players" : "teams";
    const details = await getJson(`/api/${kind}/${encodeURIComponent(item.id)}`);
    if (item.type === "player") renderPlayer(details);
    else renderTeam(details);
    profileView.scrollIntoView({ behavior: "smooth", block: "start" });
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

function renderPowerTeam(team, rank) {
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
  );
  identity.querySelector("img")?.classList.replace("result-avatar", "rank-team-logo");
  identity.querySelector(".result-name")?.classList.add("power-rank-name");
  teamCell.append(identity);
  const scoreCell = document.createElement("td");
  scoreCell.className = "power-rank-score";
  renderScoreMeter(scoreCell, team.power_score);
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
  identity.querySelector("img")?.classList.replace("result-avatar", "rank-player-image");
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
  row.append(position, playerCell, team, scoreCell, maps, rating, acs, kast);
  return row;
}

function renderPowerDetails(team) {
  const card = document.createElement("article");
  card.className = "power-team-card";
  const heading = document.createElement("div");
  heading.className = "power-team-heading";
  const name = document.createElement("h3");
  name.textContent = team.name;
  const score = document.createElement("strong");
  score.className = "power-team-score";
  score.textContent = team.power_score.toFixed(1);
  const scoreLabel = document.createElement("span");
  scoreLabel.textContent = "POWER";
  score.append(scoreLabel);
  heading.append(name, score);

  const record = document.createElement("p");
  record.className = "power-team-record";
  const matchLosses = team.matches_played - team.matches_won - team.matches_drawn;
  const mapLosses = team.maps_played - team.maps_won - team.maps_drawn;
  record.textContent = `${team.matches_won}W–${matchLosses}L–${team.matches_drawn}D (${team.matches_played} matches) · ${team.maps_won}W–${mapLosses}L–${team.maps_drawn}D (${team.maps_played} maps) · ${team.round_differential > 0 ? "+" : ""}${team.round_differential} rounds · ${team.kills} K / ${team.deaths} D`;

  const components = document.createElement("div");
  components.className = "power-components";
  [
    ["Season results · 35%", team.match_win_rate],
    ["Recent form · 25%", team.recent_performance_rate],
    ["In-game execution · 25%", team.execution_score],
    ["Opponent strength · 15%", team.opponent_strength_rate],
  ].forEach(([label, rate]) => {
    const row = document.createElement("div");
    row.className = "power-component";
    const title = document.createElement("span");
    title.textContent = label;
    const value = document.createElement("strong");
    value.textContent = formatRate(rate);
    row.append(title, value);
    components.append(row);
  });
  card.append(heading, record, components);
  return card;
}

function renderPowerComparison() {
  const firstId = document.querySelector("#team-one").value;
  const secondId = document.querySelector("#team-two").value;
  const first = powerTeams.find((team) => String(team.id) === firstId);
  const second = powerTeams.find((team) => String(team.id) === secondId);
  if (!first || !second) return;
  if (first.id === second.id) {
    powerResult.textContent = "Choose two different teams to compare their power ratings.";
    return;
  }

  const comparison = document.createElement("div");
  comparison.className = "power-comparison";
  comparison.append(renderPowerDetails(first), renderPowerDetails(second));
  const difference = document.createElement("p");
  difference.className = "power-difference";
  const gap = Math.abs(first.power_score - second.power_score).toFixed(1);
  difference.textContent = first.power_score === second.power_score
    ? "Equal 2026 power scores."
    : `${first.power_score > second.power_score ? first.name : second.name} leads by ${gap} power points. This compares 2026 results; it does not predict a match.`;
  powerResult.replaceChildren(comparison, difference);
}

async function loadPowerRankings() {
  const first = document.querySelector("#team-one");
  const second = document.querySelector("#team-two");
  try {
    const payload = await getJson("/api/power-rankings");
    powerTeams = payload.teams;
    document.querySelector("#team-count").textContent = String(powerTeams.length);
    [first, second].forEach((select, selectIndex) => {
      select.replaceChildren(new Option("Choose a 2026 team…", ""));
      powerTeams.forEach((team) => {
        const option = new Option(team.name, team.id);
        option.textContent = `${team.name} · ${team.power_score.toFixed(1)}`;
        if (selectIndex === 1 && String(team.id) === first.value) option.disabled = true;
        select.add(option);
      });
    });
    powerRankings.replaceChildren(
      ...powerTeams.map((team, index) => renderPowerTeam(team, index + 1)),
    );
  } catch (error) {
    [first, second].forEach((select) => select.replaceChildren(new Option("Data unavailable", "")));
    powerResult.textContent = error.message;
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
  const tableBody = document.querySelector("#player-rankings");
  try {
    const payload = await getJson("/api/player-power-rankings");
    document.querySelector("#player-count").textContent = String(payload.players.length);
    if (payload.players.length) renderHeroScout(payload.players[0]);
    tableBody.replaceChildren(
      ...payload.players.map((player, index) => renderPowerPlayer(player, index + 1)),
    );
  } catch (error) {
    const row = document.createElement("tr");
    const message = document.createElement("td");
    message.className = "table-message";
    message.colSpan = 8;
    message.textContent = error.message;
    row.append(message);
    tableBody.replaceChildren(row);
  }
}

powerForm.addEventListener("submit", (event) => {
  event.preventDefault();
  renderPowerComparison();
});

async function loadFuture() {
  try {
    const data = await getJson("/api/2027");
    futureMessage.textContent = data.message;
    futureEvents.replaceChildren();
    const listed = [
      ...data.events.map((event) => ({ ...event, kind: "Event" })),
      ...data.matches.map((match) => ({ ...match, kind: "Fixture" })),
    ];
    listed.forEach((item) => {
      const card = document.createElement("div");
      card.className = "future-event";
      const title = item.title || [item.team1, item.team2].filter(Boolean).join(" vs ") || "To be announced";
      const sourceUrl = safeSourceUrl(item.url);
      if (sourceUrl) {
        const link = document.createElement("a");
        link.className = "source-link";
        link.href = sourceUrl;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = title;
        card.append(link);
      } else {
        card.textContent = title;
      }
      const detail = document.createElement("small");
      const dates = item.start_date && item.end_date
        ? `${item.start_date} – ${item.end_date}`
        : item.start_date || item.date;
      detail.textContent = [item.kind, item.region, item.status, dates].filter(Boolean).join(" · ");
      card.append(detail);
      futureEvents.append(card);
    });
  } catch (error) {
    futureMessage.textContent = error.message;
  }
}

loadPowerRankings();
loadPlayerRankings();
loadFuture();
