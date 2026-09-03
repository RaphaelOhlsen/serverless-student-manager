from __future__ import annotations

import json
import sys
from collections.abc import Iterable


def select_targets(paths: Iterable[str]) -> list[str]:
    selected: set[str] = set()
    for path in paths:
        normalized = path.strip()
        if normalized.startswith("backend/students-api/"):
            selected.add("students-api")
        elif normalized.startswith("backend/users-api/"):
            selected.add("users-api")
    return sorted(selected)


def main() -> None:
    targets = select_targets(sys.stdin)
    if not targets:
        raise SystemExit("No releasable API change was detected.")
    print(json.dumps({"api": targets}, separators=(",", ":")))


if __name__ == "__main__":
    main()
