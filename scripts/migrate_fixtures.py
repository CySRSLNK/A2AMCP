#!/usr/bin/env python3
"""Move legacy fixture directories into the shared root without overwriting data."""

from __future__ import annotations

import argparse
from pathlib import Path


def migrate_fixtures(root: Path) -> int:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    occupied = {entry.name for entry in root.iterdir()}
    moves: list[tuple[Path, Path]] = []
    placeholders: list[Path] = []
    legacy_directories: list[Path] = []

    # Validate the entire move before changing either legacy directory.
    for name in ("file-reader", "file-writer"):
        legacy = root / name
        if legacy.is_symlink():
            raise ValueError(f"legacy fixture directory must not be a symlink: {legacy}")
        if not legacy.exists():
            continue
        if not legacy.is_dir():
            raise ValueError(f"legacy fixture path must be a directory: {legacy}")
        legacy_directories.append(legacy)
        for source in sorted(legacy.iterdir()):
            if (
                source.name == ".gitkeep"
                and not source.is_symlink()
                and source.is_file()
                and source.stat().st_size == 0
            ):
                placeholders.append(source)
                continue
            if source.name in occupied:
                raise ValueError(f"fixture name conflict: {source.name}; rename one file before retrying")
            occupied.add(source.name)
            moves.append((source, root / source.name))

    for source, destination in moves:
        source.rename(destination)
    for placeholder in placeholders:
        placeholder.unlink()
    for legacy in legacy_directories:
        legacy.rmdir()
    return len(moves)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "fixtures")
    args = parser.parse_args()
    try:
        moved = migrate_fixtures(args.root)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Fixture migration failed: {exc}\n")
    print(f"Migrated {moved} entries into {args.root}")
