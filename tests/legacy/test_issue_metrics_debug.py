#!/usr/bin/env python
"""Quick debug script to test issue metrics computation"""

from open_source_risk_model.issues.metrics import compute_issue_metrics

metrics = compute_issue_metrics('data/issues/numpy__numpy', window_days=365)

print('Computed metrics:')
for k, v in metrics.items():
    print(f'  {k}: {v:.4f}')

print(f'\nTotal metrics computed: {len(metrics)}')
print('\nExpected 4 metrics:')
print('  - avg_time_to_first_maintainer_response_days')
print('  - fraction_unanswered_after_30d')
print('  - median_time_to_close_days')
print('  - open_issue_age_p90_days')
