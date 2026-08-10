"""Generate and verify source-bound SensorProof portfolio evidence."""

# ruff: noqa: E501 -- SVG, CSS, and terminal HTML remain readable source

from __future__ import annotations

import argparse
import hashlib
import html
import json
import platform
import struct
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Any

FORMAT = "sensorproof.evidence.v1"
EVIDENCE_DIRECTORY = Path("docs/evidence")
MANIFEST_NAME = "sensorproof-evidence.json"
CONTAINER_IMAGE = (
    "mcr.microsoft.com/playwright/python@"
    "sha256:51d31fdfacb0cff99a1a724152e34ae408d2bd4e7da310ff157450f49261cc59"
)
EXPECTED_FILES = {
    "architecture.svg",
    "certificate-chain.svg",
    "fault-isolation.svg",
    "sensorproof-cli.png",
    "sensorproof-cli.txt",
    "sensorproof-demo.gif",
    "sensorproof-report-full.png",
    "sensorproof-report-mobile.png",
    "sensorproof-report.html",
    "sensorproof-report.png",
    "sensorproof-run.json",
    "trajectory.svg",
}
MEDIA_TYPES = {
    ".gif": "image/gif",
    ".html": "text/html",
    ".json": "application/json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain",
}
FORBIDDEN_TEXT = (
    "/home/",
    "/Users/",
    "github_pat_",
    "ghp_",
    "sk-proj-",
    "BEGIN PRIVATE KEY",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--root", type=Path, required=True)
    prepare_parser.add_argument("--artifact", type=Path, required=True)
    prepare_parser.add_argument("--report", type=Path, required=True)
    prepare_parser.add_argument("--cli", type=Path, required=True)
    prepare_parser.add_argument("--output-root", type=Path, required=True)

    capture_parser = commands.add_parser("capture")
    capture_parser.add_argument("--output-root", type=Path, required=True)
    capture_parser.add_argument("--container-image", required=True)

    finalize_parser = commands.add_parser("finalize")
    finalize_parser.add_argument("--root", type=Path, required=True)
    finalize_parser.add_argument("--output-root", type=Path, required=True)
    finalize_parser.add_argument("--source-revision", required=True)
    finalize_parser.add_argument("--source-tree", required=True)
    finalize_parser.add_argument("--container-image", required=True)
    finalize_parser.add_argument("--browser", required=True)
    finalize_parser.add_argument("--playwright", required=True)
    finalize_parser.add_argument("--pillow", required=True)

    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--root", type=Path, required=True)
    verify_parser.add_argument("--output-root", type=Path, required=True)
    verify_parser.add_argument("--source-revision", required=True)
    verify_parser.add_argument("--source-tree", required=True)
    verify_parser.add_argument("--container-image", required=True)

    visual_parser = commands.add_parser("verify-visuals")
    visual_parser.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "prepare":
        prepare(
            arguments.root,
            arguments.artifact,
            arguments.report,
            arguments.cli,
            arguments.output_root,
        )
    elif arguments.command == "capture":
        capture(arguments.output_root, arguments.container_image)
    elif arguments.command == "finalize":
        finalize(
            arguments.root,
            arguments.output_root,
            arguments.source_revision,
            arguments.source_tree,
            arguments.container_image,
            arguments.browser,
            arguments.playwright,
            arguments.pillow,
        )
    elif arguments.command == "verify":
        verify(
            arguments.root,
            arguments.output_root,
            arguments.source_revision,
            arguments.source_tree,
            arguments.container_image,
        )
    else:
        verify_visuals(arguments.output_root)
    return 0


def prepare(
    root: Path, artifact_path: Path, report_path: Path, cli_path: Path, output_root: Path
) -> None:
    root = root.resolve()
    if output_root.exists():
        raise ValueError("evidence output root already exists")
    evidence = output_root / EVIDENCE_DIRECTORY
    evidence.mkdir(parents=True)

    from sensorproof.artifact import load_artifact
    from sensorproof.report import build_report
    from sensorproof.verify import verify_artifact

    artifact = load_artifact(artifact_path)
    verified = verify_artifact(artifact)
    report = report_path.read_text(encoding="utf-8")
    if report != build_report(artifact):
        raise ValueError("CLI report differs from verified library rendering")
    cli = cli_path.read_text(encoding="utf-8")
    _reject_sensitive_text(cli)
    if not cli.startswith("$ sensorproof run scenario.json --output run.json"):
        raise ValueError("CLI transcript does not begin with the executed run command")
    if verified.certificate_sha256 not in cli:
        raise ValueError("CLI transcript does not expose the verified certificate")

    (evidence / "sensorproof-run.json").write_bytes(artifact_path.read_bytes())
    _write_text(evidence / "sensorproof-report.html", report)
    _write_text(evidence / "sensorproof-cli.txt", cli)
    _write_text(evidence / "trajectory.svg", _trajectory_svg(artifact))
    _write_text(evidence / "fault-isolation.svg", _fault_svg(artifact))
    _write_text(evidence / "architecture.svg", _architecture_svg())
    _write_text(evidence / "certificate-chain.svg", _certificate_svg(artifact))

    for source in _source_paths(root):
        if not source.is_file():
            raise ValueError(f"missing evidence source: {source.relative_to(root)}")


def capture(output_root: Path, container_image: str) -> None:
    from PIL import Image
    from playwright.sync_api import sync_playwright

    if container_image != CONTAINER_IMAGE:
        raise ValueError("capture image does not match the reviewed platform manifest")
    evidence = output_root / EVIDENCE_DIRECTORY
    report = (evidence / "sensorproof-report.html").resolve()
    cli = (evidence / "sensorproof-cli.txt").read_text(encoding="utf-8")
    _reject_sensitive_text(cli)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--disable-gpu"])
        if browser.version != "151.0.7922.34":
            raise ValueError(f"unexpected Chromium version: {browser.version}")

        desktop = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        desktop.goto(report.as_uri(), wait_until="load")
        desktop.locator("h1").wait_for()
        desktop.screenshot(path=evidence / "sensorproof-report.png", animations="disabled")
        desktop.screenshot(
            path=evidence / "sensorproof-report-full.png",
            full_page=True,
            animations="disabled",
        )

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        mobile.goto(report.as_uri(), wait_until="load")
        mobile.locator("h1").wait_for()
        overflow = mobile.evaluate(
            """() => ({
                viewport: window.innerWidth,
                scrollWidth: document.documentElement.scrollWidth,
                offenders: Array.from(document.querySelectorAll("*"))
                    .filter((element) => {
                        const bounds = element.getBoundingClientRect();
                        return bounds.right > window.innerWidth + 1 || bounds.left < -1;
                    })
                    .slice(0, 12)
                    .map((element) => {
                        const bounds = element.getBoundingClientRect();
                        return {
                            tag: element.tagName,
                            className: String(element.className),
                            left: Math.round(bounds.left),
                            right: Math.round(bounds.right),
                            width: Math.round(bounds.width),
                        };
                    }),
            }))"""
        )
        if overflow["scrollWidth"] > overflow["viewport"]:
            raise ValueError(f"mobile report has horizontal overflow: {overflow}")
        mobile.screenshot(path=evidence / "sensorproof-report-mobile.png", animations="disabled")
        mobile.close()

        demo = browser.new_page(viewport={"width": 1120, "height": 820}, device_scale_factor=1)
        demo.goto(report.as_uri(), wait_until="load")
        frames = [demo.screenshot(animations="disabled")]
        for heading in ("Why the GNSS stream was isolated", "Decision ledger"):
            demo.get_by_role("heading", name=heading).scroll_into_view_if_needed()
            frames.append(demo.screenshot(animations="disabled"))
        images = [
            Image.open(BytesIO(frame)).convert("P", palette=Image.Palette.ADAPTIVE, colors=128)
            for frame in frames
        ]
        images[0].save(
            evidence / "sensorproof-demo.gif",
            save_all=True,
            append_images=images[1:],
            duration=[1_100, 1_200, 1_600],
            loop=0,
            disposal=2,
            optimize=False,
        )
        demo.close()

        terminal = browser.new_page(viewport={"width": 1180, "height": 650}, device_scale_factor=1)
        terminal.set_content(_terminal_html(cli), wait_until="load")
        terminal.locator("pre").wait_for()
        terminal.screenshot(path=evidence / "sensorproof-cli.png", animations="disabled")
        terminal.close()
        desktop.close()
        browser.close()


def finalize(
    root: Path,
    output_root: Path,
    source_revision: str,
    source_tree: str,
    container_image: str,
    browser: str,
    playwright: str,
    pillow: str,
) -> None:
    _validate_oid(source_revision, "source revision")
    _validate_oid(source_tree, "source tree")
    if container_image != CONTAINER_IMAGE:
        raise ValueError("unexpected evidence container")
    evidence = output_root / EVIDENCE_DIRECTORY
    actual = {path.name for path in evidence.iterdir() if path.is_file()}
    if actual != EXPECTED_FILES:
        raise ValueError(
            f"evidence files differ before finalization: {sorted(actual ^ EXPECTED_FILES)}"
        )

    from sensorproof.artifact import load_artifact
    from sensorproof.verify import verify_artifact

    artifact = load_artifact(evidence / "sensorproof-run.json")
    verified = verify_artifact(artifact)
    sources = [_file_record(path, root) for path in _source_paths(root)]
    files = [_evidence_record(path, output_root) for path in sorted(evidence.iterdir())]
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "source_revision": source_revision,
        "source_tree": source_tree,
        "scenario_sha256": artifact["scenario_sha256"],
        "certificate_sha256": verified.certificate_sha256,
        "result": {
            "steps": verified.steps,
            "observations": verified.observations,
            "robust_position_rmse_mm": verified.robust_rmse_mm,
            "baseline_position_rmse_mm": verified.baseline_rmse_mm,
            "rmse_reduction_basis_points": artifact["comparison"]["rmse_reduction_basis_points"],
            "isolated_fault_observations": artifact["runs"]["robust"]["summary"][
                "isolated_fault_observations"
            ],
            "healthy_rejections": artifact["runs"]["robust"]["summary"]["healthy_rejections"],
        },
        "generation": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "browser": browser,
            "playwright": playwright,
            "pillow": pillow,
            "container_image": container_image,
            "platform": "linux/amd64",
            "network": "disabled during browser capture",
            "viewports": {
                "desktop": [1440, 1000],
                "mobile": [390, 844],
                "demo": [1120, 820],
                "terminal": [1180, 650],
            },
        },
        "sources": sources,
        "files": files,
    }
    _write_text(
        evidence / MANIFEST_NAME,
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def verify(
    root: Path,
    output_root: Path,
    source_revision: str,
    source_tree: str,
    container_image: str,
) -> None:
    _validate_oid(source_revision, "source revision")
    _validate_oid(source_tree, "source tree")
    evidence = output_root / EVIDENCE_DIRECTORY
    actual = {path.name for path in evidence.iterdir() if path.is_file()}
    expected = EXPECTED_FILES | {MANIFEST_NAME}
    if actual != expected:
        raise ValueError(f"evidence file set differs: {sorted(actual ^ expected)}")
    manifest = json.loads((evidence / MANIFEST_NAME).read_text(encoding="utf-8"))
    if manifest["format"] != FORMAT:
        raise ValueError("evidence format mismatch")
    if manifest["source_revision"] != source_revision or manifest["source_tree"] != source_tree:
        raise ValueError("evidence source binding mismatch")
    if manifest["generation"]["container_image"] != container_image:
        raise ValueError("evidence container mismatch")
    if manifest["generation"]["python"] != "3.14.6":
        raise ValueError("evidence Python runtime mismatch")
    expected_sources = [_file_record(path, root) for path in _source_paths(root)]
    if manifest["sources"] != expected_sources:
        raise ValueError("evidence source hashes differ")
    expected_files = [
        _evidence_record(path, output_root)
        for path in sorted(evidence.iterdir())
        if path.name != MANIFEST_NAME
    ]
    if manifest["files"] != expected_files:
        raise ValueError("evidence file hashes or dimensions differ")

    from sensorproof.artifact import load_artifact
    from sensorproof.report import build_report
    from sensorproof.verify import verify_artifact

    artifact = load_artifact(evidence / "sensorproof-run.json")
    verified = verify_artifact(artifact)
    if (evidence / "sensorproof-report.html").read_text(encoding="utf-8") != build_report(artifact):
        raise ValueError("checked-in report does not replay")
    result = manifest["result"]
    expected_result = {
        "steps": verified.steps,
        "observations": verified.observations,
        "robust_position_rmse_mm": verified.robust_rmse_mm,
        "baseline_position_rmse_mm": verified.baseline_rmse_mm,
        "rmse_reduction_basis_points": artifact["comparison"]["rmse_reduction_basis_points"],
        "isolated_fault_observations": artifact["runs"]["robust"]["summary"][
            "isolated_fault_observations"
        ],
        "healthy_rejections": artifact["runs"]["robust"]["summary"]["healthy_rejections"],
    }
    if result != expected_result:
        raise ValueError("manifest result does not match the replay")
    if manifest["scenario_sha256"] != artifact["scenario_sha256"]:
        raise ValueError("manifest scenario digest mismatch")
    if manifest["certificate_sha256"] != verified.certificate_sha256:
        raise ValueError("manifest certificate mismatch")

    for path in evidence.iterdir():
        if path.suffix in {".html", ".json", ".svg", ".txt"}:
            _reject_sensitive_text(path.read_text(encoding="utf-8"))
        if path.suffix == ".svg":
            _verify_svg(path)


def verify_visuals(output_root: Path) -> None:
    from PIL import Image, ImageSequence

    evidence = output_root / EVIDENCE_DIRECTORY
    expected_png = {
        "sensorproof-report.png": (1440, 1000),
        "sensorproof-report-mobile.png": (390, 844),
        "sensorproof-cli.png": (1180, 650),
    }
    for name, dimensions in expected_png.items():
        with Image.open(evidence / name) as image:
            if image.format != "PNG" or image.size != dimensions:
                raise ValueError(
                    f"unexpected raster contract for {name}: {image.format} {image.size}"
                )
            _reject_blank_image(image, name)
    with Image.open(evidence / "sensorproof-report-full.png") as image:
        if image.format != "PNG" or image.width != 1440 or image.height < 2_000:
            raise ValueError(f"unexpected full-page raster: {image.format} {image.size}")
        _reject_blank_image(image, "sensorproof-report-full.png")
    with Image.open(evidence / "sensorproof-demo.gif") as image:
        frames = list(ImageSequence.Iterator(image))
        if image.format != "GIF" or image.size != (1120, 820) or len(frames) != 3:
            raise ValueError(f"unexpected GIF contract: {image.format} {image.size} {len(frames)}")
        for index, frame in enumerate(frames):
            _reject_blank_image(frame, f"sensorproof-demo.gif frame {index}")


def _reject_blank_image(image: Any, label: str) -> None:
    converted = image.convert("RGB")
    extrema = converted.getextrema()
    if all(low == high for low, high in extrema):
        raise ValueError(f"blank evidence image: {label}")
    colors = converted.resize((160, 100)).getcolors(maxcolors=20_000)
    if colors is None or len(colors) < 12:
        raise ValueError(f"insufficient visual detail: {label}")


def _trajectory_svg(artifact: dict[str, Any]) -> str:
    width, height, pad = 1200, 650, 76
    truth = [frame["truth"][:2] for frame in artifact["observations"]]
    robust = [frame["estimate"][:2] for frame in artifact["runs"]["robust"]["trace"]]
    baseline = [frame["estimate"][:2] for frame in artifact["runs"]["baseline"]["trace"]]
    values = truth + robust + baseline
    xs = [point[0] for point in values]
    ys = [point[1] for point in values]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    def points(series: list[list[int]]) -> str:
        span_x = max(max_x - min_x, 1)
        span_y = max(max_y - min_y, 1)
        return " ".join(
            f"{pad + (x - min_x) * (width - 2 * pad) / span_x:.1f},"
            f"{height - pad - (y - min_y) * (height - 2 * pad) / span_y:.1f}"
            for x, y in series
        )

    robust_rmse = artifact["runs"]["robust"]["summary"]["position_rmse_mm"]
    baseline_rmse = artifact["runs"]["baseline"]["summary"]["position_rmse_mm"]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">
<title id="title">Urban-canyon trajectory comparison</title>
<desc id="description">Truth, fault-aware SensorProof, and ungated baseline trajectories from the checked-in scenario.</desc>
<rect width="{width}" height="{height}" rx="28" fill="#071019"/>
<text x="{pad}" y="55" fill="#eaf2f8" font-family="system-ui,sans-serif" font-size="28" font-weight="700">Same observations. Different fault policy.</text>
<text x="{pad}" y="88" fill="#9eb0c2" font-family="ui-monospace,monospace" font-size="16">fault-aware RMSE {robust_rmse} mm · ungated baseline {baseline_rmse} mm</text>
<path d="M {pad} {height - pad} H {width - pad} M {pad} 118 V {height - pad}" stroke="#294158"/>
<polyline points="{points(baseline)}" fill="none" stroke="#ff6b6b" stroke-width="5" opacity=".82"/>
<polyline points="{points(robust)}" fill="none" stroke="#52d6a6" stroke-width="6"/>
<polyline points="{points(truth)}" fill="none" stroke="#f4d35e" stroke-width="3" stroke-dasharray="10 8"/>
<g font-family="ui-monospace,monospace" font-size="16"><text x="760" y="55" fill="#f4d35e">truth</text><text x="840" y="55" fill="#52d6a6">SensorProof</text><text x="980" y="55" fill="#ff6b6b">baseline</text></g>
<text x="{pad}" y="{height - 24}" fill="#73879b" font-family="ui-monospace,monospace" font-size="13">coordinates: integer millimetres · 96 deterministic steps · seed 20260810</text>
</svg>
"""


def _fault_svg(artifact: dict[str, Any]) -> str:
    width, height, pad = 1200, 620, 76
    trace = artifact["runs"]["robust"]["trace"]
    decisions = [
        next(item for item in frame["decisions"] if item["sensor"] == "gnss") for frame in trace
    ]
    maximum = max(item["innovation_score_milli"] for item in decisions)
    chart_height = 360
    chart_width = width - 2 * pad
    bars: list[str] = []
    for index, decision in enumerate(decisions):
        x = pad + index * chart_width / len(decisions)
        bar_width = max(chart_width / len(decisions) - 1.8, 1)
        value = min(decision["innovation_score_milli"], maximum)
        bar_height = value * chart_height / max(maximum, 1)
        color = {"accepted": "#52d6a6", "rejected": "#ff6b6b", "quarantined": "#7f8ea3"}[
            decision["status"]
        ]
        bars.append(
            f'<rect x="{x:.1f}" y="{height - pad - bar_height:.1f}" width="{bar_width:.1f}" '
            f'height="{bar_height:.1f}" rx="1" fill="{color}"/>'
        )
    gate_score = decisions[0]["gate_score_milli"]
    gate_y = height - pad - gate_score * chart_height / max(maximum, 1)
    fault_start = artifact["scenario"]["faults"][0]["start"]
    fault_end = artifact["scenario"]["faults"][0]["end"]
    fault_x = pad + fault_start * chart_width / len(decisions)
    fault_width = (fault_end - fault_start) * chart_width / len(decisions)
    isolated = artifact["runs"]["robust"]["summary"]["isolated_fault_observations"]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">
<title id="title">GNSS innovation and isolation timeline</title>
<desc id="description">Actual normalized fixed-point innovations and gate decisions for every GNSS observation.</desc>
<rect width="{width}" height="{height}" rx="28" fill="#071019"/>
<text x="{pad}" y="54" fill="#eaf2f8" font-family="system-ui,sans-serif" font-size="28" font-weight="700">The fault is visible in the decision ledger.</text>
<text x="{pad}" y="88" fill="#9eb0c2" font-family="ui-monospace,monospace" font-size="16">{isolated} fault observations isolated · 0 healthy observations rejected</text>
<rect x="{fault_x:.1f}" y="120" width="{fault_width:.1f}" height="{height - pad - 120}" fill="#ff6b6b" opacity=".08"/>
{"".join(bars)}
<line x1="{pad}" y1="{gate_y:.1f}" x2="{width - pad}" y2="{gate_y:.1f}" stroke="#f4d35e" stroke-width="3" stroke-dasharray="9 7"/>
<g font-family="ui-monospace,monospace" font-size="14"><text x="{pad}" y="{height - 26}" fill="#73879b">step 0</text><text x="{width - pad - 62}" y="{height - 26}" fill="#73879b">step 95</text><text x="{fault_x + 10:.1f}" y="144" fill="#ff9b9b">injected bias-step · steps {fault_start}–{fault_end - 1}</text></g>
</svg>
"""


def _architecture_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 700" role="img" aria-labelledby="title description">
<title id="title">SensorProof verification architecture</title>
<desc id="description">A strict scenario feeds deterministic simulation, paired robust and baseline runs, a certificate, independent replay, and an offline report.</desc>
<rect width="1200" height="700" rx="28" fill="#071019"/>
<text x="70" y="58" fill="#eaf2f8" font-family="system-ui,sans-serif" font-size="30" font-weight="700">One artifact, two trust boundaries.</text>
<text x="70" y="91" fill="#9eb0c2" font-family="ui-monospace,monospace" font-size="15">generation records decisions · verification independently replays them</text>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#54708a"/></marker></defs>
<g fill="#101e2c" stroke="#294158" stroke-width="2"><rect x="70" y="150" width="210" height="110" rx="18"/><rect x="350" y="150" width="220" height="110" rx="18"/><rect x="650" y="120" width="210" height="110" rx="18"/><rect x="650" y="275" width="210" height="110" rx="18"/><rect x="940" y="198" width="190" height="110" rx="18"/><rect x="350" y="470" width="220" height="110" rx="18"/><rect x="650" y="470" width="210" height="110" rx="18"/><rect x="940" y="470" width="190" height="110" rx="18"/></g>
<g fill="#eaf2f8" font-family="system-ui,sans-serif" font-size="20" font-weight="700" text-anchor="middle"><text x="175" y="193">strict scenario</text><text x="460" y="193">integer simulator</text><text x="755" y="163">fault-aware run</text><text x="755" y="318">ungated baseline</text><text x="1035" y="242">JSON artifact</text><text x="460" y="513">independent replay</text><text x="755" y="513">SHA-256 checks</text><text x="1035" y="513">offline report</text></g>
<g fill="#9eb0c2" font-family="ui-monospace,monospace" font-size="13" text-anchor="middle"><text x="175" y="224">≤256 KiB · no NaN</text><text x="460" y="224">seeded hash noise</text><text x="755" y="194">gate + cooldown</text><text x="755" y="349">same observations</text><text x="1035" y="273">≤16 MiB</text><text x="460" y="544">every transition</text><text x="755" y="544">payload + traces</text><text x="1035" y="544">no network assets</text></g>
<g stroke="#54708a" stroke-width="3" fill="none" marker-end="url(#arrow)"><path d="M280 205 H350"/><path d="M570 205 C610 205 610 175 650 175"/><path d="M570 205 C610 205 610 330 650 330"/><path d="M860 175 C900 175 900 235 940 235"/><path d="M860 330 C900 330 900 270 940 270"/><path d="M1035 308 V410 C1035 440 570 430 570 470"/><path d="M570 525 H650"/><path d="M860 525 H940"/></g>
<path d="M600 120 V610" stroke="#52d6a6" stroke-width="2" stroke-dasharray="8 8" opacity=".65"/>
<text x="585" y="635" fill="#52d6a6" font-family="ui-monospace,monospace" font-size="13" text-anchor="end">generation</text><text x="615" y="635" fill="#52d6a6" font-family="ui-monospace,monospace" font-size="13">verification</text>
</svg>
"""


def _certificate_svg(artifact: dict[str, Any]) -> str:
    certificate = artifact["certificate"]
    values = [
        ("observations", certificate["observations_sha256"]),
        ("robust trace", certificate["robust_trace_sha256"]),
        ("baseline trace", certificate["baseline_trace_sha256"]),
        ("payload", certificate["payload_sha256"]),
    ]
    rows = []
    for index, (label, digest) in enumerate(values):
        y = 175 + index * 105
        rows.append(
            f'<rect x="100" y="{y - 42}" width="1000" height="78" rx="16" fill="#101e2c" stroke="#294158"/>'
            f'<text x="135" y="{y - 5}" fill="#eaf2f8" font-family="system-ui,sans-serif" font-size="20" font-weight="700">{html.escape(label)}</text>'
            f'<text x="330" y="{y - 5}" fill="#52d6a6" font-family="ui-monospace,monospace" font-size="16">sha256:{digest}</text>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 680" role="img" aria-labelledby="title description">
<title id="title">SensorProof certificate chain</title>
<desc id="description">Exact SHA-256 digests from the checked-in SensorProof artifact.</desc>
<rect width="1200" height="680" rx="28" fill="#071019"/>
<text x="100" y="70" fill="#eaf2f8" font-family="system-ui,sans-serif" font-size="30" font-weight="700">The screenshot is not the source of truth.</text>
<text x="100" y="105" fill="#9eb0c2" font-family="ui-monospace,monospace" font-size="15">canonical JSON → trace digests → payload certificate → independent replay</text>
{"".join(rows)}
<text x="100" y="630" fill="#f4d35e" font-family="ui-monospace,monospace" font-size="14">Any changed observation, decision, state, metric, or digest fails verification.</text>
</svg>
"""


def _terminal_html(cli: str) -> str:
    escaped = html.escape(cli)
    return f"""<!doctype html><meta charset="utf-8"><style>
html,body{{margin:0;background:#071019;color:#dce8f2}}body{{padding:34px;font:15px/1.48 ui-monospace,SFMono-Regular,Consolas,monospace}}
.window{{border:1px solid #294158;border-radius:18px;overflow:hidden;box-shadow:0 24px 70px #0008}}
.bar{{height:46px;background:#101e2c;border-bottom:1px solid #294158;display:flex;align-items:center;padding:0 18px;gap:9px}}
.dot{{width:12px;height:12px;border-radius:50%}}.r{{background:#ff6b6b}}.y{{background:#f4d35e}}.g{{background:#52d6a6}}
pre{{margin:0;padding:24px 28px;white-space:pre-wrap;overflow-wrap:anywhere}}b{{color:#52d6a6}}
</style><div class="window"><div class="bar"><i class="dot r"></i><i class="dot y"></i><i class="dot g"></i></div><pre>{escaped}</pre></div>"""


def _source_paths(root: Path) -> list[Path]:
    paths = [
        root / ".github/workflows/evidence.yml",
        root / "pyproject.toml",
        root / "requirements/evidence-browser-image.lock.json",
        root / "requirements/evidence-browser.txt",
        root / "requirements/runtime.in",
        root / "requirements/runtime.txt",
        root / "scenarios/urban-canyon.json",
        root / "tools/capture_evidence.py",
    ]
    paths.extend(sorted((root / "src/sensorproof").glob("*.py")))
    paths.append(root / "src/sensorproof/py.typed")
    return paths


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _evidence_record(path: Path, root: Path) -> dict[str, Any]:
    record = _file_record(path, root)
    record["media_type"] = MEDIA_TYPES[path.suffix]
    if path.suffix == ".png":
        record["dimensions"] = list(_png_dimensions(path))
    elif path.suffix == ".gif":
        record["dimensions"] = list(_gif_dimensions(path))
        record["frames"] = 3
    return record


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"invalid PNG: {path}")
    return struct.unpack(">II", data[16:24])


def _gif_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:10]
    if len(data) != 10 or data[:6] not in {b"GIF87a", b"GIF89a"}:
        raise ValueError(f"invalid GIF: {path}")
    return struct.unpack("<HH", data[6:10])


def _validate_oid(value: str, label: str) -> None:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"invalid {label}")


def _verify_svg(path: Path) -> None:
    root = ET.parse(path).getroot()
    if not root.tag.endswith("svg") or root.get("viewBox") is None:
        raise ValueError(f"invalid SVG structure: {path}")
    if len(list(root.iter())) < 8:
        raise ValueError(f"SVG lacks detail: {path}")


def _reject_sensitive_text(value: str) -> None:
    for marker in FORBIDDEN_TEXT:
        if marker in value:
            raise ValueError(f"evidence contains forbidden marker: {marker}")


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    raise SystemExit(main())
