"""CLI command for transitive dependency resolution."""
import argparse
import sys
import logging

from open_source_risk_model.resolution.resolver import TransitiveResolver
from open_source_risk_model.resolution.budget_tracker import BudgetConfig
from open_source_risk_model.resolution.storage import ResolvedDependencyStorage

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve transitive dependencies for a repository"
    )
    parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--ecosystems", help="Comma-separated ecosystem filter")
    parser.add_argument("--budget", type=int, default=200)
    parser.add_argument("--force", action="store_true",
                        help="Re-resolve even if data exists")
    parser.add_argument("--db-path", default="data/graphs.db")
    args = parser.parse_args()

    storage = ResolvedDependencyStorage(args.db_path)

    # Check for existing data
    if not args.force and storage.has_resolved_data(args.repo):
        oldest = storage.get_oldest_resolved_at(args.repo)
        print(f"Resolved data already exists for {args.repo} (since {oldest}).")
        print("Use --force to re-resolve.")
        return 0

    # Check direct deps exist
    eco_filter = set(args.ecosystems.split(",")) if args.ecosystems else None
    budget_config = BudgetConfig(global_budget=args.budget)
    resolver = TransitiveResolver(
        db_path=args.db_path, max_depth=args.max_depth,
        budget_config=budget_config, ecosystem_filter=eco_filter,
    )
    direct_deps = resolver._get_direct_deps(args.repo)
    if not direct_deps:
        print(f"No direct dependencies found for {args.repo}. "
              "Run dependency ingestion first.", file=sys.stderr)
        return 1

    # Resolve
    edges, summary = resolver.resolve_repo(args.repo)

    # Store
    storage.store_edges(args.repo, edges)

    # Print summary
    print(f"\nResolution complete for {args.repo}")
    print(f"  Total edges:        {summary.total_edges}")
    print(f"  Resolved:           {summary.resolved_count}")
    print(f"  Errors:             {summary.error_count}")
    print(f"  Cycles:             {summary.cycle_count}")
    print(f"  Max depth reached:  {summary.max_depth_reached_count}")
    print(f"  Budget exhausted:   {summary.budget_exhausted_count}")
    print(f"  Unsupported eco:    {summary.unsupported_ecosystem_count}")
    print(f"  Max depth seen:     {summary.actual_max_depth}")
    print(f"  API calls:          {summary.api_calls_made}")
    print(f"  Cache hits:         {summary.cache_hits}")
    print(f"  Elapsed:            {summary.elapsed_seconds:.1f}s")
    if summary.edges_per_depth:
        print(f"  Edges per depth:    {dict(sorted(summary.edges_per_depth.items()))}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
