"""Deterministic fixed-point motion and sensor simulation."""

from __future__ import annotations

from typing import Any

from sensorproof.fixed import deterministic_noise, round_div
from sensorproof.schema import Fault, Scenario


def _acceleration(scenario: Scenario, step: int) -> tuple[int, int]:
    for segment in scenario.motion:
        if segment.start <= step < segment.end:
            return segment.ax_mm_s2, segment.ay_mm_s2
    return 0, 0


def _fault_bias(fault: Fault, step: int) -> tuple[int, int]:
    if not fault.start <= step < fault.end:
        return 0, 0
    if fault.fault_type == "bias_step":
        return fault.bias_x, fault.bias_y
    elapsed = step - fault.start + 1
    duration = fault.end - fault.start
    return (
        round_div(fault.bias_x * elapsed, duration),
        round_div(fault.bias_y * elapsed, duration),
    )


def simulate(scenario: Scenario) -> list[dict[str, Any]]:
    """Generate truth and observations using integer arithmetic only."""
    truth = list(scenario.initial_state)
    frames: list[dict[str, Any]] = []
    for step in range(scenario.steps):
        ax, ay = _acceleration(scenario, step)
        truth[2] += round_div(ax * scenario.dt_ms, 1_000)
        truth[3] += round_div(ay * scenario.dt_ms, 1_000)
        truth[0] += round_div(truth[2] * scenario.dt_ms, 1_000)
        truth[1] += round_div(truth[3] * scenario.dt_ms, 1_000)

        observations: list[dict[str, Any]] = []
        for sensor in scenario.sensors:
            base = truth[:2] if sensor.kind == "position" else truth[2:]
            bias = [0, 0]
            active = False
            for fault in scenario.faults:
                if fault.sensor_id != sensor.sensor_id:
                    continue
                fault_bias = _fault_bias(fault, step)
                if fault_bias != (0, 0):
                    active = True
                    bias[0] += fault_bias[0]
                    bias[1] += fault_bias[1]
            values = [
                base[axis]
                + deterministic_noise(
                    scenario.seed,
                    step,
                    sensor.sensor_id,
                    axis,
                    sensor.noise_units,
                )
                + bias[axis]
                for axis in range(2)
            ]
            observations.append(
                {
                    "sensor": sensor.sensor_id,
                    "kind": sensor.kind,
                    "values": values,
                    "fault_active": active,
                    "injected_bias": bias,
                }
            )
        frames.append(
            {
                "step": step,
                "truth": truth.copy(),
                "observations": observations,
            }
        )
    return frames
