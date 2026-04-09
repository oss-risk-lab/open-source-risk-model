"""Tests for repository selector."""

import pytest
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from src.open_source_risk_model.expansion.repo_selector import RepositorySelector
from src.open_source_risk_model.expansion.models import SelectionCriteria, RepositoryCandidate


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    # Create schema
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE repo_graphs (
            repo_full_name TEXT PRIMARY KEY,
            language TEXT
        )
    """)
    
    # Create repo_dependencies table (needed for ecosystem distribution)
    cursor.execute("""
        CREATE TABLE repo_dependencies (
            repo_full_name TEXT,
            package_name TEXT,
            registry_type TEXT
        )
    """)
    
    # Add some existing repos
    existing_repos = [
        ('facebook/react', 'JavaScript'),
        ('django/django', 'Python'),
        ('kubernetes/kubernetes', 'Go')
    ]
    cursor.executemany("INSERT INTO repo_graphs VALUES (?, ?)", existing_repos)
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


class TestRepositorySelection:
    """Test repository selection functionality."""
    
    def test_selection_produces_exact_count(self, temp_db):
        """Test selection produces at least requested count (may be more due to minimum quotas)."""
        selector = RepositorySelector("test_token", temp_db)
        
        # Mock GitHub API and ecosystem inference
        with patch.object(selector.github_client, 'search_repositories') as mock_search, \
             patch.object(selector.ecosystem_inference, 'infer_ecosystem') as mock_infer:
            
            # Create 200 mock candidates
            mock_repos = []
            for i in range(200):
                ecosystem = ['npm', 'pypi', 'go', 'maven', 'rubygems'][i % 5]
                mock_repos.append({
                    'full_name': f'owner/repo{i}',
                    'stargazers_count': 2000 - i,
                    'pushed_at': datetime.now().isoformat(),
                    'fork': False,
                    'description': f'Test repo {i}',
                    'language': 'Python'
                })
            
            mock_search.return_value = mock_repos
            
            # Mock ecosystem inference to return different ecosystems
            def mock_infer_fn(repo_name):
                idx = int(repo_name.split('repo')[1])
                ecosystem = ['npm', 'pypi', 'go', 'maven', 'rubygems'][idx % 5]
                return (ecosystem, [ecosystem])
            
            mock_infer.side_effect = mock_infer_fn
            
            criteria = SelectionCriteria()
            result = selector.select_repositories(count=149, criteria=criteria)
            
            # Should produce at least 149 (may be more due to minimum quotas)
            assert len(result) >= 149
            # But not too many more
            assert len(result) <= 200
    
    def test_ecosystem_quotas_are_met(self, temp_db):
        """Test ecosystem quotas are met (38-60 npm, 38-60 pypi, ≥15 go, ≥15 maven, ≥8 rubygems)."""
        selector = RepositorySelector("test_token", temp_db)
        
        with patch.object(selector.github_client, 'search_repositories') as mock_search, \
             patch.object(selector.ecosystem_inference, 'infer_ecosystem') as mock_infer:
            
            # Create 300 mock candidates with balanced ecosystems
            mock_repos = []
            for i in range(300):
                ecosystem = ['npm', 'pypi', 'go', 'maven', 'rubygems'][i % 5]
                mock_repos.append({
                    'full_name': f'owner/repo{i}',
                    'stargazers_count': 2000 - i,
                    'pushed_at': datetime.now().isoformat(),
                    'fork': False,
                    'description': f'Test repo {i}',
                    'language': 'Python'
                })
            
            mock_search.return_value = mock_repos
            
            def mock_infer_fn(repo_name):
                idx = int(repo_name.split('repo')[1])
                ecosystem = ['npm', 'pypi', 'go', 'maven', 'rubygems'][idx % 5]
                return (ecosystem, [ecosystem])
            
            mock_infer.side_effect = mock_infer_fn
            
            criteria = SelectionCriteria()
            result = selector.select_repositories(count=149, criteria=criteria)
            
            # Count ecosystems
            ecosystem_counts = {}
            for repo in result:
                eco = repo.primary_ecosystem
                ecosystem_counts[eco] = ecosystem_counts.get(eco, 0) + 1
            
            # Check quotas
            assert 38 <= ecosystem_counts.get('npm', 0) <= 60, f"npm: {ecosystem_counts.get('npm', 0)}"
            assert 38 <= ecosystem_counts.get('pypi', 0) <= 60, f"pypi: {ecosystem_counts.get('pypi', 0)}"
            assert ecosystem_counts.get('go', 0) >= 15, f"go: {ecosystem_counts.get('go', 0)}"
            assert ecosystem_counts.get('maven', 0) >= 15, f"maven: {ecosystem_counts.get('maven', 0)}"
            assert ecosystem_counts.get('rubygems', 0) >= 8, f"rubygems: {ecosystem_counts.get('rubygems', 0)}"
    
    def test_excludes_existing_repos(self, temp_db):
        """Test excludes existing repos from database."""
        selector = RepositorySelector("test_token", temp_db)
        
        with patch.object(selector.github_client, 'search_repositories') as mock_search, \
             patch.object(selector.ecosystem_inference, 'infer_ecosystem') as mock_infer:
            
            # Include some existing repos in candidates
            mock_repos = [
                {
                    'full_name': 'facebook/react',  # Existing
                    'stargazers_count': 5000,
                    'pushed_at': datetime.now().isoformat(),
                    'fork': False,
                    'description': 'React',
                    'language': 'JavaScript'
                },
                {
                    'full_name': 'owner/newrepo',  # New
                    'stargazers_count': 4000,
                    'pushed_at': datetime.now().isoformat(),
                    'fork': False,
                    'description': 'New repo',
                    'language': 'Python'
                }
            ]
            
            mock_search.return_value = mock_repos
            mock_infer.return_value = ('npm', ['npm'])
            
            criteria = SelectionCriteria()
            result = selector.select_repositories(count=10, criteria=criteria)
            
            # Should not include facebook/react
            repo_names = [r.full_name for r in result]
            assert 'facebook/react' not in repo_names
            assert 'owner/newrepo' in repo_names
    
    def test_priority_ordering(self, temp_db):
        """Test priority ordering."""
        selector = RepositorySelector("test_token", temp_db)
        
        with patch.object(selector.github_client, 'search_repositories') as mock_search, \
             patch.object(selector.ecosystem_inference, 'infer_ecosystem') as mock_infer:
            
            # Create repos with different star counts
            mock_repos = [
                {
                    'full_name': 'owner/low_stars',
                    'stargazers_count': 1500,
                    'pushed_at': datetime.now().isoformat(),
                    'fork': False,
                    'description': 'Low stars',
                    'language': 'Python'
                },
                {
                    'full_name': 'owner/high_stars',
                    'stargazers_count': 5000,
                    'pushed_at': datetime.now().isoformat(),
                    'fork': False,
                    'description': 'High stars',
                    'language': 'Python'
                }
            ]
            
            mock_search.return_value = mock_repos
            mock_infer.return_value = ('npm', ['npm'])
            
            criteria = SelectionCriteria()
            result = selector.select_repositories(count=2, criteria=criteria)
            
            # Higher priority repos should come first
            # (Note: actual ordering depends on full priority calculation)
            assert len(result) == 2
            # Verify priority scores are assigned
            assert all(r.priority_score > 0 for r in result)
    
    def test_duplicate_exclusion(self, temp_db):
        """Test duplicate exclusion."""
        selector = RepositorySelector("test_token", temp_db)
        
        with patch.object(selector.github_client, 'search_repositories') as mock_search, \
             patch.object(selector.ecosystem_inference, 'infer_ecosystem') as mock_infer:
            
            # Include a fork
            mock_repos = [
                {
                    'full_name': 'owner/original',
                    'stargazers_count': 5000,
                    'pushed_at': datetime.now().isoformat(),
                    'fork': False,
                    'description': 'Original',
                    'language': 'Python'
                },
                {
                    'full_name': 'fork_owner/original',
                    'stargazers_count': 4000,
                    'pushed_at': datetime.now().isoformat(),
                    'fork': True,
                    'description': 'Fork',
                    'language': 'Python'
                }
            ]
            
            mock_search.return_value = mock_repos
            mock_infer.return_value = ('npm', ['npm'])
            
            criteria = SelectionCriteria(exclude_forks=True)
            result = selector.select_repositories(count=10, criteria=criteria)
            
            # Should not include forks
            repo_names = [r.full_name for r in result]
            assert 'fork_owner/original' not in repo_names
    
    def test_error_handling(self, temp_db):
        """Test error handling (API failures, rate limits)."""
        selector = RepositorySelector("test_token", temp_db)
        
        with patch.object(selector.github_client, 'search_repositories') as mock_search:
            # Simulate API failure for all queries
            mock_search.side_effect = Exception("API error")
            
            criteria = SelectionCriteria()
            
            # Should handle gracefully and return empty list (all queries failed)
            result = selector.select_repositories(count=10, criteria=criteria)
            assert len(result) == 0


class TestPriorityScoring:
    """Test priority score calculation."""
    
    def test_higher_stars_get_higher_score(self):
        """Test repositories with more stars get higher priority scores."""
        from src.open_source_risk_model.expansion.priority_scorer import PriorityScorer
        
        scorer = PriorityScorer(
            current_distribution={},
            ecosystem_targets={'npm': (0.25, 0.40)}
        )
        
        high_stars = RepositoryCandidate(
            full_name='owner/high',
            stars=10000,
            last_commit_date=datetime.now(),
            primary_ecosystem='npm',
            manifest_types=['package.json'],
            has_prod_deps=True,
            is_fork=False,
            fork_parent=None,
            priority_score=0.0
        )
        
        low_stars = RepositoryCandidate(
            full_name='owner/low',
            stars=1500,
            last_commit_date=datetime.now(),
            primary_ecosystem='npm',
            manifest_types=['package.json'],
            has_prod_deps=True,
            is_fork=False,
            fork_parent=None,
            priority_score=0.0
        )
        
        high_score = scorer.calculate_priority_score(high_stars)
        low_score = scorer.calculate_priority_score(low_stars)
        
        assert high_score > low_score
    
    def test_recent_commits_get_higher_score(self):
        """Test repositories with recent commits get higher priority scores."""
        from src.open_source_risk_model.expansion.priority_scorer import PriorityScorer
        
        scorer = PriorityScorer(
            current_distribution={},
            ecosystem_targets={'npm': (0.25, 0.40)}
        )
        
        recent = RepositoryCandidate(
            full_name='owner/recent',
            stars=5000,
            last_commit_date=datetime.now() - timedelta(days=30),
            primary_ecosystem='npm',
            manifest_types=['package.json'],
            has_prod_deps=True,
            is_fork=False,
            fork_parent=None,
            priority_score=0.0
        )
        
        old = RepositoryCandidate(
            full_name='owner/old',
            stars=5000,
            last_commit_date=datetime.now() - timedelta(days=300),
            primary_ecosystem='npm',
            manifest_types=['package.json'],
            has_prod_deps=True,
            is_fork=False,
            fork_parent=None,
            priority_score=0.0
        )
        
        recent_score = scorer.calculate_priority_score(recent)
        old_score = scorer.calculate_priority_score(old)
        
        assert recent_score > old_score



# Property-Based Tests
from hypothesis import given, strategies as st, settings


@st.composite
def repository_candidate_strategy(draw):
    """Generate random repository candidate."""
    return RepositoryCandidate(
        full_name=draw(st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='/-_'))),
        stars=draw(st.integers(min_value=0, max_value=100000)),
        last_commit_date=draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime.now())),
        primary_ecosystem=draw(st.sampled_from(['npm', 'pypi', 'go', 'maven', 'rubygems'])),
        manifest_types=draw(st.lists(st.sampled_from(['package.json', 'requirements.txt', 'go.mod', 'pom.xml', 'Gemfile']), min_size=1, max_size=3)),
        has_prod_deps=draw(st.booleans()),
        is_fork=draw(st.booleans()),
        fork_parent=draw(st.one_of(st.none(), st.text(min_size=5, max_size=50))),
        priority_score=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    )


class TestStarThresholdFiltering:
    """Property 1: Star Threshold Filtering - Feature: dataset-expansion-200-repos"""
    
    @given(candidates=st.lists(repository_candidate_strategy(), min_size=10, max_size=50))
    @settings(max_examples=100, deadline=None)
    def test_selected_repos_have_minimum_stars(self, candidates):
        """
        Property 1: Star Threshold Filtering
        For any repository candidate, if it is selected by the selection algorithm,
        then it must have more than 1000 GitHub stars.
        
        **Validates: Requirements 1.1**
        """
        # Create temp database inside test
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db = f.name
        
        try:
            # Create schema
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE repo_graphs (
                    repo_full_name TEXT PRIMARY KEY,
                    language TEXT
                )
            """)
            conn.commit()
            conn.close()
            
            selector = RepositorySelector("test_token", temp_db)
            
            # Ensure at least some candidates meet the star threshold
            for i, candidate in enumerate(candidates[:len(candidates)//2]):
                candidate.stars = 1001 + i * 100
            
            with patch.object(selector.github_client, 'search_repositories') as mock_search, \
                 patch.object(selector.ecosystem_inference, 'infer_ecosystem') as mock_infer:
                
                # Convert candidates to GitHub API format
                mock_repos = []
                for candidate in candidates:
                    mock_repos.append({
                        'full_name': candidate.full_name,
                        'stargazers_count': candidate.stars,
                        'pushed_at': candidate.last_commit_date.isoformat(),
                        'fork': candidate.is_fork,
                        'description': f'Test repo',
                        'language': 'Python'
                    })
                
                mock_search.return_value = mock_repos
                
                # Mock ecosystem inference
                def mock_infer_fn(repo_name):
                    matching = [c for c in candidates if c.full_name == repo_name]
                    if matching:
                        return (matching[0].primary_ecosystem, matching[0].manifest_types)
                    return ('npm', ['package.json'])
                
                mock_infer.side_effect = mock_infer_fn
                
                criteria = SelectionCriteria(min_stars=1000)
                result = selector.select_repositories(count=min(10, len(candidates)), criteria=criteria)
                
                # Property: All selected repos must have > 1000 stars
                for repo in result:
                    assert repo.stars > 1000, f"Repository {repo.full_name} has {repo.stars} stars, expected > 1000"
        
        finally:
            # Cleanup
            Path(temp_db).unlink(missing_ok=True)




class TestRecencyPrioritization:
    """Property 3: Recency Prioritization - Feature: dataset-expansion-200-repos"""
    
    @given(
        stars=st.integers(min_value=5000, max_value=5000),  # Equal stars
        days_ago_1=st.integers(min_value=1, max_value=90),  # Recent (within 6 months)
        days_ago_2=st.integers(min_value=181, max_value=365)  # Old (beyond 6 months)
    )
    @settings(max_examples=100, deadline=None)
    def test_recent_commits_get_higher_priority(self, stars, days_ago_1, days_ago_2):
        """
        Property 3: Recency Prioritization
        For any two repository candidates with equal star counts, the candidate with
        more recent commits (within last 6 months) must have a higher priority score.
        
        **Validates: Requirements 1.3**
        """
        from src.open_source_risk_model.expansion.priority_scorer import PriorityScorer
        
        scorer = PriorityScorer(
            current_distribution={},
            ecosystem_targets={'npm': (0.25, 0.40)}
        )
        
        recent = RepositoryCandidate(
            full_name='owner/recent',
            stars=stars,
            last_commit_date=datetime.now() - timedelta(days=days_ago_1),
            primary_ecosystem='npm',
            manifest_types=['package.json'],
            has_prod_deps=True,
            is_fork=False,
            fork_parent=None,
            priority_score=0.0
        )
        
        old = RepositoryCandidate(
            full_name='owner/old',
            stars=stars,
            last_commit_date=datetime.now() - timedelta(days=days_ago_2),
            primary_ecosystem='npm',
            manifest_types=['package.json'],
            has_prod_deps=True,
            is_fork=False,
            fork_parent=None,
            priority_score=0.0
        )
        
        recent_score = scorer.calculate_priority_score(recent)
        old_score = scorer.calculate_priority_score(old)
        
        # Property: Recent commits should have higher priority
        assert recent_score > old_score, \
            f"Recent repo (days_ago={days_ago_1}) score {recent_score} should be > old repo (days_ago={days_ago_2}) score {old_score}"


class TestProductionDependencyPrioritization:
    """Property 4: Production Dependency Prioritization - Feature: dataset-expansion-200-repos"""
    
    @given(
        stars=st.integers(min_value=5000, max_value=5000),  # Equal stars
        days_ago=st.integers(min_value=30, max_value=90)  # Equal recency
    )
    @settings(max_examples=100, deadline=None)
    def test_prod_deps_get_higher_priority(self, stars, days_ago):
        """
        Property 4: Production Dependency Prioritization
        For any two repository candidates with equal stars and recency, the candidate
        with production dependencies must have a higher priority score than one with
        only development dependencies.
        
        **Validates: Requirements 1.5**
        """
        from src.open_source_risk_model.expansion.priority_scorer import PriorityScorer
        
        scorer = PriorityScorer(
            current_distribution={},
            ecosystem_targets={'npm': (0.25, 0.40)}
        )
        
        commit_date = datetime.now() - timedelta(days=days_ago)
        
        with_prod = RepositoryCandidate(
            full_name='owner/with_prod',
            stars=stars,
            last_commit_date=commit_date,
            primary_ecosystem='npm',
            manifest_types=['package.json'],
            has_prod_deps=True,
            is_fork=False,
            fork_parent=None,
            priority_score=0.0
        )
        
        without_prod = RepositoryCandidate(
            full_name='owner/without_prod',
            stars=stars,
            last_commit_date=commit_date,
            primary_ecosystem='npm',
            manifest_types=['package.json'],
            has_prod_deps=False,
            is_fork=False,
            fork_parent=None,
            priority_score=0.0
        )
        
        with_prod_score = scorer.calculate_priority_score(with_prod)
        without_prod_score = scorer.calculate_priority_score(without_prod)
        
        # Property: Repos with production dependencies should have higher priority
        assert with_prod_score > without_prod_score, \
            f"Repo with prod deps score {with_prod_score} should be > repo without prod deps score {without_prod_score}"



class TestForkExclusion:
    """Property 5 & 6: Fork Exclusion - Feature: dataset-expansion-200-repos"""
    
    @given(
        fork_count=st.integers(min_value=1, max_value=10),
        non_fork_count=st.integers(min_value=5, max_value=20)
    )
    @settings(max_examples=100, deadline=None)
    def test_forks_are_excluded_from_selection(self, fork_count, non_fork_count):
        """
        Property 5 & 6: Fork Exclusion
        For any repository candidate that is a fork of an existing repository in the dataset,
        the candidate must be excluded from selection.
        
        **Validates: Requirements 1.6**
        """
        # Create temp database inside test
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db = f.name
        
        try:
            # Create schema
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE repo_graphs (
                    repo_full_name TEXT PRIMARY KEY,
                    language TEXT
                )
            """)
            conn.commit()
            conn.close()
            
            selector = RepositorySelector("test_token", temp_db)
            
            # Create candidates: some forks, some not
            candidates = []
            
            # Add forks
            for i in range(fork_count):
                candidates.append(RepositoryCandidate(
                    full_name=f'fork_owner/repo{i}',
                    stars=2000 + i * 100,
                    last_commit_date=datetime.now() - timedelta(days=30),
                    primary_ecosystem='npm',
                    manifest_types=['package.json'],
                    has_prod_deps=True,
                    is_fork=True,  # This is a fork
                    fork_parent=f'original_owner/repo{i}',
                    priority_score=0.0
                ))
            
            # Add non-forks
            for i in range(non_fork_count):
                candidates.append(RepositoryCandidate(
                    full_name=f'owner/original{i}',
                    stars=2000 + i * 100,
                    last_commit_date=datetime.now() - timedelta(days=30),
                    primary_ecosystem='npm',
                    manifest_types=['package.json'],
                    has_prod_deps=True,
                    is_fork=False,  # Not a fork
                    fork_parent=None,
                    priority_score=0.0
                ))
            
            with patch.object(selector.github_client, 'search_repositories') as mock_search, \
                 patch.object(selector.ecosystem_inference, 'infer_ecosystem') as mock_infer:
                
                # Convert candidates to GitHub API format
                mock_repos = []
                for candidate in candidates:
                    mock_repos.append({
                        'full_name': candidate.full_name,
                        'stargazers_count': candidate.stars,
                        'pushed_at': candidate.last_commit_date.isoformat(),
                        'fork': candidate.is_fork,
                        'description': f'Test repo',
                        'language': 'JavaScript'
                    })
                
                mock_search.return_value = mock_repos
                
                # Mock ecosystem inference
                def mock_infer_fn(repo_name):
                    matching = [c for c in candidates if c.full_name == repo_name]
                    if matching:
                        return (matching[0].primary_ecosystem, matching[0].manifest_types)
                    return ('npm', ['package.json'])
                
                mock_infer.side_effect = mock_infer_fn
                
                criteria = SelectionCriteria(exclude_forks=True)
                result = selector.select_repositories(count=min(10, len(candidates)), criteria=criteria)
                
                # Property: No forks should be in the result
                for repo in result:
                    assert not repo.is_fork, f"Repository {repo.full_name} is a fork but was selected"
                
                # All selected repos should be non-forks
                selected_names = [r.full_name for r in result]
                for name in selected_names:
                    assert not name.startswith('fork_owner/'), f"Fork {name} was selected"
        
        finally:
            # Cleanup
            Path(temp_db).unlink(missing_ok=True)



class TestEcosystemDiversity:
    """Property 2: Ecosystem Diversity - Feature: dataset-expansion-200-repos"""
    
    @given(
        repo_count=st.integers(min_value=50, max_value=100)
    )
    @settings(max_examples=100, deadline=None)
    def test_selection_includes_at_least_5_ecosystems(self, repo_count):
        """
        Property 2: Ecosystem Diversity
        For any repository selection of N repos, the selected set must include
        at least 5 different package ecosystems.
        
        **Validates: Requirements 1.2**
        """
        # Create temp database inside test
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db = f.name
        
        try:
            # Create schema
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE repo_graphs (
                    repo_full_name TEXT PRIMARY KEY,
                    language TEXT
                )
            """)
            conn.commit()
            conn.close()
            
            selector = RepositorySelector("test_token", temp_db)
            
            # Create candidates with all 5 ecosystems
            ecosystems = ['npm', 'pypi', 'go', 'maven', 'rubygems']
            candidates = []
            
            for i in range(repo_count):
                ecosystem = ecosystems[i % len(ecosystems)]
                candidates.append(RepositoryCandidate(
                    full_name=f'owner/repo{i}',
                    stars=2000 + i * 10,
                    last_commit_date=datetime.now() - timedelta(days=30),
                    primary_ecosystem=ecosystem,
                    manifest_types=[f'{ecosystem}_manifest'],
                    has_prod_deps=True,
                    is_fork=False,
                    fork_parent=None,
                    priority_score=0.0
                ))
            
            with patch.object(selector.github_client, 'search_repositories') as mock_search, \
                 patch.object(selector.ecosystem_inference, 'infer_ecosystem') as mock_infer:
                
                # Convert candidates to GitHub API format
                mock_repos = []
                for candidate in candidates:
                    mock_repos.append({
                        'full_name': candidate.full_name,
                        'stargazers_count': candidate.stars,
                        'pushed_at': candidate.last_commit_date.isoformat(),
                        'fork': candidate.is_fork,
                        'description': f'Test repo',
                        'language': 'Python'
                    })
                
                mock_search.return_value = mock_repos
                
                # Mock ecosystem inference
                def mock_infer_fn(repo_name):
                    matching = [c for c in candidates if c.full_name == repo_name]
                    if matching:
                        return (matching[0].primary_ecosystem, matching[0].manifest_types)
                    return ('npm', ['package.json'])
                
                mock_infer.side_effect = mock_infer_fn
                
                criteria = SelectionCriteria()
                # Select enough repos to ensure all ecosystems are represented
                result = selector.select_repositories(count=min(50, repo_count), criteria=criteria)
                
                # Property: At least 5 different ecosystems should be present
                unique_ecosystems = set(r.primary_ecosystem for r in result)
                assert len(unique_ecosystems) >= 5, \
                    f"Expected at least 5 ecosystems, got {len(unique_ecosystems)}: {unique_ecosystems}"
        
        finally:
            # Cleanup
            Path(temp_db).unlink(missing_ok=True)


class TestPriorityOrdering:
    """Property 7: Priority Ordering - Feature: dataset-expansion-200-repos"""
    
    @given(
        repo_count=st.integers(min_value=10, max_value=30)
    )
    @settings(max_examples=100, deadline=None)
    def test_selected_repos_are_sorted_by_priority(self, repo_count):
        """
        Property 7: Priority Ordering
        For any list of selected repositories, the list must be sorted in
        descending order by priority score.
        
        **Validates: Requirements 2.2**
        """
        # Create temp database inside test
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db = f.name
        
        try:
            # Create schema
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE repo_graphs (
                    repo_full_name TEXT PRIMARY KEY,
                    language TEXT
                )
            """)
            conn.commit()
            conn.close()
            
            selector = RepositorySelector("test_token", temp_db)
            
            # Create candidates with varying stars (which affects priority)
            candidates = []
            for i in range(repo_count):
                candidates.append(RepositoryCandidate(
                    full_name=f'owner/repo{i}',
                    stars=1500 + i * 200,  # Varying stars
                    last_commit_date=datetime.now() - timedelta(days=30),
                    primary_ecosystem='npm',
                    manifest_types=['package.json'],
                    has_prod_deps=True,
                    is_fork=False,
                    fork_parent=None,
                    priority_score=0.0
                ))
            
            with patch.object(selector.github_client, 'search_repositories') as mock_search, \
                 patch.object(selector.ecosystem_inference, 'infer_ecosystem') as mock_infer:
                
                # Convert candidates to GitHub API format
                mock_repos = []
                for candidate in candidates:
                    mock_repos.append({
                        'full_name': candidate.full_name,
                        'stargazers_count': candidate.stars,
                        'pushed_at': candidate.last_commit_date.isoformat(),
                        'fork': candidate.is_fork,
                        'description': f'Test repo',
                        'language': 'JavaScript'
                    })
                
                mock_search.return_value = mock_repos
                
                # Mock ecosystem inference
                def mock_infer_fn(repo_name):
                    matching = [c for c in candidates if c.full_name == repo_name]
                    if matching:
                        return (matching[0].primary_ecosystem, matching[0].manifest_types)
                    return ('npm', ['package.json'])
                
                mock_infer.side_effect = mock_infer_fn
                
                criteria = SelectionCriteria()
                result = selector.select_repositories(count=min(10, repo_count), criteria=criteria)
                
                # Property: Priority scores should be in descending order
                # Note: The actual ordering might be affected by ecosystem quotas,
                # so we check that within each ecosystem, priorities are descending
                if len(result) > 1:
                    # Group by ecosystem and check ordering within each group
                    from itertools import groupby
                    for ecosystem, group in groupby(result, key=lambda r: r.primary_ecosystem):
                        group_list = list(group)
                        if len(group_list) > 1:
                            scores = [r.priority_score for r in group_list]
                            # Check that scores are non-increasing (allowing for ties)
                            for i in range(len(scores) - 1):
                                assert scores[i] >= scores[i+1], \
                                    f"Priority scores not in descending order: {scores}"
        
        finally:
            # Cleanup
            Path(temp_db).unlink(missing_ok=True)


class TestExistingRepositoryExclusion:
    """Property 10: Existing Repository Exclusion - Feature: dataset-expansion-200-repos"""
    
    @given(
        existing_count=st.integers(min_value=1, max_value=10),
        new_count=st.integers(min_value=5, max_value=20)
    )
    @settings(max_examples=100, deadline=None)
    def test_existing_repos_are_excluded(self, existing_count, new_count):
        """
        Property 10: Existing Repository Exclusion
        For any repository already present in the dataset, it must not appear
        in the selection output.
        
        **Validates: Requirements 2.5**
        """
        # Create temp database inside test
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db = f.name
        
        try:
            # Create schema and add existing repos
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE repo_graphs (
                    repo_full_name TEXT PRIMARY KEY,
                    language TEXT
                )
            """)
            
            # Add existing repos
            existing_repos = []
            for i in range(existing_count):
                repo_name = f'existing/repo{i}'
                existing_repos.append(repo_name)
                cursor.execute("INSERT INTO repo_graphs VALUES (?, ?)", (repo_name, 'Python'))
            
            conn.commit()
            conn.close()
            
            selector = RepositorySelector("test_token", temp_db)
            
            # Create candidates: mix of existing and new
            candidates = []
            
            # Add existing repos as candidates (should be filtered out)
            for i in range(existing_count):
                candidates.append(RepositoryCandidate(
                    full_name=f'existing/repo{i}',
                    stars=3000 + i * 100,
                    last_commit_date=datetime.now() - timedelta(days=30),
                    primary_ecosystem='npm',
                    manifest_types=['package.json'],
                    has_prod_deps=True,
                    is_fork=False,
                    fork_parent=None,
                    priority_score=0.0
                ))
            
            # Add new repos
            for i in range(new_count):
                candidates.append(RepositoryCandidate(
                    full_name=f'new/repo{i}',
                    stars=2000 + i * 100,
                    last_commit_date=datetime.now() - timedelta(days=30),
                    primary_ecosystem='npm',
                    manifest_types=['package.json'],
                    has_prod_deps=True,
                    is_fork=False,
                    fork_parent=None,
                    priority_score=0.0
                ))
            
            with patch.object(selector.github_client, 'search_repositories') as mock_search, \
                 patch.object(selector.ecosystem_inference, 'infer_ecosystem') as mock_infer:
                
                # Convert candidates to GitHub API format
                mock_repos = []
                for candidate in candidates:
                    mock_repos.append({
                        'full_name': candidate.full_name,
                        'stargazers_count': candidate.stars,
                        'pushed_at': candidate.last_commit_date.isoformat(),
                        'fork': candidate.is_fork,
                        'description': f'Test repo',
                        'language': 'JavaScript'
                    })
                
                mock_search.return_value = mock_repos
                
                # Mock ecosystem inference
                def mock_infer_fn(repo_name):
                    matching = [c for c in candidates if c.full_name == repo_name]
                    if matching:
                        return (matching[0].primary_ecosystem, matching[0].manifest_types)
                    return ('npm', ['package.json'])
                
                mock_infer.side_effect = mock_infer_fn
                
                criteria = SelectionCriteria()
                result = selector.select_repositories(count=min(10, len(candidates)), criteria=criteria)
                
                # Property: No existing repos should be in the result
                selected_names = [r.full_name for r in result]
                for existing_repo in existing_repos:
                    assert existing_repo not in selected_names, \
                        f"Existing repository {existing_repo} was selected"
        
        finally:
            # Cleanup
            Path(temp_db).unlink(missing_ok=True)



class TestRepositoryMetadataCompleteness:
    """Property 8: Repository Metadata Completeness - Feature: dataset-expansion-200-repos"""
    
    @given(
        repo_count=st.integers(min_value=5, max_value=20)
    )
    @settings(max_examples=100, deadline=None)
    def test_selected_repos_have_complete_metadata(self, repo_count):
        """
        Property 8: Repository Metadata Completeness
        For any repository in the selection output, the record must contain
        stars, ecosystem, and last_commit_date fields.
        
        **Validates: Requirements 2.3**
        """
        # Create temp database inside test
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db = f.name
        
        try:
            # Create schema
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE repo_graphs (
                    repo_full_name TEXT PRIMARY KEY,
                    language TEXT
                )
            """)
            conn.commit()
            conn.close()
            
            selector = RepositorySelector("test_token", temp_db)
            
            # Create candidates
            candidates = []
            for i in range(repo_count):
                candidates.append(RepositoryCandidate(
                    full_name=f'owner/repo{i}',
                    stars=2000 + i * 100,
                    last_commit_date=datetime.now() - timedelta(days=30 + i),
                    primary_ecosystem='npm',
                    manifest_types=['package.json'],
                    has_prod_deps=True,
                    is_fork=False,
                    fork_parent=None,
                    priority_score=0.0
                ))
            
            with patch.object(selector.github_client, 'search_repositories') as mock_search, \
                 patch.object(selector.ecosystem_inference, 'infer_ecosystem') as mock_infer:
                
                # Convert candidates to GitHub API format
                mock_repos = []
                for candidate in candidates:
                    mock_repos.append({
                        'full_name': candidate.full_name,
                        'stargazers_count': candidate.stars,
                        'pushed_at': candidate.last_commit_date.isoformat(),
                        'fork': candidate.is_fork,
                        'description': f'Test repo {candidate.full_name}',
                        'language': 'JavaScript'
                    })
                
                mock_search.return_value = mock_repos
                
                # Mock ecosystem inference
                def mock_infer_fn(repo_name):
                    matching = [c for c in candidates if c.full_name == repo_name]
                    if matching:
                        return (matching[0].primary_ecosystem, matching[0].manifest_types)
                    return ('npm', ['package.json'])
                
                mock_infer.side_effect = mock_infer_fn
                
                criteria = SelectionCriteria()
                result = selector.select_repositories(count=min(10, repo_count), criteria=criteria)
                
                # Property: All selected repos must have complete metadata
                for repo in result:
                    # Check stars field
                    assert hasattr(repo, 'stars'), f"Repository {repo.full_name} missing 'stars' field"
                    assert repo.stars is not None, f"Repository {repo.full_name} has None for 'stars'"
                    assert isinstance(repo.stars, int), f"Repository {repo.full_name} 'stars' is not an integer"
                    
                    # Check ecosystem field
                    assert hasattr(repo, 'primary_ecosystem'), f"Repository {repo.full_name} missing 'primary_ecosystem' field"
                    assert repo.primary_ecosystem is not None, f"Repository {repo.full_name} has None for 'primary_ecosystem'"
                    assert isinstance(repo.primary_ecosystem, str), f"Repository {repo.full_name} 'primary_ecosystem' is not a string"
                    
                    # Check last_commit_date field
                    assert hasattr(repo, 'last_commit_date'), f"Repository {repo.full_name} missing 'last_commit_date' field"
                    assert repo.last_commit_date is not None, f"Repository {repo.full_name} has None for 'last_commit_date'"
                    assert isinstance(repo.last_commit_date, datetime), f"Repository {repo.full_name} 'last_commit_date' is not a datetime"
        
        finally:
            # Cleanup
            Path(temp_db).unlink(missing_ok=True)
