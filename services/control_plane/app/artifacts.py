from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import BinaryIO
from uuid import UUID, uuid4

from .blobs import BlobStore


class CrossTaskAccessError(PermissionError):
    pass


@dataclass(frozen=True)
class ArtifactRef:
    id: str
    run_id: str
    task_id: str | None
    media_type: str
    size: int
    sha256: str
    inline: bool
    inline_body: str | None = None
    blob_key: str | None = None


@dataclass(frozen=True)
class DestroyReport:
    run_id: str
    deleted_events: int
    deleted_artifacts: int
    deleted_blobs: int


class ArtifactStore:
    def __init__(self, root: str | Path, *, inline_limit: int = 1_048_576) -> None:
        self.inline_limit = inline_limit
        self.blobs = BlobStore(root)
        self._refs: dict[str, ArtifactRef] = {}
        self._lock = Lock()

    def put(
        self,
        run_id: UUID | str,
        task_id: UUID | str | None,
        body: bytes | bytearray | BinaryIO,
        media_type: str,
    ) -> ArtifactRef:
        if hasattr(body, "read"):
            body = body.read()
        payload = bytes(body)
        run = str(run_id)
        task = str(task_id) if task_id is not None else None
        digest = hashlib.sha256(payload).hexdigest()
        if len(payload) <= self.inline_limit:
            ref = ArtifactRef(
                id=str(uuid4()),
                run_id=run,
                task_id=task,
                media_type=media_type,
                size=len(payload),
                sha256=digest,
                inline=True,
                inline_body=base64.b64encode(payload).decode("ascii"),
            )
        else:
            stored_digest, blob_key = self.blobs.put(payload)
            ref = ArtifactRef(
                id=str(uuid4()),
                run_id=run,
                task_id=task,
                media_type=media_type,
                size=len(payload),
                sha256=stored_digest,
                inline=False,
                blob_key=blob_key,
            )
        with self._lock:
            self._refs[ref.id] = ref
        return ref

    def get(
        self,
        ref: ArtifactRef | str,
        run_id: UUID | str,
        task_id: UUID | str | None = None,
        *,
        allow_cross_task: bool = False,
    ) -> bytes:
        with self._lock:
            resolved = self._refs[ref] if isinstance(ref, str) else ref
        if resolved.run_id != str(run_id):
            raise CrossTaskAccessError("artifact belongs to another run")
        if (
            resolved.task_id is not None
            and task_id is not None
            and resolved.task_id != str(task_id)
            and not allow_cross_task
        ):
            raise CrossTaskAccessError("cross-task artifact access requires explicit opt-in")
        if resolved.inline:
            assert resolved.inline_body is not None
            return base64.b64decode(resolved.inline_body)
        assert resolved.blob_key is not None
        return self.blobs.get(resolved.blob_key)

    def delete_run(self, run_id: UUID | str) -> tuple[int, int]:
        run = str(run_id)
        with self._lock:
            doomed = [ref for ref in self._refs.values() if ref.run_id == run]
            for ref in doomed:
                if ref.blob_key:
                    self.blobs.delete(ref.blob_key)
                self._refs.pop(ref.id, None)
        return len(doomed), sum(1 for ref in doomed if ref.blob_key)


class RunDestroyer:
    def __init__(self, event_store, artifact_store: ArtifactStore) -> None:
        self.event_store = event_store
        self.artifact_store = artifact_store

    def destroy(self, run_id: UUID | str) -> DestroyReport:
        deleted_events = self.event_store.delete_run(str(run_id))
        deleted_artifacts, deleted_blobs = self.artifact_store.delete_run(run_id)
        return DestroyReport(
            run_id=str(run_id),
            deleted_events=deleted_events,
            deleted_artifacts=deleted_artifacts,
            deleted_blobs=deleted_blobs,
        )
