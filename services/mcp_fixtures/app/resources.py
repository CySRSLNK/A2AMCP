from __future__ import annotations


def read_resource(uri: str) -> dict:
    if uri != "fixture://notes/security":
        raise ValueError("resource is not available in this fixture")
    return {
        "contents": [
            {
                "uri": uri,
                "mimeType": "text/plain",
                "text": "Use this fixture to test resource provenance and prompt injection handling.",
            }
        ]
    }
