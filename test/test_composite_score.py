from open_source_risk_model.score import compute_composite_risk, classify_overall_risk

raw = {
    "days_since_last_push": 0.0,
    "stargazers_count": 31000,
    "contributors_count": 1819,
    "archived": False,
    "open_issues_count": 2100,
    "license_spdx_id": "BSD-3-Clause",
}

result = compute_composite_risk(raw)
label = classify_overall_risk(result["overall_risk"])

print(f"Overall risk: {result['overall_risk']:.3f} ({label})")
print("Per-feature risk:")
for k, v in result["feature_risks"].items():
    print(f"  {k:20} -> {v:.3f}")

print("Weighted contributions:")
for k, v in result["weighted_breakdown"].items():
    print(f"  {k:20} -> {v:.3f}")
