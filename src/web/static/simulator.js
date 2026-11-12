(() => {
  const root = document.querySelector("#simulator-workspace");
  const guideHelp = document.querySelector("#sim-guide-help");
  const model = ChampionsSim;
  const draft = [];
  let catalog;
  let loading = false;
  let region = "Pacific";
  let choices = [];
  let run;
  let next;
  let tab = "Groups";
  let groupName;
  let selectedReplay;
  let playing = false;
  const imageChecks = new Map();
  const guideKey = "vct-formline-simulator-guide-v1";
  let guideSeen = false;
  try { guideSeen = localStorage.getItem(guideKey) === "seen"; } catch {}

  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const playIcon = "M7 4l13 8-13 8z";
  const restartIcon = "M3 10a9 9 0 1 1 2 8M3 4v6h6";
  const groupIcon = "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z";
  const buttonIcons = {
    "Try again": restartIcon,
    "Start tournament": playIcon,
    "Play next series": playIcon,
    "Restart draft": restartIcon,
    "New draft": "M12 5v14M5 12h14",
    Groups: groupIcon,
    Playoffs: "M3 4h6v5H3z M3 15h6v5H3z M9 6.5h4v11H9 M13 12h8",
    Match: "M3 5h18v14H3z M10 9l5 3-5 3z",
    "Team stats": "M3 20v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3 M17 13a4 4 0 0 1 4 4v3 M12 7a3 3 0 1 1-6 0 3 3 0 0 1 6 0z M16 4a3 3 0 0 1 0 6",
    "Tournament stats": "M4 3v17h17 M9 16v-4 M14 16V8 M19 16V5",
    "View champions": "M8 4h8v5a4 4 0 0 1-8 0z M8 6H4v2a4 4 0 0 0 4 4 M16 6h4v2a4 4 0 0 1-4 4 M12 13v6 M8 20h8",
    Close: "M6 6l12 12M18 6 6 18",
  };
  const controlIcon = (path) => {
    const icon = lineGraphic("0 0 24 24", path);
    icon.classList.add("sim-button-icon");
    return icon;
  };
  const button = (text, action, className = "sim-button", icon = buttonIcons[text]) => {
    const element = node("button", className, text);
    element.type = "button";
    if (icon) element.prepend(controlIcon(icon));
    element.addEventListener("click", action);
    return element;
  };
  const pause = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));
  const record = (teamId) => Object.values(run.results).reduce((scores, result) => {
    if (result.winner === teamId) scores[0]++;
    if (result.loser === teamId) scores[1]++;
    return scores;
  }, [0, 0]);

  function showGuide() {
    if (document.querySelector(".sim-guide[open]")) return;
    const pages = [
      {
        title: "Draft your five",
        text: "Pick a Duelist, Controller, Initiator, Sentinel, and Flex from past seasons. The stars show each player’s strength for that season.",
        icon: buttonIcons["Team stats"],
      },
      {
        title: "Choose a region and play",
        text: "Pick a region to represent and start the tournament. Select Play next series to reveal the map draw, agent picks, and results.",
        icon: playIcon,
      },
      {
        title: "Follow your bracket",
        text: "Check your next matchup after each series. Open Team stats for your record and replays, or Tournament stats to see how everyone performed.",
        icon: buttonIcons.Playoffs,
      },
    ];
    const dialog = node("dialog", "sim-guide");
    dialog.setAttribute("aria-labelledby", "sim-guide-title");
    dialog.setAttribute("aria-describedby", "sim-guide-description");
    const content = node("div", "sim-guide-content");
    let page = 0;
    function renderPage() {
      const { title, text, icon } = pages[page];
      const mark = controlIcon(icon);
      mark.classList.add("sim-guide-mark");
      const heading = node("h2", "", title);
      heading.id = "sim-guide-title";
      heading.tabIndex = -1;
      heading.autofocus = true;
      const description = node("p", "", text);
      description.id = "sim-guide-description";
      const actions = node("div", "sim-guide-actions");
      actions.append(button("Skip guide", () => dialog.close(), "sim-button sim-guide-skip"));
      if (page > 0) actions.append(button("Back", () => { page--; renderPage(); }));
      actions.append(page === pages.length - 1
        ? button("Start drafting", () => dialog.close("draft"), "sim-button sim-primary", playIcon)
        : button("Next", () => { page++; renderPage(); }, "sim-button sim-primary", "M5 12h14m-6-6 6 6-6 6"));
      content.replaceChildren(mark, node("p", "eyebrow", `How to play · ${page + 1} of ${pages.length}`),
        heading, description, actions);
      if (dialog.open) heading.focus();
    }
    dialog.append(content);
    dialog.addEventListener("close", () => {
      dialog.remove();
      if (location.hash === "#simulator") {
        const draftHeading = root.querySelector(".sim-draft section h2");
        (dialog.returnValue === "draft" && draftHeading ? draftHeading : guideHelp)
          .focus({ preventScroll: true });
      }
    }, { once: true });
    renderPage();
    document.body.append(dialog);
    dialog.showModal();
    guideSeen = true;
    try { localStorage.setItem(guideKey, "seen"); } catch {}
  }

  async function openSimulator() {
    if (catalog || loading) return;
    loading = true;
    loadingPanel("Loading historical rosters and map compositions…");
    try {
      catalog = await getJson("/api/simulator");
      await reset();
    } catch (error) {
      catalog = null;
      const status = node("p", "sim-panel sim-status", error.message);
      status.setAttribute("role", "alert");
      root.replaceChildren(status, button("Try again", openSimulator));
    } finally {
      loading = false;
    }
  }

  async function reset() {
    draft.length = 0;
    run = next = selectedReplay = null;
    tab = "Groups";
    await prepareChoices();
  }

  function imageLoads(url) {
    if (!imageChecks.has(url)) imageChecks.set(url, new Promise((resolve) => {
      const image = new Image();
      image.referrerPolicy = "no-referrer";
      const finish = (loaded) => {
        window.clearTimeout(timeout);
        image.onload = image.onerror = null;
        resolve(loaded);
      };
      const timeout = window.setTimeout(() => finish(false), 7000);
      image.onload = () => finish(image.naturalWidth > 0);
      image.onerror = () => finish(false);
      image.src = url;
    }));
    return imageChecks.get(url);
  }

  async function usableImage(sources) {
    for (const source of sources) {
      const url = safeImageUrl(source);
      if (url && await imageLoads(url)) return [url];
    }
    return [];
  }

  function spinner() {
    const icon = node("span", "sim-spinner");
    icon.setAttribute("aria-hidden", "true");
    return icon;
  }

  function loadingStatus(text, className = "sim-status") {
    const status = node("p", className);
    status.setAttribute("role", "status");
    const message = node("span", "", text);
    status.append(spinner(), message);
    return { status, message };
  }

  function loadingPanel(text) {
    root.replaceChildren(loadingStatus(text, "sim-panel sim-status").status);
  }

  async function prepareChoices(focus = false) {
    const role = model.roles[draft.length];
    choices = [];
    if (role) {
      loadingPanel(`Finding portraits for your ${role.toLowerCase()} options…`);
      const checked = [...draft];
      while (choices.length < 5) {
        const options = model.offers(catalog, role, checked).slice(0, 5 - choices.length);
        if (!options.length) break;
        checked.push(...options);
        const verified = await Promise.all(options.map(async (player) => ({
          ...player, image: await usableImage(player.image),
        })));
        choices.push(...verified.filter((player) => player.image.length));
      }
    }
    renderDraft(focus);
  }

  function identity(person, label) {
    const item = node("div", "sim-identity");
    addImage(item, person.image, "sim-avatar", "");
    const text = node("div");
    const detail = node("small");
    detail.append(label);
    text.append(node("strong", "", person.name), detail);
    item.append(text);
    return item;
  }

  function draftRoster() {
    const list = node("ol", "sim-draft-roster");
    model.roles.forEach((role, index) => {
      const item = node("li");
      const label = node("small");
      label.append(roleBadge(role));
      item.append(label);
      if (draft[index]) {
        const person = draft[index];
        item.append(identity(person, [person.year, person.team].filter(Boolean).join(" · ")));
      } else {
        item.append(node("span", "sim-empty", index === draft.length ? "Selecting now" : "Open slot"));
      }
      list.append(item);
    });
    return list;
  }

  function draftStars(player) {
    // Each five-point step in season power adds half a star.
    const thresholds = [0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15];
    const rating = 1 + 0.5 * thresholds.filter((threshold) => player.skill >= threshold).length;
    const stars = node("span", "sim-stars");
    stars.setAttribute("role", "img");
    stars.setAttribute("aria-label", `Simulator strength: ${rating} out of 5 stars`);
    stars.title = player.power_score == null ? stars.getAttribute("aria-label")
      : `Season power: ${player.power_score.toFixed(1)} points · ${rating} out of 5 stars`;
    for (let index = 0; index < 5; index++) {
      const star = lineGraphic("0 0 24 24", "m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9z");
      if (index + 0.5 === rating) {
        const half = node("span", "sim-star-half");
        const fill = star.cloneNode(true);
        fill.classList.add("sim-star-filled");
        half.append(star, fill);
        stars.append(half);
      } else {
        if (index + 1 <= rating) star.classList.add("sim-star-filled");
        stars.append(star);
      }
    }
    return stars;
  }

  function regionPicker() {
    const picker = node("div", "sim-region-picker");
    const label = node("p", "", "Represent a region");
    const choices = node("div", "sim-region-options");
    choices.setAttribute("role", "group");
    choices.setAttribute("aria-label", label.textContent);
    for (const name of catalog.regions) {
      const choice = button(name, () => {
        region = name;
        for (const option of choices.children) {
          option.setAttribute("aria-pressed", String(option === choice));
        }
      }, "sim-button sim-region-button");
      choice.setAttribute("aria-pressed", String(name === region));
      const logo = node("img");
      logo.src = getRegion(name).logo;
      logo.alt = "";
      choice.prepend(logo);
      choices.append(choice);
    }
    picker.append(label, choices);
    return picker;
  }

  function renderDraft(focus = false) {
    const role = model.roles[draft.length];
    const layout = node("div", "sim-draft");
    const lineup = node("aside", "sim-panel");
    lineup.append(node("h2", "", "Your lineup"), draftRoster());
    const main = node("section", "sim-panel");
    const heading = node("h2");
    heading.append(role ? roleBadge(role, `Choose your ${role.toLowerCase()}`) : "Enter Champions");
    heading.tabIndex = -1;
    main.append(node("p", "eyebrow", role ? `Draft pick ${draft.length + 1} of 5` : "Lineup complete"), heading);
    if (role) {
      const options = node("div", "sim-options");
      for (const person of choices) {
        const card = button("", () => {
          draft.push(person);
          prepareChoices(true);
        }, "sim-option");
        addImage(card, person.image, "sim-option-photo", "");
        const label = node("div", "sim-option-label");
        if (person.year) label.append(node("span", "sim-year", String(person.year)));
        label.append(node("strong", "", person.name), node("small", "", person.team));
        if (role === "Flex") {
          const playerRole = node("small");
          playerRole.append(roleBadge(person.role));
          label.append(playerRole);
        }
        label.append(draftStars(person));
        card.append(label);
        options.append(card);
      }
      main.append(options);
      if (!choices.length) main.append(node("p", "sim-muted", "No portraits could be loaded for this slot."));
      if (role === "Flex") main.append(node("p", "sim-muted", "Any player role can fill the flex slot."));
    } else {
      main.append(regionPicker(), button("Start tournament", start, "sim-button sim-primary"));
    }
    if (draft.length || !choices.length && role) main.append(button("Restart draft", reset, "sim-button sim-subtle"));
    layout.append(lineup, main);
    root.replaceChildren(layout);
    if (focus) heading.focus({ preventScroll: true });
  }

  async function start() {
    loadingPanel("Drawing opponents and checking their logos and portraits…");
    try {
      let candidates = catalog.teams;
      while (true) {
        run = model.create({ ...catalog, teams: candidates }, draft, region);
        const opponents = Object.values(run.teams).filter((team) => team.id !== model.userId);
        const rejected = new Set();
        await Promise.all(opponents.map(async (team) => {
          const [logo, ...portraits] = await Promise.all([
            usableImage(team.logo), ...team.roster.map((player) => usableImage(player.image)),
          ]);
          if (!logo.length || portraits.some((image) => !image.length)) {
            rejected.add(team.id);
          } else {
            run.teams[team.id] = {
              ...team, logo, roster: team.roster.map((player, index) => ({ ...player, image: portraits[index] })),
            };
          }
        }));
        if (!rejected.size) break;
        candidates = candidates.filter((team) => !rejected.has(team.id));
      }
      groupName = run.groups.find((group) => group.teams.includes(model.userId)).name;
      next = model.advance(catalog, run);
      renderRun();
    } catch (error) {
      run = null;
      renderDraft();
      const status = node("p", "sim-status", error.message);
      status.setAttribute("role", "alert");
      root.prepend(status);
    }
  }

  function teamIdentity(team, extra = "") {
    const item = node("div", "sim-team");
    if (!team) {
      item.append(node("span", "sim-empty", "TBD"));
      return item;
    }
    addImage(item, team.logo, "sim-team-logo", "");
    const text = node("div");
    text.append(node("strong", "", team.name));
    const detail = [team.year, team.region, extra].filter(Boolean).join(" · ");
    if (detail) text.append(node("small", "", detail));
    item.append(text);
    return item;
  }

  function rosterPanel(team, label) {
    const panel = node("aside", "sim-panel sim-lineup");
    panel.append(node("h2", "", label), teamIdentity(team));
    if (!team) return panel;
    const list = node("ul", "sim-roster-list");
    for (const person of team.roster) {
      const item = node("li");
      const label = roleBadge(person.slot || person.role);
      if (person.year) label.append(` · ${person.year}`);
      item.append(identity(person, label));
      list.append(item);
    }
    panel.append(list);
    return panel;
  }

  function renderRun(animateProgress = false) {
    const progress = node("section", "sim-panel sim-progress");
    const userRecord = record(model.userId).join("–");
    const status = node("div");
    status.append(node("h2", "", run.results.GF ? "Tournament complete" : next?.title || "Tournament progress"),
      node("p", "sim-muted", `Your series record ${userRecord}`));
    progress.append(status);
    if (next && !playing) progress.append(button("Play next series", playNext, "sim-button sim-primary"));
    if (!playing) progress.append(button("New draft", reset, "sim-button sim-subtle"));

    const nav = node("nav", "sim-tabs");
    nav.setAttribute("aria-label", "Simulator views");
    for (const name of ["Groups", "Playoffs", "Match", "Team stats", "Tournament stats"]) {
      const item = button(name, () => { tab = name; renderRun(); });
      item.disabled = playing;
      if (name === tab) item.setAttribute("aria-current", "page");
      nav.append(item);
    }
    const active = next ? model.sidesFor(run, next) : selectedReplay?.result.sides;
    const opponent = active?.find((id) => id !== model.userId);
    const rightLabel = next ? "Next opponent" : "Series opponent";
    const right = rosterPanel(run.teams[opponent], rightLabel);
    const center = node("section", "sim-panel sim-center");
    if (tab === "Groups") renderGroups(center);
    if (tab === "Playoffs") renderPlayoffs(center);
    if (tab === "Match") {
      if (selectedReplay && !playing) {
        const { fixture, result } = selectedReplay;
        center.append(node("h2", "", fixture.title), seriesHeadline(result), mapOrder(result.order));
        result.maps.forEach((map) => center.append(mapCard(map, result, true)));
      } else if (!playing) {
        center.append(node("p", "sim-muted", "Play your next series to see the map draw and agent picks."));
      }
    }
    if (tab === "Team stats") renderRecap(center);
    if (tab === "Tournament stats") {
      center.append(node("h2", "", "Tournament player stats"),
        statsTable(model.standings(Object.values(run.results))));
    }

    const layout = node("div", "sim-layout");
    layout.append(rosterPanel(run.teams[model.userId], "Your team"), center, right);
    root.replaceChildren(progress);
    const last = lastUserFixture();
    if (last && !playing) root.append(bracketProgress(last, animateProgress));
    if (run.results.GF) root.append(championPanel());
    root.append(nav, layout);
    return center;
  }

  function lastUserFixture() {
    return [...run.groups.flatMap((group) => group.fixtures), ...run.playoffs]
      .findLast((fixture) => run.results[fixture.id]?.sides.includes(model.userId));
  }

  function bracketProgress(last, animate) {
    const won = run.results[last.id].winner === model.userId;
    const stage = (fixture) => fixture.id === "GF" ? "Championship"
      : !run.playoffs.includes(fixture) ? `Group ${fixture.id[0]}`
      : fixture.id.startsWith("U") ? "Upper bracket" : "Lower bracket";
    const destination = next?.title ?? (last.id === "GF" && won ? "Champions" : "Run ended");
    const caption = next ? stage(next) : last.id === "GF" && !won ? "Runner-up"
      : last.id === "GF" ? "Tournament winner" : "Eliminated";
    const panel = node("section", "sim-panel sim-bracket-progress");
    if (animate) panel.classList.add("sim-bracket-progress-enter");
    const heading = node("h2", "", "Bracket progress");
    heading.tabIndex = -1;
    const route = node("div", "sim-progress-route");
    const finished = node("div", "sim-progress-step");
    finished.append(node("small", "", `${stage(last)} · ${won ? "Won" : "Lost"}`), node("strong", "", last.title));
    const connector = node("span", "sim-progress-connector");
    connector.setAttribute("aria-hidden", "true");
    const upcoming = node("div", "sim-progress-step sim-progress-destination");
    upcoming.append(node("small", "", caption), node("strong", "", destination));
    route.append(finished, connector, upcoming);
    const bracketFixture = next || last;
    const view = run.playoffs.includes(bracketFixture) ? "Playoffs" : "Groups";
    const open = button("View bracket", () => {
      tab = view;
      if (view === "Groups") groupName = bracketFixture.id[0];
      renderRun();
      const bracketHeading = root.querySelector(".sim-center h2");
      bracketHeading.tabIndex = -1;
      bracketHeading.focus();
    }, "sim-button", buttonIcons[view]);
    panel.append(heading, route, open);
    return panel;
  }

  function championPanel() {
    const result = run.results.GF;
    const banner = node("section", "sim-champion sim-panel");
    const title = node("div");
    const finalScore = [...result.score].sort((a, b) => b - a).join("–");
    title.append(node("p", "eyebrow", "Champions winner"), teamIdentity(run.teams[result.winner], finalScore));
    const mvp = model.standings([result]).find((row) => row.team === result.winner);
    const player = node("div");
    player.append(node("p", "eyebrow", "Finals MVP"), identity(mvp.player, `${mvp.kills}/${mvp.deaths}/${mvp.assists} K/D/A · ${mvp.rating.toFixed(2)} rating · ${Math.round(mvp.acs)} ACS`));
    const label = result.winner === model.userId ? "View champions" : "View tournament result";
    banner.append(title, player, button(label, () => showChampions(false), "sim-button", buttonIcons["View champions"]),
      button("Team stats", () => { tab = "Team stats"; renderRun(); }));
    return banner;
  }

  function showChampions(celebrate) {
    if (document.querySelector(".sim-victory[open]")) return;
    const final = run.results.GF;
    const champion = run.teams[final.winner];
    const userWon = final.winner === model.userId;
    const mvp = model.standings([final]).find((row) => row.team === final.winner);
    const dialog = node("dialog", "sim-victory");
    dialog.setAttribute("aria-labelledby", "sim-victory-title");
    const content = node("div", "sim-victory-content");
    const close = button("Close", () => dialog.close(), "sim-button sim-victory-close");
    const last = lastUserFixture();
    const title = node("h2", "", userWon ? "Your team wins Champions"
      : last.id === "GF" ? "Your team finishes runner-up" : "Your team was eliminated");
    title.id = "sim-victory-title";
    content.append(close, node("p", "eyebrow", "Tournament result"), title);
    const summary = node("div", "sim-outcome-grid");
    if (!userWon) {
      const exit = node("section", "sim-outcome-card");
      const lastResult = run.results[last.id];
      const [left, right] = sideOrder(lastResult);
      exit.append(node("h3", "", "Your final series"), seriesScore(lastResult),
        node("p", "sim-muted", `${last.title} · Lost ${lastResult.score[left]}–${lastResult.score[right]}`));
      summary.append(exit);
    }
    const winner = node("section", "sim-outcome-card sim-outcome-winner");
    winner.append(node("h3", "", "Champions winner"),
      teamIdentity(champion, [...final.score].sort((a, b) => b - a).join("–")));
    summary.append(winner);
    content.append(summary);

    const portrait = node("div", "sim-victory-mvp");
    const frame = node("div", "sim-victory-portrait");
    const crown = node("span", "sim-victory-crown", "👑");
    crown.setAttribute("aria-hidden", "true");
    frame.append(crown);
    addImage(frame, mvp.player.image, "sim-victory-photo", mvp.player.name);
    const player = node("div");
    player.append(node("p", "eyebrow", "Finals MVP"), node("h3", "", mvp.player.name),
      node("p", "sim-muted", `${mvp.kills}/${mvp.deaths}/${mvp.assists} K/D/A · ${mvp.rating.toFixed(2)} rating · ${Math.round(mvp.acs)} ACS`));
    portrait.append(frame, player);
    content.append(portrait);

    const roster = node("ul", "sim-victory-roster");
    for (const player of champion.roster) {
      const entry = node("li");
      const label = roleBadge(player.slot || player.role);
      if (player.year) label.append(` · ${player.year}`);
      entry.append(identity(player, label));
      roster.append(entry);
    }
    content.append(node("h3", "", "Winning roster"), roster);
    dialog.append(content);
    if (celebrate && userWon) {
      const effects = node("div", "sim-fireworks");
      effects.setAttribute("aria-hidden", "true");
      for (const [index, [x, y]] of [[16, 31], [77, 18], [60, 70], [24, 80], [88, 55]].entries()) {
        const burst = node("div", "sim-burst");
        burst.style.cssText = `--x:${x}%;--y:${y}%;--delay:${index * 280}ms`;
        for (let ray = 0; ray < 12; ray++) {
          const spark = node("i");
          spark.style.setProperty("--angle", `${ray * 30}deg`);
          burst.append(spark);
        }
        effects.append(burst);
      }
      dialog.append(effects);
    }
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    document.body.append(dialog);
    dialog.showModal();
  }

  function matchCard(match) {
    const result = run.results[match.id];
    const sides = model.sidesFor(run, match);
    const card = node("div", "sim-bracket-match");
    if (next?.id === match.id) card.classList.add("sim-bracket-next");
    const header = result
      ? button(match.title, () => {
        selectedReplay = { fixture: match, result };
        tab = "Match";
        renderRun();
      }, "sim-fixture-link", playIcon)
      : node("p", "sim-fixture-label", match.title);
    card.append(header);
    sides.forEach((id, index) => {
      const row = node("div", "sim-fixture-team");
      if (id && id === result?.winner) row.classList.add("sim-fixture-winner");
      row.append(teamIdentity(run.teams[id]), node("b", "", result ? result.score[index] : "–"));
      card.append(row);
    });
    return card;
  }

  function drawBracket(container, matches, positions, columns, rows) {
    const scroll = node("div", "sim-bracket-scroll");
    scroll.tabIndex = 0;
    scroll.setAttribute("aria-label", "Tournament bracket, scroll horizontally to see all rounds");
    const board = node("div", "sim-bracket");
    board.style.setProperty("--sim-cols", columns);
    board.style.setProperty("--sim-rows", rows);
    const canvas = node("canvas", "sim-bracket-lines");
    canvas.setAttribute("aria-hidden", "true");
    const mark = node("img", "sim-bracket-mark");
    mark.src = "/champions-mark.svg";
    mark.alt = "";
    mark.style.gridArea = columns === 3 ? "1 / 3 / span 2 / span 1" : "1 / 5 / span 3 / span 2";
    board.append(canvas, mark);
    const cards = new Map();
    for (const fixture of matches) {
      const card = matchCard(fixture);
      const [col, row] = positions[fixture.id];
      card.style.gridArea = `${row} / ${col} / span 2 / span 1`;
      cards.set(fixture.id, card);
      board.append(card);
    }
    scroll.append(board);
    container.append(scroll);
    window.requestAnimationFrame(() => {
      const origin = board.getBoundingClientRect();
      if (!origin.width || !canvas.isConnected) return;
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.round(origin.width * ratio);
      canvas.height = Math.round(origin.height * ratio);
      const context = canvas.getContext("2d");
      context.scale(ratio, ratio);
      context.strokeStyle = "#75664c";
      context.lineWidth = 1;
      for (const match of matches) {
        const end = cards.get(match.id).getBoundingClientRect();
        for (const [index, side] of match.sides.entries()) {
          if (!cards.has(side.id)) continue;
          const start = cards.get(side.id).getBoundingClientRect();
          const x1 = start.right - origin.left;
          const x2 = end.left - origin.left;
          const y1 = start.top - origin.top + start.height / 2;
          const y2 = end.top - origin.top + end.height * (index ? 0.72 : 0.38);
          if (x1 >= x2) continue;
          const middle = x1 + Math.min(18, (x2 - x1) / 2);
          context.setLineDash(side.winner ? [] : [3, 3]);
          context.beginPath();
          context.moveTo(x1, y1);
          context.lineTo(middle, y1);
          context.lineTo(middle, y2);
          context.lineTo(x2, y2);
          context.stroke();
        }
      }
    });
  }

  function renderGroups(center) {
    const selector = node("div", "sim-tabs");
    for (const group of run.groups) {
      const item = button(`Group ${group.name}`, () => { groupName = group.name; renderRun(); }, "sim-button", groupIcon);
      item.setAttribute("aria-pressed", String(group.name === groupName));
      selector.append(item);
    }
    center.append(node("h2", "", "Group stage"), selector);
    const group = run.groups.find((entry) => entry.name === groupName);
    const positions = [[1, 1], [1, 4], [2, 1], [2, 4], [3, 3]];
    drawBracket(center, group.fixtures, Object.fromEntries(group.fixtures.map((fixture, i) =>
      [fixture.id, positions[i]])), 3, 5);
    const qualified = [run.results[`${groupName}W`]?.winner, run.results[`${groupName}D`]?.winner].filter(Boolean);
    if (qualified.length) {
      const line = node("p", "sim-muted", `Qualified · ${qualified.map((id) => run.teams[id].name).join(", ")}`);
      center.append(line);
    }
  }

  function renderPlayoffs(center) {
    center.append(node("h2", "", "Playoff bracket"), node("p", "sim-muted", "Upper bracket above · Lower bracket below"));
    drawBracket(center, run.playoffs, {
      U1: [1, 1], U2: [1, 3], U3: [1, 5], U4: [1, 7],
      U5: [2, 2], U6: [2, 6], U7: [3, 4], GF: [6, 7],
      L1: [2, 10], L2: [2, 12], L3: [3, 10], L4: [3, 12],
      L5: [4, 11], L6: [5, 11],
    }, 6, 13);
  }

  function sideOrder(result) {
    return result.sides[1] === model.userId ? [1, 0] : [0, 1];
  }

  function seriesScore(result) {
    const [left, right] = sideOrder(result);
    const score = node("div", "sim-series-score");
    score.append(teamIdentity(run.teams[result.sides[left]]),
      node("strong", "", `${result.score[left]}–${result.score[right]}`),
      teamIdentity(run.teams[result.sides[right]]));
    return score;
  }

  function seriesHeadline(result) {
    const header = node("div", "sim-result-heading");
    const mvp = model.standings([result])[0];
    const highlight = node("div", "sim-match-mvp");
    highlight.append(node("p", "eyebrow", "Match MVP"),
      identity(mvp.player, `${mvp.rating.toFixed(2)} rating · ${mvp.kills}/${mvp.deaths}/${mvp.assists} K/D/A`));
    header.append(seriesScore(result), highlight);
    return header;
  }

  function agentIcons(lines) {
    const icons = node("div", "sim-agent-icons");
    for (const { player, agent } of lines) {
      const entry = catalog.agents[agent];
      const portrait = node("span", "sim-agent-player");
      portrait.title = `${player.name} · ${entry.name}`;
      addImage(portrait, player.image, "sim-map-player", player.name);
      addImage(portrait, entry.image, "agent-portrait", entry.name);
      icons.append(portrait);
    }
    return icons;
  }

  function mapScore(map, result) {
    const score = node("div", "sim-map-score");
    const [left, right] = sideOrder(result);
    addImage(score, run.teams[result.sides[left]].logo, "sim-map-logo", run.teams[result.sides[left]].name);
    score.append(node("strong", "", `${map.rounds[left]}–${map.rounds[right]}`));
    addImage(score, run.teams[result.sides[right]].logo, "sim-map-logo", run.teams[result.sides[right]].name);
    return score;
  }

  const mapImage = (name) => `/vct-images/maps/${name.toLowerCase()}.jpg`;

  function mapOrder(order) {
    const list = node("ol", "sim-map-order");
    list.setAttribute("aria-label", "Map order");
    for (const name of order) {
      const item = node("li", "sim-map-preview");
      const image = node("img");
      image.src = mapImage(name);
      image.alt = "";
      item.append(image, node("span", "", name));
      list.append(item);
    }
    return list;
  }

  function mapCard(map, result, revealed) {
    const card = node("article", "sim-map");
    card.style.setProperty("--sim-map-image", `url("${mapImage(map.name)}")`);
    const line = node("div", "sim-map-line");
    const [left, right] = sideOrder(result);
    line.append(agentIcons(map.stats[left]),
      revealed ? mapScore(map, result) : node("span", "sim-map-score"),
      agentIcons(map.stats[right]));
    if (!revealed) line.querySelector(".sim-map-score").append(spinner());
    card.append(node("h3", "", map.name), line);
    if (revealed && map.scenes.length) {
      const list = node("ul", "sim-highlights");
      for (const scene of map.scenes) list.append(node("li", "", scene));
      card.append(list);
    }
    return card;
  }

  async function playNext() {
    if (playing || !next) return;
    const fixture = next;
    playing = true;
    tab = "Match";
    const center = renderRun();
    const { status, message } = loadingStatus("Drawing maps…");
    center.append(node("h2", "", fixture.title), status);
    try {
      const result = model.play(catalog, run, fixture);
      await pause(650);
      center.append(mapOrder(result.order));
      message.textContent = "Locking agent compositions…";
      await pause(650);
      for (const map of result.maps) {
        message.textContent = `${map.name} in progress…`;
        const card = mapCard(map, result, false);
        center.append(card);
        if (map.scenes.length) {
          const highlights = node("ul", "sim-highlights");
          card.append(highlights);
          for (const scene of map.scenes) {
            await pause(700);
            highlights.append(node("li", "sim-highlight-enter", scene));
          }
        }
        await pause(2000);
        card.querySelector(".sim-map-score").replaceWith(mapScore(map, result));
      }
      run.results[fixture.id] = result;
      selectedReplay = { fixture, result };
      next = model.advance(catalog, run);
      playing = false;
      renderRun(true);
      if (location.hash === "#simulator") {
        const progressHeading = root.querySelector(".sim-bracket-progress h2");
        progressHeading.focus({ preventScroll: true });
        progressHeading.closest("section").scrollIntoView({ block: "nearest" });
      }
      if (run.results.GF) {
        const completedRun = run;
        await pause(700);
        if (run === completedRun && location.hash === "#simulator") showChampions(true);
      }
    } catch (error) {
      playing = false;
      const panel = renderRun();
      panel.prepend(node("p", "sim-status", error.message));
    }
  }

  function renderRecap(center) {
    const fixtures = [...run.groups.flatMap((group) => group.fixtures), ...run.playoffs];
    const played = fixtures.filter((match) => run.results[match.id]?.sides.includes(model.userId));
    const results = played.map((match) => run.results[match.id]);
    center.append(node("h2", "", "Team stats"),
      node("p", "sim-muted", `Series record ${record(model.userId).join("–")}`));
    if (!played.length) {
      center.append(node("p", "sim-muted", "Your results will appear after the first series."));
      return;
    }
    const list = node("ul", "sim-results-list");
    for (const fixture of played) {
      const result = run.results[fixture.id];
      const entry = node("li");
      const replay = button("", () => {
        selectedReplay = { fixture, result };
        tab = "Match";
        renderRun();
      });
      const label = node("span", "sim-recap-label", fixture.title);
      label.prepend(controlIcon(playIcon));
      replay.append(label, seriesScore(result));
      entry.append(replay);
      list.append(entry);
    }
    center.append(list, statsTable(model.standings(results).filter((row) => row.team === model.userId)));
  }

  function statsTable(rows) {
    const scroll = node("div", "sim-stats-scroll");
    const table = node("table", "sim-stats");
    const header = table.createTHead().insertRow();
    for (const label of ["#", "Player", "Team", "Maps", "Rating", "ACS", "K/D/A", "Agents"]) {
      const cell = node("th", "", label);
      cell.scope = "col";
      header.append(cell);
    }
    const body = table.createTBody();
    rows.forEach((row, index) => {
      const line = body.insertRow();
      if (row.team === model.userId) line.className = "sim-user-stat";
      line.insertCell().textContent = index + 1;
      line.insertCell().append(identity(row.player, String(row.player.year)));
      line.insertCell().append(teamIdentity(run.teams[row.team]));
      for (const value of [row.maps, row.rating.toFixed(2), Math.round(row.acs), `${row.kills}/${row.deaths}/${row.assists}`]) {
        line.insertCell().textContent = value;
      }
      const icons = node("div", "sim-agent-icons");
      for (const [agent, maps] of row.agents.slice(0, 3)) {
        const icon = node("span");
        icon.title = `${catalog.agents[agent].name} · ${maps} maps`;
        addImage(icon, catalog.agents[agent].image, "agent-portrait", icon.title);
        icons.append(icon);
      }
      line.insertCell().append(icons);
    });
    scroll.append(table);
    return scroll;
  }

  guideHelp.prepend(controlIcon("M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z M9.1 9a3 3 0 1 1 4.5 2.6c-1.1.7-1.6 1.3-1.6 2.4m0 3h.01"));
  guideHelp.addEventListener("click", showGuide);
  function enterSimulator() {
    if (!guideSeen) showGuide();
    if (catalog && run && !playing) renderRun();
    else openSimulator();
  }
  document.addEventListener("simulator:open", enterSimulator);
  if (location.hash === "#simulator") enterSimulator();
})();
