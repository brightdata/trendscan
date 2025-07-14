import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from dotenv import load_dotenv


class DataSource(Enum):
    CRUNCHBASE = "crunchbase"
    LINKEDIN = "linkedin"
    REDDIT = "reddit"
    TWITTER = "twitter"


@dataclass
class LLMConfig:
    model: str = "gemini/gemini-2.0-flash-lite"
    temperature: float = 0.0
    seed: int = 42
    top_p: float = 1.0
    max_tokens: Optional[int] = None

    def validate(self) -> None:
        if not self.model:
            raise ValueError("LLM model must be specified")

        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError("Temperature must be between 0.0 and 2.0")

        if not (0.0 <= self.top_p <= 1.0):
            raise ValueError("Top-p must be between 0.0 and 1.0")

        if self.max_tokens is not None and self.max_tokens < 1:
            raise ValueError("Max tokens must be positive")


@dataclass
class APIKeysConfig:
    gemini: str = ""
    bright_data: str = ""

    def validate(self) -> None:
        missing = []
        if not self.gemini:
            missing.append("GEMINI_API_KEY")
        if not self.bright_data:
            missing.append("BRIGHT_DATA_API_TOKEN")

        if missing:
            raise ValueError(f"Missing required API keys: {', '.join(missing)}")


@dataclass
class BrightDataConfig:
    web_unlocker_zone: str = ""
    browser_zone: str = ""


@dataclass
class LoggingConfig:
    level: str = "INFO"
    enable_file_logging: bool = True
    log_directory: str = "logs"
    max_file_size_mb: int = 10
    backup_count: int = 5
    format: str = (
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    )


@dataclass
class OutputConfig:
    base_directory: str = "output"
    include_timestamp: bool = True
    create_company_folders: bool = True


@dataclass
class ExecutionConfig:
    parallel_execution: bool = True
    max_workers: int = 4
    timeout_minutes: int = 30


@dataclass
class SourcesConfig:
    enable_crunchbase: bool = True
    enable_linkedin: bool = True
    enable_reddit: bool = True
    enable_twitter: bool = True


@dataclass
class CrunchbaseConfig:
    max_retries: int = 3
    base_backoff_delay: float = 2.0
    max_backoff_delay: float = 60.0
    temperature: float = 0.0
    timeout_seconds: int = 60
    max_search_attempts: int = 3


@dataclass
class LinkedInConfig:
    collect_jobs: bool = True
    collect_posts: bool = True
    posts_date_range_days: int = 7
    max_wait_time: int = 1000
    status_check_interval: int = 10
    jobs_dataset_id: str = "gd_lpfll7v5hcqtkxl6l"
    posts_dataset_id: str = "gd_lyy3tktm25m4avu764"
    api_timeout: int = 60
    max_retries: int = 3


@dataclass
class RedditConfig:
    max_iterations: int = 5
    verbose: bool = True
    search_queries: list = field(
        default_factory=lambda: [
            "{company_name} site:reddit.com",
            "{company_name} review opinion site:reddit.com",
            "{company_name} problem issue site:reddit.com",
            "{company_name} vs alternative site:reddit.com",
        ]
    )
    timeout_seconds: int = 120
    max_retries: int = 3


@dataclass
class TwitterConfig:
    days_back: int = 7
    max_wait_minutes: int = 10
    api_timeout: int = 30
    dataset_id: str = "gd_lwxkxvnf1cynvib9co"
    max_retries: int = 3
    search_timeout: int = 60
    username_search_queries: list = field(
        default_factory=lambda: [
            '"{company_name} twitter"',
            '"{company_name} X.com"',
            '"{company_name} site:x.com"',
            '{company_name} "@"',
        ]
    )


@dataclass
class TrendScanConfig:
    api_keys: APIKeysConfig = field(default_factory=APIKeysConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    bright_data: BrightDataConfig = field(default_factory=BrightDataConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    crunchbase: CrunchbaseConfig = field(default_factory=CrunchbaseConfig)
    linkedin: LinkedInConfig = field(default_factory=LinkedInConfig)
    reddit: RedditConfig = field(default_factory=RedditConfig)
    twitter: TwitterConfig = field(default_factory=TwitterConfig)

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "TrendScanConfig":
        """Load configuration from environment variables and optional config file"""
        load_dotenv()

        config = cls()

        if config_path and Path(config_path).exists():
            config = cls._load_from_file(config, config_path)

        config = cls._load_from_environment(config)
        config.validate()

        return config

    @classmethod
    def _load_from_file(
        cls, config: "TrendScanConfig", config_path: str
    ) -> "TrendScanConfig":
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                file_config = json.load(f)

            cls._update_config_from_dict(config, file_config)

        except Exception as e:
            raise ValueError(f"Failed to load config file {config_path}: {e}")

        return config

    @classmethod
    def _load_from_environment(cls, config: "TrendScanConfig") -> "TrendScanConfig":
        """Load configuration from environment variables with type conversion"""
        # API Keys
        config.api_keys.gemini = os.getenv("GEMINI_API_KEY", config.api_keys.gemini)
        config.api_keys.bright_data = os.getenv(
            "BRIGHT_DATA_API_TOKEN", config.api_keys.bright_data
        )

        # LLM Configuration
        config.llm.model = os.getenv("LLM_MODEL", config.llm.model)
        config.llm.temperature = cls._get_float_env(
            "LLM_TEMPERATURE", config.llm.temperature
        )
        config.llm.seed = cls._get_int_env("LLM_SEED", config.llm.seed)
        config.llm.top_p = cls._get_float_env("LLM_TOP_P", config.llm.top_p)
        max_tokens = os.getenv("LLM_MAX_TOKENS")
        if max_tokens:
            config.llm.max_tokens = int(max_tokens)

        # Bright Data
        config.bright_data.web_unlocker_zone = os.getenv(
            "WEB_UNLOCKER_ZONE", config.bright_data.web_unlocker_zone
        )
        config.bright_data.browser_zone = os.getenv(
            "BROWSER_ZONE", config.bright_data.browser_zone
        )

        # Logging
        config.logging.level = os.getenv("LOG_LEVEL", config.logging.level)
        config.logging.enable_file_logging = cls._get_bool_env(
            "ENABLE_FILE_LOGGING", config.logging.enable_file_logging
        )
        config.logging.log_directory = os.getenv(
            "LOG_DIRECTORY", config.logging.log_directory
        )

        # Output
        config.output.base_directory = os.getenv(
            "OUTPUT_DIRECTORY", config.output.base_directory
        )
        config.output.include_timestamp = cls._get_bool_env(
            "INCLUDE_TIMESTAMP", config.output.include_timestamp
        )
        config.output.create_company_folders = cls._get_bool_env(
            "CREATE_COMPANY_FOLDERS", config.output.create_company_folders
        )

        # Execution
        config.execution.parallel_execution = cls._get_bool_env(
            "PARALLEL_EXECUTION", config.execution.parallel_execution
        )
        config.execution.max_workers = cls._get_int_env(
            "MAX_WORKERS", config.execution.max_workers
        )
        config.execution.timeout_minutes = cls._get_int_env(
            "TIMEOUT_MINUTES", config.execution.timeout_minutes
        )

        # Sources
        config.sources.enable_crunchbase = cls._get_bool_env(
            "ENABLE_CRUNCHBASE", config.sources.enable_crunchbase
        )
        config.sources.enable_linkedin = cls._get_bool_env(
            "ENABLE_LINKEDIN", config.sources.enable_linkedin
        )
        config.sources.enable_reddit = cls._get_bool_env(
            "ENABLE_REDDIT", config.sources.enable_reddit
        )
        config.sources.enable_twitter = cls._get_bool_env(
            "ENABLE_TWITTER", config.sources.enable_twitter
        )

        # Crunchbase
        config.crunchbase.max_retries = cls._get_int_env(
            "CRUNCHBASE_MAX_RETRIES", config.crunchbase.max_retries
        )
        config.crunchbase.base_backoff_delay = cls._get_float_env(
            "CRUNCHBASE_BASE_BACKOFF_DELAY", config.crunchbase.base_backoff_delay
        )
        config.crunchbase.max_backoff_delay = cls._get_float_env(
            "CRUNCHBASE_MAX_BACKOFF_DELAY", config.crunchbase.max_backoff_delay
        )
        config.crunchbase.timeout_seconds = cls._get_int_env(
            "CRUNCHBASE_TIMEOUT", config.crunchbase.timeout_seconds
        )

        # LinkedIn
        config.linkedin.collect_jobs = cls._get_bool_env(
            "LINKEDIN_COLLECT_JOBS", config.linkedin.collect_jobs
        )
        config.linkedin.collect_posts = cls._get_bool_env(
            "LINKEDIN_COLLECT_POSTS", config.linkedin.collect_posts
        )
        config.linkedin.posts_date_range_days = cls._get_int_env(
            "LINKEDIN_POSTS_DATE_RANGE_DAYS", config.linkedin.posts_date_range_days
        )
        config.linkedin.api_timeout = cls._get_int_env(
            "LINKEDIN_API_TIMEOUT", config.linkedin.api_timeout
        )
        config.linkedin.max_retries = cls._get_int_env(
            "LINKEDIN_MAX_RETRIES", config.linkedin.max_retries
        )

        # Reddit
        config.reddit.max_iterations = cls._get_int_env(
            "REDDIT_MAX_ITERATIONS", config.reddit.max_iterations
        )
        config.reddit.verbose = cls._get_bool_env(
            "REDDIT_VERBOSE", config.reddit.verbose
        )
        config.reddit.timeout_seconds = cls._get_int_env(
            "REDDIT_TIMEOUT", config.reddit.timeout_seconds
        )
        config.reddit.max_retries = cls._get_int_env(
            "REDDIT_MAX_RETRIES", config.reddit.max_retries
        )

        # Twitter
        config.twitter.days_back = cls._get_int_env(
            "TWITTER_DAYS_BACK", config.twitter.days_back
        )
        config.twitter.max_wait_minutes = cls._get_int_env(
            "TWITTER_MAX_WAIT_MINUTES", config.twitter.max_wait_minutes
        )
        config.twitter.api_timeout = cls._get_int_env(
            "TWITTER_API_TIMEOUT", config.twitter.api_timeout
        )
        config.twitter.max_retries = cls._get_int_env(
            "TWITTER_MAX_RETRIES", config.twitter.max_retries
        )
        config.twitter.search_timeout = cls._get_int_env(
            "TWITTER_SEARCH_TIMEOUT", config.twitter.search_timeout
        )

        return config

    @staticmethod
    def _get_bool_env(key: str, default: bool) -> bool:
        value = os.getenv(key)
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "on")

    @staticmethod
    def _get_int_env(key: str, default: int) -> int:
        value = os.getenv(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    @staticmethod
    def _get_float_env(key: str, default: float) -> float:
        value = os.getenv(key)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    @staticmethod
    def _update_config_from_dict(
        config: "TrendScanConfig", config_dict: Dict[str, Any]
    ) -> None:
        """Update config object from dictionary using reflection"""
        for section_name, section_data in config_dict.items():
            if hasattr(config, section_name) and isinstance(section_data, dict):
                section_obj = getattr(config, section_name)
                for key, value in section_data.items():
                    if hasattr(section_obj, key):
                        setattr(section_obj, key, value)

    def validate(self) -> None:
        """Validate all configuration values"""
        self.api_keys.validate()
        self.llm.validate()

        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.logging.level.upper() not in valid_levels:
            raise ValueError(
                f"Invalid log level: {self.logging.level}. Must be one of {valid_levels}"
            )

        if self.execution.max_workers < 1:
            raise ValueError("max_workers must be at least 1")

        if self.execution.timeout_minutes < 1:
            raise ValueError("timeout_minutes must be at least 1")

        if self.crunchbase.max_retries < 1:
            raise ValueError("crunchbase max_retries must be at least 1")

        if self.crunchbase.timeout_seconds < 1:
            raise ValueError("crunchbase timeout_seconds must be at least 1")

        if self.linkedin.posts_date_range_days < 1:
            raise ValueError("linkedin posts_date_range_days must be at least 1")

        if self.linkedin.api_timeout < 1:
            raise ValueError("linkedin api_timeout must be at least 1")

        if self.reddit.timeout_seconds < 1:
            raise ValueError("reddit timeout_seconds must be at least 1")

        if self.twitter.days_back < 1:
            raise ValueError("twitter days_back must be at least 1")

        if self.twitter.api_timeout < 1:
            raise ValueError("twitter api_timeout must be at least 1")

        if not any(
            [
                self.sources.enable_crunchbase,
                self.sources.enable_linkedin,
                self.sources.enable_reddit,
                self.sources.enable_twitter,
            ]
        ):
            raise ValueError("At least one data source must be enabled")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for serialization"""

        def dataclass_to_dict(obj):
            if hasattr(obj, "__dataclass_fields__"):
                return {
                    field_name: dataclass_to_dict(getattr(obj, field_name))
                    for field_name in obj.__dataclass_fields__
                }
            elif isinstance(obj, Enum):
                return obj.value
            else:
                return obj

        return dataclass_to_dict(self)

    def save_to_file(self, file_path: str) -> None:
        """Save configuration to JSON file with sensitive data redacted"""
        config_dict = self.to_dict()

        if "api_keys" in config_dict:
            config_dict["api_keys"] = {
                "gemini": "***REDACTED***" if config_dict["api_keys"]["gemini"] else "",
                "bright_data": (
                    "***REDACTED***" if config_dict["api_keys"]["bright_data"] else ""
                ),
            }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)

    @classmethod
    def create_example_config(cls, file_path: str) -> None:
        """Create an example configuration file"""
        example_config = {
            "api_keys": {
                "gemini": "your_gemini_api_key_here",
                "bright_data": "your_bright_data_token_here",
            },
            "bright_data": {
                "web_unlocker_zone": "optional_web_unlocker_zone",
                "browser_zone": "optional_browser_zone",
            },
            "logging": {
                "level": "INFO",
                "enable_file_logging": True,
                "log_directory": "logs",
                "max_file_size_mb": 10,
                "backup_count": 5,
            },
            "output": {
                "base_directory": "output",
                "include_timestamp": True,
                "create_company_folders": True,
            },
            "execution": {
                "parallel_execution": True,
                "max_workers": 4,
                "timeout_minutes": 30,
            },
            "sources": {
                "enable_crunchbase": True,
                "enable_linkedin": True,
                "enable_reddit": True,
                "enable_twitter": True,
            },
            "crunchbase": {
                "max_retries": 3,
                "base_backoff_delay": 2.0,
                "max_backoff_delay": 60.0,
                "temperature": 0.0,
                "timeout_seconds": 60,
                "max_search_attempts": 3,
            },
            "linkedin": {
                "collect_jobs": True,
                "collect_posts": True,
                "posts_date_range_days": 7,
                "max_wait_time": 1000,
                "status_check_interval": 30,
                "api_timeout": 60,
                "max_retries": 10,
            },
            "reddit": {
                "max_iterations": 5,
                "verbose": True,
                "timeout_seconds": 120,
                "max_retries": 3,
            },
            "twitter": {
                "days_back": 7,
                "max_wait_minutes": 10,
                "api_timeout": 30,
                "max_retries": 3,
                "search_timeout": 60,
            },
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(example_config, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "create-example":
            file_path = sys.argv[2] if len(sys.argv) > 2 else "TrendScan_config.json"
            TrendScanConfig.create_example_config(file_path)
            print(f"Example configuration created: {file_path}")
        else:
            print("Usage: python config.py [create-example] [filename]")
    else:
        try:
            config = TrendScanConfig.load()
            print("Configuration loaded successfully!")
            enabled_sources = [
                s.value
                for s in [
                    DataSource.CRUNCHBASE if config.sources.enable_crunchbase else None,
                    DataSource.LINKEDIN if config.sources.enable_linkedin else None,
                    DataSource.REDDIT if config.sources.enable_reddit else None,
                    DataSource.TWITTER if config.sources.enable_twitter else None,
                ]
                if s
            ]
            print(f"Enabled sources: {enabled_sources}")
        except Exception as e:
            print(f"Configuration error: {e}")
            sys.exit(1)