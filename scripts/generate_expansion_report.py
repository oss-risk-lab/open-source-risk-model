#!/usr/bin/env python3
"""Generate comprehensive expansion report.

This script generates a detailed Markdown report summarizing the dataset expansion,
including metrics, validation results, insights, and duplicate detection.
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.open_source_risk_model.expansion.insight_analyzer import SignalQualityAnalyzer, InsightAnalysis
from src.open_source_risk_model.expansion.duplicate_detector import detect_duplicate_graphs
from src.open_source_risk_model.expansion.validators import DataQualityValidator


def generate_executive_summary(
    repo_count: int,
    dependency_count: int,
    resolution_rate: float,
    repos_added: int,
    repos_failed: int
) -> str:
    """Generate executive summary section."""
    return f"""# Dataset Expansion Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

- **Total Repositories:** {repo_count}
- **Total Dependencies:** {dependency_count:,}
- **Resolution Rate:** {resolution_rate:.1%}
- **Repositories Added:** {repos_added}
- **Failed Ingestions:** {repos_failed}
- **Status:** {'✅ SUCCESS' if repos_failed == 0 else '⚠️  PARTIAL SUCCESS'}

"""


def generate_newly_added_section(
    added_repos: List[Dict[str, Any]]
) -> str:
    """Generate newly added repositories section."""
    if not added_repos:
        return "## Newly Added Repositories\n\nNo new repositories added.\n\n"
    
    lines = [
        "## Newly Added Repositories\n",
        f"\nAdded {len(added_repos)} repositories:\n\n"
    ]
    
    # Group by ecosystem
    by_ecosystem: Dict[str, List[Dict]] = {}
    for repo in added_repos:
        ecosystem = repo.get('ecosystem', 'unknown')
        if ecosystem not in by_ecosystem:
            by_ecosystem[ecosystem] = []
        by_ecosystem[ecosystem].append(repo)
    
    for ecosystem, repos in sorted(by_ecosystem.items()):
        lines.append(f"\n### {ecosystem.upper()} ({len(repos)} repositories)\n\n")
        for repo in sorted(repos, key=lambda r: r.get('stars', 0), reverse=True)[:20]:
            stars = repo.get('stars', 0)
            lines.append(f"- **{repo['name']}** ({stars:,} ⭐)\n")
        
        if len(repos) > 20:
            lines.append(f"\n... and {len(repos) - 20} more\n")
    
    return ''.join(lines) + '\n'


def generate_failed_ingestions_section(
    failed_repos: List[Dict[str, Any]]
) -> str:
    """Generate failed ingestions section."""
    if not failed_repos:
        return "## Failed Ingestions\n\n✅ All repositories ingested successfully.\n\n"
    
    lines = [
        "## Failed Ingestions\n",
        f"\n⚠️  {len(failed_repos)} repositories failed to ingest:\n\n"
    ]
    
    for repo in failed_repos:
        reason = repo.get('reason', 'Unknown error')
        lines.append(f"- **{repo['name']}**: {reason}\n")
    
    return ''.join(lines) + '\n'


def generate_ecosystem_distribution_section(
    distribution: Dict[str, float],
    repo_count: int
) -> str:
    """Generate ecosystem distribution section."""
    lines = [
        "## Ecosystem Distribution\n\n",
        "| Ecosystem | Count | Percentage | Target |\n",
        "|-----------|-------|------------|--------|\n"
    ]
    
    targets = {
        'npm': '25-40%',
        'pypi': '25-40%',
        'go': '≥10%',
        'maven': '≥10%',
        'rubygems': '≥5%'
    }
    
    for ecosystem in ['npm', 'pypi', 'go', 'maven', 'rubygems']:
        pct = distribution.get(ecosystem, 0.0)
        count = int(repo_count * pct)
        target = targets.get(ecosystem, '-')
        status = '✅' if _check_ecosystem_target(ecosystem, pct) else '❌'
        lines.append(
            f"| {ecosystem} | {count} | {pct:.1%} | {target} {status} |\n"
        )
    
    # Other ecosystems
    other_ecosystems = [e for e in distribution.keys() if e not in targets]
    if other_ecosystems:
        for ecosystem in sorted(other_ecosystems):
            pct = distribution[ecosystem]
            count = int(repo_count * pct)
            lines.append(f"| {ecosystem} | {count} | {pct:.1%} | - |\n")
    
    return ''.join(lines) + '\n'


def _check_ecosystem_target(ecosystem: str, pct: float) -> bool:
    """Check if ecosystem percentage meets target."""
    targets = {
        'npm': (0.25, 0.40),
        'pypi': (0.25, 0.40),
        'go': (0.10, 1.0),
        'maven': (0.10, 1.0),
        'rubygems': (0.05, 1.0)
    }
    
    if ecosystem not in targets:
        return True
    
    min_pct, max_pct = targets[ecosystem]
    return min_pct <= pct <= max_pct


def generate_query_performance_section(
    performance_metrics: Optional[Dict[str, Any]]
) -> str:
    """Generate query performance section."""
    if not performance_metrics:
        return "## Query Performance\n\nNo performance metrics available.\n\n"
    
    lines = [
        "## Query Performance\n\n",
        "| Query Pattern | Cold Cache | Warm Cache (Median) | P95 | Status |\n",
        "|---------------|------------|---------------------|-----|--------|\n"
    ]
    
    pattern_results = performance_metrics.get('pattern_results', {})
    for pattern_name, metrics in sorted(pattern_results.items()):
        cold = metrics.get('cold', 0)
        median = metrics.get('median', 0)
        p95 = metrics.get('p95', 0)
        status = '✅' if p95 < 5.0 else '❌'
        
        lines.append(
            f"| {pattern_name} | {cold:.2f}s | {median:.2f}s | {p95:.2f}s | {status} |\n"
        )
    
    max_duration = performance_metrics.get('max_duration', 0)
    avg_duration = performance_metrics.get('avg_duration', 0)
    
    lines.append(f"\n**Summary:**\n")
    lines.append(f"- Maximum P95: {max_duration:.2f}s\n")
    lines.append(f"- Average Median: {avg_duration:.2f}s\n")
    lines.append(f"- Target: <5.0s (P95)\n")
    
    if max_duration < 5.0:
        lines.append(f"- Status: ✅ All queries meet performance target\n")
    else:
        lines.append(f"- Status: ❌ Some queries exceed performance target\n")
    
    return ''.join(lines) + '\n'


def generate_insights_section(
    analysis: InsightAnalysis
) -> str:
    """Generate cross-repository insights section."""
    lines = [
        "## Cross-Repository Insights\n\n",
        f"**Total Insights Discovered:** {analysis.new_insights_count}\n\n"
    ]
    
    if analysis.new_insights_count < 5:
        lines.append("⚠️  **WARNING:** Fewer than 5 insights discovered. Signal quality may be insufficient.\n\n")
    else:
        lines.append("✅ Signal quality sufficient (≥5 insights discovered)\n\n")
    
    # Hub packages
    if analysis.hub_packages:
        lines.append(f"### Hub Packages ({len(analysis.hub_packages)} found)\n\n")
        lines.append("Packages used by >25% of repositories:\n\n")
        
        for hub in analysis.hub_packages[:10]:
            lines.append(
                f"- **{hub.package_name}** ({hub.registry_type}): "
                f"{hub.repo_count} repos ({hub.usage_percentage:.1%})\n"
            )
        
        if len(analysis.hub_packages) > 10:
            lines.append(f"\n... and {len(analysis.hub_packages) - 10} more\n")
        lines.append("\n")
    
    # Ecosystem patterns
    if analysis.ecosystem_patterns:
        lines.append(f"### Ecosystem Patterns ({len(analysis.ecosystem_patterns)} found)\n\n")
        
        for pattern in analysis.ecosystem_patterns:
            lines.append(
                f"- **{pattern.ecosystem}**: {pattern.description} "
                f"({pattern.example_count} examples)\n"
            )
        lines.append("\n")
    
    # Baseline comparison
    lines.append("### Baseline Comparison\n\n")
    baseline = analysis.baseline_comparison
    lines.append(f"- Baseline repos: {baseline.get('baseline_repo_count', 0)}\n")
    lines.append(f"- Current repos: {baseline.get('current_repo_count', 0)}\n")
    lines.append(f"- Hub packages: {baseline.get('hub_packages_found', 0)}\n")
    lines.append(f"- Ecosystem patterns: {baseline.get('ecosystem_patterns_found', 0)}\n")
    
    return ''.join(lines) + '\n'


def generate_duplicate_graphs_section(
    duplicate_groups: List[List[str]]
) -> str:
    """Generate duplicate graph detection section."""
    if not duplicate_groups:
        return "## Duplicate Graph Detection\n\n✅ No duplicate dependency graphs detected.\n\n"
    
    lines = [
        "## Duplicate Graph Detection\n\n",
        f"⚠️  Found {len(duplicate_groups)} group(s) of repositories with identical dependency graphs:\n\n"
    ]
    
    for i, group in enumerate(duplicate_groups, 1):
        lines.append(f"### Group {i} ({len(group)} repositories)\n\n")
        for repo in group:
            lines.append(f"- {repo}\n")
        lines.append("\n")
    
    return ''.join(lines)


def generate_validation_section(
    validation_passed: bool,
    validation_details: Optional[Dict[str, Any]]
) -> str:
    """Generate validation status section."""
    lines = [
        "## Validation Status\n\n",
        f"**Overall Status:** {'✅ PASSED' if validation_passed else '❌ FAILED'}\n\n"
    ]
    
    if validation_details:
        lines.append("### Validation Checks\n\n")
        
        checks = validation_details.get('checks', [])
        for check in checks:
            name = check.get('name', 'Unknown')
            passed = check.get('passed', False)
            message = check.get('message', '')
            status = '✅' if passed else '❌'
            
            lines.append(f"- {status} **{name}**: {message}\n")
    
    return ''.join(lines) + '\n'


def generate_expansion_report(
    db_path: str,
    repos_added: int = 0,
    repos_failed: int = 0,
    added_repos: Optional[List[Dict]] = None,
    failed_repos: Optional[List[Dict]] = None,
    performance_metrics: Optional[Dict] = None,
    validation_passed: bool = True,
    validation_details: Optional[Dict] = None,
    output_path: Optional[str] = None
) -> str:
    """
    Generate comprehensive expansion report.
    
    Args:
        db_path: Path to database
        repos_added: Number of repositories added
        repos_failed: Number of failed ingestions
        added_repos: List of added repository metadata
        failed_repos: List of failed repository metadata
        performance_metrics: Query performance metrics
        validation_passed: Whether validation passed
        validation_details: Detailed validation results
        output_path: Output file path (optional)
    
    Returns:
        Path to generated report
    """
    # Get current database stats
    validator = DataQualityValidator(db_path)
    
    # Get repo count
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM repo_graphs")
    repo_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM repo_dependencies")
    dependency_count = cursor.fetchone()[0]
    conn.close()
    
    # Calculate resolution rate
    resolution_validation = validator.validate_resolution_rate()
    resolution_rate = resolution_validation.resolution_rate
    
    # Get ecosystem distribution
    ecosystem_validation = validator.validate_ecosystem_distribution()
    distribution = ecosystem_validation.distribution
    
    # Run insight analysis
    analyzer = SignalQualityAnalyzer(db_path)
    analysis = analyzer.analyze_insights(baseline_repo_count=51)
    
    # Detect duplicate graphs
    duplicate_groups = detect_duplicate_graphs(db_path)
    
    # Generate report sections
    report = []
    
    report.append(generate_executive_summary(
        repo_count, dependency_count, resolution_rate,
        repos_added, repos_failed
    ))
    
    report.append(generate_newly_added_section(added_repos or []))
    report.append(generate_failed_ingestions_section(failed_repos or []))
    report.append(generate_ecosystem_distribution_section(distribution, repo_count))
    report.append(generate_query_performance_section(performance_metrics))
    report.append(generate_insights_section(analysis))
    report.append(generate_duplicate_graphs_section(duplicate_groups))
    report.append(generate_validation_section(validation_passed, validation_details))
    
    report_text = ''.join(report)
    
    # Write to file
    if output_path:
        Path(output_path).write_text(report_text)
        return output_path
    else:
        # Default output path
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_path = f"data/expansion_reports/expansion_report_{timestamp}.md"
        Path(default_path).parent.mkdir(parents=True, exist_ok=True)
        Path(default_path).write_text(report_text)
        return default_path


def main():
    parser = argparse.ArgumentParser(
        description='Generate dataset expansion report'
    )
    parser.add_argument(
        '--db-path',
        default='data/graphs.db',
        help='Path to database (default: data/graphs.db)'
    )
    parser.add_argument(
        '--output',
        help='Output file path (default: data/expansion_reports/expansion_report_TIMESTAMP.md)'
    )
    parser.add_argument(
        '--repos-added',
        type=int,
        default=0,
        help='Number of repositories added'
    )
    parser.add_argument(
        '--repos-failed',
        type=int,
        default=0,
        help='Number of failed ingestions'
    )
    parser.add_argument(
        '--added-repos-json',
        help='JSON file with added repository metadata'
    )
    parser.add_argument(
        '--failed-repos-json',
        help='JSON file with failed repository metadata'
    )
    parser.add_argument(
        '--performance-json',
        help='JSON file with performance metrics'
    )
    
    args = parser.parse_args()
    
    # Load optional JSON files
    added_repos = None
    if args.added_repos_json and Path(args.added_repos_json).exists():
        added_repos = json.loads(Path(args.added_repos_json).read_text())
    
    failed_repos = None
    if args.failed_repos_json and Path(args.failed_repos_json).exists():
        failed_repos = json.loads(Path(args.failed_repos_json).read_text())
    
    performance_metrics = None
    if args.performance_json and Path(args.performance_json).exists():
        performance_metrics = json.loads(Path(args.performance_json).read_text())
    
    # Generate report
    print(f"Generating expansion report from {args.db_path}...", file=sys.stderr)
    
    report_path = generate_expansion_report(
        db_path=args.db_path,
        repos_added=args.repos_added,
        repos_failed=args.repos_failed,
        added_repos=added_repos,
        failed_repos=failed_repos,
        performance_metrics=performance_metrics,
        output_path=args.output
    )
    
    print(f"\n✅ Report generated: {report_path}", file=sys.stderr)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
