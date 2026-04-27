from open_source_risk_model.feature_mappings.dispatcher import compute_feature_risk

licenses = [
    "MIT",
    "Apache-2.0",
    "GPL-3.0",
    "AGPL-3.0",
    None,
    "Unknown",
]

for l in licenses:
    r = compute_feature_risk("license_risk", l)
    print(f"{l!r:12} -> risk={r:.3f}")
