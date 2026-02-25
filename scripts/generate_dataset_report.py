#!/usr/bin/env python3
"""
Generate Dataset Report

Produces a comprehensive report on ingestion quality:
- Per-repo metrics (manifests, deps, resolution rate, errors)
- Summary statistics
- Quality gate evaluation

Usage:
    python scripts/generate_dataset_report.py [--db-path data/graphs.db] [--output report.json]
"""

import sys
import json
import argparse
import sqlite3
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.open_source_risk_model.persistence.db import get_connection


class DatasetReporter:
    """Generate dataset quality reports."""
    
    def __init__(self, db_path: str = "data/graphs.db"):
        self.db_path = db_path
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive dataset report."""
        conn = get_connection(self.db_path)
        
        # Get per-repo metrics
        repo_metrics = self._get_repo_metrics(conn)
        
        # Calculate summary statistics
        summary = self._calculate_summary(repo_metrics)
        
        # Evaluate quality gate
        gate_result = self._evaluate_quality_gate(summary)
        
        conn.close()
        
        return {
            "generated_at": datetime.now().isoformat(),
            "database": self.db_path,
            "repos": repo_metrics,
            "summary": summary,
            "quality_gate": gate_result,
        }
    
    def _get_repo_metrics(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        """Get metrics for each repository."""
        conn.row_factory = sqlite3.Row
        
        # Get all repos with graphs
        cursor = conn.execute("""
            SELECT repo_full_name, created_at, updated_at
            FROM repo_graphs
            ORDER BY repo_full_name
        """)
        
        repos = cursor.fetchall()
        metrics = []
        
        for repo in repos:
            repo_name = repo['repo_full_name']
            
            # Get manifest count (distinct manifest_path)
            cursor = conn.execute("""
                SELECT COUNT(DISTINCT manifest_path) as manifest_count
                FROM repo_dependencies
                WHERE repo_full_name = ?
            """, (repo_name,))
            manifest_count = cursor.fetchone()['manifest_count']
            
            # Get dependency count
            cursor = conn.execute("""
                SELECT COUNT(*) as dep_count
                FROM repo_dependencies
                WHERE repo_full_name = ?
            """, (repo_name,))
            dep_count = cursor.fetchone()['dep_count']
            
            # Get resolved count
            cursor = conn.execute("""
                SELECT COUNT(*) as resolved_count
                FROM repo_dependencies
                WHERE repo_full_name = ?
                  AND resolved_repo IS NOT NULL
                  AND resolved_repo != ''
            """, (repo_name,))
            resolved_count = cursor.fetchone()['resolved_count']
            
            # Calculate resolution rate
            resolution_rate = (resolved_count / dep_count * 100) if dep_count > 0 else 0
            
            # Get manifest paths
            cursor = conn.execute("""
                SELECT DISTINCT manifest_path
                FROM repo_dependencies
                WHERE repo_full_name = ?
            """, (repo_name,))
            manifests = [row['manifest_path'] for row in cursor.fetchall()]
            
            # Get CVE count
            cursor = conn.execute("""
                SELECT COUNT(*) as cve_count
                FROM repo_cves
                WHERE repo_full_name = ?
            """, (repo_name,))
            cve_count = cursor.fetchone()['cve_count']
            
            # Detect errors (no manifests found = error)
            errors_count = 1 if manifest_count == 0 else 0
            error_messages = []
            if manifest_count == 0:
                error_messages.append("No manifests found")
            if dep_count == 0 and manifest_count > 0:
                error_messages.append("Manifests found but no dependencies parsed")
            if resolution_rate < 50 and dep_count > 0:
                error_messages.append(f"Low resolution rate: {resolution_rate:.1f}%")
            
            metrics.append({
                "repo_full_name": repo_name,
                "manifests_found": manifest_count,
                "manifest_paths": manifests,
                "deps_found": dep_count,
                "resolved_count": resolved_count,
                "resolution_rate": round(resolution_rate, 1),
                "cves_found": cve_count,
                "errors_count": errors_count,
                "error_messages": error_messages,
                "created_at": repo['created_at'],
                "updated_at": repo['updated_at'],
            })
        
        return metrics
    
    def _calculate_summary(self, repo_metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate summary statistics."""
        total_repos = len(repo_metrics)
        
        if total_repos == 0:
            return {
                "total_repos": 0,
                "repos_with_manifests": 0,
                "repos_with_deps": 0,
                "total_manifests": 0,
                "total_deps": 0,
                "total_resolved": 0,
                "avg_resolution_rate": 0,
                "total_cves": 0,
                "total_errors": 0,
                "repos_with_errors": 0,
                "manifest_type_distribution": {},
            }
        
        repos_with_manifests = sum(1 for r in repo_metrics if r['manifests_found'] > 0)
        repos_with_deps = sum(1 for r in repo_metrics if r['deps_found'] > 0)
        total_manifests = sum(r['manifests_found'] for r in repo_metrics)
        total_deps = sum(r['deps_found'] for r in repo_metrics)
        total_resolved = sum(r['resolved_count'] for r in repo_metrics)
        total_cves = sum(r['cves_found'] for r in repo_metrics)
        total_errors = sum(r['errors_count'] for r in repo_metrics)
        repos_with_errors = sum(1 for r in repo_metrics if r['errors_count'] > 0)
        
        avg_resolution_rate = (total_resolved / total_deps * 100) if total_deps > 0 else 0
        
        # Manifest type distribution
        manifest_types = {}
        for repo in repo_metrics:
            for manifest in repo['manifest_paths']:
                # Extract file type
                if 'requirements' in manifest:
                    manifest_type = 'requirements.txt'
                elif 'pyproject.toml' in manifest:
                    manifest_type = 'pyproject.toml'
                elif 'package.json' in manifest:
                    manifest_type = 'package.json'
                elif 'pom.xml' in manifest:
                    manifest_type = 'pom.xml'
                elif 'go.mod' in manifest:
                    manifest_type = 'go.mod'
                else:
                    manifest_type = 'other'
                
                manifest_types[manifest_type] = manifest_types.get(manifest_type, 0) + 1
        
        return {
            "total_repos": total_repos,
            "repos_with_manifests": repos_with_manifests,
            "repos_with_deps": repos_with_deps,
            "total_manifests": total_manifests,
            "total_deps": total_deps,
            "total_resolved": total_resolved,
            "avg_resolution_rate": round(avg_resolution_rate, 1),
            "total_cves": total_cves,
            "total_errors": total_errors,
            "repos_with_errors": repos_with_errors,
            "manifest_type_distribution": manifest_types,
        }
    
    def _evaluate_quality_gate(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate quality gate criteria.
        
        Gate passes if:
        - At least 80% of repos have manifests
        - At least 70% of repos have dependencies
        - Average resolution rate >= 75%
        - Less than 20% of repos have errors
        """
        total_repos = summary['total_repos']
        
        if total_repos == 0:
            return {
                "passed": False,
                "reason": "No repos ingested",
                "criteria": {}
            }
        
        # Calculate criteria
        manifest_coverage = (summary['repos_with_manifests'] / total_repos * 100)
        dep_coverage = (summary['repos_with_deps'] / total_repos * 100)
        resolution_rate = summary['avg_resolution_rate']
        error_rate = (summary['repos_with_errors'] / total_repos * 100)
        
        criteria = {
            "manifest_coverage": {
                "value": round(manifest_coverage, 1),
                "threshold": 80.0,
                "passed": manifest_coverage >= 80.0,
                "description": "At least 80% of repos have manifests"
            },
            "dependency_coverage": {
                "value": round(dep_coverage, 1),
                "threshold": 70.0,
                "passed": dep_coverage >= 70.0,
                "description": "At least 70% of repos have dependencies"
            },
            "resolution_rate": {
                "value": round(resolution_rate, 1),
                "threshold": 75.0,
                "passed": resolution_rate >= 75.0,
                "description": "Average resolution rate >= 75%"
            },
            "error_rate": {
                "value": round(error_rate, 1),
                "threshold": 20.0,
                "passed": error_rate <= 20.0,
                "description": "Less than 20% of repos have errors"
            }
        }
        
        # Gate passes if all criteria pass
        all_passed = all(c['passed'] for c in criteria.values())
        
        # Identify failing criteria
        failing_criteria = [
            name for name, c in criteria.items() if not c['passed']
        ]
        
        return {
            "passed": all_passed,
            "criteria": criteria,
            "failing_criteria": failing_criteria,
            "recommendation": self._get_recommendation(failing_criteria)
        }
    
    def _get_recommendation(self, failing_criteria: List[str]) -> str:
        """Get recommendation based on failing criteria."""
        if not failing_criteria:
            return "Quality gate passed. Proceed with full dataset ingestion."
        
        recommendations = []
        
        if "manifest_coverage" in failing_criteria:
            recommendations.append(
                "Low manifest coverage: Check manifest discovery logic. "
                "Verify repos have manifest files (requirements.txt, package.json, etc.)"
            )
        
        if "dependency_coverage" in failing_criteria:
            recommendations.append(
                "Low dependency coverage: Check dependency parsing logic. "
                "Verify parsers handle all manifest formats correctly."
            )
        
        if "resolution_rate" in failing_criteria:
            recommendations.append(
                "Low resolution rate: Check package resolver logic. "
                "Verify PyPI/npm API queries are working correctly."
            )
        
        if "error_rate" in failing_criteria:
            recommendations.append(
                "High error rate: Review error logs. "
                "Fix discovery/parsing issues before full ingestion."
            )
        
        return " ".join(recommendations)
    
    def print_report(self, report: Dict[str, Any]) -> None:
        """Print report in human-readable format."""
        print(f"\n{'='*80}")
        print(f"DATASET QUALITY REPORT")
        print(f"{'='*80}")
        print(f"Generated: {report['generated_at']}")
        print(f"Database: {report['database']}")
        print(f"{'='*80}\n")
        
        # Summary
        summary = report['summary']
        print(f"SUMMARY STATISTICS")
        print(f"{'-'*80}")
        print(f"Total repos:              {summary['total_repos']}")
        if summary['total_repos'] > 0:
            print(f"Repos with manifests:     {summary['repos_with_manifests']} "
                  f"({summary['repos_with_manifests']/summary['total_repos']*100:.1f}%)")
            print(f"Repos with dependencies:  {summary['repos_with_deps']} "
                  f"({summary['repos_with_deps']/summary['total_repos']*100:.1f}%)")
        else:
            print(f"Repos with manifests:     {summary['repos_with_manifests']}")
            print(f"Repos with dependencies:  {summary['repos_with_deps']}")
        print(f"Total manifests:          {summary['total_manifests']}")
        print(f"Total dependencies:       {summary['total_deps']}")
        print(f"Total resolved:           {summary['total_resolved']} "
              f"({summary['avg_resolution_rate']:.1f}%)")
        print(f"Total CVEs:               {summary['total_cves']}")
        if summary['total_repos'] > 0:
            print(f"Repos with errors:        {summary['repos_with_errors']} "
                  f"({summary['repos_with_errors']/summary['total_repos']*100:.1f}%)")
        else:
            print(f"Repos with errors:        {summary['repos_with_errors']}")
        print(f"\nManifest Type Distribution:")
        for manifest_type, count in summary['manifest_type_distribution'].items():
            print(f"  {manifest_type:<20} {count}")
        print(f"{'='*80}\n")
        
        # Quality Gate
        gate = report['quality_gate']
        print(f"QUALITY GATE")
        print(f"{'-'*80}")
        print(f"Status: {'✅ PASSED' if gate['passed'] else '❌ FAILED'}\n")
        
        for name, criterion in gate['criteria'].items():
            status = "✅" if criterion['passed'] else "❌"
            print(f"{status} {criterion['description']}")
            print(f"   Value: {criterion['value']}% | Threshold: {criterion['threshold']}%")
        
        if not gate['passed']:
            if 'failing_criteria' in gate:
                print(f"\nFailing Criteria: {', '.join(gate['failing_criteria'])}")
            if 'recommendation' in gate:
                print(f"\nRecommendation:")
                print(f"  {gate['recommendation']}")
        
        print(f"{'='*80}\n")
        
        # Per-Repo Details
        print(f"PER-REPO METRICS")
        print(f"{'-'*80}")
        print(f"{'Repository':<35} {'Mnfst':<6} {'Deps':<6} {'Rslvd':<6} {'Rate':<6} {'CVEs':<6} {'Errs':<6}")
        print(f"{'-'*80}")
        
        for repo in report['repos']:
            errors_marker = "⚠️ " if repo['errors_count'] > 0 else "   "
            print(
                f"{errors_marker}{repo['repo_full_name']:<32} "
                f"{repo['manifests_found']:<6} "
                f"{repo['deps_found']:<6} "
                f"{repo['resolved_count']:<6} "
                f"{repo['resolution_rate']:<5.1f}% "
                f"{repo['cves_found']:<6} "
                f"{repo['errors_count']:<6}"
            )
            
            # Show error messages
            if repo['error_messages']:
                for error in repo['error_messages']:
                    print(f"      └─ {error}")
        
        print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(description='Generate dataset quality report')
    parser.add_argument(
        '--db-path',
        default='data/graphs.db',
        help='Path to database (default: data/graphs.db)'
    )
    parser.add_argument(
        '--output',
        help='Output JSON file (optional)'
    )
    parser.add_argument(
        '--json-only',
        action='store_true',
        help='Output JSON only (no human-readable format)'
    )
    
    args = parser.parse_args()
    
    # Generate report
    reporter = DatasetReporter(db_path=args.db_path)
    report = reporter.generate_report()
    
    # Print human-readable format
    if not args.json_only:
        reporter.print_report(report)
    
    # Save JSON if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"Report saved to {args.output}")
    
    # Print JSON if requested
    if args.json_only:
        print(json.dumps(report, indent=2))
    
    # Exit with appropriate code
    sys.exit(0 if report['quality_gate']['passed'] else 1)


if __name__ == '__main__':
    main()
