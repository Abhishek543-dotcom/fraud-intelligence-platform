"""Build transaction graphs from financial data for fraud analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import networkx as nx
import structlog

logger = structlog.get_logger(__name__)


class TransactionGraphBuilder:
    """Build directed graphs of money flows between accounts.

    Nodes represent customer accounts. Edges represent transactions
    weighted by amount, with timestamps. Identifies structural
    patterns indicative of fraud: cycles, high-degree nodes (mules),
    and anomalous flow patterns.
    """

    def __init__(self) -> None:
        self._graph = nx.DiGraph()

    @property
    def graph(self) -> nx.DiGraph:
        return self._graph

    def add_transaction(
        self,
        sender_id: str,
        receiver_id: str,
        amount: float,
        timestamp: datetime,
        transaction_id: str = "",
        metadata: Optional[dict] = None,
    ) -> None:
        """Add a transaction edge to the graph.

        Args:
            sender_id: Source customer/account ID.
            receiver_id: Destination customer/account ID.
            amount: Transaction amount.
            timestamp: When the transaction occurred.
            transaction_id: Unique transaction identifier.
            metadata: Additional edge metadata.
        """
        if not self._graph.has_node(sender_id):
            self._graph.add_node(sender_id, total_out=0.0, total_in=0.0, tx_count=0)
        if not self._graph.has_node(receiver_id):
            self._graph.add_node(receiver_id, total_out=0.0, total_in=0.0, tx_count=0)

        self._graph.nodes[sender_id]["total_out"] += amount
        self._graph.nodes[sender_id]["tx_count"] += 1
        self._graph.nodes[receiver_id]["total_in"] += amount

        edge_data = {
            "amount": amount,
            "timestamp": timestamp.isoformat(),
            "transaction_id": transaction_id,
            **(metadata or {}),
        }

        if self._graph.has_edge(sender_id, receiver_id):
            existing = self._graph[sender_id][receiver_id]
            existing.setdefault("transactions", []).append(edge_data)
            existing["total_amount"] = existing.get("total_amount", 0) + amount
            existing["count"] = existing.get("count", 0) + 1
        else:
            self._graph.add_edge(
                sender_id, receiver_id,
                transactions=[edge_data],
                total_amount=amount,
                count=1,
            )

    def build_from_dataframe(self, df) -> None:
        """Build graph from a pandas or Spark DataFrame.

        Expects columns: customer_id (sender), merchant_id (receiver),
        amount, timestamp, transaction_id.
        """
        for _, row in df.iterrows():
            self.add_transaction(
                sender_id=row["customer_id"],
                receiver_id=row["merchant_id"],
                amount=float(row["amount"]),
                timestamp=row["timestamp"] if isinstance(row["timestamp"], datetime) else datetime.fromisoformat(str(row["timestamp"])),
                transaction_id=str(row.get("transaction_id", "")),
            )
        logger.info("graph_built", nodes=self._graph.number_of_nodes(), edges=self._graph.number_of_edges())

    def detect_cycles(self, max_length: int = 5) -> list[list[str]]:
        """Find cycles in the transaction graph (circular money movement).

        Args:
            max_length: Maximum cycle length to search for.

        Returns:
            List of cycles (each cycle is a list of node IDs).
        """
        cycles = []
        try:
            for cycle in nx.simple_cycles(self._graph, length_bound=max_length):
                cycles.append(cycle)
        except Exception:
            # Fallback for older NetworkX versions
            all_cycles = list(nx.simple_cycles(self._graph))
            cycles = [c for c in all_cycles if len(c) <= max_length]

        logger.info("cycles_detected", count=len(cycles))
        return cycles

    def find_high_degree_nodes(self, threshold: int = 10) -> list[dict]:
        """Identify high-degree nodes (potential money mules).

        Money mules receive from many sources and send to few destinations.

        Args:
            threshold: Minimum in-degree to flag a node.

        Returns:
            List of dicts with node info and degree metrics.
        """
        suspects = []
        for node in self._graph.nodes():
            in_deg = self._graph.in_degree(node)
            out_deg = self._graph.out_degree(node)

            if in_deg >= threshold:
                node_data = self._graph.nodes[node]
                suspects.append({
                    "node_id": node,
                    "in_degree": in_deg,
                    "out_degree": out_deg,
                    "total_in": node_data.get("total_in", 0),
                    "total_out": node_data.get("total_out", 0),
                    "in_out_ratio": in_deg / max(out_deg, 1),
                    "mule_score": min(1.0, (in_deg / threshold) * (1 - out_deg / max(in_deg, 1))),
                })

        suspects.sort(key=lambda x: x["mule_score"], reverse=True)
        logger.info("high_degree_nodes", count=len(suspects), threshold=threshold)
        return suspects

    def get_summary(self) -> dict:
        """Return graph summary statistics."""
        return {
            "nodes": self._graph.number_of_nodes(),
            "edges": self._graph.number_of_edges(),
            "density": nx.density(self._graph),
            "is_weakly_connected": nx.is_weakly_connected(self._graph) if self._graph.number_of_nodes() > 0 else False,
            "avg_in_degree": sum(d for _, d in self._graph.in_degree()) / max(self._graph.number_of_nodes(), 1),
            "avg_out_degree": sum(d for _, d in self._graph.out_degree()) / max(self._graph.number_of_nodes(), 1),
        }
