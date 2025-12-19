# Open Source Risk Model

A modular risk-scoring engine for evaluating open-source software repositories using GitHub metadata.

This project ingests repository-level signals (activity, contributors, issues, licensing, etc.), maps them to normalized risk scores using configurable strategies, and aggregates them into a composite risk score suitable for comparison and analysis.

---

## Project Goals

- Provide a transparent, explainable framework for open-source risk assessment
- Support multiple feature-to-risk mapping strategies
- Enable reproducible scoring via baseline population distributions
- Serve as a foundation for experimentation, calibration, and evaluation

---

## High-Level Architecture

GitHub API -> Feature Ingestion -> Feature-to-Risk Mapping (Option A/B/C) -> Composite Scoring -> Evaluation & Analysis


---

## Core Concepts

### Feature Ingestion
Repository metadata is collected using the GitHub API, including:
- activity recency
- contributor counts
- issue statistics
- licensing information
- popularity signals

### Feature-to-Risk Mapping
Each raw feature is converted into a normalized risk score in `[0, 1]` using configurable mapping strategies:

- **Option A**: anchor-based monotonic mappings
- **Option B**: population-aware percentile mappings
- **Option C**: alternative / experimental mapping approach

> Option A and Option B are currently used in the default scoring pipeline.  
> Option C is fully implemented and tested but not active by default.

### Composite Scoring
Individual feature risks are combined into a weighted composite score using configuration-driven weights.

---

## Repository Structure

- `src/open_source_risk_model/`  
  Core library code (ingestion, mappings, scoring, utilities)

- `data/baseline/`  
  Baseline population distributions used for calibration and normalization

- `test/`  
  Unit tests and validation scripts for features, mappings, and scoring logic

- `spikes/`  
  Exploratory and evaluation scripts (non-library entry points)

- `docs/`  
  Project documentation, including a detailed file-by-file guide

---

## Documentation

A detailed description of every module, script, and configuration file is available here:

**`docs/File_Guide.docx`**

---

## Design Notes

- Baseline population files are intentionally committed to ensure reproducibility
- Alternative mapping strategies are retained to support future experimentation
- Emphasis is placed on transparency and explainability over black-box modeling

---

## Status

This project is under active development.  
APIs, configurations, and scoring logic may evolve as calibration and evaluation continue.

---

## License

MIT License (or update as appropriate)
