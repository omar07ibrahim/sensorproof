# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| Development snapshots | Best effort |

## Reporting a vulnerability

Please use GitHub's **Report a vulnerability** flow in the Security tab. Do not open a public issue for a suspected input-validation bypass, artifact-verification bypass, path-handling flaw, dependency compromise, or credential exposure.

Include:

- the affected command and version;
- a minimal synthetic input or artifact;
- the expected and observed behavior;
- whether the issue can alter a verified result or write outside the requested output path.

No production service is operated from this repository, so there is no live account, endpoint, or uptime incident channel.

## Security boundaries

SensorProof treats scenario and artifact files as untrusted and enforces:

- strict UTF-8 and JSON;
- duplicate-key and non-finite-number rejection;
- exact schema keys and integer types;
- bounded file size, step, sensor, fault, and motion counts;
- atomic output replacement;
- complete transition replay before a report is rendered;
- canonical payload and trace digests.

The package has no third-party runtime dependency, network client, telemetry, dynamic plugin loader, shell invocation, or model download.

The evidence workflow has a separate supply-chain boundary: exact actions SHAs, hash-locked Python wheels, a digest-pinned amd64 browser image, read-only container root, no browser-capture network, dropped Linux capabilities, and bounded resources.

## Operational warning

This software is not certified for localization, navigation, control, collision avoidance, or any other safety decision. The synthetic scenario is not a hardware safety case. Operators must not use SensorProof in a vehicle or robot control loop without domain-specific validation, calibrated uncertainty, hardware-in-the-loop tests, redundancy analysis, and independent safety review.
