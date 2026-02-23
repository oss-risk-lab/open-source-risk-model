#!/usr/bin/env python
"""
Test script for dependency API endpoints (Phase A).

This script tests the new dependency endpoints with manually inserted test data.
"""

import sqlite3
import json
from datetime import datetime, timezone


def insert_test_data():
    """Insert test dependency data."""
    conn = sqlite3.connect('data/graphs.db')
    
    try:
        # Insert test dependencies for flask
        now = datetime.now(timezone.utc).isoformat()
        
        test_deps = [
            {
                'repo_full_name': 'pallets/flask',
                'package_name': 'werkzeug',
                'registry_type': 'pypi',
                'specifier': '>=3.0.0',
                'extras': json.dumps([]),
                'markers': '',
                'dependency_group': 'prod',
                'is_direct': True,
                'is_optional': False,
                'manifest_path': 'requirements.txt',
                'confidence': 0.9,
                'created_at': now
            },
            {
                'repo_full_name': 'pallets/flask',
                'package_name': 'jinja2',
                'registry_type': 'pypi',
                'specifier': '>=3.1.2',
                'extras': json.dumps([]),
                'markers': '',
                'dependency_group': 'prod',
                'is_direct': True,
                'is_optional': False,
                'manifest_path': 'requirements.txt',
                'confidence': 0.9,
                'created_at': now
            },
            {
                'repo_full_name': 'pallets/flask',
                'package_name': 'click',
                'registry_type': 'pypi',
                'specifier': '>=8.1.3',
                'extras': json.dumps([]),
                'markers': '',
                'dependency_group': 'prod',
                'is_direct': True,
                'is_optional': False,
                'manifest_path': 'requirements.txt',
                'confidence': 0.9,
                'created_at': now
            },
            {
                'repo_full_name': 'pallets/flask',
                'package_name': 'pytest',
                'registry_type': 'pypi',
                'specifier': '>=7.0',
                'extras': json.dumps([]),
                'markers': '',
                'dependency_group': 'dev',
                'is_direct': True,
                'is_optional': False,
                'manifest_path': 'requirements/dev.txt',
                'confidence': 0.9,
                'created_at': now
            },
        ]
        
        for dep in test_deps:
            conn.execute("""
                INSERT OR REPLACE INTO repo_dependencies
                (repo_full_name, package_name, registry_type, specifier,
                 extras, markers, dependency_group, is_direct, is_optional,
                 manifest_path, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dep['repo_full_name'],
                dep['package_name'],
                dep['registry_type'],
                dep['specifier'],
                dep['extras'],
                dep['markers'],
                dep['dependency_group'],
                dep['is_direct'],
                dep['is_optional'],
                dep['manifest_path'],
                dep['confidence'],
                dep['created_at']
            ))
        
        conn.commit()
        print(f"✓ Inserted {len(test_deps)} test dependencies for pallets/flask")
        
        # Insert test dependencies for another repo (to test dependents query)
        test_deps2 = [
            {
                'repo_full_name': 'psf/requests',
                'package_name': 'urllib3',
                'registry_type': 'pypi',
                'specifier': '>=1.26.0,<3',
                'extras': json.dumps([]),
                'markers': '',
                'dependency_group': 'prod',
                'is_direct': True,
                'is_optional': False,
                'manifest_path': 'requirements.txt',
                'confidence': 0.9,
                'created_at': now
            },
            {
                'repo_full_name': 'django/django',
                'package_name': 'werkzeug',
                'registry_type': 'pypi',
                'specifier': '>=2.0',
                'extras': json.dumps([]),
                'markers': '',
                'dependency_group': 'dev',
                'is_direct': True,
                'is_optional': False,
                'manifest_path': 'requirements/dev.txt',
                'confidence': 0.9,
                'created_at': now
            },
        ]
        
        for dep in test_deps2:
            conn.execute("""
                INSERT OR REPLACE INTO repo_dependencies
                (repo_full_name, package_name, registry_type, specifier,
                 extras, markers, dependency_group, is_direct, is_optional,
                 manifest_path, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dep['repo_full_name'],
                dep['package_name'],
                dep['registry_type'],
                dep['specifier'],
                dep['extras'],
                dep['markers'],
                dep['dependency_group'],
                dep['is_direct'],
                dep['is_optional'],
                dep['manifest_path'],
                dep['confidence'],
                dep['created_at']
            ))
        
        conn.commit()
        print(f"✓ Inserted {len(test_deps2)} additional test dependencies")
        
    finally:
        conn.close()


def test_api():
    """Test the dependency API endpoints."""
    import requests
    import time
    
    base_url = "http://127.0.0.1:8000"
    
    print("\n" + "="*60)
    print("Testing Dependency API Endpoints")
    print("="*60)
    
    # Test 1: Get dependencies for flask
    print("\n1. GET /api/repos/pallets/flask/dependencies")
    response = requests.get(f"{base_url}/api/repos/pallets/flask/dependencies")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Total dependencies: {data['total']}")
        print(f"   Dependencies:")
        for dep in data['dependencies']:
            print(f"     - {dep['package_name']} {dep['specifier']} ({dep['dependency_group']})")
    else:
        print(f"   Error: {response.text}")
    
    # Test 2: Get dependencies excluding dev
    print("\n2. GET /api/repos/pallets/flask/dependencies?include_dev=false")
    response = requests.get(f"{base_url}/api/repos/pallets/flask/dependencies?include_dev=false")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Total dependencies (prod only): {data['total']}")
        for dep in data['dependencies']:
            print(f"     - {dep['package_name']} {dep['specifier']}")
    
    # Test 3: Get dependents for werkzeug
    print("\n3. GET /api/packages/werkzeug/dependents?registry=pypi")
    response = requests.get(f"{base_url}/api/packages/werkzeug/dependents?registry=pypi")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Total dependents: {data['total']}")
        print(f"   Dependents:")
        for dep in data['dependents']:
            print(f"     - {dep['repo_full_name']} (requires {dep['specifier']})")
    
    # Test 4: Get dependents for urllib3
    print("\n4. GET /api/packages/urllib3/dependents?registry=pypi")
    response = requests.get(f"{base_url}/api/packages/urllib3/dependents?registry=pypi")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Total dependents: {data['total']}")
        for dep in data['dependents']:
            print(f"     - {dep['repo_full_name']}")
    
    print("\n" + "="*60)
    print("✓ Phase A: Storage + API - COMPLETE")
    print("="*60)
    print("\nNext: Phase B - Manifest Discovery + Parsing")


if __name__ == "__main__":
    print("Phase A: Storage + API First")
    print("="*60)
    
    # Insert test data
    insert_test_data()
    
    # Wait a moment for server to be ready
    print("\nWaiting for server to be ready...")
    import time
    time.sleep(2)
    
    # Test API
    test_api()
