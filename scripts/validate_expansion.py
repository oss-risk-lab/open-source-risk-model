#!/usr/bin/env python3
"""
Validation CLI for dataset expansion.

Validates that the expanded dataset meets all quality requirements:
- Repository and dependency counts
- Ecosystem distribution
- Resolution rate
- Query performance
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from open_source_risk_model.expansion.validators import DataQualityValidator


def print_validation_result(result):
    """Print validation results in human-readable format."""
    print("\n" + "=" * 80)
    print("DATASET EXPANSION VALIDATION REPORT")
    print("=" * 80)
    
    # Overall status
    status_symbol = "✅" if result.passed else "❌"
    print(f"\nOverall Status: {status_symbol} {'PASSED' if result.passed else 'FAILED'}")
    
    # Count validation
    print("\n" + "-" * 80)
    print("1. COUNT VALIDATION")
    print("-" * 80)
    cv = result.count_validation
    print(f"Status: {'✅ PASSED' if cv.passed else '❌ FAILED'}")
    print(f"Repository Count: {cv.repo_count} (expected: {cv.expected_repo_count})")
    print(f"Dependency Count: {cv.dependency_count} (expected: {cv.min_dependency_count}-{cv.max_dependency_count})")
    if cv.failures:
        print("\nFailures:")
        for failure in cv.failures:
            print(f"  - {failure}")
    
    # Ecosystem validation
    print("\n" + "-" * 80)
    print("2. ECOSYSTEM DISTRIBUTION VALIDATION")
    print("-" * 80)
    ev = result.ecosystem_validation
    print(f"Status: {'✅ PASSED' if ev.passed else '❌ FAILED'}")
    print(f"Ecosystem Count: {ev.ecosystem_count}")
    print("\nDistribution:")
    for ecosystem, pct in sorted(ev.distribution.items()):
        print(f"  {ecosystem:12s}: {pct:6.1%}")
    if ev.failures:
        print("\nFailures:")
        for failure in ev.failures:
            print(f"  - {failure}")
    
    # Resolution validation
    print("\n" + "-" * 80)
    print("3. RESOLUTION RATE VALIDATION")
    print("-" * 80)
    rv = result.resolution_validation
    print(f"Status: {'✅ PASSED' if rv.passed else '❌ FAILED'}")
    print(f"Resolution Rate: {rv.resolution_rate:.1%} (minimum: {rv.min_resolution_rate:.1%})")
    print(f"Resolved Dependencies: {rv.resolved_dependencies:,} / {rv.total_dependencies:,}")
    if rv.failures:
        print("\nFailures:")
        for failure in rv.failures:
            print(f"  - {failure}")
    if rv.unresolved_details:
        print(f"\nSample Unresolved Dependencies (showing {min(10, len(rv.unresolved_details))} of {len(rv.unresolved_details)}):")
        for detail in rv.unresolved_details[:10]:
            print(f"  - {detail['repo']}/{detail['package']}: {detail['reason']}")
    
    # Performance validation
    print("\n" + "-" * 80)
    print("4. QUERY PERFORMANCE VALIDATION")
    print("-" * 80)
    pv = result.performance_validation
    print(f"Status: {'✅ PASSED' if pv.passed else '❌ FAILED'}")
    print(f"Max Duration (p95): {pv.metrics.max_duration:.3f}s")
    print(f"Avg Duration (median): {pv.metrics.avg_duration:.3f}s")
    print(f"\nNote: {pv.metrics.measurement_note}")
    print("\nQuery Pattern Results:")
    for pattern, metrics in sorted(pv.metrics.pattern_results.items()):
        print(f"  {pattern:25s}: cold={metrics['cold']:.3f}s, median={metrics['median']:.3f}s, p95={metrics['p95']:.3f}s")
    if pv.failures:
        print("\nFailures:")
        for failure in pv.failures:
            print(f"  - {failure}")
    
    print("\n" + "=" * 80)
    print(f"Validation {'PASSED' if result.passed else 'FAILED'}")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Validate dataset expansion quality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate with default settings (200 repos, 85% resolution)
  python scripts/validate_expansion.py

  # Validate with custom database path
  python scripts/validate_expansion.py --db-path data/graphs.db

  # Validate with custom thresholds
  python scripts/validate_expansion.py --expected-repos 150 --min-resolution 0.80
        """
    )
    
    parser.add_argument(
        "--db-path",
        default="data/graphs.db",
        help="Path to database file (default: data/graphs.db)"
    )
    
    parser.add_argument(
        "--expected-repos",
        type=int,
        default=200,
        help="Expected number of repositories (default: 200)"
    )
    
    parser.add_argument(
        "--min-resolution",
        type=float,
        default=0.85,
        help="Minimum resolution rate (default: 0.85)"
    )
    
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print pass/fail status"
    )
    
    args = parser.parse_args()
    
    # Validate database exists
    if not Path(args.db_path).exists():
        print(f"Error: Database not found at {args.db_path}", file=sys.stderr)
        return 1
    
    # Run validation
    print(f"Validating database: {args.db_path}")
    print(f"Expected repositories: {args.expected_repos}")
    print(f"Minimum resolution rate: {args.min_resolution:.1%}")
    
    validator = DataQualityValidator(args.db_path)
    result = validator.validate_expansion(
        expected_repo_count=args.expected_repos,
        min_resolution_rate=args.min_resolution
    )
    
    # Print results
    if args.quiet:
        print("PASSED" if result.passed else "FAILED")
    else:
        print_validation_result(result)
    
    # Exit with appropriate code
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
