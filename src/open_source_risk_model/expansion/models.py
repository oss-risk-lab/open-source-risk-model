"""Data models for dataset expansion."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any


@dataclass
class SelectionCriteria:
    """Criteria for repository selection."""
    min_stars: int = 1000
    max_days_since_commit: int = 365  # 1 year (renamed from min_commit_age_days for clarity)
    required_ecosystems: List[str] = field(default_factory=lambda: [
        'npm', 'pypi', 'go', 'maven', 'rubygems'
    ])
    ecosystem_targets: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        'npm': (0.25, 0.40),
        'pypi': (0.25, 0.40),
        'go': (0.10, 1.0),
        'maven': (0.10, 1.0),
        'rubygems': (0.05, 1.0)
    })
    exclude_forks: bool = True
    exclude_duplicate_graphs: bool = True


@dataclass
class RepositoryCandidate:
    """Repository candidate for selection."""
    full_name: str
    stars: int
    last_commit_date: datetime
    primary_ecosystem: str  # Primary ecosystem for distribution counting
    manifest_types: List[str]  # All detected manifest types
    has_prod_deps: bool
    is_fork: bool
    fork_parent: Optional[str]
    priority_score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HubPackage:
    """Package used across many repositories."""
    package_name: str
    registry_type: str
    repo_count: int
    usage_percentage: float


@dataclass
class FootprintMetric:
    """Transitive dependency footprint for a package."""
    package_name: str
    registry_type: str
    transitive_count: int
    direct_dependents: int


@dataclass
class EcosystemPattern:
    """Ecosystem-specific dependency pattern."""
    ecosystem: str
    pattern_type: str
    description: str
    example_repos: List[str]
    occurrence_count: int


@dataclass
class ValidationFailure:
    """Details of a validation failure."""
    check_name: str
    expected: Any
    actual: Any
    message: str


@dataclass
class PerformanceMetrics:
    """Query performance metrics."""
    pattern_results: Dict[str, Dict[str, float]]
    max_duration: float
    avg_duration: float
    passed: bool
    measurement_note: str = "End-to-end query time including Python overhead"


@dataclass
class CountValidation:
    """Repository and dependency count validation."""
    passed: bool
    repo_count: int
    expected_repo_count: int
    dependency_count: int
    min_dependency_count: int
    max_dependency_count: int


@dataclass
class EcosystemValidation:
    """Ecosystem distribution validation."""
    passed: bool
    distribution: Dict[str, float]
    failures: List[str]


@dataclass
class ResolutionValidation:
    """Resolution rate validation."""
    passed: bool
    resolution_rate: float
    min_resolution_rate: float
    total_dependencies: int
    resolved_dependencies: int
    unresolved_details: List[Dict[str, Any]]


@dataclass
class PerformanceValidation:
    """Query performance validation."""
    passed: bool
    metrics: PerformanceMetrics
    slow_queries: List[str]


@dataclass
class ValidationResult:
    """Result of data quality validation."""
    passed: bool
    repo_count: int
    dependency_count: int
    resolution_rate: float
    ecosystem_distribution: Dict[str, float]
    performance_metrics: PerformanceMetrics
    failures: List[ValidationFailure]
    timestamp: datetime


@dataclass
class InsightAnalysis:
    """Cross-repository insight analysis."""
    hub_packages: List[HubPackage]
    large_footprints: List[FootprintMetric]
    ecosystem_patterns: List[EcosystemPattern]
    new_insights_count: int
    baseline_comparison: Dict[str, Any]
    duplicate_groups: List[List[str]] = field(default_factory=list)


@dataclass
class ExpansionResult:
    """Result of dataset expansion."""
    success: bool
    repos_added: int
    repos_failed: int
    backup_path: str
    validation_result: Optional[ValidationResult]
    insight_analysis: Optional[InsightAnalysis]
    report_path: str
    duration_seconds: float
    timestamp: datetime
    failed_repos: List[Tuple[str, str]] = field(default_factory=list)  # (repo_name, error_reason)
