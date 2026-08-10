# ADR 0001: Use bounded fixed-point replay

- Status: accepted
- Date: 2026-08-10

## Context

A portfolio-grade fault-isolation demonstration needs reviewers to distinguish an algorithmic result from plotting noise, hidden random state, dependency drift, and hand-edited output. A conventional floating-point matrix stack would be more familiar, but exact byte replay across supported Python versions and evidence regeneration would become harder to audit.

## Decision

SensorProof v0.1.0 uses:

- integer millimetres and millimetres/second for state and observations;
- explicit half-away-from-zero division;
- fixed integer gains;
- hash-derived bounded noise;
- canonical JSON and SHA-256 certificates;
- an independently implemented transition replay.

The release presents this as an inspectable alpha-beta fault-isolation lab, not as a Kalman filter.

## Consequences

Positive:

- every state transition and metric is exactly reproducible;
- the runtime has no third-party dependency;
- artifacts can be verified offline;
- tampering is detected at observation, trace, summary, and payload levels.

Negative:

- there is no covariance propagation or statistically calibrated uncertainty;
- fixed gains do not adapt to changing sensor regimes;
- integer quantization and the configured gate are part of the model;
- more advanced fault types require a new estimator rather than a documentation claim.

A future probabilistic estimator may be added as a separately named engine with tolerance-aware verification; it must not silently change the v1 artifact contract.
