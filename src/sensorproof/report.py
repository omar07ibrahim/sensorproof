"""Self-contained HTML evidence report for a verified SensorProof artifact."""

from __future__ import annotations

from html import escape
from typing import Any

from sensorproof.verify import verify_artifact

_WIDTH = 920
_HEIGHT = 400
_PAD = 42


def _points(values: list[list[int]], bounds: tuple[int, int, int, int]) -> str:
    min_x, max_x, min_y, max_y = bounds
    span_x = max(max_x - min_x, 1)
    span_y = max(max_y - min_y, 1)
    points: list[str] = []
    for x, y in values:
        px = _PAD + (x - min_x) * (_WIDTH - 2 * _PAD) / span_x
        py = _HEIGHT - _PAD - (y - min_y) * (_HEIGHT - 2 * _PAD) / span_y
        points.append(f"{px:.1f},{py:.1f}")
    return " ".join(points)


def _trajectory(artifact: dict[str, Any]) -> str:
    truth = [frame["truth"][:2] for frame in artifact["observations"]]
    robust = [frame["estimate"][:2] for frame in artifact["runs"]["robust"]["trace"]]
    baseline = [frame["estimate"][:2] for frame in artifact["runs"]["baseline"]["trace"]]
    all_points = truth + robust + baseline
    xs = [point[0] for point in all_points]
    ys = [point[1] for point in all_points]
    margin_x = max((max(xs) - min(xs)) // 20, 1)
    margin_y = max((max(ys) - min(ys)) // 20, 1)
    bounds = (
        min(xs) - margin_x,
        max(xs) + margin_x,
        min(ys) - margin_y,
        max(ys) + margin_y,
    )
    return f"""<svg viewBox="0 0 {_WIDTH} {_HEIGHT}" role="img" aria-label="Truth, robust and baseline trajectories">
  <rect width="{_WIDTH}" height="{_HEIGHT}" rx="18" fill="#09131f"/>
  <path d="M {_PAD} {_HEIGHT - _PAD} H {_WIDTH - _PAD} M {_PAD} {_PAD} V {_HEIGHT - _PAD}" stroke="#294158" stroke-width="1"/>
  <polyline points="{_points(baseline, bounds)}" fill="none" stroke="#ff6b6b" stroke-width="3" opacity=".82"/>
  <polyline points="{_points(robust, bounds)}" fill="none" stroke="#52d6a6" stroke-width="4"/>
  <polyline points="{_points(truth, bounds)}" fill="none" stroke="#f4d35e" stroke-width="2" stroke-dasharray="7 6"/>
  <g font-family="ui-monospace,monospace" font-size="14">
    <text x="58" y="28" fill="#f4d35e">truth</text>
    <text x="130" y="28" fill="#52d6a6">robust</text>
    <text x="212" y="28" fill="#ff6b6b">ungated baseline</text>
  </g>
</svg>"""


def _innovation(artifact: dict[str, Any], sensor_id: str) -> str:
    trace = artifact["runs"]["robust"]["trace"]
    decisions = [
        next(item for item in frame["decisions"] if item["sensor"] == sensor_id) for frame in trace
    ]
    maximum = max(
        max(item["innovation_score_milli"], item["gate_score_milli"]) for item in decisions
    )
    chart_width = _WIDTH - 2 * _PAD
    chart_height = 238
    bars: list[str] = []
    for index, decision in enumerate(decisions):
        x = _PAD + index * chart_width / len(decisions)
        width = max(chart_width / len(decisions) - 1.3, 1)
        value = min(decision["innovation_score_milli"], maximum)
        height = value * chart_height / max(maximum, 1)
        color = {
            "accepted": "#52d6a6",
            "rejected": "#ff6b6b",
            "quarantined": "#7f8ea3",
        }[decision["status"]]
        bars.append(
            f'<rect x="{x:.1f}" y="{_HEIGHT - _PAD - height:.1f}" '
            f'width="{width:.1f}" height="{height:.1f}" fill="{color}" rx="1"/>'
        )
    gate = decisions[0]["gate_score_milli"] * chart_height / max(maximum, 1)
    gate_y = _HEIGHT - _PAD - gate
    return f"""<svg viewBox="0 0 {_WIDTH} {_HEIGHT}" role="img" aria-label="{escape(sensor_id)} innovation gate decisions">
  <rect width="{_WIDTH}" height="{_HEIGHT}" rx="18" fill="#09131f"/>
  {"".join(bars)}
  <line x1="{_PAD}" y1="{gate_y:.1f}" x2="{_WIDTH - _PAD}" y2="{gate_y:.1f}" stroke="#f4d35e" stroke-width="2" stroke-dasharray="7 5"/>
  <text x="{_PAD}" y="28" fill="#c9d7e5" font-family="ui-monospace,monospace" font-size="14">{escape(sensor_id)} normalized innovation · yellow = configured gate</text>
  <text x="{_PAD}" y="{_HEIGHT - 14}" fill="#7f8ea3" font-family="ui-monospace,monospace" font-size="12">green accepted · red rejected · gray quarantined · step 0 → {len(decisions) - 1}</text>
</svg>"""


def _decision_rows(artifact: dict[str, Any]) -> str:
    rows: list[str] = []
    for frame in artifact["runs"]["robust"]["trace"]:
        for decision in frame["decisions"]:
            if decision["status"] == "accepted":
                continue
            rows.append(
                "<tr>"
                f"<td>{frame['step']}</td>"
                f"<td>{escape(decision['sensor'])}</td>"
                f'<td><span class="status {decision["status"]}">{decision["status"]}</span></td>'
                f"<td>{str(decision['fault_active']).lower()}</td>"
                f"<td>{decision['innovation_score_milli'] / 1000:.3f}</td>"
                f"<td>{decision['gate_score_milli'] / 1000:.3f}</td>"
                "</tr>"
            )
    return "".join(rows)


def build_report(artifact: dict[str, Any]) -> str:
    """Return an offline report only after full certificate verification."""
    verified = verify_artifact(artifact)
    scenario = artifact["scenario"]
    robust = artifact["runs"]["robust"]["summary"]
    baseline = artifact["runs"]["baseline"]["summary"]
    comparison = artifact["comparison"]
    reduction = comparison["rmse_reduction_basis_points"] / 100
    sensor_id = next(fault["sensor"] for fault in scenario["faults"] if fault["sensor"])
    certificate = artifact["certificate"]["payload_sha256"]
    trajectory = _trajectory(artifact)
    innovation = _innovation(artifact, sensor_id)
    rows = _decision_rows(artifact)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SensorProof · {escape(scenario["name"])}</title>
<style>
:root{{--ink:#eaf2f8;--muted:#9eb0c2;--panel:#101e2c;--line:#294158;--green:#52d6a6;--red:#ff6b6b;--yellow:#f4d35e}}
*{{box-sizing:border-box}} body{{margin:0;background:#071019;color:var(--ink);font:16px/1.55 Inter,ui-sans-serif,system-ui,sans-serif}}
main{{width:min(1120px,calc(100% - 32px));margin:0 auto;padding:64px 0 80px}}
.eyebrow{{color:var(--green);font:700 13px ui-monospace,monospace;letter-spacing:.13em;text-transform:uppercase}}
h1{{font-size:clamp(38px,7vw,72px);line-height:1;margin:12px 0 18px;letter-spacing:-.045em}}
h2{{font-size:28px;margin:48px 0 14px}} p{{color:var(--muted);max-width:78ch}}
.hero{{display:grid;grid-template-columns:1.5fr 1fr;gap:28px;align-items:end}}
.certificate{{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:20px}}
code{{font-family:ui-monospace,monospace;color:#cfe2f2}} .hash{{display:block;overflow-wrap:anywhere;font-size:12px;margin-top:8px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:34px 0}}
.kpi{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px}}
.kpi strong{{display:block;font-size:30px;letter-spacing:-.03em}} .kpi span{{color:var(--muted);font-size:13px}}
.good{{color:var(--green)}} .bad{{color:var(--red)}} figure{{margin:16px 0}} svg{{display:block;width:100%;height:auto}}
table{{width:100%;border-collapse:collapse;background:var(--panel);border-radius:16px;overflow:hidden}}
th,td{{padding:11px 14px;text-align:left;border-bottom:1px solid var(--line);font:13px ui-monospace,monospace}}
th{{color:var(--muted)}} .status{{padding:3px 7px;border-radius:999px}} .rejected{{color:var(--red);background:#3a1d27}} .quarantined{{color:#c7d0da;background:#293543}}
.callout{{border-left:3px solid var(--yellow);padding:4px 0 4px 18px}}
footer{{margin-top:50px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}}
@media(max-width:760px){{main{{width:min(100% - 20px,1120px);padding-top:36px}}.hero{{grid-template-columns:1fr}}.grid{{grid-template-columns:1fr 1fr}}h2{{font-size:24px}}table{{table-layout:fixed}}th,td{{padding:8px 7px;font-size:11px;overflow-wrap:anywhere}}th:nth-child(5),td:nth-child(5),th:nth-child(6),td:nth-child(6){{display:none}}}}
</style>
</head>
<body><main>
<section class="hero">
<div><div class="eyebrow">Verified robotics evidence · schema v1</div>
<h1>Faults should leave a proof.</h1>
<p>SensorProof replayed {verified.observations} observations across {verified.steps} fixed-point steps. A synthetic GNSS bias is isolated while wheel odometry and visual-inertial position keep the estimate bounded.</p></div>
<div class="certificate"><div class="eyebrow">Replay certificate</div><code class="hash">sha256:{certificate}</code></div>
</section>
<section class="grid">
<div class="kpi"><strong class="good">{robust["position_rmse_mm"]} mm</strong><span>fault-aware RMSE</span></div>
<div class="kpi"><strong class="bad">{baseline["position_rmse_mm"]} mm</strong><span>ungated baseline RMSE</span></div>
<div class="kpi"><strong>{reduction:.2f}%</strong><span>RMSE reduction</span></div>
<div class="kpi"><strong>{robust["isolated_fault_observations"]}</strong><span>fault observations isolated</span></div>
</section>
<h2>Trajectory under an urban-canyon bias</h2>
<p>The comparison changes one thing: innovation gating and cooldown are enabled for the robust run and disabled for the baseline. Motion, observations, update gains and ordering are byte-identical.</p>
<figure>{trajectory}</figure>
<h2>Why the GNSS stream was isolated</h2>
<p>Each bar is the exact normalized integer innovation recorded in the artifact. There is no hidden model call and no floating-point threshold drift.</p>
<figure>{innovation}</figure>
<h2>Decision ledger</h2>
<p class="callout">Every non-accepted measurement is shown below. The verifier independently rebuilds its residual, gate, health state, state transition, metric and SHA-256 certificate.</p>
<table><thead><tr><th>step</th><th>sensor</th><th>decision</th><th>fault active</th><th>innovation</th><th>gate</th></tr></thead>
<tbody>{rows}</tbody></table>
<h2>Reproduce</h2>
<p><code>sensorproof run scenarios/urban-canyon.json --output run.json</code><br>
<code>sensorproof verify run.json</code><br>
<code>sensorproof report run.json --output report.html</code></p>
<footer>SensorProof {escape(artifact["engine_version"])} · scenario digest {escape(artifact["scenario_sha256"])} · self-contained offline report</footer>
</main></body></html>
"""
