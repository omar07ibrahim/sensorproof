"""Tests for the self-contained evidence interface."""

from sensorproof.engine import run_experiment
from sensorproof.report import build_report
from sensorproof.schema import Scenario


def test_report_is_offline_and_contains_verified_result(scenario: Scenario) -> None:
    artifact = run_experiment(scenario)
    report = build_report(artifact)
    robust = artifact["runs"]["robust"]["summary"]["position_rmse_mm"]
    assert "<!doctype html>" in report
    assert f"{robust} mm" in report
    assert artifact["certificate"]["payload_sha256"] in report
    assert "http://" not in report
    assert "https://" not in report
    assert "<svg" in report
    assert "@media(max-width:760px)" in report
    assert "table-layout:fixed" in report
    assert 'class="table-scroll"' in report
    assert "overflow-x:auto" in report
    assert "th:nth-child(5)" in report


def test_report_lists_rejections(scenario: Scenario) -> None:
    report = build_report(run_experiment(scenario))
    assert 'class="status rejected"' in report
    assert "fault active" in report
