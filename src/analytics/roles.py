import json
from collections import Counter
from functools import lru_cache
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parents[2] / "vct_images" / "agents" / "catalog.json"


def agent_profile(picks):
    catalog = agent_catalog()
    counts = Counter(
        "".join(char for char in pick.casefold() if char.isalnum())
        for pick in (picks or ()) if pick
    )
    roles = Counter()
    agents = []
    for key, maps in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])):
        entry = catalog.get(key)
        if entry:
            roles[entry["role"]] += maps
            agents.append({**entry, "maps": maps})
        else:
            agents.append({"name": key, "maps": maps})
    classified = sum(roles.values())
    role = None
    if classified >= 5:
        top = roles.most_common(2)
        role = top[0][0]
        if len(top) == 2 and top[0][1] / classified < 0.6 and top[1][1] / classified >= 0.25:
            role = "Flex"
    return {"role": role, "role_maps": dict(roles), "top_agents": agents[:3]}


@lru_cache(maxsize=1)
def agent_catalog():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
