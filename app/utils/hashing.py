from __future__ import annotations

import hashlib


def fingerprint(*parts: str) -> str:
    """Deterministic sha256 fingerprint for deduplication. None-safe."""
    raw = "\x1f".join((p or "").strip().lower() for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
