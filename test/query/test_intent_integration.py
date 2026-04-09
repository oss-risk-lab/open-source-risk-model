"""
Tests for Query Coverage System Integration with IntentExecutor

Tests cover:
- repo_lookup intent
- repo_comparison intent
- missing_repo_handling intent
- Entity normalization integration
- Coverage checking integration
- Retrieval strategy integration
- Result summarization integration
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from open_source_risk_model.query.intent_executor import IntentExecutor, QueryResult


@pytest.fixture
def executor():
    """Create executor with test database."""
    return IntentExecutor(db_path="data/graphs.db")


class TestRepoLookupIntent:
    """Test repo_lookup intent."""
    
    @patch('open_source_risk_model.query.intent_executor.IntentExecutor._get_entity_normalizer')
    @patch('open_source_risk_model.query.intent_executor.IntentExecutor._get_coverage_checker')
    @patch('open_source_risk_model.query.intent_executor.IntentExecutor._get_retrieval_strategy')
    @patch('open_source_risk_model.query.intent_executor.IntentExecutor._get_db_retriever')
    @patch('open_source_risk_model.query.intent_executor.IntentExecutor._get_result_summarizer')
    def test_repo_lookup_database_only(
        self,
        mock_summarizer,
        mock_db_retriever,
        mock_strategy,
        mock_coverage,
        mock_normalizer,
        executor
    ):
        """Test repo_lookup when repo is in database."""
        from open_source_risk_model.query.models import (
            NormalizationResult,
            CoverageReport,
            RepoStatus,
            RetrievalPlan,
            RepoSummary,
            QueryResponse,
            EvidenceScope
        )
        from open_source_risk_model.ingestion.models import DataProvenance
        from datetime import datetime, timezone
        
        # Setup mocks
        mock_normalizer.return_value.normalize_repository.return_value = NormalizationResult(
            canonical_identifier="numpy/numpy",
            confidence=0.95,
            alternatives=[],
            warning=None
        )
        
        mock_coverage.return_value.check_coverage.return_value = CoverageReport(
            coverage_mode="database_only",
            in_database=[RepoStatus(
                repo_full_name="numpy/numpy",
                last_updated=datetime.now(timezone.utc),
                score_completeness="full"
            )],
            missing=[],
            invalid=[]
        )
        
        evidence_scope = EvidenceScope(
            source_level="scored_features",
            includes_live_fetch=False,
            includes_cached_results=False,
            includes_database_results=True
        )
        
        mock_strategy.return_value.select_strategy.return_value = RetrievalPlan(
            use_database=True,
            use_live_ingestion=False,
            live_ingestion_mode="provisional",
            repos_from_database=["numpy/numpy"],
            repos_for_ingestion=[],
            cost_classification="low",
            evidence_scope=evidence_scope
        )
        
        mock_db_retriever.return_value.retrieve_summary.return_value = [
            RepoSummary(
                repo_full_name="numpy/numpy",
                maintenance_risk_score=0.25,
                risk_band="low",
                features={"days_since_last_push": 5.0},
                provenance=DataProvenance(
                    source="database",
                    last_updated=datetime.now(timezone.utc),
                    score_completeness="full"
                )
            )
        ]
        
        mock_summarizer.return_value.summarize.return_value = QueryResponse(
            natural_language_response="numpy/numpy has low maintenance risk (score: 0.25)",
            structured_results=mock_db_retriever.return_value.retrieve_summary.return_value,
            warnings=[],
            metadata={},
            evidence_scope=evidence_scope
        )
        
        # Execute
        result = executor.execute(
            intent="repo_lookup",
            parameters={"repo_identifier": "numpy"},
            max_results=1
        )
        
        # Verify
        assert result.intent == "repo_lookup"
        assert result.result_count == 1
        assert result.results[0]["repo_full_name"] == "numpy/numpy"
        assert result.results[0]["maintenance_risk_score"] == 0.25
        assert result.results[0]["risk_band"] == "low"
        assert result.metadata["canonical_repo"] == "numpy/numpy"
        assert result.metadata["coverage_mode"] == "database_only"
        assert result.metadata["retrieval_plan"]["use_database"] is True
        assert result.metadata["retrieval_plan"]["use_live_ingestion"] is False
    
    def test_repo_lookup_missing_identifier(self, executor):
        """Test that repo_lookup requires repo_identifier."""
        with pytest.raises(ValueError, match="repo_identifier is required"):
            executor.execute(
                intent="repo_lookup",
                parameters={},
                max_results=1
            )
    
    @patch('open_source_risk_model.query.intent_executor.IntentExecutor._get_entity_normalizer')
    def test_repo_lookup_unresolved_entity(self, mock_normalizer, executor):
        """Test repo_lookup with unresolved entity."""
        from open_source_risk_model.query.models import NormalizationResult
        
        # Setup mock for unresolved entity
        mock_normalizer.return_value.normalize_repository.return_value = NormalizationResult(
            canonical_identifier=None,
            confidence=0.0,
            alternatives=["option1/repo", "option2/repo"],
            warning="Ambiguous package name"
        )
        
        # Execute
        result = executor.execute(
            intent="repo_lookup",
            parameters={"repo_identifier": "ambiguous-package"},
            max_results=1
        )
        
        # Verify
        assert result.result_count == 0
        assert result.metadata["status"] == "unresolved"
        assert "warning" in result.metadata
        assert len(result.metadata["alternatives"]) == 2


class TestRepoComparisonIntent:
    """Test repo_comparison intent."""
    
    def test_repo_comparison_missing_identifiers(self, executor):
        """Test that repo_comparison requires repo_identifiers list."""
        with pytest.raises(ValueError, match="repo_identifiers is required and must be a list"):
            executor.execute(
                intent="repo_comparison",
                parameters={},
                max_results=10
            )
    
    def test_repo_comparison_invalid_identifiers_type(self, executor):
        """Test that repo_identifiers must be a list."""
        with pytest.raises(ValueError, match="repo_identifiers is required and must be a list"):
            executor.execute(
                intent="repo_comparison",
                parameters={"repo_identifiers": "not-a-list"},
                max_results=10
            )
    
    @patch('open_source_risk_model.query.intent_executor.IntentExecutor._get_entity_normalizer')
    def test_repo_comparison_all_unresolved(self, mock_normalizer, executor):
        """Test repo_comparison when all entities are unresolved."""
        from open_source_risk_model.query.models import NormalizationResult
        
        # Setup mock for all unresolved
        mock_normalizer.return_value.normalize_repository.return_value = NormalizationResult(
            canonical_identifier=None,
            confidence=0.0,
            alternatives=[],
            warning="Unknown package"
        )
        
        # Execute
        result = executor.execute(
            intent="repo_comparison",
            parameters={"repo_identifiers": ["unknown1", "unknown2"]},
            max_results=10
        )
        
        # Verify
        assert result.result_count == 0
        assert result.metadata["status"] == "all_unresolved"
        assert "normalization_results" in result.metadata


class TestMissingRepoHandlingIntent:
    """Test missing_repo_handling intent."""
    
    def test_missing_repo_handling_missing_identifier(self, executor):
        """Test that missing_repo_handling requires repo_identifier."""
        with pytest.raises(ValueError, match="repo_identifier is required"):
            executor.execute(
                intent="missing_repo_handling",
                parameters={},
                max_results=1
            )
    
    @patch('open_source_risk_model.query.intent_executor.IntentExecutor._get_entity_normalizer')
    def test_missing_repo_handling_unresolved_entity(self, mock_normalizer, executor):
        """Test missing_repo_handling with unresolved entity."""
        from open_source_risk_model.query.models import NormalizationResult
        
        # Setup mock for unresolved entity
        mock_normalizer.return_value.normalize_repository.return_value = NormalizationResult(
            canonical_identifier=None,
            confidence=0.0,
            alternatives=[],
            warning="Unknown package"
        )
        
        # Execute
        result = executor.execute(
            intent="missing_repo_handling",
            parameters={"repo_identifier": "unknown-package"},
            max_results=1
        )
        
        # Verify
        assert result.result_count == 0
        assert result.metadata["status"] == "unresolved"
        assert "warning" in result.metadata


class TestIntentDispatcher:
    """Test that new intents are properly dispatched."""
    
    def test_repo_lookup_intent_exists(self, executor):
        """Test that repo_lookup intent is registered."""
        # This will raise ValueError if intent doesn't exist
        try:
            executor.execute(
                intent="repo_lookup",
                parameters={"repo_identifier": "test"},
                max_results=1
            )
        except Exception as e:
            # We expect errors from missing mocks, but not "Unknown intent"
            assert "Unknown intent" not in str(e)
    
    def test_repo_comparison_intent_exists(self, executor):
        """Test that repo_comparison intent is registered."""
        try:
            executor.execute(
                intent="repo_comparison",
                parameters={"repo_identifiers": ["test"]},
                max_results=10
            )
        except Exception as e:
            assert "Unknown intent" not in str(e)
    
    def test_missing_repo_handling_intent_exists(self, executor):
        """Test that missing_repo_handling intent is registered."""
        try:
            executor.execute(
                intent="missing_repo_handling",
                parameters={"repo_identifier": "test"},
                max_results=1
            )
        except Exception as e:
            assert "Unknown intent" not in str(e)


class TestLazyLoading:
    """Test lazy loading of query coverage components."""
    
    def test_components_not_loaded_initially(self, executor):
        """Test that components are not loaded on initialization."""
        assert executor._entity_normalizer is None
        assert executor._coverage_checker is None
        assert executor._retrieval_strategy is None
        assert executor._db_retriever is None
        assert executor._live_repo_ingestor is None
        assert executor._result_summarizer is None
    
    def test_entity_normalizer_lazy_loads(self, executor):
        """Test that EntityNormalizer is lazy loaded."""
        assert executor._entity_normalizer is None
        normalizer = executor._get_entity_normalizer()
        assert normalizer is not None
        assert executor._entity_normalizer is normalizer
        # Second call returns same instance
        assert executor._get_entity_normalizer() is normalizer
    
    def test_coverage_checker_lazy_loads(self, executor):
        """Test that CoverageChecker is lazy loaded."""
        assert executor._coverage_checker is None
        checker = executor._get_coverage_checker()
        assert checker is not None
        assert executor._coverage_checker is checker
        assert executor._get_coverage_checker() is checker
    
    def test_retrieval_strategy_lazy_loads(self, executor):
        """Test that RetrievalStrategy is lazy loaded."""
        assert executor._retrieval_strategy is None
        strategy = executor._get_retrieval_strategy()
        assert strategy is not None
        assert executor._retrieval_strategy is strategy
        assert executor._get_retrieval_strategy() is strategy
    
    def test_db_retriever_lazy_loads(self, executor):
        """Test that DBRetriever is lazy loaded."""
        assert executor._db_retriever is None
        retriever = executor._get_db_retriever()
        assert retriever is not None
        assert executor._db_retriever is retriever
        assert executor._get_db_retriever() is retriever
    
    def test_live_repo_ingestor_lazy_loads(self, executor):
        """Test that LiveRepoIngestor is lazy loaded."""
        assert executor._live_repo_ingestor is None
        ingestor = executor._get_live_repo_ingestor()
        assert ingestor is not None
        assert executor._live_repo_ingestor is ingestor
        assert executor._get_live_repo_ingestor() is ingestor
    
    def test_result_summarizer_lazy_loads(self, executor):
        """Test that ResultSummarizer is lazy loaded."""
        assert executor._result_summarizer is None
        summarizer = executor._get_result_summarizer()
        assert summarizer is not None
        assert executor._result_summarizer is summarizer
        assert executor._get_result_summarizer() is summarizer


class TestBackwardCompatibility:
    """Test that existing intents still work."""
    
    def test_existing_intents_unchanged(self, executor):
        """Test that all existing intents still work."""
        existing_intents = [
            ("list_dependencies", {"repo_full_name": "django/django"}),
            ("find_dependents", {"package_name": "flask", "registry_type": "pypi"}),
            ("dataset_stats", {}),
            ("search_repos", {"pattern": "django"}),
        ]
        
        for intent, params in existing_intents:
            result = executor.execute(intent, params, max_results=10)
            assert result.intent == intent
            assert isinstance(result.results, list)
            assert isinstance(result.metadata, dict)
