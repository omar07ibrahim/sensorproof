"""Fault-aware fixed-point sensor fusion and experiment construction."""

from __future__ import annotations

from typing import Any

from sensorproof import __version__
from sensorproof.fixed import integer_rmse, round_div, sha256_hex
from sensorproof.schema import Scenario, Sensor, scenario_to_dict
from sensorproof.simulate import simulate

State = list[int]


def _predict(state: State, dt_ms: int) -> None:
    state[0] += round_div(state[2] * dt_ms, 1_000)
    state[1] += round_div(state[3] * dt_ms, 1_000)


def _apply_update(state: State, sensor: Sensor, residual: list[int], dt_ms: int) -> None:
    if sensor.kind == "position":
        for axis in range(2):
            state[axis] += round_div(residual[axis] * sensor.alpha_milli, 1_000)
            state[axis + 2] += round_div(residual[axis] * sensor.beta_milli, dt_ms)
    else:
        for axis in range(2):
            state[axis + 2] += round_div(residual[axis] * sensor.alpha_milli, 1_000)


def _summary(trace: list[dict[str, Any]]) -> dict[str, int]:
    squared_errors: list[int] = []
    accepted = rejected = quarantined = 0
    isolated_faults = healthy_rejections = 0
    for frame in trace:
        error = frame["position_error"]
        squared_errors.append(error[0] ** 2 + error[1] ** 2)
        for decision in frame["decisions"]:
            status = decision["status"]
            if status == "accepted":
                accepted += 1
            elif status == "rejected":
                rejected += 1
            else:
                quarantined += 1
            if status != "accepted" and decision["fault_active"]:
                isolated_faults += 1
            if status != "accepted" and not decision["fault_active"]:
                healthy_rejections += 1
    terminal = trace[-1]["position_error"]
    return {
        "position_rmse_mm": integer_rmse(squared_errors),
        "terminal_error_mm": integer_rmse([terminal[0] ** 2 + terminal[1] ** 2]),
        "accepted_observations": accepted,
        "rejected_observations": rejected,
        "quarantined_observations": quarantined,
        "isolated_fault_observations": isolated_faults,
        "healthy_rejections": healthy_rejections,
    }


def run_filter(
    scenario: Scenario,
    frames: list[dict[str, Any]],
    *,
    robust: bool,
) -> dict[str, Any]:
    """Run the same estimator with or without innovation gating."""
    state = list(scenario.initial_state)
    health = {sensor.sensor_id: {"reject_streak": 0, "cooldown": 0} for sensor in scenario.sensors}
    sensors = {sensor.sensor_id: sensor for sensor in scenario.sensors}
    trace: list[dict[str, Any]] = []

    for frame in frames:
        _predict(state, scenario.dt_ms)
        predicted = state.copy()
        decisions: list[dict[str, Any]] = []
        for observation in frame["observations"]:
            sensor = sensors[observation["sensor"]]
            indexes = (0, 1) if sensor.kind == "position" else (2, 3)
            before = state.copy()
            residual = [observation["values"][axis] - state[indexes[axis]] for axis in range(2)]
            residual_sq = sum(value * value for value in residual)
            gate_radius = round_div(sensor.noise_units * sensor.gate_sigma_milli, 1_000)
            gate_limit_sq = 2 * gate_radius * gate_radius
            sensor_health = health[sensor.sensor_id]

            if robust and sensor_health["cooldown"] > 0:
                status = "quarantined"
                sensor_health["cooldown"] -= 1
            elif robust and residual_sq > gate_limit_sq:
                status = "rejected"
                sensor_health["reject_streak"] += 1
                if sensor_health["reject_streak"] >= 2:
                    sensor_health["cooldown"] = 3
                    sensor_health["reject_streak"] = 0
            else:
                status = "accepted"
                sensor_health["reject_streak"] = 0
                _apply_update(state, sensor, residual, scenario.dt_ms)

            denominator = 2 * sensor.noise_units * sensor.noise_units
            decisions.append(
                {
                    "sensor": sensor.sensor_id,
                    "kind": sensor.kind,
                    "status": status,
                    "fault_active": observation["fault_active"],
                    "before": before,
                    "residual": residual,
                    "residual_sq": residual_sq,
                    "innovation_score_milli": round_div(residual_sq * 1_000, denominator),
                    "gate_limit_sq": gate_limit_sq,
                    "gate_score_milli": round_div(gate_limit_sq * 1_000, denominator),
                    "after": state.copy(),
                    "cooldown_remaining": sensor_health["cooldown"],
                }
            )
        truth = frame["truth"]
        trace.append(
            {
                "step": frame["step"],
                "predicted": predicted,
                "decisions": decisions,
                "estimate": state.copy(),
                "position_error": [state[0] - truth[0], state[1] - truth[1]],
            }
        )
    return {"trace": trace, "summary": _summary(trace)}


def run_experiment(scenario: Scenario) -> dict[str, Any]:
    """Build a deterministic, self-contained experiment artifact."""
    frames = simulate(scenario)
    robust = run_filter(scenario, frames, robust=True)
    baseline = run_filter(scenario, frames, robust=False)
    robust_rmse = robust["summary"]["position_rmse_mm"]
    baseline_rmse = baseline["summary"]["position_rmse_mm"]
    reduction = 0
    if baseline_rmse:
        reduction = round_div((baseline_rmse - robust_rmse) * 10_000, baseline_rmse)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "engine_version": __version__,
        "scenario_sha256": sha256_hex(scenario_to_dict(scenario)),
        "scenario": scenario_to_dict(scenario),
        "observations": frames,
        "runs": {"robust": robust, "baseline": baseline},
        "comparison": {
            "rmse_reduction_basis_points": reduction,
            "winner": "robust" if robust_rmse < baseline_rmse else "baseline",
        },
    }
    payload["certificate"] = {
        "algorithm": "sha256",
        "observations_sha256": sha256_hex(frames),
        "robust_trace_sha256": sha256_hex(robust["trace"]),
        "baseline_trace_sha256": sha256_hex(baseline["trace"]),
        "payload_sha256": sha256_hex(payload),
    }
    return payload
