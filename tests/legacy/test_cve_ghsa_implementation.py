#!/usr/bin/env python3
"""
Test script for CVE/GHSA implementation.

Tests that both CVE and GHSA identifiers are properly extracted,
stored, and can be queried.
"""

import sqlite3
from src.open_source_risk_model.graph.cve_fetcher import CVEFetcher
from src.open_source_risk_model.graph.builder import build_graph
from src.open_source_risk_model.graph.schema import GraphConfig
from src.open_source_risk_model.service.score_repo import score_repo
from src.open_source_risk_model.persistence.graph_repo import GraphRepository


def test_cve_fetcher():
    """Test that CVE fetcher extracts both CVE and GHSA IDs."""
    print("=" * 60)
    print("TEST 1: CVE Fetcher Extraction")
    print("=" * 60)
    
    fetcher = CVEFetcher()
    cves = fetcher.fetch_cves(ecosystem='PyPI', package_name='flask')
    
    print(f"✓ Found {len(cves)} CVEs for Flask\n")
    
    if cves:
        cve = cves[0]
        print(f"First CVE:")
        print(f"  Primary ID: {cve.id}")
        print(f"  CVE ID: {cve.cve_id}")
        print(f"  GHSA ID: {cve.ghsa_id}")
        print(f"  Aliases: {cve.aliases}")
        print(f"  Severity: {cve.severity}")
        
        # Verify both IDs are present
        assert cve.cve_id is not None, "CVE ID should not be None"
        assert cve.ghsa_id is not None, "GHSA ID should not be None"
        assert len(cve.aliases) > 0, "Aliases should not be empty"
        
        print("\n✅ CVE Fetcher Test PASSED\n")
        return True
    else:
        print("❌ No CVEs found\n")
        return False


def test_graph_builder():
    """Test that graph builder includes CVE/GHSA data in nodes."""
    print("=" * 60)
    print("TEST 2: Graph Builder CVE Nodes")
    print("=" * 60)
    
    score_data = score_repo('pallets/flask')
    config = GraphConfig(include_cves=True, max_releases=3)
    graph = build_graph('pallets/flask', score_data, config)
    
    cve_nodes = [n for n in graph.nodes if n.type.value == 'cve']
    print(f"✓ Found {len(cve_nodes)} CVE nodes in graph\n")
    
    if cve_nodes:
        cve = cve_nodes[0]
        print(f"First CVE node:")
        print(f"  Node ID: {cve.id}")
        print(f"  Label: {cve.label}")
        print(f"  cve_id: {cve.metadata.get('cve_id')}")
        print(f"  ghsa_id: {cve.metadata.get('ghsa_id')}")
        print(f"  aliases: {cve.metadata.get('aliases')}")
        
        # Verify metadata includes both IDs
        assert cve.metadata.get('cve_id') is not None, "CVE ID should be in metadata"
        assert cve.metadata.get('ghsa_id') is not None, "GHSA ID should be in metadata"
        assert cve.metadata.get('aliases') is not None, "Aliases should be in metadata"
        
        print("\n✅ Graph Builder Test PASSED\n")
        return True
    else:
        print("❌ No CVE nodes found\n")
        return False


def test_database_storage():
    """Test that CVE/GHSA data is stored correctly in database."""
    print("=" * 60)
    print("TEST 3: Database Storage")
    print("=" * 60)
    
    # Build and save graph
    score_data = score_repo('pallets/flask')
    config = GraphConfig(include_cves=True, max_releases=3)
    graph = build_graph('pallets/flask', score_data, config)
    
    repo = GraphRepository('data/graphs.db')
    repo.save_graph('pallets/flask', graph, generation_time_ms=100)
    print("✓ Graph saved to database\n")
    
    # Query database
    conn = sqlite3.connect('data/graphs.db')
    cursor = conn.execute("""
        SELECT cve_id, ghsa_id, cve_aliases, severity
        FROM repo_cves
        WHERE repo_full_name = 'pallets/flask'
        ORDER BY cve_id
        LIMIT 2
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    print(f"✓ Found {len(rows)} CVE records in database\n")
    
    if rows:
        print("First CVE record:")
        cve_id, ghsa_id, cve_aliases, severity = rows[0]
        print(f"  cve_id: {cve_id}")
        print(f"  ghsa_id: {ghsa_id}")
        print(f"  cve_aliases: {cve_aliases}")
        print(f"  severity: {severity[:50]}...")
        
        # Verify both columns are populated
        assert cve_id is not None, "cve_id column should not be None"
        assert ghsa_id is not None, "ghsa_id column should not be None"
        assert cve_aliases is not None, "cve_aliases column should not be None"
        
        print("\n✅ Database Storage Test PASSED\n")
        return True
    else:
        print("❌ No CVE records found in database\n")
        return False


def test_database_queries():
    """Test that we can query by both CVE and GHSA IDs."""
    print("=" * 60)
    print("TEST 4: Database Queries")
    print("=" * 60)
    
    conn = sqlite3.connect('data/graphs.db')
    
    # First, get an actual CVE from the database
    cursor = conn.execute("""
        SELECT cve_id, ghsa_id
        FROM repo_cves
        WHERE repo_full_name = 'pallets/flask'
        LIMIT 1
    """)
    sample = cursor.fetchone()
    
    if not sample:
        print("❌ No CVEs found in database to test with")
        conn.close()
        return False
    
    test_cve_id, test_ghsa_id = sample
    print(f"Testing with: CVE={test_cve_id}, GHSA={test_ghsa_id}\n")
    
    # Query by CVE ID
    cursor = conn.execute("""
        SELECT repo_full_name, cve_id, ghsa_id
        FROM repo_cves
        WHERE cve_id = ?
    """, (test_cve_id,))
    cve_result = cursor.fetchone()
    
    # Query by GHSA ID
    cursor = conn.execute("""
        SELECT repo_full_name, cve_id, ghsa_id
        FROM repo_cves
        WHERE ghsa_id = ?
    """, (test_ghsa_id,))
    ghsa_result = cursor.fetchone()
    
    conn.close()
    
    print("Query by CVE ID:")
    if cve_result:
        print(f"  ✓ Found: {cve_result[0]} - CVE: {cve_result[1]}, GHSA: {cve_result[2]}")
    else:
        print("  ❌ Not found")
    
    print("\nQuery by GHSA ID:")
    if ghsa_result:
        print(f"  ✓ Found: {ghsa_result[0]} - CVE: {ghsa_result[1]}, GHSA: {ghsa_result[2]}")
    else:
        print("  ❌ Not found")
    
    # Verify both queries work
    assert cve_result is not None, "Should be able to query by CVE ID"
    assert ghsa_result is not None, "Should be able to query by GHSA ID"
    assert cve_result == ghsa_result, "Both queries should return the same record"
    
    print("\n✅ Database Queries Test PASSED\n")
    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("CVE/GHSA Implementation Test Suite")
    print("=" * 60 + "\n")
    
    results = []
    
    try:
        results.append(("CVE Fetcher", test_cve_fetcher()))
    except Exception as e:
        print(f"❌ CVE Fetcher Test FAILED: {e}\n")
        results.append(("CVE Fetcher", False))
    
    try:
        results.append(("Graph Builder", test_graph_builder()))
    except Exception as e:
        print(f"❌ Graph Builder Test FAILED: {e}\n")
        results.append(("Graph Builder", False))
    
    try:
        results.append(("Database Storage", test_database_storage()))
    except Exception as e:
        print(f"❌ Database Storage Test FAILED: {e}\n")
        results.append(("Database Storage", False))
    
    try:
        results.append(("Database Queries", test_database_queries()))
    except Exception as e:
        print(f"❌ Database Queries Test FAILED: {e}\n")
        results.append(("Database Queries", False))
    
    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:.<40} {status}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! CVE/GHSA implementation is working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed.")
        return 1


if __name__ == "__main__":
    exit(main())
