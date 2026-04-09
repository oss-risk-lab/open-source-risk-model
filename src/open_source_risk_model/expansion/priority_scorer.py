"""Priority scoring for repository selection."""

import math
import logging
from datetime import datetime, timezone
from typing import Dict
from .models import RepositoryCandidate

logger = logging.getLogger(__name__)


class PriorityScorer:
    """Calculate priority scores for repository candidates."""
    
    # Weights for score components
    STARS_WEIGHT = 0.4
    RECENCY_WEIGHT = 0.3
    PROD_DEPS_WEIGHT = 0.2
    DIVERSITY_WEIGHT = 0.1
    
    def __init__(self, current_distribution: Dict[str, float], ecosystem_targets: Dict[str, tuple]):
        """
        Initialize priority scorer.
        
        Args:
            current_distribution: Current ecosystem distribution (ecosystem -> percentage)
            ecosystem_targets: Target ecosystem ranges (ecosystem -> (min, max))
        """
        self.current_distribution = current_distribution
        self.ecosystem_targets = ecosystem_targets
    
    def calculate_priority_score(self, candidate: RepositoryCandidate) -> float:
        """
        Calculate priority score (0.0-1.0).
        
        Score = 0.4 * stars_score + 
                0.3 * recency_score + 
                0.2 * prod_deps_score +
                0.1 * ecosystem_diversity_bonus
        
        Args:
            candidate: Repository candidate
        
        Returns:
            Priority score between 0.0 and 1.0
        """
        stars_score = self._calculate_stars_score(candidate.stars)
        recency_score = self._calculate_recency_score(candidate.last_commit_date)
        prod_deps_score = self._calculate_prod_deps_score(candidate.has_prod_deps)
        diversity_bonus = self._calculate_diversity_bonus(candidate.primary_ecosystem)
        
        score = (
            self.STARS_WEIGHT * stars_score +
            self.RECENCY_WEIGHT * recency_score +
            self.PROD_DEPS_WEIGHT * prod_deps_score +
            self.DIVERSITY_WEIGHT * diversity_bonus
        )
        
        return score
    
    def _calculate_stars_score(self, stars: int) -> float:
        """
        Calculate normalized star score (log scale).
        
        100,000 stars = 1.0
        10,000 stars = 0.8
        1,000 stars = 0.6
        """
        if stars <= 0:
            return 0.0
        
        # Log scale: log10(stars) / 5.0
        # 100k stars = log10(100000) / 5.0 = 5.0 / 5.0 = 1.0
        score = math.log10(stars) / 5.0
        return min(1.0, score)
    
    def _calculate_recency_score(self, last_commit_date: datetime) -> float:
        """
        Calculate recency score based on days since last commit.
        
        0 days = 1.0
        365 days = 0.0
        """
        # Make datetime timezone-aware if it isn't already
        now = datetime.now(timezone.utc)
        if last_commit_date.tzinfo is None:
            last_commit_date = last_commit_date.replace(tzinfo=timezone.utc)
        
        days_since_commit = (now - last_commit_date).days
        
        # Linear decay over 365 days
        score = max(0.0, 1.0 - (days_since_commit / 365.0))
        return score
    
    def _calculate_prod_deps_score(self, has_prod_deps: bool) -> float:
        """
        Calculate production dependencies score.
        
        Has prod deps = 1.0
        No prod deps = 0.5
        """
        return 1.0 if has_prod_deps else 0.5
    
    def _calculate_diversity_bonus(self, ecosystem: str) -> float:
        """
        Calculate ecosystem diversity bonus.
        
        Underrepresented ecosystems get a boost.
        """
        if ecosystem not in self.ecosystem_targets:
            return 0.0
        
        target_min, _ = self.ecosystem_targets[ecosystem]
        current_pct = self.current_distribution.get(ecosystem, 0.0)
        
        # Bonus if below target minimum
        bonus = max(0.0, target_min - current_pct)
        
        return bonus
