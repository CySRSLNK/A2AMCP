from pathlib import Path

import pytest

from services.mcp_fixtures.app.server import handle_message


def request(path: str, *, file_root: Path) -> dict:
    return handle_message(
        "file-tools",
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "read_file", "arguments": {"path": path}},
        },
        file_root=file_root,
    )


def test_file_reader_lists_only_read_file(tmp_path: Path):
    response = handle_message(
        "file-tools",
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        file_root=tmp_path,
    )

    assert [tool["name"] for tool in response["result"]["tools"]] == ["read_file"]


def test_file_reader_returns_content_from_allowed_root(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("untrusted fixture content", encoding="utf-8")

    response = request("notes.txt", file_root=tmp_path)

    assert response["result"]["content"][0]["text"] == "untrusted fixture content"


@pytest.mark.parametrize("path", ["../notes.txt", "/etc/passwd", "missing.txt"])
def test_file_reader_rejects_paths_outside_root_or_missing_files(tmp_path: Path, path: str):
    (tmp_path / "notes.txt").write_text("safe", encoding="utf-8")

    response = request(path, file_root=tmp_path)

    assert response["error"]["code"] == -32602


def test_file_reader_rejects_directories_and_oversized_files(tmp_path: Path, monkeypatch):
    (tmp_path / "folder").mkdir()
    (tmp_path / "large.txt").write_text("123456789", encoding="utf-8")
    monkeypatch.setenv("MCP_FILE_MAX_BYTES", "8")

    directory_response = request("folder", file_root=tmp_path)
    large_response = request("large.txt", file_root=tmp_path)

    assert directory_response["error"]["code"] == -32602
    assert large_response["error"]["code"] == -32602
