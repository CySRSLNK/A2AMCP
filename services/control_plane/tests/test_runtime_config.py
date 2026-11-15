from pathlib import Path

import pytest

from services.control_plane.app.events import EventStore
from services.control_plane.app.runtime_config import (
    RuntimeConfig,
    RuntimeConfigStore,
    build_default_runtime_config,
)


def test_runtime_config_store_masks_and_preserves_api_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CONFIG_ENCRYPTION_KEY", "2" * 43 + "=")
    store = RuntimeConfigStore(EventStore(f"sqlite:///{tmp_path / 'config.db'}"))
    config = build_default_runtime_config()

    saved = store.replace_active(
        config,
        api_key_action="replace",
        api_key="secret-one",
        expected_version=1,
    )
    public = store.public()
    assert public["version"] == saved.version
    assert public["model"]["api_key_set"] is True
    assert public["model"]["api_key_masked"] == "********"
    assert "secret-one" not in str(public)

    store.replace_active(
        config.model_copy(update={"model": config.model.model_copy(update={"model_name": "next"})}),
        api_key_action="preserve",
        api_key=None,
        expected_version=saved.version,
    )
    assert store.get_full_active()[1] == "secret-one"


def test_runtime_config_store_rejects_stale_version_and_unsafe_endpoint(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CONFIG_ENCRYPTION_KEY", "2" * 43 + "=")
    store = RuntimeConfigStore(EventStore(f"sqlite:///{tmp_path / 'config.db'}"))
    config = build_default_runtime_config()
    with pytest.raises(ValueError, match="expected_version"):
        store.replace_active(config, api_key_action="preserve", api_key=None, expected_version=99)

    with pytest.raises(ValueError, match="sensitive network"):
        RuntimeConfig.model_validate(
            {
                **config.model_dump(mode="json"),
                "mcp_servers": [
                    {
                        "id": "bad",
                        "endpoint": "http://127.0.0.1:9000",
                        "capabilities": ["tools/call"],
                        "allowed_tools": ["calculator"],
                    }
                ],
            }
        )


def test_snapshot_is_immutable_and_never_contains_plaintext_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CONFIG_ENCRYPTION_KEY", "2" * 43 + "=")
    event_store = EventStore(f"sqlite:///{tmp_path / 'config.db'}")
    store = RuntimeConfigStore(event_store)
    config = store.get_active()
    saved = store.replace_active(config, api_key_action="replace", api_key="snapshot-key", expected_version=1)
    run_id = "00000000-0000-0000-0000-000000000001"
    store.create_run_with_snapshot(run_id, scenario_id=None, prompt="hello", policy={})
    store.replace_active(
        config.model_copy(update={"model": config.model.model_copy(update={"model_name": "changed"})}),
        api_key_action="clear",
        api_key=None,
        expected_version=saved.version,
    )
    snapshot = store.get_snapshot(run_id, include_secret=True)
    assert snapshot["model"]["model_name"] == config.model.model_name
    assert snapshot["api_key"] == "snapshot-key"
    assert "snapshot-key" not in str(store.public())
