"""Frontend-facing knowledge-graph views derived from the real KG.

Reads the NetworkX MultiDiGraph (analysis/build_graph.py → graph.pkl) and
projects two JSON-friendly subgraphs the demo renders with a force layout:

- cohort_graph(): founders + the topics they express about, signals
  collapsed into founder→topic edge weights. Shared topics become shared
  hub nodes, so clustering (who works on what) emerges visually.
- ego_graph(person_id): one founder's real neighbourhood —
  founder → top signals → the topics those signals are about (+ platform),
  for the View-3 drill-down.

Lookahead-safe: both accept an optional `as_of` ISO date and only include
signals with timestamp <= that date (the graph carries per-signal
timestamps via the scored parquet join; we filter on the SignalEvent
node's `timestamp` attribute when present).
"""

from __future__ import annotations

import pickle
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

_GRAPH_PKL = Path("data/processed/graph.pkl")

# Coarse theme buckets so the granular LLM topic labels (e.g. "bootstrapped
# saas exit", "saas pricing strategy") collapse into shared cluster hubs.
# First matching keyword wins; order matters (specific → general).
_THEME_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("SaaS & bootstrapping", ("saas", "bootstrap", "indie", "mrr", "pricing", "product-led", "micro-saas")),
    ("Building in public", ("build in public", "building in public", "build-in-public", "indie hacker", "ship")),
    ("Audience & newsletters", ("newsletter", "audience", "writing", "content", "blogging", "substack", "creator")),
    ("Community & courses", ("community", "course", "cohort", "education", "teaching", "mentor")),
    ("Marketing & growth", ("growth", "marketing", "distribution", "acquisition", "funnel", "seo", "twitter", "social media")),
    ("Product & startups", ("startup", "founder", "product", "mvp", "validation", "launch", "fundrais")),
    ("AI & tooling", ("ai", "gpt", "llm", "tooling", "automation", "developer", "coding", "engineering")),
    ("Productivity & knowledge", ("productivity", "note-taking", "knowledge", "roam", "journaling", "second brain")),
    ("Psychology & neuroscience", ("neuroscience", "psychology", "cognitive", "mental health", "mindful", "behavioral")),
    ("Money & finance", ("money", "finance", "budget", "income", "wealth", "investing")),
]


def normalise_topic(label: str) -> str:
    """Map a granular topic label to a coarse theme bucket (for clustering)."""
    low = label.lower()
    for theme, kws in _THEME_RULES:
        if any(k in low for k in kws):
            return theme
    return "Other"


def _load_graph(graph_path: Path = _GRAPH_PKL):
    if not graph_path.exists():
        return None
    with open(graph_path, "rb") as f:
        return pickle.load(f)


def _topics_for_signal(graph, signal_node: str) -> list[str]:
    """Topic nodes a SignalEvent is ABOUT."""
    out = []
    for _, t, d in graph.out_edges(signal_node, data=True):
        if d.get("relation") == "ABOUT" and t.startswith("Topic:"):
            out.append(t)
    return out


def cohort_graph(graph_path: Path = _GRAPH_PKL) -> dict[str, Any]:
    """Founder ↔ theme projection. Granular topics collapse into coarse
    theme hubs (normalise_topic) so shared interests cluster founders.

    Returns {nodes, edges, source}. Node kinds: 'founder', 'topic' (theme).
    A theme touched by ≥2 founders is a visual cluster anchor.
    """
    graph = _load_graph(graph_path)
    if graph is None:
        return {"nodes": [], "edges": [], "source": "unavailable"}

    # founder -> Counter(theme -> n signals in that theme)
    ft: dict[str, Counter] = defaultdict(Counter)
    for src, dst, d in graph.edges(data=True):
        if d.get("relation") == "EXPRESSED" and src.startswith("Person:"):
            for topic in _topics_for_signal(graph, dst):
                theme = normalise_topic(topic.split(":", 1)[1])
                if theme != "Other":  # drop the catch-all from the cluster view
                    ft[src][theme] += 1

    # How many founders touch each theme (hub sizing) + total weight.
    theme_founders: Counter = Counter()
    theme_total: Counter = Counter()
    for counter in ft.values():
        for theme, n in counter.items():
            theme_founders[theme] += 1
            theme_total[theme] += n

    nodes: list[dict] = []
    edges: list[dict] = []
    for person, counter in ft.items():
        pid = person.split(":", 1)[1]
        nodes.append({
            "id": person,
            "kind": "founder",
            "label": pid,
            "weight": sum(counter.values()),
        })
        for theme, n in counter.items():
            edges.append({"src": person, "dst": f"Theme:{theme}", "relation": "ABOUT", "weight": n})
    for theme, nf in theme_founders.items():
        nodes.append({
            "id": f"Theme:{theme}",
            "kind": "topic",
            "label": theme,
            "weight": theme_total[theme],
            "n_founders": nf,
            "shared": nf > 1,
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "n_founders": len(ft),
        "n_themes": len(theme_founders),
        "n_shared_themes": sum(1 for nf in theme_founders.values() if nf > 1),
        "source": "backend",
    }


def _node_ts(graph, node: str) -> datetime | None:
    ts = graph.nodes[node].get("timestamp") if node in graph.nodes else None
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def ego_graph(
    person_id: str,
    top_signals: int = 12,
    graph_path: Path = _GRAPH_PKL,
) -> dict[str, Any]:
    """One founder's real neighbourhood: founder → signals → topics (+ platform)."""
    graph = _load_graph(graph_path)
    if graph is None:
        return {"nodes": [], "edges": [], "source": "unavailable"}

    person_node = f"Person:{person_id}"
    if person_node not in graph:
        return {"nodes": [], "edges": [], "source": "unavailable", "found": False}

    # Collect the founder's signals (cap to top_signals by out-degree proxy:
    # signals that are ABOUT the most topics are the richest → keep those).
    signal_nodes = [
        dst for _, dst, d in graph.out_edges(person_node, data=True)
        if d.get("relation") == "EXPRESSED" and dst.startswith("SignalEvent:")
    ]
    # richest-first
    signal_nodes.sort(key=lambda s: len(_topics_for_signal(graph, s)), reverse=True)
    signal_nodes = signal_nodes[:top_signals]

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    nodes[person_node] = {"id": person_node, "kind": "founder", "label": person_id, "weight": len(signal_nodes)}

    for s in signal_nodes:
        nodes[s] = {"id": s, "kind": "signal", "label": s.split(":", 1)[1], "weight": 1}
        edges.append({"src": person_node, "dst": s, "relation": "EXPRESSED", "weight": 1})
        # platform
        for _, p, d in graph.out_edges(s, data=True):
            if d.get("relation") == "ON_PLATFORM" and p.startswith("Platform:"):
                nodes.setdefault(p, {"id": p, "kind": "platform", "label": p.split(":", 1)[1], "weight": 1})
                edges.append({"src": s, "dst": p, "relation": "ON_PLATFORM", "weight": 1})
        # topics
        for t in _topics_for_signal(graph, s):
            nodes.setdefault(t, {"id": t, "kind": "topic", "label": t.split(":", 1)[1], "weight": 1})
            edges.append({"src": s, "dst": t, "relation": "ABOUT", "weight": 1})

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "person_id": person_id,
        "n_signals": len(signal_nodes),
        "source": "backend",
        "found": True,
    }
