"""Independent transition replay for SensorProof artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sensorproof import __version__
from sensorproof.artifact import ArtifactError
from sensorproof.fixed import canonical_bytes, integer_rmse, round_div, sha256_hex
from sensorproof.schema import Scenario, Sensor, parse_scenario_bytes, scenario_to_dict
from sensorproof.simulate import simulate

_HEX = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class Verification:
    """Verified summary safe to present to a user."""

    steps: int
    observations: int
    robust_rmse_mm: int
    baseline_rmse_mm: int
    certificate_sha256: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ArtifactError(message)


def _updated(
    before: list[int],
    sensor: Sensor,
    residual: list[int],
    dt_ms: int,
    accepted: bool,
) -> list[int]:
    state = before.copy()
    if not accepted:
        return state
    if sensor.kind == "position":
        for axis in range(2):
            state[axis] += round_div(residual[axis] * sensor.alpha_milli, 1_000)
            state[axis + 2] += round_div(residual[axis] * sensor.beta_milli, dt_ms)
    else:
        for axis in range(2):
            state[axis + 2] += round_div(residual[axis] * sensor.alpha_milli, 1_000)
    return state


def _expected_summary(trace: list[dict[str, Any]]) -> dict[str, int]:
    squared_errors: list[int] = []
    counts = {"accepted": 0, "rejected": 0, "quarantined": 0}
    isolated_faults = healthy_rejections = 0
    for frame in trace:
        error = frame["position_error"]
        squared_errors.append(error[0] ** 2 + error[1] ** 2)
        for decision in frame["decisions"]:
            status = decision["status"]
            _require(status in counts, f"unknown decision status: {status}")
            counts[status] += 1
            if status != "accepted" and decision["fault_active"]:
                isolated_faults += 1
            if status != "accepted" and not decision["fault_active"]:
                healthy_rejections += 1
    terminal = trace[-1]["position_error"]
    return {
        "position_rmse_mm": integer_rmse(squared_errors),
        "terminal_error_mm": integer_rmse([terminal[0] ** 2 + terminal[1] ** 2]),
        "accepted_observations": counts["accepted"],
        "rejected_observations": counts["rejected"],
        "quarantined_observations": counts["quarantined"],
        "isolated_fault_observations": isolated_faults,
        "healthy_rejections": healthy_rejections,
    }


def _replay(
    scenario: Scenario,
    observations: list[dict[str, Any]],
    run: dict[str, Any],
    *,
    robust: bool,
) -> None:
    trace = run.get("trace")
    _require(isinstance(trace, list), "run.trace must be an array")
    _require(len(trace) == scenario.steps, "trace length does not match scenario")
    state = list(scenario.initial_state)
    sensors = {sensor.sensor_id: sensor for sensor in scenario.sensors}
    health = {
        sensor.sensor_id: {"reject_streak": 0, "cooldown": 0}
        for sensor in scenario.sensors
    }

    for step, (frame, logged) in enumerate(zip(observations, trace, strict=True)):
        _require(logged.get("step") == step, f"trace step mismatch at {step}")
        state[0] += round_div(state[2] * scenario.dt_ms, 1_000)
        state[1] += round_div(state[3] * scenario.dt_ms, 1_000)
        _require(logged.get("predicted") == state, f"prediction mismatch at step {step}")
        decisions = logged.get("decisions")
        frame_observations = frame.get("observations")
        _require(isinstance(decisions, list), f"decisions must be an array at step {step}")
        _require(
            isinstance(frame_observations, list) and len(decisions) == len(frame_observations),
            f"decision count mismatch at step {step}",
        )
        for observation, decision in zip(frame_observations, decisions, strict=True):
            sensor_id = observation.get("sensor")
            _require(sensor_id in sensors, f"unknown sensor at step {step}")
            sensor = sensors[sensor_id]
            _require(decision.get("sensor") == sensor_id, f"sensor mismatch at step {step}")
            _require(decision.get("kind") == sensor.kind, f"kind mismatch at step {step}")
            _require(
                decision.get("fault_active") is observation.get("fault_active"),
                f"fault label mismatch at step {step}",
            )
            _require(decision.get("before") == state, f"before-state mismatch at step {step}")
            indexes = (0, 1) if sensor.kind == "position" else (2, 3)
            values = observation.get("values")
            _require(
                isinstance(values, list)
                and len(values) == 2
                and all(type(value) is int for value in values),
                f"invalid observation values at step {step}",
            )
            residual = [values[axis] - state[indexes[axis]] for axis in range(2)]
            residual_sq = sum(value * value for value in residual)
            gate_radius = round_div(sensor.noise_units * sensor.gate_sigma_milli, 1_000)
            gate_limit_sq = 2 * gate_radius * gate_radius
            denominator = 2 * sensor.noise_units * sensor.noise_units
            _require(decision.get("residual") == residual, f"residual mismatch at step {step}")
            _require(
                decision.get("residual_sq") == residual_sq,
                f"residual norm mismatch at step {step}",
            )
            _require(
                decision.get("innovation_score_milli")
                == round_div(residual_sq * 1_000, denominator),
                f"innovation score mismatch at step {step}",
            )
            _require(
                decision.get("gate_limit_sq") == gate_limit_sq,
                f"gate mismatch at step {step}",
            )
            _require(
                decision.get("gate_score_milli")
                == round_div(gate_limit_sq * 1_000, denominator),
                f"gate score mismatch at step {step}",
            )

            sensor_health = health[sensor_id]
            if robust and sensor_health["cooldown"] > 0:
                expected_status = "quarantined"
                sensor_health["cooldown"] -= 1
            elif robust and residual_sq > gate_limit_sq:
                expected_status = "rejected"
                sensor_health["reject_streak"] += 1
                if sensor_health["reject_streak"] >= 2:
                    sensor_health["cooldown"] = 3
                    sensor_health["reject_streak"] = 0
            else:
                expected_status = "accepted"
                sensor_health["reject_streak"] = 0
            _require(
                decision.get("status") == expected_status,
                f"decision mismatch for {sensor_id} at step {step}",
            )
            state = _updated(
                state,
                sensor,
                residual,
                scenario.dt_ms,
                expected_status == "accepted",
            )
            _require(decision.get("after") == state, f"after-state mismatch at step {step}")
            _require(
                decision.get("cooldown_remaining") == sensor_health["cooldown"],
                f"cooldown mismatch at step {step}",
            )
        _require(logged.get("estimate") == state, f"estimate mismatch at step {step}")
        truth = frame.get("truth")
        _require(
            isinstance(truth, list) and len(truth) == 4,
            f"invalid truth state at step {step}",
        )
        expected_error = [state[0] - truth[0], state[1] - truth[1]]
        _require(
            logged.get("position_error") == expected_error,
            f"position error mismatch at step {step}",
        )
    summary = run.get("summary")
    _require(summary == _expected_summary(trace), "run summary does not replay")


def verify_artifact(artifact: dict[str, Any]) -> Verification:
    """Validate hashes, regenerate observations, and replay every state transition."""
    expected_root = {
        "schema_version",
        "engine_version",
        "scenario_sha256",
        "scenario",
        "observations",
        "runs",
        "comparison",
        "certificate",
    }
    _require(set(artifact) == expected_root, "artifact root keys mismatch")
    _require(artifact["schema_version"] == 1, "unsupported artifact schema")
    _require(artifact["engine_version"] == __version__, "engine version mismatch")

    scenario_value = artifact["scenario"]
    _require(isinstance(scenario_value, dict), "scenario must be an object")
    scenario = parse_scenario_bytes(canonical_bytes(scenario_value))
    _require(scenario_to_dict(scenario) == scenario_value, "scenario is not canonical")
    _require(
        artifact["scenario_sha256"] == sha256_hex(scenario_value),
        "scenario digest mismatch",
    )

    observations = artifact["observations"]
    _require(isinstance(observations, list), "observations must be an array")
    _require(observations == simulate(scenario), "observations do not regenerate")

    runs = artifact["runs"]
    _require(isinstance(runs, dict) and set(runs) == {"robust", "baseline"}, "runs mismatch")
    robust = runs["robust"]
    baseline = runs["baseline"]
    _require(isinstance(robust, dict) and isinstance(baseline, dict), "runs must be objects")
    _replay(scenario, observations, robust, robust=True)
    _replay(scenario, observations, baseline, robust=False)

    robust_rmse = robust["summary"]["position_rmse_mm"]
    baseline_rmse = baseline["summary"]["position_rmse_mm"]
    reduction = 0
    if baseline_rmse:
        reduction = round_div((baseline_rmse - robust_rmse) * 10_000, baseline_rmse)
    expected_comparison = {
        "rmse_reduction_basis_points": reduction,
        "winner": "robust" if robust_rmse < baseline_rmse else "baseline",
    }
    _require(artifact["comparison"] == expected_comparison, "comparison does not replay")

    certificate = artifact["certificate"]
    _require(isinstance(certificate, dict), "certificate must be an object")
    _require(
        set(certificate)
        == {
            "algorithm",
            "observations_sha256",
            "robust_trace_sha256",
            "baseline_trace_sha256",
            "payload_sha256",
        },
        "certificate keys mismatch",
    )
    _require(certificate["algorithm"] == "sha256", "unsupported certificate algorithm")
    for key in (
        "observations_sha256",
        "robust_trace_sha256",
        "baseline_trace_sha256",
        "payload_sha256",
    ):
        _require(
            isinstance(certificate[key], str) and _HEX.fullmatch(certificate[key]) is not None,
            f"invalid certificate digest: {key}",
        )
    _require(
        certificate["observations_sha256"] == sha256_hex(observations),
        "observation digest mismatch",
    )
    _require(
        certificate["robust_trace_sha256"] == sha256_hex(robust["trace"]),
        "robust trace digest mismatch",
    )
    _require(
        certificate["baseline_trace_sha256"] == sha256_hex(baseline["trace"]),
        "baseline trace digest mismatch",
    )
    payload = {key: value for key, value in artifact.items() if key != "certificate"}
    _require(certificate["payload_sha256"] == sha256_hex(payload), "payload digest mismatch")

    return Verification(
        steps=scenario.steps,
        observations=scenario.steps * len(scenario.sensors),
        robust_rmse_mm=robust_rmse,
        baseline_rmse_mm=baseline_rmse,
        certificate_sha256=certificate["payload_sha256"],
    )
