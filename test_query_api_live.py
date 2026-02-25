#!/usr/bin/env python3
"""
Live test script for Query API in dev mode.
No OpenAI API key required!

Usage:
    python test_query_api_live.py
"""

import requests
import json
from typing import Dict, Any

API_URL = "http://localhost:8000"


def query(intent: str, parameters: Dict[str, Any], max_results: int = 100) -> Dict:
    """Execute a query in dev mode."""
    response = requests.post(
        f"{API_URL}/api/query",
        json={
            "query": f"Testing {intent}",
            "intent": intent,
            "parameters": parameters,
            "max_results": max_results
        }
    )
    response.raise_for_status()
    return response.json()


def print_result(title: str, result: Dict):
    """Pretty print a query result."""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    print(f"Intent: {result['intent']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Result Count: {result['result_count']}")
    print(f"Execution Time: {result['execution_time_ms']}ms")
    print(f"\nResults:")
    print(json.dumps(result['results'][:3], indent=2))  # Show first 3 results
    if result['result_count'] > 3:
        print(f"... and {result['result_count'] - 3} more")


def main():
    print("Query API Dev Mode - Live Test")
    print("Make sure the API server is running: uvicorn api.app:app --reload")
    print()
    
    try:
        # Test 1: Dataset stats
        result = query("dataset_stats", {})
        print_result("1. Dataset Statistics", result)
        
        # Test 2: List dependencies
        result = query("list_dependencies", {"repo_full_name": "pallets/flask"}, max_results=10)
        print_result("2. List Dependencies (pallets/flask)", result)
        
        # Test 3: Find dependents
        result = query("find_dependents", {"package_name": "flask", "registry_type": "pypi"}, max_results=5)
        print_result("3. Find Dependents (flask)", result)
        
        # Test 4: Dependency tree
        result = query("get_dependency_tree", {"repo_full_name": "pallets/flask", "max_depth": 2}, max_results=20)
        print_result("4. Dependency Tree (pallets/flask, depth=2)", result)
        
        # Test 5: Repo stats
        result = query("repo_stats", {"repo_full_name": "pallets/flask"})
        print_result("5. Repository Statistics (pallets/flask)", result)
        
        # Test 6: List unresolved
        result = query("list_unresolved", {}, max_results=10)
        print_result("6. Unresolved Dependencies", result)
        
        # Test 7: Search repos
        result = query("search_repos", {"pattern": "%django%"}, max_results=5)
        print_result("7. Search Repositories (django)", result)
        
        # Test 8: Search packages
        result = query("search_packages", {"pattern": "flask%", "registry_type": "pypi"}, max_results=10)
        print_result("8. Search Packages (flask*)", result)
        
        print(f"\n{'='*60}")
        print("✅ All tests passed!")
        print(f"{'='*60}")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to API server")
        print("Make sure the server is running: uvicorn api.app:app --reload")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
