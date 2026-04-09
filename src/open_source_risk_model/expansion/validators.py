"""Data quality validators for dataset expansion."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import sqlite3
import time


@dataclass
class CountValidation:
    """Result of count validation."""
    passed: bool
    repo_count: int
    dependency_count: int
    expected_repo_count: int
    min_dependency_count: int
    max_dependency_count: int
    failures: List[str]


@dataclass
class EcosystemValidation:
    """Result of ecosystem distribution validation."""
    passed: bool
    ecosystem_count: int
    distribution: Dict[str, float]
    failures: List[str]


@dataclass
class ResolutionValidation:
    """Result of resolution rate validation."""
    passed: bool
    resolution_rate: float
    total_dependencies: int
    resolved_dependencies: int
    min_resolution_rate: float
    unresolved_details: List[Dict[str, str]]
    failures: List[str]


@dataclass
class PerformanceMetrics:
    """Query performance metrics."""
    pattern_results: Dict[str, Dict[str, float]]
    max_duration: float
    avg_duration: float
    passed: bool
    measurement_note: str


@dataclass
class PerformanceValidation:
    """Result of performance validation."""
    passed: bool
    metrics: PerformanceMetrics
    failures: List[str]


@dataclass
class ValidationResult:
    """Complete validation result."""
    passed: bool
    count_validation: CountValidation
    ecosystem_validation: EcosystemValidation
    resolution_validation: ResolutionValidation
    performance_validation: PerformanceValidation
    timestamp: float


class DataQualityValidator:
    """Validates data quality after dataset expansion."""
    
    def __init__(self, db_path: str):
        """Initialize validator with database connection."""
        self.db_path = db_path
    
    def validate_counts(
        self,
        expected_repo_count: int = 200,
        min_dependency_count: int = 15000,
        max_dependency_count: int = 50000
    ) -> CountValidation:
        """
        Validate repository and dependency counts.
        
        Args:
            expected_repo_count: Expected number of repositories
            min_dependency_count: Minimum expected dependencies
            max_dependency_count: Maximum expected dependencies
        
        Returns:
            CountValidation with pass/fail status
        """
        conn = sqlite3.connect(self.db_path)
        failures = []
        
        try:
            # Get repository count
            repo_count = conn.execute(
                "SELECT COUNT(*) FROM repo_graphs"
            ).fetchone()[0]
            
            # Get dependency count
            dependency_count = conn.execute(
                "SELECT COUNT(*) FROM repo_dependencies"
            ).fetchone()[0]
            
            # Validate repo count
            if repo_count != expected_repo_count:
                failures.append(
                    f"Repository count mismatch: expected {expected_repo_count}, got {repo_count}"
                )
            
            # Validate dependency count range
            if dependency_count < min_dependency_count:
                failures.append(
                    f"Dependency count too low: expected >={min_dependency_count}, got {dependency_count}"
                )
            elif dependency_count > max_dependency_count:
                failures.append(
                    f"Dependency count too high: expected <={max_dependency_count}, got {dependency_count}"
                )
            
            return CountValidation(
                passed=len(failures) == 0,
                repo_count=repo_count,
                dependency_count=dependency_count,
                expected_repo_count=expected_repo_count,
                min_dependency_count=min_dependency_count,
                max_dependency_count=max_dependency_count,
                failures=failures
            )
        
        finally:
            conn.close()
    
    def validate_ecosystem_distribution(
        self,
        min_ecosystem_count: int = 5,
        ecosystem_targets: Optional[Dict[str, Tuple[float, float]]] = None
    ) -> EcosystemValidation:
        """
        Validate ecosystem distribution meets targets.
        
        Args:
            min_ecosystem_count: Minimum number of ecosystems required
            ecosystem_targets: Dict of ecosystem -> (min_pct, max_pct) targets
        
        Returns:
            EcosystemValidation with pass/fail status
        """
        if ecosystem_targets is None:
            ecosystem_targets = {
                'npm': (0.25, 0.40),
                'pypi': (0.25, 0.40),
                'go': (0.10, 1.0),
                'maven': (0.10, 1.0),
                'rubygems': (0.05, 1.0)
            }
        
        conn = sqlite3.connect(self.db_path)
        failures = []
        
        try:
            # Get total repo count
            total_repos = conn.execute(
                "SELECT COUNT(*) FROM repo_graphs"
            ).fetchone()[0]
            
            if total_repos == 0:
                return EcosystemValidation(
                    passed=False,
                    ecosystem_count=0,
                    distribution={},
                    failures=["No repositories in database"]
                )
            
            # Get ecosystem distribution
            # Note: We need to infer ecosystem from dependencies since repo_graphs
            # doesn't have an ecosystem column. We'll use the most common registry_type
            # for each repo as its primary ecosystem.
            query = """
                WITH repo_ecosystems AS (
                    SELECT 
                        repo_full_name,
                        registry_type,
                        COUNT(*) as dep_count
                    FROM repo_dependencies
                    WHERE registry_type IS NOT NULL AND registry_type != ''
                    GROUP BY repo_full_name, registry_type
                ),
                primary_ecosystems AS (
                    SELECT 
                        repo_full_name,
                        registry_type as ecosystem,
                        ROW_NUMBER() OVER (
                            PARTITION BY repo_full_name 
                            ORDER BY dep_count DESC
                        ) as rn
                    FROM repo_ecosystems
                )
                SELECT ecosystem, COUNT(*) as count
                FROM primary_ecosystems
                WHERE rn = 1
                GROUP BY ecosystem
            """
            
            results = conn.execute(query).fetchall()
            
            # Calculate distribution
            distribution = {}
            for ecosystem, count in results:
                distribution[ecosystem] = count / total_repos
            
            ecosystem_count = len(distribution)
            
            # Validate minimum ecosystem count
            if ecosystem_count < min_ecosystem_count:
                failures.append(
                    f"Too few ecosystems: expected >={min_ecosystem_count}, got {ecosystem_count}"
                )
            
            # Validate ecosystem targets
            for ecosystem, (min_pct, max_pct) in ecosystem_targets.items():
                actual_pct = distribution.get(ecosystem, 0.0)
                
                if actual_pct < min_pct:
                    failures.append(
                        f"{ecosystem} below target: expected >={min_pct:.1%}, got {actual_pct:.1%}"
                    )
                elif actual_pct > max_pct:
                    failures.append(
                        f"{ecosystem} above target: expected <={max_pct:.1%}, got {actual_pct:.1%}"
                    )
            
            return EcosystemValidation(
                passed=len(failures) == 0,
                ecosystem_count=ecosystem_count,
                distribution=distribution,
                failures=failures
            )
        
        finally:
            conn.close()
    
    def validate_resolution_rate(
        self,
        min_resolution_rate: float = 0.85
    ) -> ResolutionValidation:
        """
        Validate resolution rate meets threshold.
        
        A dependency is resolved if ALL three criteria are met:
        1. Package is matched to a registry (registry_type IS NOT NULL)
        2. Version is successfully parsed (specifier IS NOT NULL)
        3. Registry metadata is retrieved (resolved_repo IS NOT NULL)
        
        Args:
            min_resolution_rate: Minimum acceptable resolution rate
        
        Returns:
            ResolutionValidation with pass/fail status
        """
        conn = sqlite3.connect(self.db_path)
        failures = []
        
        try:
            # Get total dependencies
            total_dependencies = conn.execute(
                "SELECT COUNT(*) FROM repo_dependencies"
            ).fetchone()[0]
            
            if total_dependencies == 0:
                return ResolutionValidation(
                    passed=False,
                    resolution_rate=0.0,
                    total_dependencies=0,
                    resolved_dependencies=0,
                    min_resolution_rate=min_resolution_rate,
                    unresolved_details=[],
                    failures=["No dependencies in database"]
                )
            
            # Get resolved dependencies (all three criteria met)
            resolved_query = """
                SELECT COUNT(*) FROM repo_dependencies
                WHERE registry_type IS NOT NULL
                  AND registry_type != ''
                  AND specifier IS NOT NULL
                  AND resolved_repo IS NOT NULL
                  AND resolution_confidence IS NOT NULL
            """
            resolved_dependencies = conn.execute(resolved_query).fetchone()[0]
            
            # Calculate resolution rate
            resolution_rate = resolved_dependencies / total_dependencies
            
            # Get sample of unresolved dependencies for documentation
            unresolved_query = """
                SELECT 
                    repo_full_name,
                    package_name,
                    CASE 
                        WHEN registry_type IS NULL OR registry_type = '' THEN 'no_registry'
                        WHEN specifier IS NULL THEN 'no_version'
                        WHEN resolved_repo IS NULL THEN 'no_metadata'
                        ELSE 'unknown'
                    END as failure_reason
                FROM repo_dependencies
                WHERE NOT (
                    registry_type IS NOT NULL
                    AND registry_type != ''
                    AND specifier IS NOT NULL
                    AND resolved_repo IS NOT NULL
                    AND resolution_confidence IS NOT NULL
                )
                LIMIT 100
            """
            
            unresolved_results = conn.execute(unresolved_query).fetchall()
            unresolved_details = [
                {
                    'repo': repo,
                    'package': package,
                    'reason': reason
                }
                for repo, package, reason in unresolved_results
            ]
            
            # Validate resolution rate
            if resolution_rate < min_resolution_rate:
                failures.append(
                    f"Resolution rate below threshold: expected >={min_resolution_rate:.1%}, "
                    f"got {resolution_rate:.1%}"
                )
            
            return ResolutionValidation(
                passed=len(failures) == 0,
                resolution_rate=resolution_rate,
                total_dependencies=total_dependencies,
                resolved_dependencies=resolved_dependencies,
                min_resolution_rate=min_resolution_rate,
                unresolved_details=unresolved_details,
                failures=failures
            )
        
        finally:
            conn.close()
    
    def validate_query_performance(
        self,
        max_duration: float = 5.0
    ) -> PerformanceValidation:
        """
        Validate query performance across patterns.
        
        Measures end-to-end query time including Python overhead.
        Includes cold/warm cache runs to account for SQLite page cache.
        
        Args:
            max_duration: Maximum acceptable query duration (seconds)
        
        Returns:
            PerformanceValidation with pass/fail status
        """
        from ..persistence.graph_repo import GraphRepository
        from ..persistence.dependency_repo import DependencyRepository
        
        failures = []
        pattern_results = {}
        
        # Define query patterns
        patterns = [
            ("single_repo_deps", self._benchmark_single_repo_deps),
            ("package_dependents", self._benchmark_package_dependents),
            ("cross_repo_search", self._benchmark_cross_repo_search),
            ("ecosystem_dist", self._benchmark_ecosystem_dist),
            ("resolution_rate", self._benchmark_resolution_rate),
            ("top_packages", self._benchmark_top_packages),
        ]
        
        for pattern_name, query_func in patterns:
            durations = []
            
            # Run 3 times: 1 cold + 2 warm
            for i in range(3):
                if i == 0:
                    # Cold cache: create fresh connection
                    conn = sqlite3.connect(self.db_path)
                    conn.close()
                
                start = time.time()
                try:
                    query_func()
                    duration = time.time() - start
                    durations.append(duration)
                except Exception as e:
                    failures.append(f"Query {pattern_name} failed: {str(e)}")
                    durations.append(max_duration * 2)  # Penalty for failure
            
            # Calculate metrics
            median = sorted(durations)[1] if len(durations) >= 2 else durations[0]
            p95 = sorted(durations)[-1]
            cold = durations[0]
            
            pattern_results[pattern_name] = {
                'median': median,
                'p95': p95,
                'cold': cold
            }
            
            # Check if p95 exceeds threshold
            if p95 > max_duration:
                failures.append(
                    f"Query {pattern_name} too slow: p95={p95:.2f}s (max={max_duration}s)"
                )
        
        # Calculate aggregate metrics
        max_p95 = max(r['p95'] for r in pattern_results.values())
        avg_median = sum(r['median'] for r in pattern_results.values()) / len(pattern_results)
        
        metrics = PerformanceMetrics(
            pattern_results=pattern_results,
            max_duration=max_p95,
            avg_duration=avg_median,
            passed=max_p95 < max_duration,
            measurement_note="End-to-end query time including Python overhead"
        )
        
        return PerformanceValidation(
            passed=len(failures) == 0,
            metrics=metrics,
            failures=failures
        )
    
    def _benchmark_single_repo_deps(self):
        """Benchmark: Get dependencies for single repo."""
        conn = sqlite3.connect(self.db_path)
        try:
            # Get first repo
            repo = conn.execute("SELECT repo_full_name FROM repo_graphs LIMIT 1").fetchone()
            if repo:
                conn.execute(
                    "SELECT * FROM repo_dependencies WHERE repo_full_name = ?",
                    (repo[0],)
                ).fetchall()
        finally:
            conn.close()
    
    def _benchmark_package_dependents(self):
        """Benchmark: Get dependents for popular package."""
        conn = sqlite3.connect(self.db_path)
        try:
            # Get most common package
            result = conn.execute("""
                SELECT package_name, registry_type 
                FROM repo_dependencies 
                WHERE registry_type IS NOT NULL
                GROUP BY package_name, registry_type 
                ORDER BY COUNT(*) DESC 
                LIMIT 1
            """).fetchone()
            
            if result:
                package_name, registry_type = result
                conn.execute("""
                    SELECT DISTINCT repo_full_name 
                    FROM repo_dependencies 
                    WHERE package_name = ? AND registry_type = ?
                """, (package_name, registry_type)).fetchall()
        finally:
            conn.close()
    
    def _benchmark_cross_repo_search(self):
        """Benchmark: Cross-repo dependency search."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                SELECT repo_full_name, package_name, registry_type
                FROM repo_dependencies
                WHERE package_name LIKE '%test%'
                LIMIT 100
            """).fetchall()
        finally:
            conn.close()
    
    def _benchmark_ecosystem_dist(self):
        """Benchmark: Ecosystem distribution query."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                SELECT registry_type, COUNT(DISTINCT repo_full_name) as count
                FROM repo_dependencies
                WHERE registry_type IS NOT NULL
                GROUP BY registry_type
            """).fetchall()
        finally:
            conn.close()
    
    def _benchmark_resolution_rate(self):
        """Benchmark: Resolution rate calculation."""
        conn = sqlite3.connect(self.db_path)
        try:
            total = conn.execute("SELECT COUNT(*) FROM repo_dependencies").fetchone()[0]
            resolved = conn.execute("""
                SELECT COUNT(*) FROM repo_dependencies
                WHERE registry_type IS NOT NULL
                  AND registry_type != ''
                  AND specifier IS NOT NULL
                  AND resolved_repo IS NOT NULL
                  AND resolution_confidence IS NOT NULL
            """).fetchone()[0]
        finally:
            conn.close()
    
    def _benchmark_top_packages(self):
        """Benchmark: Top packages by usage."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                SELECT package_name, registry_type, COUNT(DISTINCT repo_full_name) as usage
                FROM repo_dependencies
                WHERE registry_type IS NOT NULL
                GROUP BY package_name, registry_type
                ORDER BY usage DESC
                LIMIT 100
            """).fetchall()
        finally:
            conn.close()
    
    def validate_expansion(
        self,
        expected_repo_count: int = 200,
        min_resolution_rate: float = 0.85
    ) -> ValidationResult:
        """
        Run complete validation suite.
        
        Args:
            expected_repo_count: Expected number of repositories
            min_resolution_rate: Minimum acceptable resolution rate
        
        Returns:
            ValidationResult with pass/fail status and detailed metrics
        """
        timestamp = time.time()
        
        # Run all validators
        count_validation = self.validate_counts(expected_repo_count=expected_repo_count)
        ecosystem_validation = self.validate_ecosystem_distribution()
        resolution_validation = self.validate_resolution_rate(
            min_resolution_rate=min_resolution_rate
        )
        performance_validation = self.validate_query_performance()
        
        # Overall pass/fail
        passed = all([
            count_validation.passed,
            ecosystem_validation.passed,
            resolution_validation.passed,
            performance_validation.passed
        ])
        
        return ValidationResult(
            passed=passed,
            count_validation=count_validation,
            ecosystem_validation=ecosystem_validation,
            resolution_validation=resolution_validation,
            performance_validation=performance_validation,
            timestamp=timestamp
        )
