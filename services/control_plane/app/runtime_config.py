from __future__ import annotations

import ipaddress
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

from .models import (
    ConfigAuditRecord,
    RunConfigSnapshotRecord,
    RunRecord,
    RuntimeConfigRecord,
)


_CONFIG_ID = "active"
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "instance-data.ec2.internal",
}


def validate_endpoint(value: str, *, allow_empty: bool = False) -> str:
    value = value.strip()
    if not value and allow_empty:
        return value
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"}:
        raise ValueError("endpoint must use http or https")
    if parts.username or parts.password:
        raise ValueError("endpoint must not contain credentials")
    if not parts.hostname or parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise ValueError("endpoint must be an origin URL without path or query")
    host = parts.hostname.lower().rstrip(".")
    if host in _BLOCKED_HOSTS or host.endswith(".internal"):
        raise ValueError("endpoint targets a sensitive network")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise ValueError("endpoint targets a sensitive network")
    return value.rstrip("/")


class ModelRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["mock", "openai-compatible"] = "mock"
    model_name: str = Field(default="lab-agent", min_length=1, max_length=128)
    base_url: str = ""
    request_timeout: float = Field(default=120, ge=5, le=600)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return validate_endpoint(value, allow_empty=True)

    @model_validator(mode="after")
    def require_base_url_for_remote_provider(self) -> "ModelRuntimeConfig":
        if self.provider == "openai-compatible" and not self.base_url:
            raise ValueError("openai-compatible provider requires base_url")
        return self


class AgentRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_hop: int = Field(default=8, ge=0, le=64)
    allowed_targets: list[str] = Field(default_factory=list)
    allowed_mcp_servers: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)


class McpServerRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=2, max_length=64)
    endpoint: str
    enabled: bool = True
    capabilities: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    revision: int = Field(default=1, ge=1)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("server id must use lowercase letters, digits, and hyphens")
        return value

    @field_validator("endpoint")
    @classmethod
    def validate_server_endpoint(cls, value: str) -> str:
        return validate_endpoint(value)


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1)
    model: ModelRuntimeConfig = Field(default_factory=ModelRuntimeConfig)
    agents: dict[str, AgentRuntimeConfig] = Field(default_factory=dict)
    mcp_servers: list[McpServerRuntimeConfig] = Field(default_factory=list)
    a2a_request_timeout: float = Field(default=300, ge=5, le=900)
    mcp_request_timeout: float = Field(default=60, ge=5, le=600)
    run_request_timeout: float = Field(default=600, ge=5, le=1800)

    @model_validator(mode="after")
    def validate_unique_servers(self) -> "RuntimeConfig":
        ids = [server.id for server in self.mcp_servers]
        if len(ids) != len(set(ids)):
            raise ValueError("MCP server ids must be unique")
        return self


def _csv_env(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def build_default_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        model=ModelRuntimeConfig(
            provider=os.getenv("MODEL_PROVIDER", "mock"),
            model_name=os.getenv("MODEL_NAME", "lab-agent"),
            base_url=os.getenv("MODEL_BASE_URL", ""),
            request_timeout=float(os.getenv("MODEL_REQUEST_TIMEOUT", "120")),
        ),
        agents={
            "root-agent": AgentRuntimeConfig(
                max_hop=int(os.getenv("ROOT_AGENT_MAX_HOP", "8")),
                allowed_targets=_csv_env("ROOT_AGENT_ALLOWED_TARGETS", "worker-agent"),
                allowed_mcp_servers=_csv_env(
                    "ROOT_AGENT_ALLOWED_MCP_SERVERS", "mcp-tools,mcp-resources,mcp-file-reader"
                ),
                allowed_tools=_csv_env("ROOT_AGENT_ALLOWED_TOOLS"),
            ),
            "worker-agent": AgentRuntimeConfig(
                max_hop=int(os.getenv("WORKER_AGENT_MAX_HOP", "8")),
                allowed_targets=_csv_env("WORKER_AGENT_ALLOWED_TARGETS", "worker-agent"),
                allowed_mcp_servers=_csv_env(
                    "WORKER_AGENT_ALLOWED_MCP_SERVERS", "mcp-tools,mcp-resources,mcp-file-reader"
                ),
                allowed_tools=_csv_env(
                    "WORKER_AGENT_ALLOWED_TOOLS", "calculator,fixture_http_get,read_file"
                ),
            ),
        },
        mcp_servers=[
            McpServerRuntimeConfig(
                id="mcp-tools",
                endpoint=os.getenv("MCP_TOOLS_URL", "http://mcp-tools:8200"),
                capabilities=["tools/list", "tools/call"],
                allowed_tools=["calculator", "fixture_http_get"],
            ),
            McpServerRuntimeConfig(
                id="mcp-resources",
                endpoint=os.getenv("MCP_RESOURCES_URL", "http://mcp-resources:8200"),
                capabilities=["resources/read"],
                allowed_tools=[],
            ),
            McpServerRuntimeConfig(
                id="mcp-file-reader",
                endpoint=os.getenv("MCP_FILE_READER_URL", "http://mcp-file-reader:8200"),
                capabilities=["tools/list", "tools/call"],
                allowed_tools=["read_file"],
            ),
        ],
        a2a_request_timeout=float(os.getenv("A2A_REQUEST_TIMEOUT", "300")),
        mcp_request_timeout=float(os.getenv("MCP_REQUEST_TIMEOUT", "60")),
        run_request_timeout=float(os.getenv("RUN_REQUEST_TIMEOUT", "600")),
    )


class RuntimeConfigStore:
    def __init__(self, event_store) -> None:
        self._session_factory = event_store._session_factory
        self._ensure_active()

    @staticmethod
    def _fernet() -> Fernet | None:
        raw = os.getenv("CONFIG_ENCRYPTION_KEY", "").strip()
        if not raw:
            return None
        try:
            return Fernet(raw.encode())
        except Exception as exc:
            raise RuntimeError("CONFIG_ENCRYPTION_KEY must be a valid Fernet key") from exc

    def _ensure_active(self) -> None:
        with self._session_factory.begin() as session:
            row = session.get(RuntimeConfigRecord, _CONFIG_ID)
            if row is not None:
                self._migrate_builtin_mcp(session, row)
                return
            config = build_default_runtime_config()
            api_key = os.getenv("MODEL_API_KEY", "")
            encrypted = self._encrypt(api_key) if api_key and self._fernet() is not None else None
            session.add(
                RuntimeConfigRecord(
                    id=_CONFIG_ID,
                    version=config.version,
                    document=config.model_dump(mode="json"),
                    encrypted_api_key=encrypted,
                )
            )

    def _migrate_builtin_mcp(self, session, row: RuntimeConfigRecord) -> None:
        """Add newly shipped fixture MCPs without widening custom policies unexpectedly."""
        document = deepcopy(row.document)
        document["version"] = row.version
        current = RuntimeConfig.model_validate(document)
        defaults = build_default_runtime_config()
        existing_ids = {server.id for server in current.mcp_servers}
        additions = [server for server in defaults.mcp_servers if server.id not in existing_ids]
        if not additions:
            return

        agents = dict(current.agents)
        for agent_id, default_agent in defaults.agents.items():
            agent = agents.get(agent_id)
            if agent is None:
                continue
            if agent.allowed_mcp_servers == ["mcp-tools", "mcp-resources"]:
                agents[agent_id] = agent.model_copy(
                    update={"allowed_mcp_servers": [*agent.allowed_mcp_servers, "mcp-file-reader"]}
                )
            if agent_id == "worker-agent" and agent.allowed_tools == ["calculator", "fixture_http_get"]:
                agents[agent_id] = agents[agent_id].model_copy(
                    update={"allowed_tools": [*agent.allowed_tools, "read_file"]}
                )

        migrated = current.model_copy(
            update={"mcp_servers": [*current.mcp_servers, *additions], "agents": agents}
        )
        new_version = row.version + 1
        row.version = new_version
        row.document = migrated.model_copy(update={"version": new_version}).model_dump(mode="json")
        row.document.pop("version", None)
        row.updated_at = datetime.now(timezone.utc)
        session.add(
            ConfigAuditRecord(
                id=str(uuid4()),
                version=new_version,
                action="migration",
                changed_fields=["agents", "mcp_servers"],
                api_key_set=row.encrypted_api_key is not None,
            )
        )

    def get_active(self) -> RuntimeConfig:
        with self._session_factory() as session:
            row = session.get(RuntimeConfigRecord, _CONFIG_ID)
            if row is None:
                raise RuntimeError("active runtime configuration is missing")
            document = deepcopy(row.document)
            document["version"] = row.version
            return RuntimeConfig.model_validate(document)

    def get_full_active(self) -> tuple[RuntimeConfig, str | None]:
        with self._session_factory() as session:
            row = session.get(RuntimeConfigRecord, _CONFIG_ID)
            if row is None:
                raise RuntimeError("active runtime configuration is missing")
            document = deepcopy(row.document)
            document["version"] = row.version
            return RuntimeConfig.model_validate(document), self._decrypt(row.encrypted_api_key)

    def public(self) -> dict[str, Any]:
        config, api_key = self.get_full_active()
        result = config.model_dump(mode="json")
        result["model"]["api_key_set"] = bool(api_key)
        result["model"]["api_key_masked"] = "********" if api_key else ""
        return result

    def replace_active(
        self,
        config: RuntimeConfig,
        *,
        api_key_action: Literal["preserve", "replace", "clear"] = "preserve",
        api_key: str | None = None,
        expected_version: int | None = None,
    ) -> RuntimeConfig:
        if api_key_action not in {"preserve", "replace", "clear"}:
            raise ValueError("api_key_action must be preserve, replace, or clear")
        with self._session_factory.begin() as session:
            row = session.get(RuntimeConfigRecord, _CONFIG_ID)
            if row is None:
                raise RuntimeError("active runtime configuration is missing")
            if expected_version is not None and row.version != expected_version:
                raise ValueError("expected_version does not match active configuration")
            current_key = row.encrypted_api_key
            if api_key_action == "replace":
                if not api_key:
                    raise ValueError("api_key is required when api_key_action is replace")
                current_key = self._encrypt(api_key)
            elif api_key_action == "clear":
                current_key = None
            new_version = row.version + 1
            document = config.model_copy(update={"version": new_version}).model_dump(mode="json")
            document.pop("version", None)
            changed = sorted(_changed_fields(row.document, document))
            row.version = new_version
            row.document = document
            row.encrypted_api_key = current_key
            row.updated_at = datetime.now(timezone.utc)
            session.add(
                ConfigAuditRecord(
                    id=str(uuid4()),
                    version=new_version,
                    action="update",
                    changed_fields=changed,
                    api_key_set=current_key is not None,
                )
            )
            return config.model_copy(update={"version": new_version})

    def create_run_with_snapshot(
        self,
        run_id: str,
        *,
        scenario_id: str | None,
        prompt: str | None,
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        with self._session_factory.begin() as session:
            config_row = session.get(RuntimeConfigRecord, _CONFIG_ID)
            if config_row is None:
                raise RuntimeError("active runtime configuration is missing")
            if session.get(RunRecord, run_id) is not None:
                raise ValueError("run already exists")
            snapshot_document = deepcopy(config_row.document)
            snapshot_document["version"] = config_row.version
            snapshot_document["policy"] = deepcopy(policy)
            session.add(RunRecord(id=run_id, scenario_id=scenario_id, status="queued", prompt=prompt))
            session.flush()
            session.add(
                RunConfigSnapshotRecord(
                    run_id=run_id,
                    config_version=config_row.version,
                    document=snapshot_document,
                    encrypted_api_key=config_row.encrypted_api_key,
                )
            )
            return {
                "id": run_id,
                "scenario_id": scenario_id,
                "status": "queued",
                "prompt": prompt,
                "runtime_config_version": config_row.version,
            }

    def get_snapshot(self, run_id: str, *, include_secret: bool = False) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.get(RunConfigSnapshotRecord, run_id)
            if row is None:
                return None
            result = deepcopy(row.document)
            result["config_version"] = row.config_version
            if include_secret:
                result["api_key"] = self._decrypt(row.encrypted_api_key)
            return result

    def projection(self, run_id: str) -> dict[str, Any] | None:
        result = self.get_snapshot(run_id)
        if result is None:
            return None
        result.pop("api_key", None)
        return result

    def clone_snapshot(self, source_run_id: str, replay_run_id: str) -> None:
        with self._session_factory.begin() as session:
            source = session.get(RunConfigSnapshotRecord, source_run_id)
            if source is None:
                raise ValueError("source run has no runtime configuration snapshot")
            destination = session.get(RunConfigSnapshotRecord, replay_run_id)
            if destination is None:
                session.add(
                    RunConfigSnapshotRecord(
                        run_id=replay_run_id,
                        config_version=source.config_version,
                        document=deepcopy(source.document),
                        encrypted_api_key=source.encrypted_api_key,
                    )
                )
            else:
                destination.config_version = source.config_version
                destination.document = deepcopy(source.document)
                destination.encrypted_api_key = source.encrypted_api_key

    def create_replay_run_with_snapshot(
        self,
        replay_run_id: str,
        source_run_id: str,
        *,
        scenario_id: str | None,
        prompt: str | None,
    ) -> dict[str, Any]:
        with self._session_factory.begin() as session:
            source = session.get(RunConfigSnapshotRecord, source_run_id)
            if source is None:
                raise ValueError("source run has no runtime configuration snapshot")
            if session.get(RunRecord, replay_run_id) is not None:
                raise ValueError("run already exists")
            session.add(RunRecord(id=replay_run_id, scenario_id=scenario_id, status="queued", prompt=prompt))
            session.flush()
            session.add(
                RunConfigSnapshotRecord(
                    run_id=replay_run_id,
                    config_version=source.config_version,
                    document=deepcopy(source.document),
                    encrypted_api_key=source.encrypted_api_key,
                )
            )
            return {
                "id": replay_run_id,
                "scenario_id": scenario_id,
                "status": "queued",
                "prompt": prompt,
                "runtime_config_version": source.config_version,
            }

    def _encrypt(self, value: str) -> str:
        fernet = self._fernet()
        if fernet is None:
            raise ValueError("CONFIG_ENCRYPTION_KEY is required to store an API key")
        return fernet.encrypt(value.encode()).decode()

    def _decrypt(self, value: str | None) -> str | None:
        if not value:
            return None
        fernet = self._fernet()
        if fernet is None:
            raise RuntimeError("CONFIG_ENCRYPTION_KEY is required to read the stored API key")
        try:
            return fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("stored API key cannot be decrypted with CONFIG_ENCRYPTION_KEY") from exc


def _changed_fields(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    keys = set(before) | set(after)
    return {key for key in keys if before.get(key) != after.get(key)}
