from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_attack_catalog_file_exists_and_has_expected_protocol_paths():
    document = yaml.safe_load((ROOT / "scenarios" / "attack-catalog.yaml").read_text())

    assert document["version"] == 1
    assert {case["protocol_path"] for case in document["cases"]} == {"cross-mcp", "a2a-mcp"}
    assert all(case["safe_fixture"] == "local-only" for case in document["cases"])


def test_list_attacks_script_uses_read_only_api():
    script = (ROOT / "scripts" / "list-attacks.sh").read_text()

    assert "/api/v1/attacks" in script
    assert "-X POST" not in script
    assert "/api/v1/runs" not in script

