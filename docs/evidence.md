# Reproducible visual evidence

The files in `docs/evidence/` are generated outputs, not mockups. They are committed so a reviewer can inspect the result without installing the project, while the workflow prevents them from drifting away from the implementation.

## Evidence set

| File | Source |
| --- | --- |
| `sensorproof-run.json` | Actual `sensorproof run` artifact |
| `sensorproof-cli.txt` | Actual run, verify, and report stdout |
| `sensorproof-report.html` | Report rendered only after artifact verification |
| `trajectory.svg` | Truth and both estimates read from the artifact |
| `fault-isolation.svg` | Every recorded GNSS innovation and status |
| `architecture.svg` | Diagram of the implemented generation/replay boundaries |
| `certificate-chain.svg` | Exact digests stored in the artifact |
| `sensorproof-report*.png` | Real Chromium captures at declared viewports |
| `sensorproof-cli.png` | Browser capture of the actual CLI transcript |
| `sensorproof-demo.gif` | Three real report viewports, not an animated mockup |
| `sensorproof-evidence.json` | Source binding, environment, dimensions, sizes, and SHA-256 records |

## Generation boundary

The permanent `SensorProof evidence` workflow:

1. checks out the exact PR or main SHA with credentials disabled;
2. installs the application with the hash-locked quality environment on CPython 3.14.6;
3. runs the checked-in scenario and verifies its artifact;
4. downloads five hash-locked evidence wheels with CPython 3.12.3;
5. pulls the Playwright image by its amd64 platform digest;
6. starts the container with no network, read-only root, all Linux capabilities dropped, no privilege escalation, bounded processes/CPU/memory, and explicit temporary filesystems;
7. captures Chromium 151.0.7922.34 output with Playwright 1.62.0 and Pillow 12.3.0;
8. verifies dimensions, frame count, visual detail, SVG structure, forbidden secret/path markers, artifact replay, and source/file hashes;
9. regenerates the complete set and byte-compares all 13 files.

The browser image lock is recorded in `requirements/evidence-browser-image.lock.json`. The exact platform manifest digest is also stored in the evidence manifest.

## Source binding

The manifest records:

- the last commit that changed an evidence source;
- that commit's complete Git tree;
- SHA-256 and byte length for each relevant source file;
- SHA-256, media type, dimensions, and byte length for every evidence output;
- the experiment certificate and exact metrics;
- the runtime, browser, image, platform, and viewports.

Evidence-only commits do not create a self-reference: source revision is derived from the scenario, package, runtime locks, permanent workflow, and generator, not from `docs/evidence/`.

## Privacy and authenticity

The generator rejects common credential prefixes, private-key markers, and absolute home-directory paths from textual evidence. The scenario is fully synthetic and contains no personal data, GPS traces, external dataset rows, account identifiers, or API calls.

Raster files were also manually inspected at their original dimensions before release. Structural SVG checks are automated; the SVG source is human-readable and data-bound.

## Updating evidence

Any change to the scenario, engine, verifier, renderer, runtime lock, capture code, or evidence workflow must regenerate the evidence set in the same change. A PR with stale outputs fails `Visual evidence drift (Chromium 151)`.

Do not edit generated PNG, GIF, SVG, HTML, JSON, transcript, or manifest files by hand.
