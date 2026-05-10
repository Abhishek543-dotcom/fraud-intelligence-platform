"""Nessie REST catalog configuration for Iceberg lakehouse."""

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

NESSIE_URI = os.getenv("NESSIE_URI", "http://nessie:19120/api/v1")


def get_nessie_default_branch() -> str:
    """Get the default branch name from Nessie server."""
    try:
        resp = requests.get(f"{NESSIE_URI}/trees", timeout=10)
        resp.raise_for_status()
        trees = resp.json()
        for ref in trees.get("references", []):
            if ref.get("type") == "BRANCH" and ref.get("name") == "main":
                return ref["name"]
        return "main"
    except requests.RequestException as e:
        logger.warning("Could not fetch Nessie default branch: %s. Using 'main'.", e)
        return "main"


def create_branch(branch_name: str, from_ref: str = "main") -> dict:
    """Create a new branch in the Nessie catalog.

    Args:
        branch_name: Name of the new branch.
        from_ref: Source branch to fork from.

    Returns:
        Branch metadata dict from Nessie.
    """
    source_resp = requests.get(f"{NESSIE_URI}/trees/tree/{from_ref}", timeout=10)
    source_resp.raise_for_status()
    source_hash = source_resp.json().get("hash")

    payload = {
        "type": "BRANCH",
        "name": branch_name,
        "hash": source_hash,
    }
    resp = requests.post(f"{NESSIE_URI}/trees/tree", json=payload, timeout=10)
    resp.raise_for_status()
    result = resp.json()
    logger.info("Created branch '%s' from '%s' at hash %s", branch_name, from_ref, source_hash)
    return result


def delete_branch(branch_name: str) -> None:
    """Delete a branch from the Nessie catalog."""
    ref_resp = requests.get(f"{NESSIE_URI}/trees/tree/{branch_name}", timeout=10)
    ref_resp.raise_for_status()
    ref_hash = ref_resp.json().get("hash")

    resp = requests.delete(
        f"{NESSIE_URI}/trees/tree/{branch_name}",
        headers={"If-Match": f'"{ref_hash}"'},
        timeout=10,
    )
    resp.raise_for_status()
    logger.info("Deleted branch '%s'", branch_name)


def list_branches() -> list[dict]:
    """List all branches in the Nessie catalog."""
    resp = requests.get(f"{NESSIE_URI}/trees", timeout=10)
    resp.raise_for_status()
    return resp.json().get("references", [])


def list_tables(ref: str = "main") -> list[dict]:
    """List all tables visible on a given Nessie ref.

    Args:
        ref: Branch or tag name.

    Returns:
        List of content key entries.
    """
    resp = requests.get(f"{NESSIE_URI}/trees/tree/{ref}/entries", timeout=10)
    resp.raise_for_status()
    entries = resp.json().get("entries", [])
    tables = [e for e in entries if e.get("type") == "ICEBERG_TABLE"]
    logger.info("Found %d tables on ref '%s'", len(tables), ref)
    return tables


def get_table_content(ref: str, namespace: str, table: str) -> Optional[dict]:
    """Get content metadata for a specific table.

    Args:
        ref: Branch or tag name.
        namespace: Namespace (e.g., 'bronze').
        table: Table name.

    Returns:
        Table content dict or None.
    """
    key = f"{namespace}.{table}"
    resp = requests.get(
        f"{NESSIE_URI}/contents/{key}",
        params={"ref": ref},
        timeout=10,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()
