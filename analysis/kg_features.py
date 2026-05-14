"""Per-person feature extraction from the KG.

Produces one row per Person node with the graph-derived features
listed in `COMPREHENSIVE_PLAN.md §4.5`:

  - degree_centrality   (Person-Signal-Topic-Platform combined)
  - clustering_coeff    (clustering of the Person's 1-hop ego network)
  - topic_diversity     (Shannon entropy over the Person's topic distribution)
  - n_topics            (count of distinct topics the Person touches)
  - n_signals           (count of signals expressed)
  - n_platforms         (count of distinct platforms used)
  - bip_triad           ("build-in-public" triad — Person → SignalEvent → Topic
                         where the Topic node has ≥1 other Person also touching it)
  - mean_signal_strength average overall_signal_strength across the Person's signals

Writes `data/processed/kg_features.parquet`.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import networkx as nx
import pandas as pd

from analysis.build_graph import load_graph

logger = logging.getLogger(__name__)

_OUT_DEFAULT = Path("data/processed/kg_features.parquet")


def _shannon_entropy(counts: list[int]) -> float:
    total = sum(counts)
    if total == 0:
        return 0.0
    h = 0.0
    for c in counts:
        if c <= 0:
            continue
        p = c / total
        h -= p * math.log(p, 2)
    return h


def _person_topic_distribution(g: nx.MultiDiGraph, person_node: str) -> dict[str, int]:
    """Topic-frequency distribution for one Person, via Person->Signal->Topic."""
    counts: dict[str, int] = {}
    for _, signal in g.out_edges(person_node):
        for _, topic in g.out_edges(signal):
            if g.nodes[topic].get("kind") != "Topic":
                continue
            counts[topic] = counts.get(topic, 0) + 1
    return counts


def _bip_triad_count(g: nx.MultiDiGraph, person_node: str) -> int:
    """How many of this Person's topics have ≥1 OTHER Person also touching them?"""
    my_topics: set[str] = set()
    for _, signal in g.out_edges(person_node):
        for _, topic in g.out_edges(signal):
            if g.nodes[topic].get("kind") == "Topic":
                my_topics.add(topic)
    shared = 0
    for topic in my_topics:
        # Predecessors of a topic are SignalEvents; their predecessors are Persons.
        people_on_topic: set[str] = set()
        for signal, _ in g.in_edges(topic):
            for p, _ in g.in_edges(signal):
                if g.nodes[p].get("kind") == "Person":
                    people_on_topic.add(p)
        if len(people_on_topic) > 1:
            shared += 1
    return shared


def _person_signals(g: nx.MultiDiGraph, person_node: str) -> list[str]:
    return [s for _, s in g.out_edges(person_node) if g.nodes[s].get("kind") == "SignalEvent"]


def _person_platforms(g: nx.MultiDiGraph, person_node: str) -> set[str]:
    out: set[str] = set()
    for signal in _person_signals(g, person_node):
        for _, plat in g.out_edges(signal):
            if g.nodes[plat].get("kind") == "Platform":
                out.add(plat)
    return out


def _clustering_for_person(g: nx.MultiDiGraph, person_node: str) -> float:
    """Local clustering coefficient on the undirected projection of the ego graph."""
    # NetworkX clustering for MultiDiGraph isn't directly defined; cast to simple Graph.
    neighbours = set()
    for _, n in g.out_edges(person_node):
        neighbours.add(n)
    for n, _ in g.in_edges(person_node):
        neighbours.add(n)
    if len(neighbours) < 2:
        return 0.0
    ego_nodes = {person_node, *neighbours}
    sub = nx.Graph(g.subgraph(ego_nodes))
    if person_node not in sub:
        return 0.0
    return float(nx.clustering(sub, person_node))


def compute_person_features(g: nx.MultiDiGraph) -> pd.DataFrame:
    """One row per Person node, with graph-derived features."""
    rows = []
    persons = [n for n, d in g.nodes(data=True) if d.get("kind") == "Person"]

    # Pre-compute degree centrality on the full graph (cast to simple DiGraph).
    simple = nx.DiGraph()
    for u, v in g.edges():
        simple.add_edge(u, v)
    if simple.number_of_nodes() > 0:
        deg_cen = nx.degree_centrality(simple)
    else:
        deg_cen = {}

    for p in persons:
        signals = _person_signals(g, p)
        platforms = _person_platforms(g, p)
        topic_counts = _person_topic_distribution(g, p)
        n_signals = len(signals)
        n_topics = len(topic_counts)
        topic_div = _shannon_entropy(list(topic_counts.values()))
        bip = _bip_triad_count(g, p)
        # Mean signal strength.
        if signals:
            strengths = [
                float(g.nodes[s].get("overall_signal_strength", 0.0) or 0.0) for s in signals
            ]
            mean_strength = sum(strengths) / len(strengths) if strengths else 0.0
        else:
            mean_strength = 0.0
        rows.append(
            {
                "person_id": g.nodes[p].get("person_id", p.removeprefix("Person:")),
                "degree_centrality": float(deg_cen.get(p, 0.0)),
                "clustering_coeff": _clustering_for_person(g, p),
                "topic_diversity": topic_div,
                "n_topics": n_topics,
                "n_signals": n_signals,
                "n_platforms": len(platforms),
                "bip_triad": bip,
                "mean_signal_strength": mean_strength,
            }
        )
    return pd.DataFrame(rows)


def extract_and_save(
    pickle_path: Path | None = None,
    out_path: Path = _OUT_DEFAULT,
    graph: nx.MultiDiGraph | None = None,
) -> Path:
    g = graph if graph is not None else load_graph(pickle_path) if pickle_path else load_graph()
    df = compute_person_features(g)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"kg_features | {len(df)} persons | written to {out_path}")
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    extract_and_save()
