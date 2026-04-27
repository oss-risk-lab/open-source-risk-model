from open_source_risk_model.feature_mappings.dispatcher import compute_feature_risk

VALUES = [0, 1, 10, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 2500]

for v in VALUES:
    r = compute_feature_risk("stars_count", v)
    print(f"{v:6d} stars -> risk={r:.3f}")
