"""Bounded artifact input and atomic output helpers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

from sensorproof.schema import ScenarioError

MAX_ARTIFACT_BYTES: Final = 16 * 1024 * 1024


class ArtifactError(ValueError):
    """Raised when an experiment artifact cannot be trusted."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ArtifactError(f"non-finite JSON number is not allowed: {value}")


def load_artifact(path: Path) -> dict[str, Any]:
    """Read one bounded, strict UTF-8 artifact."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ArtifactError(f"cannot inspect artifact: {exc}") from exc
    if size > MAX_ARTIFACT_BYTES:
        raise ArtifactError(f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ArtifactError(f"cannot read artifact: {exc}") from exc
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ArtifactError("artifact must be strict UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ArtifactError(f"invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(value, dict):
        raise ArtifactError("artifact root must be an object")
    return value


def _atomic_write(path: Path, content: bytes) -> None:
    parent = path.parent
    if not parent.is_dir():
        raise ArtifactError(f"output directory does not exist: {parent}")
    temporary: Path | None = None
    try:
        descriptor, raw_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
        temporary = Path(raw_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ArtifactError(f"cannot write output: {exc}") from exc


def write_artifact(path: Path, artifact: dict[str, Any]) -> None:
    """Write a stable, human-readable artifact after enforcing its size budget."""
    try:
        content = (
            json.dumps(
                artifact,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ArtifactError(f"artifact is not JSON serializable: {exc}") from exc
    if len(content) > MAX_ARTIFACT_BYTES:
        raise ArtifactError(f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes")
    _atomic_write(path, content)


def write_text(path: Path, content: str) -> None:
    """Atomically write strict UTF-8 text."""
    try:
        encoded = content.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ScenarioError("output is not valid UTF-8") from exc
    _atomic_write(path, encoded)
