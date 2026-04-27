from open_source_risk_model.feature_mappings.dispatcher import compute_feature_risk

for v in [0.0, 1.0]:
    r = compute_feature_risk("archived", v)
    print(f"archived={int(v)} -> risk={r:.3f}")
