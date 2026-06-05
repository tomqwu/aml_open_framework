"""Deterministic mule-ring / dense-community builder over an identity graph (#498).

Offline analyzer over an undirected identity-link edge list (e.g. shared
device, shared address, shared beneficiary). Finds connected components
that are large *and* dense enough to look like a mule ring — a cluster of
accounts that coordinate to move funds — so an investigator gets a
community lens instead of a flat pile of pairwise links.

Design rules (mirror ``engine/equivalence_clustering.py``):

* **Pure / deterministic.** No I/O, no clock reads, no random state.
  Same edge list -> identical ``MuleRingReport`` regardless of input
  order. Union-find iterates edges in sorted order and roots resolve to
  the min id; ring ids are content hashes of the sorted member list.
* **Stdlib + pydantic only.** No sklearn/numpy/networkx — ``hashlib``
  for stable ids, plain dict-based union-find for components. The
  framework's determinism contract and the ``.[dev]``-only unit CI (no
  heavy deps) both forbid those libraries here.
* **OFFLINE + advisory.** This never runs in the engine path and is not
  hashed into the audit ledger. It is a triage community lens, not an
  auto-decision: density is a heuristic prioritization signal.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MuleRing(_Base):
    """One dense account community flagged as a candidate mule ring."""

    ring_id: str
    members: list[str]
    size: int
    internal_edges: int
    density: float
    label: str


class MuleRingReport(_Base):
    """Dense-community report over an identity-link edge list."""

    rings: list[MuleRing]
    n_entities: int
    n_rings: int


def _find(parent: dict[str, str], node: str) -> str:
    """Union-find root with path compression."""
    root = node
    while parent[root] != root:
        root = parent[root]
    # Path compression keeps lookups flat without affecting determinism.
    while parent[node] != root:
        parent[node], node = root, parent[node]
    return root


def _union(parent: dict[str, str], a: str, b: str) -> None:
    ra, rb = _find(parent, a), _find(parent, b)
    if ra == rb:
        return
    # Always attach the larger id under the smaller so the root is the min id
    # of the component — deterministic, independent of union order.
    hi, lo = (ra, rb) if ra > rb else (rb, ra)
    parent[hi] = lo


def detect_mule_rings(
    edges: list[tuple[str, str]],
    *,
    min_ring_size: int = 3,
    min_density: float = 0.5,
) -> MuleRingReport:
    """Find large, dense communities in an undirected identity-link graph.

    Edges are normalised to undirected, deduped pairs; self-loops are
    ignored. Connected components are found via union-find; a component is
    a ring iff ``size >= min_ring_size`` and ``density >= min_density``,
    where ``density = internal_edges / (size * (size - 1) / 2)``. Rings are
    sorted by ``(-size, ring_id)``.
    """
    # 1. Normalise: dedupe undirected pairs, drop self-loops, collect nodes.
    pairs: set[tuple[str, str]] = set()
    nodes: set[str] = set()
    for a, b in edges:
        nodes.add(a)
        nodes.add(b)
        if a == b:
            continue
        pairs.add((a, b) if a <= b else (b, a))

    # 2. Union-find over the nodes; iterate edges in sorted order.
    parent: dict[str, str] = {n: n for n in nodes}
    for a, b in sorted(pairs):
        _union(parent, a, b)

    # 3. Group nodes by root → components.
    components: dict[str, list[str]] = {}
    for n in nodes:
        components.setdefault(_find(parent, n), []).append(n)

    # Count internal edges per component root (both endpoints share a root).
    edge_counts: dict[str, int] = {}
    for a, b in pairs:
        edge_counts[_find(parent, a)] = edge_counts.get(_find(parent, a), 0) + 1

    rings: list[MuleRing] = []
    for root, comp_nodes in components.items():
        members = sorted(comp_nodes)
        size = len(members)
        internal_edges = edge_counts.get(root, 0)
        max_edges = size * (size - 1) // 2
        density = internal_edges / max_edges if max_edges > 0 else 0.0
        # 4. Ring iff large enough and dense enough.
        if size < min_ring_size or density < min_density:
            continue
        # 5. Content-addressed id + human label.
        ring_id = "MR-" + hashlib.sha256(",".join(members).encode()).hexdigest()[:10]
        density = round(density, 4)
        label = f"{size}-account ring · {internal_edges} links · density {density:.2f}"
        rings.append(
            MuleRing(
                ring_id=ring_id,
                members=members,
                size=size,
                internal_edges=internal_edges,
                density=density,
                label=label,
            )
        )

    # 6. Sort by size desc, then ring_id for stability.
    rings.sort(key=lambda r: (-r.size, r.ring_id))

    return MuleRingReport(rings=rings, n_entities=len(nodes), n_rings=len(rings))
