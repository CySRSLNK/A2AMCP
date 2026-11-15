from __future__ import annotations

from pathlib import Path

import hashlib


class BlobStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, body: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(body).hexdigest()
        relative = Path(digest[:2]) / digest[2:]
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(body)
        return digest, str(relative)

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def delete(self, key: str) -> None:
        target = self.root / key
        if target.exists():
            target.unlink()
