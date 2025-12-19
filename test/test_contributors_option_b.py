from open_source_risk_model.feature_mappings.dispatcher import compute_feature_risk

VALUES = [1, 2, 3, 5, 8, 10, 20, 50]

for v in VALUES:
    r = compute_feature_risk("contributors_count", v)
    print(f"{v:4d} contributors -> risk={r:.3f}")
