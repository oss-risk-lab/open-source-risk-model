#!/usr/bin/env python3
"""Analyze cross-repository insights and signal quality.

This script identifies hub packages, transitive footprints, ecosystem patterns,
and duplicate dependency graphs to validate that dataset expansion produces
actionable intelligence beyond just data volume.
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.open_source_risk_model.expansion.insight_analyzer import SignalQualityAnalyzer
from src.open_source_risk_model.expansion.duplicate_detector import detect_duplicate_graphs


def format_hub_packages(hubs):
    """Format hub packages for display."""
    if not hubs:
        return "No hub packages found."
    
    lines = ["\n## Hub Packages (used by >25% of repositories)\n"]
    for i, hub in enumerate(hubs[:20], 1):  # Top 20
        lines.append(
            f"{i}. **{hub.package_name}** ({hub.registry_type})\n"
            f"   - Used by: {hub.repo_count} repos ({hub.usage_percentage:.1%})\n"
            f"   - Examples: {', '.join(hub.example_repos[:3])}\n"
        )
    return '\n'.join(lines)


def format_footprints(footprints):
    """Format transitive footprints for display."""
    if not footprints:
        return "No footprint data available."
    
    lines = ["\n## Top Packages by Usage\n"]
    for i, fp in enumerate(footprints[:20], 1):  # Top 20
        lines.append(
            f"{i}. **{fp.package_name}** ({fp.registry_type})\n"
            f"   - Direct dependents: {fp.direct_dependents} repos\n"
        )
    return '\n'.join(lines)


def format_patterns(patterns):
    """Format ecosystem patterns for display."""
    if not patterns:
        return "No ecosystem patterns detected."
    
    lines = ["\n## Ecosystem-Specific Patterns\n"]
    for pattern in patterns:
        lines.append(
            f"\n### {pattern.ecosystem.upper()}: {pattern.pattern_type}\n"
            f"{pattern.description}\n"
            f"Examples found: {pattern.example_count}\n"
        )
        
        # Show first few examples
        for example in pattern.examples[:3]:
            lines.append(f"  - {example}\n")
    
    return '\n'.join(lines)


def format_duplicates(duplicate_groups):
    """Format duplicate graph groups for display."""
    if not duplicate_groups:
        return "\n## Duplicate Dependency Graphs\n\nNo duplicate graphs detected."
    
    lines = [
        "\n## Duplicate Dependency Graphs\n",
        f"\nFound {len(duplicate_groups)} group(s) of repositories with identical dependency graphs:\n"
    ]
    
    for i, group in enumerate(duplicate_groups, 1):
        lines.append(f"\n### Group {i} ({len(group)} repositories):\n")
        for repo in group:
            lines.append(f"  - {repo}\n")
    
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Analyze cross-repository insights and signal quality'
    )
    parser.add_argument(
        '--db-path',
        default='data/graphs.db',
        help='Path to database (default: data/graphs.db)'
    )
    parser.add_argument(
        '--baseline-repo-count',
        type=int,
        default=51,
        help='Repository count in baseline dataset (default: 51)'
    )
    parser.add_argument(
        '--output',
        help='Output file path (default: stdout)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output in JSON format'
    )
    parser.add_argument(
        '--min-insights',
        type=int,
        default=5,
        help='Minimum required insights (default: 5)'
    )
    
    args = parser.parse_args()
    
    # Verify database exists
    if not Path(args.db_path).exists():
        print(f"Error: Database not found: {args.db_path}", file=sys.stderr)
        return 1
    
    print(f"Analyzing insights from {args.db_path}...", file=sys.stderr)
    
    # Run analysis
    analyzer = SignalQualityAnalyzer(args.db_path)
    analysis = analyzer.analyze_insights(baseline_repo_count=args.baseline_repo_count)
    
    # Detect duplicate graphs
    print("Detecting duplicate dependency graphs...", file=sys.stderr)
    duplicate_groups = detect_duplicate_graphs(args.db_path)
    
    # Check if sufficient insights found
    if analysis.new_insights_count < args.min_insights:
        print(
            f"\nWARNING: Insufficient signal quality detected!\n"
            f"Found {analysis.new_insights_count} insights, expected at least {args.min_insights}",
            file=sys.stderr
        )
    
    # Format output
    if args.json:
        # JSON output
        output = {
            'timestamp': datetime.now().isoformat(),
            'database': args.db_path,
            'baseline_comparison': analysis.baseline_comparison,
            'new_insights_count': analysis.new_insights_count,
            'hub_packages': [
                {
                    'package_name': h.package_name,
                    'registry_type': h.registry_type,
                    'repo_count': h.repo_count,
                    'usage_percentage': h.usage_percentage,
                    'example_repos': h.example_repos
                }
                for h in analysis.hub_packages
            ],
            'large_footprints': [
                {
                    'package_name': f.package_name,
                    'registry_type': f.registry_type,
                    'transitive_count': f.transitive_count,
                    'direct_dependents': f.direct_dependents
                }
                for f in analysis.large_footprints
            ],
            'ecosystem_patterns': [
                {
                    'ecosystem': p.ecosystem,
                    'pattern_type': p.pattern_type,
                    'description': p.description,
                    'example_count': p.example_count,
                    'examples': p.examples
                }
                for p in analysis.ecosystem_patterns
            ],
            'duplicate_graphs': [
                {'repositories': group}
                for group in duplicate_groups
            ],
            'sufficient_signal': analysis.new_insights_count >= args.min_insights
        }
        
        output_text = json.dumps(output, indent=2)
    else:
        # Markdown output
        lines = [
            "# Cross-Repository Insights Analysis\n",
            f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"**Database:** {args.db_path}\n",
            "\n## Summary\n",
            f"- Baseline repository count: {analysis.baseline_comparison['baseline_repo_count']}\n",
            f"- Current repository count: {analysis.baseline_comparison['current_repo_count']}\n",
            f"- New insights discovered: {analysis.new_insights_count}\n",
            f"- Hub packages found: {len(analysis.hub_packages)}\n",
            f"- Ecosystem patterns found: {len(analysis.ecosystem_patterns)}\n",
            f"- Duplicate graph groups: {len(duplicate_groups)}\n",
        ]
        
        if analysis.new_insights_count < args.min_insights:
            lines.append(
                f"\n⚠️  **WARNING:** Insufficient signal quality! "
                f"Found {analysis.new_insights_count} insights, expected at least {args.min_insights}\n"
            )
        else:
            lines.append(
                f"\n✅ **Signal quality sufficient:** "
                f"{analysis.new_insights_count} insights found (>= {args.min_insights} required)\n"
            )
        
        lines.append(format_hub_packages(analysis.hub_packages))
        lines.append(format_footprints(analysis.large_footprints))
        lines.append(format_patterns(analysis.ecosystem_patterns))
        lines.append(format_duplicates(duplicate_groups))
        
        output_text = ''.join(lines)
    
    # Write output
    if args.output:
        Path(args.output).write_text(output_text)
        print(f"\nAnalysis written to {args.output}", file=sys.stderr)
    else:
        print(output_text)
    
    # Exit with error if insufficient insights
    if analysis.new_insights_count < args.min_insights:
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
