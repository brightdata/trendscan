"""
TrendScan Agents Package

Data source agents for collecting company intelligence from various platforms.
Each agent works independently but is orchestrated by the main TrendScan system.
"""

from .crunchbase_agent import CrunchbaseScraper
from .linkedin_agent import LinkedInScraper
from .reddit_agent import RedditScraper
from .twitter_agent import TwitterScraper

from .base_agent import BaseDataCollector, CollectionResult, CollectionStatus

__version__ = "1.0.0"
__author__ = "Satyam Tripathi"

# Agent registry for the main TrendScan system
AVAILABLE_AGENTS = {
    "crunchbase": {
        "class": CrunchbaseScraper,
        "description": "Collects company data from Crunchbase including funding, personnel, and metrics",
        "data_source": "crunchbase",
        "output_formats": ["json"],
    },
    "linkedin": {
        "class": LinkedInScraper,
        "description": "Collects LinkedIn company posts and job listings",
        "data_source": "linkedin",
        "output_formats": ["json"],
    },
    "reddit": {
        "class": RedditScraper,
        "description": "Collects Reddit discussions and opinions about companies",
        "data_source": "reddit",
        "output_formats": ["txt", "json"],
    },
    "twitter": {
        "class": TwitterScraper,
        "description": "Collects Twitter/X posts and social media presence",
        "data_source": "twitter",
        "output_formats": ["json"],
    },
}

__all__ = [
    "CrunchbaseScraper",
    "LinkedInScraper",
    "RedditScraper",
    "TwitterScraper",
    "BaseDataCollector",
    "CollectionResult",
    "CollectionStatus",
    "AVAILABLE_AGENTS",
]