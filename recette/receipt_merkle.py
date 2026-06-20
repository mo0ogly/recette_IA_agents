"""Merkle inclusion proofs over context receipts -- selective disclosure.

The hash chain (``recette/context_receipt.py``) proves the whole SEQUENCE is
intact but forces revealing every receipt to verify any one. A Merkle tree over
the receipt leaves yields a single ``root`` that commits to the whole batch AND
lets a holder prove that ONE specific receipt is included -- by disclosing only
that receipt plus a short audit path, never the others. This is selective
disclosure: an auditor receives the signed root, and to attest "this exact side
effect crossed the boundary" you hand them the single leaf + its path, not the
batch.

Content-free (the leaf hashes a receipt that already carries no body) and
deterministic (I4): SHA-256, fixed pairing (duplicate the last node on an odd
level), no clock, no randomness. Domain separation follows RFC 6962 -- leaves are
hashed with a ``0x00`` prefix and internal nodes with ``0x01`` -- so a leaf digest
can never be reinterpreted as an internal node (second-preimage resistance).
"""

from __future__ import annotations

import hashlib
import json

_LEAF_PREFIX = b"\x00"
_NODE_PREFIX = b"\x01"


def _canonical(body: dict) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def leaf_hash(receipt: dict) -> str:
    """SHA-256 (RFC 6962 leaf prefix) of one receipt's canonical body, EXCLUDING
    ``prev_hash``/``hash``. Computable from the receipt ALONE -- so a single
    receipt can be disclosed and proven without revealing the others."""
    body = {k: v for k, v in receipt.items() if k not in ("prev_hash", "hash")}
    return hashlib.sha256(_LEAF_PREFIX + _canonical(body)).hexdigest()


def _node_hash(left: str, right: str) -> str:
    return hashlib.sha256(_NODE_PREFIX + bytes.fromhex(left) + bytes.fromhex(right)).hexdigest()


def merkle_root(receipts: list[dict]) -> str:
    """Root committing to every receipt. Empty list -> ``""`` (no commitment)."""
    if not receipts:
        return ""
    level = [leaf_hash(r) for r in receipts]
    while len(level) > 1:
        level = [
            _node_hash(level[i], level[i + 1] if i + 1 < len(level) else level[i])
            for i in range(0, len(level), 2)
        ]
    return level[0]


def inclusion_proof(receipts: list[dict], index: int) -> dict:
    """Audit path proving ``receipts[index]`` is committed under the root.

    Returns ``{leaf, index, count, root, path}`` where ``path`` is a list of
    ``{sibling, side}`` steps (``side`` is the SIBLING's side: ``left``/``right``)
    bottom-up. Raises ``IndexError`` for an out-of-range index. Pure (I4)."""
    n = len(receipts)
    if index < 0 or index >= n:
        raise IndexError(f"index {index} out of range for {n} receipts")
    level = [leaf_hash(r) for r in receipts]
    leaf = level[index]
    path: list[dict] = []
    idx = index
    while len(level) > 1:
        if idx % 2 == 0:
            sib = level[idx + 1] if idx + 1 < len(level) else level[idx]
            path.append({"sibling": sib, "side": "right"})
        else:
            path.append({"sibling": level[idx - 1], "side": "left"})
        level = [
            _node_hash(level[i], level[i + 1] if i + 1 < len(level) else level[i])
            for i in range(0, len(level), 2)
        ]
        idx //= 2
    return {"leaf": leaf, "index": index, "count": n, "root": level[0], "path": path}


def verify_inclusion(leaf: str, path: list[dict], root: str) -> bool:
    """Fold ``leaf`` with its audit ``path``; true iff it reconstructs ``root``.

    Pure, content-free, off-platform: a verifier needs only the disclosed leaf,
    the path, and the (signed) root -- never the other receipts."""
    h = leaf
    for step in path:
        sib = step.get("sibling", "")
        if step.get("side") == "left":
            h = _node_hash(sib, h)
        else:
            h = _node_hash(h, sib)
    return bool(root) and h == root
