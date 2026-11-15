from pathlib import Path
from stat import S_IMODE

from services.mcp_fixtures.app.server import handle_message


def test_file_writer_lists_write_file():
    response = handle_message("file-writer", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert response["result"]["tools"] == [
        {
            "name": "write_file",
            "description": "Write UTF-8 text to the isolated MCP file fixture.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        }
    ]


def test_file_writer_writes_utf8_and_returns_result_metadata(tmp_path: Path):
    response = handle_message(
        "file-writer",
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "write_file",
                "arguments": {"path": "nested/result.txt", "content": "你好，实验室"},
            },
        },
        file_root=str(tmp_path),
    )

    assert response["result"]["content"][0]["text"] == "wrote nested/result.txt (18 bytes)"
    assert (tmp_path / "nested/result.txt").read_text(encoding="utf-8") == "你好，实验室"
    assert S_IMODE((tmp_path / "nested/result.txt").stat().st_mode) == 0o644


def test_file_writer_rejects_missing_arguments(tmp_path: Path):
    response = handle_message(
        "file-writer",
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "write_file", "arguments": {"path": "result.txt"}},
        },
        file_root=str(tmp_path),
    )

    assert response["error"]["code"] == -32602
    assert "content" in response["error"]["message"]


def test_file_writer_rejects_path_escape_and_absolute_path(tmp_path: Path):
    for path in ("../escape.txt", str(tmp_path.parent / "escape.txt")):
        response = handle_message(
            "file-writer",
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "write_file",
                    "arguments": {"path": path, "content": "blocked"},
                },
            },
            file_root=str(tmp_path),
        )

        assert response["error"]["code"] == -32602
        assert "inside the configured file root" in response["error"]["message"]


def test_file_writer_rejects_directories_and_oversized_content(tmp_path: Path):
    (tmp_path / "folder").mkdir()
    directory_response = handle_message(
        "file-writer",
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "write_file",
                "arguments": {"path": "folder", "content": "blocked"},
            },
        },
        file_root=str(tmp_path),
    )
    oversized_response = handle_message(
        "file-writer",
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "write_file",
                "arguments": {"path": "too-large.txt", "content": "ééé"},
            },
        },
        file_root=str(tmp_path),
        max_bytes=5,
    )

    assert directory_response["error"]["code"] == -32602
    assert "directory" in directory_response["error"]["message"]
    assert oversized_response["error"]["code"] == -32602
    assert "5-byte limit" in oversized_response["error"]["message"]
    assert not (tmp_path / "too-large.txt").exists()


def test_file_writer_rejects_symlink_escape(tmp_path: Path):
    outside = tmp_path.parent / "writer-outside"
    outside.mkdir()
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)

    response = handle_message(
        "file-writer",
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "write_file",
                "arguments": {"path": "linked/escape.txt", "content": "blocked"},
            },
        },
        file_root=str(tmp_path),
    )

    assert response["error"]["code"] == -32602
    assert not (outside / "escape.txt").exists()
