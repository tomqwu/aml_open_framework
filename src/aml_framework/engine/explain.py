"""Network-pattern alert explainability.

The `network_pattern` rule type emits alerts whose `subgraph` field
carries the actual matched subgraph (added by the engine in PR #49):
nodes with hop distance, undirected edges with linking attribute,
and a `topology_hash` for clustering identical-shape detections.

This module reads that payload and renders it for human review:
  - `explain_network_alert(alert)` → ExplainPayload (dataclass)
  - `to_mermaid(explain_payload)`  → Mermaid graph string the
                                     dashboard can drop into
                                     `st.markdown` or st.code(...,
                                     language="mermaid").

Pure functions only — no IO, no DuckDB. Designed to run from any
context that has the alert dict in hand (dashboard page, narrative
drafter, audit replay).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExplainNode:
    id: str
    hops: int


@dataclass(frozen=True)
class ExplainEdge:
    source: str
    target: str
    attribute: str = ""
    weight: float = 1.0


@dataclass(frozen=True)
class ExplainPayload:
    """Structured view of one network-pattern match.

    Returned by `explain_network_alert`. Attributes:
      - seed:           the customer the rule fired on
      - pattern:        e.g. "component_size", "common_counterparty"
      - max_hops:       the rule's max_hops parameter
      - nodes/edges:    the matched subgraph
      - topology_hash:  SHA-256 over canonical edge list (cluster key)
      - summary:        one-line human description
    """

    seed: str
    pattern: str
    max_hops: int
    nodes: list[ExplainNode] = field(default_factory=list)
    edges: list[ExplainEdge] = field(default_factory=list)
    topology_hash: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "pattern": self.pattern,
            "max_hops": self.max_hops,
            "topology_hash": self.topology_hash,
            "summary": self.summary,
            "nodes": [{"id": n.id, "hops": n.hops} for n in self.nodes],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "attribute": e.attribute,
                    "weight": e.weight,
                }
                for e in self.edges
            ],
        }


class NotANetworkAlert(ValueError):
    """Raised when the alert has no `subgraph` field — caller should fall
    back to its non-graph explanation path (eg. python_ref feature
    attribution, aggregation_window threshold inspection)."""


def explain_network_alert(alert: dict[str, Any]) -> ExplainPayload:
    """Build an ExplainPayload from a network_pattern alert dict.

    Raises NotANetworkAlert if the alert isn't a network_pattern fire.
    """
    sub = alert.get("subgraph")
    if not isinstance(sub, dict) or "nodes" not in sub:
        raise NotANetworkAlert(f"alert has no 'subgraph' payload (rule {alert.get('rule_id')!r})")

    seed = sub.get("seed") or alert.get("customer_id", "")
    nodes = [ExplainNode(id=n["id"], hops=int(n.get("hops", 0))) for n in sub.get("nodes", [])]
    edges = [
        ExplainEdge(
            source=e["source"],
            target=e["target"],
            attribute=e.get("attribute", ""),
            weight=float(e.get("weight", 1.0)),
        )
        for e in sub.get("edges", [])
    ]
    pattern = alert.get("pattern", "component_size")
    max_hops = int(sub.get("max_hops", alert.get("max_hops", 2)))
    topology_hash = sub.get("topology_hash", "")

    summary = _build_summary(alert, nodes, edges, pattern)

    return ExplainPayload(
        seed=seed,
        pattern=pattern,
        max_hops=max_hops,
        nodes=nodes,
        edges=edges,
        topology_hash=topology_hash,
        summary=summary,
    )


def _build_summary(
    alert: dict[str, Any],
    nodes: list[ExplainNode],
    edges: list[ExplainEdge],
    pattern: str,
) -> str:
    """Compose the human-readable one-liner explaining the match."""
    component_size = alert.get("component_size", len(nodes))
    counterparty_count = alert.get("counterparty_count", max(len(nodes) - 1, 0))
    edge_attrs: dict[str, int] = {}
    for e in edges:
        attr = e.attribute or "?"
        edge_attrs[attr] = edge_attrs.get(attr, 0) + 1
    attr_breakdown = ", ".join(f"{attr}×{count}" for attr, count in sorted(edge_attrs.items()))
    base = (
        f"Pattern '{pattern}' fired on customer {alert.get('customer_id', '?')}: "
        f"{component_size} entity(ies) reachable within "
        f"{alert.get('max_hops', '?')} hop(s), "
        f"{counterparty_count} unique counterpart(ies)."
    )
    if attr_breakdown:
        base += f" Linking attributes: {attr_breakdown}."
    return base


def to_mermaid(explain: ExplainPayload, *, max_render_nodes: int = 50) -> str:
    """Render an ExplainPayload as a Mermaid graph block.

    The dashboard drops this into `st.code(..., language="mermaid")` or
    a Mermaid renderer for the analyst review queue. Caps node count at
    `max_render_nodes` to keep huge subgraphs from freezing the page —
    the topology hash and summary still describe the full match.
    """
    if not explain.nodes:
        return 'graph TD\n  empty["(no subgraph)"]'

    lines = ["graph TD"]
    nodes_to_render = explain.nodes[:max_render_nodes]
    rendered_ids = {n.id for n in nodes_to_render}

    # Node declarations — distinguish the seed visually.
    for n in nodes_to_render:
        label = f"{n.id}\\n(hops={n.hops})"
        if n.id == explain.seed:
            lines.append(f'  {_safe(n.id)}(["{label}"]):::seed')
        else:
            lines.append(f'  {_safe(n.id)}["{label}"]')

    # Edge declarations (only edges where both endpoints are rendered).
    for e in explain.edges:
        if e.source not in rendered_ids or e.target not in rendered_ids:
            continue
        attr = f"|{e.attribute}|" if e.attribute else ""
        lines.append(f"  {_safe(e.source)} ---{attr} {_safe(e.target)}")

    if len(explain.nodes) > max_render_nodes:
        lines.append(
            f'  more["… {len(explain.nodes) - max_render_nodes} more node(s) '
            f'(see topology_hash {explain.topology_hash[:12]}…)"]'
        )

    lines.append("  classDef seed fill:#ffd54f,stroke:#f57c00,stroke-width:2px;")
    return "\n".join(lines)


def _safe(node_id: str) -> str:
    """Mermaid identifiers must be alphanumeric/underscore. Escape others."""
    return "".join(ch if ch.isalnum() else "_" for ch in str(node_id))
