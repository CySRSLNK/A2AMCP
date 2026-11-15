import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/migrate_fixtures.py"


def migrate(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
    )


def test_migration_preserves_existing_files_and_removes_legacy_directories(tmp_path):
    root = tmp_path / "fixtures"
    reader = root / "file-reader"
    writer = root / "file-writer"
    reader.mkdir(parents=True)
    writer.mkdir()
    (reader / "example.txt").write_bytes(b"original fixture\n")
    (reader / ".hidden.txt").write_bytes(b"hidden fixture\n")
    (writer / "result.txt").write_bytes(b"48")
    (writer / "result.txt").chmod(0o644)
    (writer / "nested").mkdir()
    (writer / "nested/output.txt").write_bytes(b"nested output")
    (writer / ".gitkeep").touch()
    (root / "existing.txt").write_bytes(b"keep me")

    result = migrate(root)

    assert result.returncode == 0, result.stderr
    assert (root / "example.txt").read_bytes() == b"original fixture\n"
    assert (root / ".hidden.txt").read_bytes() == b"hidden fixture\n"
    assert (root / "result.txt").read_bytes() == b"48"
    assert (root / "result.txt").stat().st_mode & 0o777 == 0o644
    assert (root / "nested/output.txt").read_bytes() == b"nested output"
    assert (root / "existing.txt").read_bytes() == b"keep me"
    assert not reader.exists()
    assert not writer.exists()
    assert not (root / ".gitkeep").exists()
    assert migrate(root).returncode == 0


@pytest.mark.parametrize("conflict_location", ["root", "other-legacy", "root-directory"])
def test_migration_stops_before_moving_any_files_on_name_conflicts(tmp_path, conflict_location):
    root = tmp_path / "fixtures"
    reader = root / "file-reader"
    writer = root / "file-writer"
    reader.mkdir(parents=True)
    writer.mkdir()
    (reader / "example.txt").write_bytes(b"keep original")
    (writer / "result.txt").write_bytes(b"48")
    if conflict_location == "root":
        destination = root / "result.txt"
        destination.write_bytes(b"root result")
    elif conflict_location == "other-legacy":
        destination = reader / "result.txt"
        destination.write_bytes(b"reader result")
    else:
        destination = root / "result.txt"
        destination.mkdir()

    result = migrate(root)

    assert result.returncode != 0
    assert "conflict" in result.stderr.lower()
    assert (reader / "example.txt").read_bytes() == b"keep original"
    assert (writer / "result.txt").read_bytes() == b"48"
    assert not (root / "example.txt").exists()
    assert destination.exists()
    if destination.is_file():
        assert destination.read_bytes() == (b"reader result" if conflict_location == "other-legacy" else b"root result")


def test_migration_rejects_a_symlinked_legacy_directory(tmp_path):
    root = tmp_path / "fixtures"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "result.txt").write_bytes(b"preserve outside")
    (root / "file-writer").symlink_to(outside, target_is_directory=True)

    result = migrate(root)

    assert result.returncode != 0
    assert "symlink" in result.stderr.lower()
    assert (outside / "result.txt").read_bytes() == b"preserve outside"
    assert (root / "file-writer").is_symlink()


def test_generated_outputs_are_ignored_but_fixture_examples_are_trackable():
    paths = ["fixtures/result.txt", "fixtures/nested/output.txt", "fixtures/example.txt", "fixtures/email.txt"]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        cwd=ROOT,
        input="\n".join(paths) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert set(result.stdout.splitlines()) == {"fixtures/result.txt", "fixtures/nested/output.txt"}
