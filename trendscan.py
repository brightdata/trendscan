"""
Data scraping orchestrator 
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import TrendScanConfig, DataSource
from utils import setup_logging, create_output_structure

from agents.crunchbase_agent import CrunchbaseScraper
from agents.linkedin_agent import LinkedInScraper
from agents.reddit_agent import RedditScraper
from agents.twitter_agent import TwitterScraper
from agents.base_agent import CollectionResult, CollectionStatus


@dataclass
class HuntSession:
    """Container for complete hunt session results and metrics"""

    company_name: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    results: List[CollectionResult] = field(default_factory=list)
    output_directory: Optional[str] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate total session duration in seconds"""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def success_rate(self) -> float:
        if not self.results:
            return 0.0
        completed = sum(
            1 for r in self.results if r.status == CollectionStatus.COMPLETED
        )
        return (completed / len(self.results)) * 100

    @property
    def successful_sources(self) -> List[str]:
        return [
            r.source for r in self.results if r.status == CollectionStatus.COMPLETED
        ]

    @property
    def failed_sources(self) -> List[str]:
        return [r.source for r in self.results if r.status == CollectionStatus.FAILED]

    @property
    def total_files_created(self) -> int:
        """Count total files created across all sources"""
        total = 0
        for result in self.results:
            if result.metadata and "files_created" in result.metadata:
                total += len(result.metadata["files_created"])
            elif result.metadata and "file_count" in result.metadata:
                total += result.metadata["file_count"]
            elif result.data_file:
                total += 1
        return total

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company_name": self.company_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_seconds": self.duration_seconds,
            "success_rate": self.success_rate,
            "successful_sources": self.successful_sources,
            "failed_sources": self.failed_sources,
            "total_files_created": self.total_files_created,
            "output_directory": self.output_directory,
            "results": [r.to_dict() for r in self.results],
        }


class TrendScan:
    """Multi-source company intelligence orchestrator"""

    def __init__(self, config_path: Optional[str] = None):
        self.config = TrendScanConfig.load(config_path)
        self.logger = setup_logging(self.config.logging)

        self.logger.info("TrendScan initialized successfully")
        self._validate_and_log_configuration()

    def _validate_and_log_configuration(self):
        """Validate required configuration and log key settings"""
        try:
            if not self.config.api_keys.gemini:
                raise ValueError("GEMINI_API_KEY is required")
            if not self.config.api_keys.bright_data:
                raise ValueError("BRIGHT_DATA_API_TOKEN is required")

            enabled_sources = self._get_enabled_sources()
            if not enabled_sources:
                raise ValueError("At least one data source must be enabled")

            self.logger.info(f"Enabled sources: {[s.value for s in enabled_sources]}")

            if DataSource.LINKEDIN in enabled_sources:
                self.logger.info(
                    f"LinkedIn config - Jobs: {self.config.linkedin.collect_jobs}, Posts: {self.config.linkedin.collect_posts}"
                )

            self.logger.info(
                f"Execution - Parallel: {self.config.execution.parallel_execution}, Workers: {self.config.execution.max_workers}"
            )

        except Exception as e:
            self.logger.error(f"Configuration validation failed: {e}")
            raise

    def hunt(
        self, company_name: str, sources: Optional[List[DataSource]] = None
    ) -> HuntSession:
        """
        Collect intelligence from multiple data sources

        Args:
            company_name: Name of the company to research
            sources: List of data sources to use (default: all enabled sources)

        Returns:
            HuntSession with complete results and metrics
        """
        self.logger.info(f"Starting intelligence hunt for: {company_name}")

        session = HuntSession(company_name=company_name, started_at=datetime.now())

        try:
            # Determine sources to use
            if sources is None:
                sources = self._get_enabled_sources()

            if not sources:
                raise ValueError("No sources specified or enabled")

            # Create output directory structure
            output_dir = create_output_structure(
                company_name,
                self.config.output.base_directory,
                self.config.output.include_timestamp,
            )
            session.output_directory = str(output_dir)

            self.logger.info(f"Output directory: {output_dir}")
            self.logger.info(f"Target sources: {[s.value for s in sources]}")

            # Execute collections (parallel or sequential)
            if self.config.execution.parallel_execution and len(sources) > 1:
                self.logger.info("Using parallel execution")
                session.results = self._collect_parallel(
                    company_name, sources, output_dir
                )
            else:
                self.logger.info("Using sequential execution")
                session.results = self._collect_sequential(
                    company_name, sources, output_dir
                )

            session.completed_at = datetime.now()

            # Log final results summary
            self.logger.info(f"Hunt completed for {company_name}")
            self.logger.info(f"Success rate: {session.success_rate:.1f}%")
            self.logger.info(f"Duration: {session.duration_seconds:.1f} seconds")
            self.logger.info(f"Files created: {session.total_files_created}")

            if session.successful_sources:
                self.logger.info(
                    f"Successful sources: {', '.join(session.successful_sources)}"
                )
            if session.failed_sources:
                self.logger.warning(
                    f"Failed sources: {', '.join(session.failed_sources)}"
                )

            return session

        except Exception as e:
            self.logger.error(f"Hunt failed for {company_name}: {e}")
            session.completed_at = datetime.now()

            # Add system error if no results were collected
            if not session.results:
                session.results.append(
                    CollectionResult(
                        source="system",
                        status=CollectionStatus.FAILED,
                        error_message=str(e),
                    )
                )

            return session

    def _get_enabled_sources(self) -> List[DataSource]:
        """Get list of enabled data sources from configuration"""
        enabled_sources = []

        if self.config.sources.enable_crunchbase:
            enabled_sources.append(DataSource.CRUNCHBASE)
        if self.config.sources.enable_linkedin:
            enabled_sources.append(DataSource.LINKEDIN)
        if self.config.sources.enable_reddit:
            enabled_sources.append(DataSource.REDDIT)
        if self.config.sources.enable_twitter:
            enabled_sources.append(DataSource.TWITTER)

        return enabled_sources

    def _collect_sequential(
        self, company_name: str, sources: List[DataSource], output_dir: Path
    ) -> List[CollectionResult]:
        results = []

        for i, source in enumerate(sources, 1):
            self.logger.info(f"[{i}/{len(sources)}] Collecting from {source.value}...")

            try:
                result = self._collect_from_source(source, company_name, output_dir)
                results.append(result)

                if result.status == CollectionStatus.COMPLETED:
                    # Log completion with file details
                    if result.metadata and "files_created" in result.metadata:
                        files_created = result.metadata["files_created"]
                        if len(files_created) > 1:
                            self.logger.info(
                                f"{source.value} completed ({len(files_created)} files):"
                            )
                            for file_path in files_created:
                                self.logger.info(f"   {Path(file_path).name}")
                        else:
                            self.logger.info(
                                f"{source.value} completed -> {Path(files_created[0]).name}"
                            )
                    elif result.data_file:
                        self.logger.info(
                            f"{source.value} completed -> {Path(result.data_file).name}"
                        )
                    else:
                        self.logger.info(f"{source.value} completed")

                    if result.duration_seconds:
                        self.logger.info(f"   {result.duration_seconds:.1f}s")
                else:
                    self.logger.error(f"{source.value} failed: {result.error_message}")

            except Exception as e:
                self.logger.error(f"Unexpected error with {source.value}: {e}")
                results.append(
                    CollectionResult(
                        source=source.value,
                        status=CollectionStatus.FAILED,
                        error_message=f"Unexpected error: {str(e)}",
                    )
                )

        return results

    def _collect_parallel(
        self, company_name: str, sources: List[DataSource], output_dir: Path
    ) -> List[CollectionResult]:
        results = []

        with ThreadPoolExecutor(
            max_workers=self.config.execution.max_workers
        ) as executor:
            # Submit all collection tasks
            future_to_source = {
                executor.submit(
                    self._collect_from_source, source, company_name, output_dir
                ): source
                for source in sources
            }

            # Collect results as they complete
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    result = future.result()
                    results.append(result)

                    if result.status == CollectionStatus.COMPLETED:
                        if result.metadata and "files_created" in result.metadata:
                            files_created = result.metadata["files_created"]
                            if len(files_created) > 1:
                                self.logger.info(
                                    f"{source.value} completed ({len(files_created)} files)"
                                )
                            else:
                                self.logger.info(f"{source.value} completed")
                        else:
                            self.logger.info(f"{source.value} completed")
                    else:
                        self.logger.error(
                            f"{source.value} failed: {result.error_message}"
                        )

                except Exception as e:
                    self.logger.error(f"Unexpected error with {source.value}: {e}")
                    results.append(
                        CollectionResult(
                            source=source.value,
                            status=CollectionStatus.FAILED,
                            error_message=f"Unexpected error: {str(e)}",
                        )
                    )

        # Sort results by source order for consistency
        source_order = {source: i for i, source in enumerate(sources)}
        results.sort(key=lambda r: source_order.get(DataSource(r.source), 999))

        return results

    def _collect_from_source(
        self, source: DataSource, company_name: str, output_dir: Path
    ) -> CollectionResult:
        """
        Collect data from a specific source using standardized interface

        Creates the appropriate scraper and calls its collect() method.
        """
        try:
            if source == DataSource.CRUNCHBASE:
                scraper = CrunchbaseScraper(company_name, self.config)
                return scraper.collect(company_name, output_dir)

            elif source == DataSource.LINKEDIN:
                scraper = LinkedInScraper(company_name, self.config)
                return scraper.collect(company_name, output_dir)

            elif source == DataSource.REDDIT:
                scraper = RedditScraper(company_name, self.config)
                return scraper.collect(company_name, output_dir)

            elif source == DataSource.TWITTER:
                scraper = TwitterScraper(company_name, self.config)
                return scraper.collect(company_name, output_dir)

            else:
                raise ValueError(f"Unknown data source: {source}")

        except Exception as e:
            self.logger.error(f"Error collecting from {source.value}: {e}")
            return CollectionResult(
                source=source.value,
                status=CollectionStatus.FAILED,
                error_message=str(e),
            )


def main():
    """Example usage and CLI interface"""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    company_name = sys.argv[1] if len(sys.argv) > 1 else "OpenAI"

    try:
        # Initialize and run hunt
        hunter = TrendScan()

        print(f"\nStarting intelligence hunt for: {company_name}")
        print("=" * 60)

        session = hunter.hunt(company_name)

        # Display results summary
        print(f"\nHunt Results:")
        print(f"Company: {session.company_name}")
        print(f"Duration: {session.duration_seconds:.1f} seconds")
        print(f"Success Rate: {session.success_rate:.1f}%")
        print(f"Total Files: {session.total_files_created}")
        print(f"Output Directory: {session.output_directory}")

        print(f"\nSource Results:")
        for result in session.results:
            status_indicator = (
                "PASS" if result.status == CollectionStatus.COMPLETED else "FAIL"
            )
            print(f"{status_indicator} {result.source.title()}: {result.status.value}")

            if result.status == CollectionStatus.COMPLETED:
                # Show files created
                if result.metadata and "files_created" in result.metadata:
                    files_created = result.metadata["files_created"]
                    for file_path in files_created:
                        print(f"   {Path(file_path).name}")
                elif result.data_file:
                    print(f"   {Path(result.data_file).name}")

                # Show timing and additional metadata
                if result.duration_seconds:
                    print(f"   {result.duration_seconds:.1f}s")

                if result.source == "linkedin" and result.metadata:
                    if "collections_successful" in result.metadata:
                        successful = [
                            c for c in result.metadata["collections_successful"] if c
                        ]
                        print(f"   Collections: {', '.join(successful)}")
            else:
                if result.error_message:
                    print(f"   {result.error_message}")

        print(f"\nHunt completed!")

        if session.success_rate == 100:
            print("Perfect! All data sources completed successfully!")
        elif session.success_rate > 0:
            print(
                f"Partial success: {len(session.successful_sources)}/{len(session.results)} sources completed"
            )
        else:
            print("Complete failure: No data sources completed successfully")
            sys.exit(1)

    except KeyboardInterrupt:
        print(f"\nHunt interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nHunt failed: {e}")
        logging.error(f"Critical error in main: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()