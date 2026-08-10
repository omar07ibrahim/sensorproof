"""Tests for bounded artifact I/O."""

from __future__ import annotations

from pathlib import Path

import pytest

from sensorproof.artifact import ArtifactError, load_artifact, write_artifact, write_text


def test_artifact_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    write_artifact(path, {"answer": 42})
    assert path.read_bytes().endswith(b"\n")
    assert load_artifact(path) == {"answer": 42}


def test_duplicate_artifact_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    path.write_text('{"answer":1,"answer":2}')
    with pytest.raises(ArtifactError, match="duplicate JSON key"):
        load_artifact(path)


def test_nonfinite_artifact_number_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    path.write_text('{"answer":NaN}')
    with pytest.raises(ArtifactError, match="non-finite"):
        load_artifact(path)


def test_output_parent_must_exist(tmp_path: Path) -> None:
    with pytest.raises(ArtifactError, match="does not exist"):
        write_text(tmp_path / "missing" / "report.html", "report")


def test_atomic_text_replaces_existing_target(tmp_path: Path) -> None:
    path = tmp_path / "report.html"
    path.write_text("old")
    write_text(path, "new")
    assert path.read_text() == "new"
