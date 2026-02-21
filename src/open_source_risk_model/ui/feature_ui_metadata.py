# src/open_source_risk_model/ui/feature_ui_metadata.py

FEATURE_UI_METADATA: dict[str, dict] = {
    # --- Activity / Release ---
    "days_since_last_push": {
        "category": "Activity",
        "unit": "days",
        "explanation": "How recently the repository was updated. Longer gaps increase risk.",
        "interpretation": {
            "direction": "higher_is_worse",
            "bands": [
                {"label": "good", "max": 7},
                {"label": "ok", "max": 30},
                {"label": "risky", "max": None},
            ],
        },
    },
    "days_since_last_release": {
        "category": "Release",
        "unit": "days",
        "explanation": "Time since the last tagged release. Long gaps can indicate slower delivery.",
        "interpretation": {
            "direction": "higher_is_worse",
            "bands": [
                {"label": "good", "max": 30},
                {"label": "ok", "max": 120},
                {"label": "risky", "max": None},
            ],
        },
    },

    # --- Issues ---
    "fraction_issues_closed_12mo": {
        "category": "Issues",
        "unit": "ratio",
        "explanation": "Issue throughput signal. Lower closure fraction increases risk.",
        "interpretation": {
            "direction": "lower_is_worse",
            "bands": [
                {"label": "risky", "max": 0.30},
                {"label": "ok", "max": 0.60},
                {"label": "good", "max": 1.00},
            ],
        },
    },
    "fraction_open_issues_stale_180d": {
        "category": "Issues",
        "unit": "ratio",
        "explanation": "Backlog staleness signal. Higher stale fraction increases risk.",
        # Interpretation intentionally omitted for v1
    },
    "issues_per_contributor": {
        "category": "Issues",
        "unit": "issues/contributor",
        "explanation": "Approximates maintainer load. Higher load per contributor increases risk.",
        # Interpretation intentionally omitted for v1
    },
    "avg_time_to_first_maintainer_response_days": {
        "category": "Issues",
        "unit": "days",
        "explanation": "Responsiveness signal from issues. Slower first response increases risk.",
        # Interpretation intentionally omitted for v1
    },
    "fraction_unanswered_after_30d": {
        "category": "Issues",
        "unit": "ratio",
        "explanation": "Share of issues with no maintainer response after 30 days. Higher fraction increases risk.",
        # Interpretation intentionally omitted for v1
    },
    "median_time_to_close_days": {
        "category": "Issues",
        "unit": "days",
        "explanation": "Time to resolve issues. Longer closure times increase risk.",
        # Interpretation intentionally omitted for v1
    },
    "open_issue_age_p90_days": {
        "category": "Issues",
        "unit": "days",
        "explanation": "Age of older open issues (p90). Higher values indicate a stale backlog.",
        # Interpretation intentionally omitted for v1
    },

    # --- Contributors ---
    "contributors_last_12mo": {
        "category": "Contributors",
        "unit": "count",
        "explanation": "Number of contributors in the last 12 months. Fewer contributors increases risk.",
        # Interpretation intentionally omitted for v1
    },
    "top_contributor_fraction_12mo": {
        "category": "Contributors",
        "unit": "ratio",
        "explanation": "Bus factor proxy. Higher contribution concentration increases risk.",
        "interpretation": {
            "direction": "higher_is_worse",
            "bands": [
                {"label": "good", "max": 0.20},
                {"label": "ok", "max": 0.35},
                {"label": "risky", "max": None},
            ],
        },
    },

    # --- Governance / Status ---
    "archived": {
        "category": "Governance",
        "unit": "boolean",
        "explanation": "Archived repositories are higher risk for ongoing maintenance.",
        "interpretation": {
            "direction": "boolean",
            "bands": [
                {"label": "good", "max": False},
                {"label": "risky", "max": True},
            ],
        },
    },

    # --- Popularity ---
    "stars_count": {
        "category": "Popularity",
        "unit": "count",
        "explanation": "Stars are a weak proxy for adoption or community interest. Lower stars can increase risk slightly.",
        # Interpretation intentionally omitted for v1
    },
}

DEFAULT_UI_METADATA = {
    "category": "Other",
    "unit": None,
    "explanation": None,
    "interpretation": None,
}
