"""Knowledge-graph construction from scored signals.

Builds an in-memory NetworkX MultiDiGraph following the schema in
`COMPREHENSIVE_PLAN.md §4.5`:

  Nodes
    - Person      (one per person_id in scored_signals.parquet)
    - SignalEvent (one per row)
    - Topic       (one per distinct LLM-assigned s6_topic_label)
    - Platform    (twitter / hackernews / reddit / youtube / producthunt)

  Edges
    - (Person) -EXPRESSED-> (SignalEvent)
    - (SignalEvent) -ABOUT-> (Topic)         (only when topic_label is non-empty)
    - (SignalEvent) -ON_PLATFORM-> (Platform)
    - (Topic) -CO_OCCURS_WITH-> (Topic)      (derived: same Person produces both)

The graph is serialised to GraphML so Gephi / Cytoscape can open it for
the thesis figures, and to pickle for fast load by downstream feature
extraction.

The (Person)-[OUTCOME]->(OutcomeLabel) edge and the optional
(Person)-[FOLLOWS]->(Person) edge are constructed only if a labels
file / follow-graph file is provided. The cohort is positive-only by
construction, so OutcomeLabel is rarely useful inside the KG — it
lives on the per-person feature row in `kg_features.py` instead.
"""

from __future__ import annotations

import logging
import pickle
from collections import defaultdict
from pathlib import Path

import networkx as nx
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

_SCORED_DEFAULT = Path("data/processed/scored_signals.parquet")
_GRAPHML_DEFAULT = Path("data/processed/graph.graphml")
_PICKLE_DEFAULT = Path("data/processed/graph.pkl")


def _node_id(kind: str, name: str) -> str:
    return f"{kind}:{name}"


def build_graph(
    scored_path: Path = _SCORED_DEFAULT,
    follows_edges: list[tuple[str, str]] | None = None,
) -> nx.MultiDiGraph:
    """Materialise the KG from scored_signals.parquet.

    `follows_edges` is an optional list of (follower_person_id,
    followee_person_id) tuples for the (Person)-[FOLLOWS]->(Person)
    edge. Pass None to skip.
    """
    g = nx.MultiDiGraph()
    if not scored_path.exists():
        logger.warning("no scored signals at %s — returning empty graph", scored_path)
        return g

    table = pq.read_table(scored_path)
    rows = table.to_pylist()
    if not rows:
        return g

    # Track (person, topic) pairs for the CO_OCCURS_WITH derivation.
    topics_per_person: dict[str, set[str]] = defaultdict(set)

    for r in rows:
        person = r["person_id"]
        signal = r["signal_id"]
        platform = r["platform"]
        topic = (r.get("s6_topic_label") or "").strip().lower()
        strength = r.get("overall_signal_strength") or 0.0

        person_node = _node_id("Person", person)
        signal_node = _node_id("SignalEvent", signal)
        platform_node = _node_id("Platform", platform)

        if not g.has_node(person_node):
            g.add_node(person_node, kind="Person", person_id=person)
        if not g.has_node(platform_node):
            g.add_node(platform_node, kind="Platform", platform=platform)
        g.add_node(
            signal_node,
            kind="SignalEvent",
            timestamp=str(r["timestamp"]),
            overall_signal_strength=float(strength),
            prompt_version=r.get("prompt_version", "v1"),
        )

        g.add_edge(person_node, signal_node, relation="EXPRESSED")
        g.add_edge(signal_node, platform_node, relation="ON_PLATFORM")

        if topic:
            topic_node = _node_id("Topic", topic)
            if not g.has_node(topic_node):
                g.add_node(topic_node, kind="Topic", label=topic)
            g.add_edge(signal_node, topic_node, relation="ABOUT")
            topics_per_person[person].add(topic)

    # Derive (Topic)-CO_OCCURS_WITH-(Topic) — both directions counted once.
    for topics in topics_per_person.values():
        tlist = sorted(topics)
        for i in range(len(tlist)):
            for j in range(i + 1, len(tlist)):
                a, b = _node_id("Topic", tlist[i]), _node_id("Topic", tlist[j])
                # Accumulate weight = number of persons in which both topics co-occur.
                if g.has_edge(a, b):
                    # MultiDiGraph: increment weight on the first existing edge key.
                    for attrs in g[a][b].values():
                        attrs["weight"] = attrs.get("weight", 1) + 1
                        break
                else:
                    g.add_edge(a, b, relation="CO_OCCURS_WITH", weight=1)

    # Optional follow edges.
    if follows_edges:
        for src, dst in follows_edges:
            s = _node_id("Person", src)
            d = _node_id("Person", dst)
            if g.has_node(s) and g.has_node(d):
                g.add_edge(s, d, relation="FOLLOWS")

    logger.info(
        "kg built | nodes=%d edges=%d persons=%d signals=%d topics=%d",
        g.number_of_nodes(),
        g.number_of_edges(),
        sum(1 for _, d in g.nodes(data=True) if d.get("kind") == "Person"),
        sum(1 for _, d in g.nodes(data=True) if d.get("kind") == "SignalEvent"),
        sum(1 for _, d in g.nodes(data=True) if d.get("kind") == "Topic"),
    )
    return g


def save_graph(
    g: nx.MultiDiGraph,
    graphml_path: Path = _GRAPHML_DEFAULT,
    pickle_path: Path = _PICKLE_DEFAULT,
) -> tuple[Path, Path]:
    """Serialise to GraphML (for Gephi) and pickle (for fast reload)."""
    graphml_path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(g, graphml_path)
    with pickle_path.open("wb") as f:
        pickle.dump(g, f)
    print(
        f"kg | nodes={g.number_of_nodes()} edges={g.number_of_edges()} | "
        f"graphml={graphml_path} pickle={pickle_path}"
    )
    return graphml_path, pickle_path


def load_graph(pickle_path: Path = _PICKLE_DEFAULT) -> nx.MultiDiGraph:
    with pickle_path.open("rb") as f:
        return pickle.load(f)


def build_and_save(
    scored_path: Path = _SCORED_DEFAULT,
    graphml_path: Path = _GRAPHML_DEFAULT,
    pickle_path: Path = _PICKLE_DEFAULT,
    follows_edges: list[tuple[str, str]] | None = None,
) -> tuple[Path, Path]:
    g = build_graph(scored_path, follows_edges=follows_edges)
    return save_graph(g, graphml_path, pickle_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build_and_save()
