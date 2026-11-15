from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_file(
    arguments: dict,
    file_root: str | Path | None = None,
    max_bytes: int | None = None,
) -> dict:
    path_value = arguments.get("path")
    content = arguments.get("content")
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError("write_file requires a non-empty path")
    if not isinstance(content, str):
        raise ValueError("write_file requires string content")

    root = Path(file_root or os.getenv("MCP_FILE_ROOT", "/var/lib/a2a-mcp/files")).resolve()
    candidate = (root / path_value).resolve()
    _ensure_inside_root(candidate, root)

    limit = max_bytes
    if limit is None:
        try:
            limit = int(os.getenv("MCP_FILE_WRITER_MAX_BYTES", "65536"))
        except ValueError as exc:
            raise ValueError("MCP_FILE_WRITER_MAX_BYTES must be an integer") from exc
    if limit < 1:
        raise ValueError("MCP_FILE_WRITER_MAX_BYTES must be positive")

    encoded = content.encode("utf-8")
    if len(encoded) > limit:
        raise ValueError(f"content exceeds the {limit}-byte limit")

    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate = (root / path_value).resolve()
    _ensure_inside_root(candidate, root)
    if candidate.exists() and candidate.is_dir():
        raise ValueError("path resolves to a directory")

    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=candidate.parent, prefix=f".{candidate.name}.", delete=False
        ) as temporary:
            temporary_path = temporary.name
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
        # The reader fixture may run as a different container user. Keep the
        # generated fixture readable while retaining owner-only write access.
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, candidate)
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass

    relative_path = candidate.relative_to(root).as_posix()
    return {"content": [{"type": "text", "text": f"wrote {relative_path} ({len(encoded)} bytes)"}]}


def _ensure_inside_root(candidate: Path, root: Path) -> None:
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("path must stay inside the configured file root") from exc
