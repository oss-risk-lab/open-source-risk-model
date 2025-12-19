from open_source_risk_model.feature_mappings.dispatcher import compute_feature_risk

VALUES = [0, 1, 5, 10, 20, 50, 100, 150, 200, 500]

for v in VALUES:
    r = compute_feature_risk("open_issues_count", v)
    print(f"{v:4d} open issues -> risk={r:.3f}")
