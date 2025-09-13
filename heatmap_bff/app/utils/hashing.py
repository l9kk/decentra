from __future__ import annotations

import hashlib
from typing import Iterable


def stable_key(parts: Iterable[str | int | float | None]) -> str:
    joined = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(joined.encode()).hexdigest()  # nosec - not security critical
