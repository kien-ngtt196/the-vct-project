/* Fictional match model and the Champions Shanghai tournament bracket. */
const ChampionsSim = (() => {
  const roles = ["Duelist", "Controller", "Initiator", "Sentinel", "Flex"];
  const userId = "draft";
  const letters = ["A", "B", "C", "D"];
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const sum = (values) => values.reduce((total, value) => total + value, 0);

  function shuffle(values, random) {
    const output = [...values];
    for (let index = output.length - 1; index > 0; index--) {
      const other = Math.floor(random() * (index + 1));
      [output[index], output[other]] = [output[other], output[index]];
    }
    return output;
  }

  function offers(catalog, role, selected, random = Math.random) {
    const used = new Set(selected.map((player) => player.id));
    const candidates = catalog.players.filter((player) => !used.has(player.id) && player.image.length
      && (role === "Flex" || player.role === role));
    const result = [];
    for (const player of shuffle(candidates, random)) {
      if (used.has(player.id)) continue;
      used.add(player.id);
      result.push(player);
      if (result.length === 5) break;
    }
    return result;
  }

  const winner = (id) => ({ id, winner: true });
  const loser = (id) => ({ id, winner: false });
  const fixture = (id, title, sides, bestOf = 3) => ({ id, title, sides, bestOf });

  function create(catalog, draft, userRegion, random = Math.random) {
    const user = {
      id: userId, name: "Your team", region: userRegion, logo: ["/favicon.svg"],
      roster: draft.map((player, index) => ({ ...player, slot: roles[index] })),
    };
    const teams = { [userId]: user };
    const groups = letters.map((name) => ({ name, teams: [], fixtures: [] }));
    const used = new Set();
    for (const region of catalog.regions) {
      const candidates = catalog.teams.filter((team) => team.region === region && team.logo.length
        && team.roster.length === 5 && team.roster.every((player) => player.image.length));
      const chosen = region === userRegion ? [user] : [];
      for (const team of shuffle(candidates, random)) {
        if (used.has(team.org)) continue;
        used.add(team.org);
        chosen.push(team);
        teams[team.id] = team;
        if (chosen.length === 4) break;
      }
      if (chosen.length !== 4) throw new Error(`Need four distinct entries for ${region}.`);
      shuffle(chosen, random).forEach((team, index) => groups[index].teams.push(team.id));
    }
    for (const group of groups) {
      const [a, b, c, d] = shuffle(group.teams, random);
      const id = group.name;
      group.fixtures = [
        fixture(`${id}1`, "Opening 1", [a, b]),
        fixture(`${id}2`, "Opening 2", [c, d]),
        fixture(`${id}W`, "Winners match", [winner(`${id}1`), winner(`${id}2`)]),
        fixture(`${id}L`, "Elimination match", [loser(`${id}1`), loser(`${id}2`)]),
        fixture(`${id}D`, "Decider", [loser(`${id}W`), winner(`${id}L`)]),
      ];
    }
    const playoffs = [
      fixture("U1", "Upper quarterfinal 1", [winner("AW"), winner("BD")]),
      fixture("U2", "Upper quarterfinal 2", [winner("CW"), winner("DD")]),
      fixture("U3", "Upper quarterfinal 3", [winner("BW"), winner("AD")]),
      fixture("U4", "Upper quarterfinal 4", [winner("DW"), winner("CD")]),
      fixture("U5", "Upper semifinal 1", [winner("U1"), winner("U2")]),
      fixture("U6", "Upper semifinal 2", [winner("U3"), winner("U4")]),
      fixture("L1", "Lower round 1 · Match 1", [loser("U1"), loser("U2")]),
      fixture("L2", "Lower round 1 · Match 2", [loser("U3"), loser("U4")]),
      fixture("U7", "Upper final", [winner("U5"), winner("U6")]),
      fixture("L3", "Lower round 2 · Match 1", [winner("L1"), loser("U6")]),
      fixture("L4", "Lower round 2 · Match 2", [winner("L2"), loser("U5")]),
      fixture("L5", "Lower semifinal", [winner("L3"), winner("L4")]),
      fixture("L6", "Lower final", [winner("L5"), loser("U7")], 5),
      fixture("GF", "Grand final", [winner("U7"), winner("L6")], 5),
    ];
    return { teams, groups, playoffs, results: {} };
  }

  function sidesFor(run, match) {
    return match.sides.map((side) => typeof side === "string" ? side
      : run.results[side.id]?.[side.winner ? "winner" : "loser"]);
  }

  function weightedIndex(weights, random) {
    let draw = random() * sum(weights);
    for (let index = 0; index < weights.length - 1; index++) {
      draw -= weights[index];
      if (draw < 0) return index;
    }
    return weights.length - 1;
  }

  function composition(catalog, map, roster, random) {
    const comps = catalog.comps[map];
    const chosen = comps[weightedIndex(comps.map(({ uses }) => Math.sqrt(uses)), random)];
    const fit = roster.map((player) => chosen.agents.map((agent) => {
      const affinity = player.agents.indexOf(agent);
      const role = player.slot || player.role;
      return (affinity < 0 ? 0 : 8 - affinity)
        + (catalog.agents[agent].role === role ? 4 : 0);
    }));
    let best = [];
    let bestFit = -1;
    const assign = (picks, used, score) => {
      if (picks.length === roster.length) {
        if (score > bestFit) [best, bestFit] = [picks, score];
        return;
      }
      chosen.agents.forEach((agent, index) => {
        if (!(used & (1 << index))) assign([...picks, agent], used | (1 << index), score + fit[picks.length][index]);
      });
    };
    assign([], 0, 0);
    return { agents: best, fit: bestFit };
  }

  function roundsFor(chance, random) {
    const rounds = [0, 0];
    while (Math.max(...rounds) < 13 || Math.abs(rounds[0] - rounds[1]) < 2) {
      rounds[random() < chance ? 0 : 1]++;
      if (rounds[0] === 30 && rounds[1] === 30) {
        rounds[random() < chance ? 0 : 1] += 2;
        break;
      }
    }
    return rounds;
  }

  function distribute(total, weights, random) {
    const result = weights.map(() => 0);
    for (let index = 0; index < total; index++) result[weightedIndex(weights, random)]++;
    return result;
  }

  function statLines(team, agents, ownDeaths, enemyDeaths, rounds, random) {
    const form = team.roster.map((player) => player.skill * (0.72 + random() * 0.56));
    const kills = distribute(enemyDeaths, form, random);
    const deaths = distribute(ownDeaths, form.map((value) => 1 / value), random);
    const assists = distribute(Math.round(enemyDeaths * 0.5), form, random);
    return team.roster.map((player, i) => ({
      player, team: team.id, agent: agents[i], kills: kills[i], deaths: deaths[i], assists: assists[i],
      acs: Math.round((kills[i] * 235 + assists[i] * 48) / rounds),
      rating: clamp(0.54 + (kills[i] + assists[i] * 0.3) / rounds * 0.82
        + (kills[i] - deaths[i]) / rounds * 0.26, 0.15, 2.4),
    }));
  }

  const highlights = [
    (w, l) => `${w} converts a 1v4 clutch after ${l} misses the opening shot.`,
    (w, l) => `${w} times the swing and wins the 1v1 against ${l}.`,
    (w, l) => `${l} breaks into the site, but ${w} finds a quick trade and sticks the defuse.`,
    (w, l) => `${w} reads ${l}'s flank and turns the retake into a triple kill.`,
    (w, l) => `${l} nearly steals the round with a Sheriff; ${w} wins it with seconds left.`,
    (w, l) => `${w} catches ${l} on the rotate and secures the round with a two-piece.`,
  ];

  function play(catalog, run, match, random = Math.random) {
    const sides = sidesFor(run, match);
    if (sides.some((side) => !side) || run.results[match.id]) throw new Error("This match is unavailable.");
    const teams = sides.map((id) => run.teams[id]);
    const order = shuffle(catalog.maps, random).slice(0, match.bestOf);
    const maps = [];
    const score = [0, 0];
    for (const name of order) {
      const picks = teams.map((team) => composition(catalog, name, team.roster, random));
      const power = teams.map((team, index) =>
        sum(team.roster.map((player) => player.skill)) / 5 + picks[index].fit * 0.0007);
      const chance = clamp(0.5 + (power[0] - power[1]) * 0.63 + (random() - 0.5) * 0.13, 0.28, 0.72);
      const rounds = roundsFor(chance, random);
      const won = rounds[0] > rounds[1] ? 0 : 1;
      score[won]++;
      const deaths = rounds.map((wonRounds, index) =>
        Math.round(wonRounds * (1.65 + random() * 0.65) + rounds[1 - index] * (3.8 + random() * 0.8)));
      const stats = teams.map((team, index) =>
        statLines(team, picks[index].agents, deaths[index], deaths[1 - index], sum(rounds), random));
      const scenes = match.id === "GF" ? shuffle(highlights, random).slice(0, 3).map((scene, index) => {
        const w = teams[won].roster[Math.floor(random() * 5)].name;
        const l = teams[1 - won].roster[Math.floor(random() * 5)].name;
        return `Round ${[4, Math.floor(sum(rounds) / 2), sum(rounds)][index]} · ${scene(w, l)}`;
      }) : [];
      maps.push({ name, rounds, stats, scenes });
      if (score[won] > match.bestOf / 2) break;
    }
    const win = score[0] > score[1] ? 0 : 1;
    return { sides, score, maps, order, winner: sides[win], loser: sides[1 - win] };
  }

  function advance(catalog, run, random = Math.random) {
    const groups = run.groups.flatMap((group) => group.fixtures);
    while (!run.results.GF) {
      const phase = groups.every((match) => run.results[match.id]) ? run.playoffs : groups;
      const ready = phase.filter((match) => !run.results[match.id] && sidesFor(run, match).every(Boolean));
      const automatic = ready.find((match) => !sidesFor(run, match).includes(userId));
      if (automatic) run.results[automatic.id] = play(catalog, run, automatic, random);
      else if (ready.length) return ready[0];
      else throw new Error("The next tournament fixture could not be resolved.");
    }
    return null;
  }

  function standings(results) {
    const totals = new Map();
    for (const result of results) {
      for (const map of result.maps) {
        for (const line of map.stats.flat()) {
          const key = `${line.team}:${line.player.id}`;
          if (!totals.has(key)) totals.set(key, {
            player: line.player, team: line.team, maps: 0,
            kills: 0, deaths: 0, assists: 0, acs: 0, rating: 0, agents: {},
          });
          const player = totals.get(key);
          player.maps++;
          for (const metric of ["kills", "deaths", "assists", "acs", "rating"]) player[metric] += line[metric];
          player.agents[line.agent] = (player.agents[line.agent] || 0) + 1;
        }
      }
    }
    return [...totals.values()].map((row) => ({
      ...row, acs: row.acs / row.maps, rating: row.rating / row.maps,
      agents: Object.entries(row.agents).sort((a, b) => b[1] - a[1]),
    })).sort((a, b) => b.rating - a.rating || b.acs - a.acs || b.maps - a.maps);
  }

  return { roles, userId, offers, create, sidesFor, play, advance, standings };
})();
