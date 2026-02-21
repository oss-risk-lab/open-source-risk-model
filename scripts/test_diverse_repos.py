"""
Test supply chain graph on diverse repositories and document findings.

This script tests the graph generation on various types of repositories
to identify interesting patterns and validate robustness.
"""

import requests
import json
import time
from typing import Dict, Any, List

# Test repositories covering different scenarios
TEST_REPOS = [
    # Large, well-maintained projects
    ("numpy/numpy", "Large scientific computing library"),
    ("psf/requests", "Popular HTTP library"),
    ("django/django", "Web framework"),
    
    # Security-focused
    ("pyca/cryptography", "Cryptography library (likely has CVEs)"),
    
    # Small/example repos
    ("octocat/Hello-World", "GitHub's example repository"),
    
    # Different ecosystems
    ("expressjs/express", "Node.js web framework"),
    ("spring-projects/spring-boot", "Java framework"),
    
    # Archived/unmaintained
    ("moment/moment", "Archived JavaScript library"),
    
    # Monorepo
    ("vercel/next.js", "Large monorepo"),
    
    # New/small project
    ("fastapi/fastapi", "Modern Python web framework"),
]

API_BASE = "http://localhost:8000"


def test_repo(repo: str, description: str) -> Dict[str, Any]:
    """Test graph generation for a repository."""
    print(f"\n{'='*60}")
    print(f"Testing: {repo}")
    print(f"Description: {description}")
    print(f"{'='*60}")
    
    start_time = time.time()
    
    try:
        response = requests.get(
            f"{API_BASE}/api/graph",
            params={"repo": repo},
            timeout=30
        )
        
        elapsed = time.time() - start_time
        
        if response.status_code != 200:
            print(f"❌ Failed: HTTP {response.status_code}")
            print(f"   Error: {response.json().get('detail', 'Unknown error')}")
            return {
                "repo": repo,
                "description": description,
                "status": "failed",
                "error": response.json().get('detail'),
                "elapsed": elapsed
            }
        
        data = response.json()
        graph = data["graph"]
        metadata = data["metadata"]
        
        # Analyze the graph
        node_types = {}
        for node in graph["nodes"]:
            node_type = node["type"]
            node_types[node_type] = node_types.get(node_type, 0) + 1
        
        # Check for interesting patterns
        has_cves = node_types.get("cve", 0) > 0
        has_releases = node_types.get("release", 0) > 0
        has_registry = node_types.get("registry", 0) > 0
        
        # Get data sources
        data_sources = metadata.get("data_sources", [])
        
        # Find interesting nodes
        cve_nodes = [n for n in graph["nodes"] if n["type"] == "cve"]
        high_severity_cves = [
            n for n in cve_nodes 
            if n.get("metadata", {}).get("severity") in ["HIGH", "CRITICAL"]
        ]
        
        print(f"✅ Success in {elapsed:.2f}s")
        print(f"   Nodes: {len(graph['nodes'])} | Edges: {len(graph['edges'])}")
        print(f"   Node types: {dict(sorted(node_types.items()))}")
        print(f"   Data sources: {', '.join(data_sources)}")
        print(f"   Cache hit: {metadata.get('cache_hit', False)}")
        
        if has_cves:
            print(f"   🔴 CVEs found: {node_types['cve']} total, {len(high_severity_cves)} high/critical")
        
        if has_releases:
            print(f"   📦 Releases: {node_types['release']}")
        
        if has_registry:
            registries = [n for n in graph["nodes"] if n["type"] == "registry"]
            registry_types = [n["metadata"]["registry_type"] for n in registries]
            print(f"   📚 Registries: {', '.join(registry_types)}")
        
        # Check confidence levels
        low_confidence_nodes = [
            n for n in graph["nodes"]
            if n.get("provenance", {}).get("confidence", 1.0) < 0.8
            or n.get("provenance", {}).get("data_confidence", 1.0) < 0.8
        ]
        
        if low_confidence_nodes:
            print(f"   ⚠️  Low confidence nodes: {len(low_confidence_nodes)}")
        
        return {
            "repo": repo,
            "description": description,
            "status": "success",
            "elapsed": elapsed,
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "node_types": node_types,
            "data_sources": data_sources,
            "has_cves": has_cves,
            "cve_count": node_types.get("cve", 0),
            "high_severity_cve_count": len(high_severity_cves),
            "cache_hit": metadata.get("cache_hit", False),
            "low_confidence_count": len(low_confidence_nodes),
        }
        
    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        print(f"❌ Timeout after {elapsed:.2f}s")
        return {
            "repo": repo,
            "description": description,
            "status": "timeout",
            "elapsed": elapsed
        }
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ Error: {e}")
        return {
            "repo": repo,
            "description": description,
            "status": "error",
            "error": str(e),
            "elapsed": elapsed
        }


def generate_report(results: List[Dict[str, Any]]):
    """Generate a markdown report of findings."""
    print(f"\n\n{'='*60}")
    print("SUMMARY REPORT")
    print(f"{'='*60}\n")
    
    successful = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] != "success"]
    
    print(f"Total repos tested: {len(results)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    
    if successful:
        avg_time = sum(r["elapsed"] for r in successful) / len(successful)
        avg_nodes = sum(r["node_count"] for r in successful) / len(successful)
        avg_edges = sum(r["edge_count"] for r in successful) / len(successful)
        
        print(f"\nPerformance:")
        print(f"  Average time: {avg_time:.2f}s")
        print(f"  Average nodes: {avg_nodes:.1f}")
        print(f"  Average edges: {avg_edges:.1f}")
        
        repos_with_cves = [r for r in successful if r["has_cves"]]
        if repos_with_cves:
            print(f"\nSecurity:")
            print(f"  Repos with CVEs: {len(repos_with_cves)}/{len(successful)}")
            total_cves = sum(r["cve_count"] for r in repos_with_cves)
            total_high = sum(r["high_severity_cve_count"] for r in repos_with_cves)
            print(f"  Total CVEs found: {total_cves}")
            print(f"  High/Critical CVEs: {total_high}")
        
        print(f"\nInteresting Findings:")
        for result in successful:
            if result["high_severity_cve_count"] > 0:
                print(f"  🔴 {result['repo']}: {result['high_severity_cve_count']} high/critical CVEs")
            if result["low_confidence_count"] > 5:
                print(f"  ⚠️  {result['repo']}: {result['low_confidence_count']} low-confidence nodes")
    
    if failed:
        print(f"\nFailed Repos:")
        for result in failed:
            print(f"  ❌ {result['repo']}: {result['status']}")
    
    # Save detailed results
    with open("DIVERSE_REPOS_RESULTS.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Detailed results saved to DIVERSE_REPOS_RESULTS.json")


def main():
    """Run tests on all repositories."""
    print("Supply Chain Graph - Diverse Repository Testing")
    print("=" * 60)
    print(f"Testing {len(TEST_REPOS)} repositories...")
    print(f"API: {API_BASE}")
    
    results = []
    
    for repo, description in TEST_REPOS:
        result = test_repo(repo, description)
        results.append(result)
        time.sleep(1)  # Be nice to the API
    
    generate_report(results)


if __name__ == "__main__":
    main()
