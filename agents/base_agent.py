"""Base Agent Classes and Common Functionality

Provides standardized interfaces and shared functionality for all TrendScan agents.
"""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from crewai.llm import LLM
from mcp import StdioServerParameters


class CollectionStatus(Enum):
    """Represents the current state of a data collection operation."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class CollectionResult:
    """Encapsulates the outcome of a data collection operation."""

    source: str
    status: CollectionStatus
    data_file: Optional[str] = None
    error_message: Optional[str] = None
    duration_seconds: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status.value,
            "data_file": self.data_file,
            "error_message": self.error_message,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
        }


class RetryManager:
    """Handles retry logic with exponential backoff for transient failures."""

    def __init__(
        self, max_retries: int = 3, base_delay: float = 2.0, max_delay: float = 60.0
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.logger = logging.getLogger(f"{__name__}.RetryManager")

    def execute_with_retry(self, operation_name: str, operation_func, *args, **kwargs):
        """Execute operation with retry logic, preserving the original exception."""
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                self.logger.debug(
                    f"Executing {operation_name} - Attempt {attempt + 1}/{self.max_retries}"
                )
                result = operation_func(*args, **kwargs)

                if result is not None:
                    self.logger.debug(
                        f"{operation_name} succeeded on attempt {attempt + 1}"
                    )
                    return result
                else:
                    self.logger.warning(
                        f"{operation_name} returned None on attempt {attempt + 1}"
                    )

            except Exception as e:
                last_exception = e
                self.logger.warning(
                    f"{operation_name} failed on attempt {attempt + 1}: {str(e)}"
                )

                if attempt < self.max_retries - 1:
                    delay = self._calculate_backoff_delay(attempt)
                    self.logger.info(f"Waiting {delay:.2f}s before retry...")
                    time.sleep(delay)

        # All attempts exhausted - raise the last exception or create a generic one
        self.logger.error(f"{operation_name} failed after {self.max_retries} attempts")
        if last_exception:
            raise last_exception
        else:
            raise Exception(f"{operation_name} failed - no valid result obtained")

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """Calculate delay using exponential backoff with jitter to prevent thundering herd."""
        import random

        base_delay = self.base_delay * (2**attempt)
        jitter = random.uniform(0, 1.0)
        delay = min(base_delay + jitter, self.max_delay)
        return delay


class LLMManager:
    """Manages LLM instance creation and configuration with lazy initialization."""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.LLMManager")
        self._llm = None

    @property
    def llm(self) -> LLM:
        """Lazy-load LLM instance to defer expensive initialization."""
        if self._llm is None:
            self._llm = self._create_llm()
        return self._llm

    def _create_llm(self) -> LLM:
        """Create configured LLM instance, wrapping exceptions with context."""
        try:
            llm = LLM(
                model=self.config.llm.model,
                api_key=self.config.api_keys.gemini,
                temperature=self.config.llm.temperature,
                seed=self.config.llm.seed,
                top_p=self.config.llm.top_p,
            )
            self.logger.info(f"LLM initialized: {self.config.llm.model}")
            return llm
        except Exception as e:
            self.logger.error(f"Failed to initialize LLM: {str(e)}")
            raise Exception(f"LLM initialization failed: {e}")


class MCPManager:
    """Manages MCP server configuration and parameter setup."""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.MCPManager")

    def get_server_parameters(self) -> StdioServerParameters:
        """Build MCP server parameters with required and optional environment variables."""
        try:
            env_vars = {
                "API_TOKEN": self.config.api_keys.bright_data,
            }

            # Add optional zone configurations if present
            if self.config.bright_data.web_unlocker_zone:
                env_vars["WEB_UNLOCKER_ZONE"] = (
                    self.config.bright_data.web_unlocker_zone
                )
            if self.config.bright_data.browser_zone:
                env_vars["BROWSER_ZONE"] = self.config.bright_data.browser_zone

            self.logger.debug(
                f"MCP environment variables configured: {list(env_vars.keys())}"
            )

            return StdioServerParameters(
                command="npx", args=["@brightdata/mcp"], env=env_vars
            )
        except Exception as e:
            self.logger.error(f"Failed to create MCP server parameters: {e}")
            raise Exception(f"MCP configuration failed: {e}")


class DataSaver:
    """Handles data persistence with format detection and metadata embedding."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(f"{__name__}.DataSaver")

    def save_data(
        self, data: Any, output_path: Path, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save data to file, automatically detecting format from extension."""
        try:
            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Route to appropriate saver based on file extension
            if output_path.suffix.lower() == ".json":
                self._save_json(data, output_path, metadata)
            elif output_path.suffix.lower() == ".txt":
                self._save_text(data, output_path, metadata)
            else:
                raise ValueError(f"Unsupported file format: {output_path.suffix}")

            self.logger.info(f"Data saved to: {output_path}")
            return str(output_path)

        except Exception as e:
            self.logger.error(f"Failed to save data to {output_path}: {e}")
            raise Exception(f"Data saving failed: {e}")

    def _save_json(
        self, data: Any, output_path: Path, metadata: Optional[Dict[str, Any]]
    ):
        """Save as JSON with structured metadata wrapper."""
        import json

        # Wrap data with metadata for better traceability
        file_data = {
            "extraction_timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
            "data": data,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(file_data, f, indent=2, ensure_ascii=False)

    def _save_text(
        self, data: Any, output_path: Path, metadata: Optional[Dict[str, Any]]
    ):
        """Save as text with optional metadata header."""
        with open(output_path, "w", encoding="utf-8") as f:
            # Write metadata header if provided
            if metadata:
                f.write("=" * 80 + "\n")
                f.write("EXTRACTION METADATA\n")
                f.write("=" * 80 + "\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                for key, value in metadata.items():
                    f.write(f"{key}: {value}\n")
                f.write("=" * 80 + "\n\n")

            # Handle both string and non-string data
            if isinstance(data, str):
                f.write(data)
            else:
                f.write(str(data))


class BaseDataCollector(ABC):
    """Abstract base class defining the interface for all data source collectors."""

    def __init__(self, company_name: str, config, source_name: str):
        self.company_name = company_name.strip()
        self.config = config
        self.source_name = source_name
        self.logger = logging.getLogger(f"{__name__}.{source_name.title()}Collector")

        # Initialize shared components with source-specific configurations
        self.retry_manager = RetryManager(
            max_retries=getattr(config, source_name).max_retries,
            base_delay=getattr(config, source_name, None)
            and getattr(getattr(config, source_name), "base_backoff_delay", 2.0)
            or 2.0,
            max_delay=getattr(config, source_name, None)
            and getattr(getattr(config, source_name), "max_backoff_delay", 60.0)
            or 60.0,
        )
        self.llm_manager = LLMManager(config)
        self.mcp_manager = MCPManager(config)
        self.data_saver = DataSaver(self.logger)

        self.logger.info(
            f"{source_name.title()} collector initialized for: {company_name}"
        )

    @abstractmethod
    def collect(self, company_name: str, output_dir: Path) -> CollectionResult:
        """Collect data from the source. Must be implemented by subclasses."""
        pass

    def _create_collection_result(
        self,
        status: CollectionStatus,
        data_file: Optional[str] = None,
        error_message: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CollectionResult:
        """Factory method for creating standardized collection results."""
        return CollectionResult(
            source=self.source_name,
            status=status,
            data_file=data_file,
            error_message=error_message,
            duration_seconds=duration_seconds,
            metadata=metadata or {},
        )

    def _sanitize_filename(self, filename: str) -> str:
        """Clean filename for cross-platform filesystem compatibility."""
        import re

        # Replace filesystem-unsafe characters
        sanitized = re.sub(r'[<>:"/\\|?*]', "_", filename)
        # Normalize whitespace
        sanitized = re.sub(r"\s+", "_", sanitized)
        # Remove leading/trailing problematic characters
        sanitized = sanitized.strip(" .")
        sanitized = sanitized.lower()

        # Provide fallback for empty results
        if not sanitized:
            sanitized = "unknown"

        # Prevent excessively long filenames
        if len(sanitized) > 100:
            sanitized = sanitized[:100]
        return sanitized
