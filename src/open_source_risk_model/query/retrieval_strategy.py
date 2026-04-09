"""
Retrieval strategy selector for query execution.

This module selects the optimal data retrieval approach based on coverage
and user preferences, balancing query latency with data freshness.
"""

import logging
from typing import Any, Dict

from ..ingestion.models import EvidenceScope
from .models import CoverageReport, RetrievalPlan

logger = logging.getLogger(__name__)


class RetrievalStrategy:
    """
    Selects optimal data retrieval strategy based on coverage.
    
    Determines whether to use database retrieval, live ingestion, or both,
    and configures ingestion mode (provisional vs full) based on user preferences.
    """
    
    def __init__(self):
        """Initialize retrieval strategy selector."""
        pass
    
    def select_strategy(
        self,
        coverage_report: CoverageReport,
        user_preferences: Dict[str, Any]
    ) -> RetrievalPlan:
        """
        Select retrieval strategy based on coverage.
        
        Args:
            coverage_report: Report of repository coverage in database
            user_preferences: User preferences for retrieval (e.g., score_mode)
            
        Returns:
            RetrievalPlan with strategy details
            
        Example:
            >>> strategy = RetrievalStrategy()
            >>> coverage = CoverageReport(
            ...     coverage_mode="hybrid",
            ...     in_database=[...],
            ...     missing=["missing/repo"],
            ...     invalid=[]
            ... )
            >>> preferences = {"score_mode": "provisional"}
            >>> plan = strategy.select_strategy(coverage, preferences)
            >>> plan.use_database
            True
            >>> plan.use_live_ingestion
            True
            >>> plan.live_ingestion_mode
            'provisional'
        """
        # Extract coverage mode
        coverage_mode = coverage_report.coverage_mode
        
        # Determine which retrievers to use
        use_database = coverage_mode in ["database_only", "hybrid"]
        use_live_ingestion = coverage_mode in ["live_ingestion_required", "hybrid"]
        
        # Extract repositories for each retriever
        repos_from_database = [
            status.repo_full_name for status in coverage_report.in_database
        ]
        repos_for_ingestion = coverage_report.missing.copy()
        
        # Determine live ingestion mode from user preferences
        # Default to "provisional" (fast) if not specified
        score_mode = user_preferences.get("score_mode", "provisional")
        if score_mode == "full":
            live_ingestion_mode = "full"
        else:
            live_ingestion_mode = "provisional"
        
        # Classify cost for internal logging
        cost_classification = self._classify_cost(
            coverage_mode, live_ingestion_mode, len(repos_for_ingestion)
        )
        
        # Create evidence scope
        evidence_scope = self._create_evidence_scope(
            use_database, use_live_ingestion, live_ingestion_mode
        )
        
        return RetrievalPlan(
            use_database=use_database,
            use_live_ingestion=use_live_ingestion,
            live_ingestion_mode=live_ingestion_mode,
            repos_from_database=repos_from_database,
            repos_for_ingestion=repos_for_ingestion,
            cost_classification=cost_classification,
            evidence_scope=evidence_scope
        )
    
    def _classify_cost(
        self,
        coverage_mode: str,
        live_ingestion_mode: str,
        ingestion_count: int
    ) -> str:
        """
        Classify expected retrieval cost.
        
        Args:
            coverage_mode: Coverage mode (database_only, live_ingestion_required, hybrid)
            live_ingestion_mode: Live ingestion mode (provisional or full)
            ingestion_count: Number of repositories requiring live ingestion
            
        Returns:
            Cost classification: "low", "medium", or "high"
        """
        # Database-only is always low cost
        if coverage_mode == "database_only":
            return "low"
        
        # Live ingestion required or hybrid
        if coverage_mode == "live_ingestion_required":
            # Full mode is high cost
            if live_ingestion_mode == "full":
                return "high"
            # Provisional mode is medium cost
            else:
                return "medium"
        
        # Hybrid mode
        if coverage_mode == "hybrid":
            # Full mode is high cost
            if live_ingestion_mode == "full":
                return "high"
            # Provisional mode is medium cost
            else:
                return "medium"
        
        # Default to medium
        return "medium"
    
    def _create_evidence_scope(
        self,
        use_database: bool,
        use_live_ingestion: bool,
        live_ingestion_mode: str
    ) -> EvidenceScope:
        """
        Create evidence scope for tracking data sources.
        
        Args:
            use_database: Whether database retrieval is used
            use_live_ingestion: Whether live ingestion is used
            live_ingestion_mode: Live ingestion mode (provisional or full)
            
        Returns:
            EvidenceScope object
        """
        # Determine source level
        if use_database and use_live_ingestion:
            source_level = "hybrid"
        elif use_database:
            source_level = "scored_features"
        else:
            # Live ingestion only
            if live_ingestion_mode == "full":
                source_level = "scored_features"
            else:
                source_level = "raw_ingestion"
        
        return EvidenceScope(
            source_level=source_level,
            includes_live_fetch=use_live_ingestion,
            includes_cached_results=False,  # Will be updated by cache manager
            includes_database_results=use_database
        )
