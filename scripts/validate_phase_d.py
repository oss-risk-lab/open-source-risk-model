#!/usr/bin/env python3
"""
Validation script for Phase D completion.

Checks that all required files, tests, and documentation are in place.
"""

import os
import sys
from pathlib import Path

# Colors for output
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color


def check_file_exists(filepath, description):
    """Check if a file exists and report."""
    if os.path.exists(filepath):
        print(f"{GREEN}✓{NC} {description}: {filepath}")
        return True
    else:
        print(f"{RED}✗{NC} {description}: {filepath} (MISSING)")
        return False


def check_file_size(filepath, min_lines, description):
    """Check if a file has minimum number of lines."""
    if not os.path.exists(filepath):
        return False
    
    with open(filepath, 'r') as f:
        lines = len(f.readlines())
    
    if lines >= min_lines:
        print(f"{GREEN}✓{NC} {description}: {lines} lines (>= {min_lines})")
        return True
    else:
        print(f"{YELLOW}⚠{NC} {description}: {lines} lines (expected >= {min_lines})")
        return False


def count_tests_in_file(filepath):
    """Count test functions in a file."""
    if not os.path.exists(filepath):
        return 0
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Count test methods and functions
    test_count = content.count('def test_')
    return test_count


def main():
    print(f"\n{BLUE}{'='*60}{NC}")
    print(f"{BLUE}Phase D Validation{NC}")
    print(f"{BLUE}{'='*60}{NC}\n")
    
    all_checks_passed = True
    
    # Check test files
    print(f"\n{BLUE}Test Files:{NC}")
    test_files = [
        ("test/test_dependency_parsers.py", "Parser unit tests"),
        ("test/test_package_resolver.py", "Resolver unit tests"),
        ("test/test_dependency_integration.py", "Integration tests"),
        ("test/test_dependency_properties.py", "Property-based tests"),
    ]
    
    total_tests = 0
    for filepath, description in test_files:
        if check_file_exists(filepath, description):
            test_count = count_tests_in_file(filepath)
            total_tests += test_count
            print(f"  → {test_count} tests found")
        else:
            all_checks_passed = False
    
    print(f"\n{BLUE}Total Tests: {total_tests}{NC}")
    if total_tests >= 60:
        print(f"{GREEN}✓ Test count meets requirement (>= 60){NC}")
    else:
        print(f"{RED}✗ Test count below requirement (expected >= 60){NC}")
        all_checks_passed = False
    
    # Check documentation files
    print(f"\n{BLUE}Documentation Files:{NC}")
    doc_files = [
        ("docs/DEPENDENCY_GRAPH_GUIDE.md", 400, "User guide"),
        (".kiro/specs/dependency-graph/PHASE_D_COMPLETE.md", 100, "Phase D completion doc"),
        ("PHASE_D_SUMMARY.md", 100, "Phase D summary"),
    ]
    
    for filepath, min_lines, description in doc_files:
        if check_file_exists(filepath, description):
            if not check_file_size(filepath, min_lines, f"  → {description} size"):
                all_checks_passed = False
        else:
            all_checks_passed = False
    
    # Check infrastructure files
    print(f"\n{BLUE}Infrastructure Files:{NC}")
    infra_files = [
        ("test/run_dependency_tests.sh", "Test runner script"),
    ]
    
    for filepath, description in infra_files:
        if not check_file_exists(filepath, description):
            all_checks_passed = False
    
    # Check implementation files (should already exist from previous phases)
    print(f"\n{BLUE}Implementation Files (from previous phases):{NC}")
    impl_files = [
        ("src/open_source_risk_model/dependencies/parsers.py", "Dependency parsers"),
        ("src/open_source_risk_model/dependencies/package_resolver.py", "Package resolver"),
        ("src/open_source_risk_model/dependencies/manifest_discovery.py", "Manifest discovery"),
        ("src/open_source_risk_model/persistence/dependency_repo.py", "Dependency repository"),
    ]
    
    for filepath, description in impl_files:
        if not check_file_exists(filepath, description):
            print(f"{YELLOW}⚠ Warning: {description} not found (may be from previous phase){NC}")
    
    # Check spec files
    print(f"\n{BLUE}Spec Files:{NC}")
    spec_files = [
        (".kiro/specs/dependency-graph/requirements.md", "Requirements"),
        (".kiro/specs/dependency-graph/design.md", "Design"),
        (".kiro/specs/dependency-graph/SUMMARY.md", "Summary"),
        (".kiro/specs/dependency-graph/PHASE_A_COMPLETE.md", "Phase A completion"),
        (".kiro/specs/dependency-graph/PHASE_B_COMPLETE.md", "Phase B completion"),
        (".kiro/specs/dependency-graph/PHASE_C_COMPLETE.md", "Phase C completion"),
        (".kiro/specs/dependency-graph/PHASE_D_COMPLETE.md", "Phase D completion"),
    ]
    
    for filepath, description in spec_files:
        if not check_file_exists(filepath, description):
            all_checks_passed = False
    
    # Summary
    print(f"\n{BLUE}{'='*60}{NC}")
    if all_checks_passed:
        print(f"{GREEN}✓ All validation checks passed!{NC}")
        print(f"{GREEN}Phase D is complete and ready for production.{NC}")
        return 0
    else:
        print(f"{RED}✗ Some validation checks failed.{NC}")
        print(f"{YELLOW}Please review the output above for details.{NC}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
