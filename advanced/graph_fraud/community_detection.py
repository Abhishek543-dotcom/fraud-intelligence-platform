"""Community detection for identifying fraud rings in transaction graphs."""

from __future__ import annotations

from collections import defaultdict

import networkx as nx
import structlog

logger = structlog.get_logger(__name__)


class FraudCommunityDetector:
    """Detect tightly connected communities in transaction graphs.

    Uses the Louvain algorithm for community detection, then scores
    each community by its internal fraud rate to identify potential
    fraud rings.
    """

    def __init__(self, graph: nx.DiGraph) -> None:
        """Initialize with a directed transaction graph.

        Args:
            graph: NetworkX DiGraph from TransactionGraphBuilder.
        """
        self._directed = graph
        # Louvain works on undirected graphs
        self._undirected = graph.to_undirected()

    def detect_communities(self, resolution: float = 1.0) -> dict[int, list[str]]:
        """Run Louvain community detection.

        Args:
            resolution: Louvain resolution parameter. Higher values
                produce more, smaller communities.

        Returns:
            Dict mapping community_id to list of node IDs.
        """
        if self._undirected.number_of_nodes() == 0:
            return {}

        communities = nx.community.louvain_communities(
            self._undirected, resolution=resolution, seed=42
        )

        result: dict[int, list[str]] = {}
        for idx, community in enumerate(communities):
            result[idx] = sorted(community)

        logger.info("communities_detected",
                     total=len(result),
                     avg_size=sum(len(v) for v in result.values()) / max(len(result), 1))
        return result

    def score_communities(
        self,
        communities: dict[int, list[str]],
        fraud_labels: dict[str, bool],
        min_size: int = 3,
    ) -> list[dict]:
        """Score communities by their internal fraud rate.

        Args:
            communities: Output from detect_communities().
            fraud_labels: Dict mapping transaction_id to is_fraud bool.
            min_size: Minimum community size to consider.

        Returns:
            Sorted list of community dicts with fraud scores.
        """
        scored = []

        for community_id, members in communities.items():
            if len(members) < min_size:
                continue

            # Count fraud edges within this community
            subgraph = self._directed.subgraph(members)
            total_txns = 0
            fraud_txns = 0

            for u, v, data in subgraph.edges(data=True):
                for txn in data.get("transactions", []):
                    txn_id = txn.get("transaction_id", "")
                    total_txns += 1
                    if fraud_labels.get(txn_id, False):
                        fraud_txns += 1

            fraud_rate = fraud_txns / max(total_txns, 1)
            internal_edges = subgraph.number_of_edges()
            density = nx.density(subgraph) if subgraph.number_of_nodes() > 1 else 0

            # Total money flow within community
            total_flow = sum(
                data.get("total_amount", 0)
                for _, _, data in subgraph.edges(data=True)
            )

            scored.append({
                "community_id": community_id,
                "size": len(members),
                "members": members,
                "internal_edges": internal_edges,
                "density": round(density, 4),
                "total_transactions": total_txns,
                "fraud_transactions": fraud_txns,
                "fraud_rate": round(fraud_rate, 4),
                "total_flow": round(total_flow, 2),
                "risk_score": round(fraud_rate * density * len(members), 4),
            })

        scored.sort(key=lambda x: x["risk_score"], reverse=True)
        logger.info("communities_scored",
                     total=len(scored),
                     high_risk=sum(1 for s in scored if s["fraud_rate"] > 0.1))
        return scored

    def get_suspicious_communities(
        self,
        fraud_labels: dict[str, bool],
        fraud_rate_threshold: float = 0.1,
        min_size: int = 3,
    ) -> list[dict]:
        """Convenience method: detect communities and return suspicious ones.

        Args:
            fraud_labels: Dict mapping transaction_id to is_fraud.
            fraud_rate_threshold: Minimum fraud rate to flag.
            min_size: Minimum community size.

        Returns:
            List of suspicious communities above the fraud rate threshold.
        """
        communities = self.detect_communities()
        scored = self.score_communities(communities, fraud_labels, min_size)
        return [c for c in scored if c["fraud_rate"] >= fraud_rate_threshold]
