"""Command-line interface for SensorProof."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections.abc import Sequence

from sensorproof import __version__
from sensorproof.artifact import ArtifactError, load_artifact, write_artifact, write_text
from sensorproof.engine import run_experiment
from sensorproof.report import build_report
from sensorproof.schema import ScenarioError, load_scenario
from sensorproof.verify import verify_artifact


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sensorproof",
        description="Deterministic fault-aware sensor fusion with replayable certificates.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run one bounded scenario")
    run.add_argument("scenario", type=Path)
    run.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify", help="replay and verify an artifact")
    verify.add_argument("artifact", type=Path)

    report = subparsers.add_parser("report", help="build a verified offline HTML report")
    report.add_argument("artifact", type=Path)
    report.add_argument("--output", type=Path, required=True)

    inspect = subparsers.add_parser("inspect", help="inspect one robust decision")
    inspect.add_argument("artifact", type=Path)
    inspect.add_argument("--step", type=int, required=True)
    inspect.add_argument("--sensor", required=True)
    return parser


def _run(scenario_path: Path, output: Path) -> None:
    scenario = load_scenario(scenario_path)
    artifact = run_experiment(scenario)
    verified = verify_artifact(artifact)
    write_artifact(output, artifact)
    comparison = artifact["comparison"]["rmse_reduction_basis_points"] / 100
    robust = artifact["runs"]["robust"]["summary"]
    print("SensorProof run complete")
    print(f"  scenario: {scenario.name}")
    print(f"  fixed-point steps: {verified.steps}")
    print(f"  observations: {verified.observations}")
    print(f"  robust position RMSE: {verified.robust_rmse_mm} mm")
    print(f"  ungated baseline RMSE: {verified.baseline_rmse_mm} mm")
    print(f"  RMSE reduction: {comparison:.2f}%")
    print(f"  isolated fault observations: {robust['isolated_fault_observations']}")
    print(f"  certificate: sha256:{verified.certificate_sha256}")
    print(f"  artifact: {output}")


def _verify(path: Path) -> None:
    result = verify_artifact(load_artifact(path))
    print("SensorProof certificate verified")
    print(f"  steps replayed: {result.steps}")
    print(f"  observations replayed: {result.observations}")
    print(f"  robust position RMSE: {result.robust_rmse_mm} mm")
    print(f"  ungated baseline RMSE: {result.baseline_rmse_mm} mm")
    print(f"  payload: sha256:{result.certificate_sha256}")


def _report(path: Path, output: Path) -> None:
    artifact = load_artifact(path)
    verify_artifact(artifact)
    write_text(output, build_report(artifact))
    print("SensorProof report written")
    print(f"  report: {output}")
    print("  network dependencies: none")


def _inspect(path: Path, step: int, sensor: str) -> None:
    artifact = load_artifact(path)
    verify_artifact(artifact)
    trace = artifact["runs"]["robust"]["trace"]
    if not 0 <= step < len(trace):
        raise ArtifactError(f"step must be between 0 and {len(trace) - 1}")
    decisions = [item for item in trace[step]["decisions"] if item["sensor"] == sensor]
    if not decisions:
        known = ", ".join(item["sensor"] for item in trace[step]["decisions"])
        raise ArtifactError(f"unknown sensor {sensor}; choose one of: {known}")
    print(json.dumps(decisions[0], indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and translate expected input failures into concise diagnostics."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            _run(args.scenario, args.output)
        elif args.command == "verify":
            _verify(args.artifact)
        elif args.command == "report":
            _report(args.artifact, args.output)
        else:
            _inspect(args.artifact, args.step, args.sensor)
    except (ArtifactError, ScenarioError) as exc:
        print(f"sensorproof: error: {exc}", file=sys.stderr)
        return 2
    return 0
