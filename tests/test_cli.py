"""End-to-end CLI tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from sensorproof.cli import main


def test_run_verify_report_and_inspect(
    scenario_path: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact = tmp_path / "run.json"
    report = tmp_path / "report.html"
    assert main(["run", str(scenario_path), "--output", str(artifact)]) == 0
    run_output = capsys.readouterr().out
    assert "SensorProof run complete" in run_output
    assert "ungated baseline RMSE" in run_output

    assert main(["verify", str(artifact)]) == 0
    assert "certificate verified" in capsys.readouterr().out

    assert main(["report", str(artifact), "--output", str(report)]) == 0
    assert "network dependencies: none" in capsys.readouterr().out
    assert report.read_text().startswith("<!doctype html>")

    assert main(["inspect", str(artifact), "--step", "40", "--sensor", "gnss"]) == 0
    inspected = capsys.readouterr().out
    assert '"sensor": "gnss"' in inspected
    assert '"innovation_score_milli"' in inspected


def test_inspect_rejects_bad_step(
    scenario_path: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact = tmp_path / "run.json"
    assert main(["run", str(scenario_path), "--output", str(artifact)]) == 0
    capsys.readouterr()
    assert main(["inspect", str(artifact), "--step", "999", "--sensor", "gnss"]) == 2
    assert "step must be between" in capsys.readouterr().err
