"""
LinkedIn Agent - Company Posts and Jobs Collection
"""

import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from crewai import Agent, Crew, Process, Task
from mcpadapt.core import MCPAdapt
from mcpadapt.crewai_adapter import CrewAIAdapter

from .base_agent import BaseDataCollector, CollectionResult, CollectionStatus
from config import TrendScanConfig


class ScrapingStatus(Enum):
    """Status enum for scraping operations."""

    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    ERROR = "error"
    CANCELLED = "cancelled"


class DateRangeManager:
    """Manages date range calculations for scraping operations."""

    @staticmethod
    def get_date_range(days: int) -> Tuple[str, str]:
        """Get start and end dates for the specified time period.

        Args:
            days: Number of days to go back from now

        Returns:
            Tuple of (start_date_iso, end_date_iso) in ISO 8601 format
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Format as ISO 8601 with timezone
        start_date_iso = start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
        end_date_iso = end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"

        return start_date_iso, end_date_iso


class CompanyInfoExtractor:
    """Extracts and validates LinkedIn company information using MCP tools."""

    def __init__(self, config: TrendScanConfig, llm_manager, logger: logging.Logger):
        """Initialize the company info extractor.

        Args:
            config: Configuration object containing API keys and settings
            llm_manager: Language model manager for CrewAI agents
            logger: Logger instance for output
        """
        self.config = config
        self.llm_manager = llm_manager
        self.logger = logger
        self.server_params = self._configure_mcp_server()

    def _configure_mcp_server(self):
        """Configure MCP server parameters for Bright Data integration."""
        from mcp import StdioServerParameters

        return StdioServerParameters(
            command="npx",
            args=["@brightdata/mcp"],
            env={
                "API_TOKEN": self.config.api_keys.bright_data,
                "WEB_UNLOCKER_ZONE": self.config.bright_data.web_unlocker_zone,
                "BROWSER_ZONE": self.config.bright_data.browser_zone,
            },
        )

    def extract_company_info(
        self, company_name: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Extract LinkedIn company information using CrewAI agents.

        Args:
            company_name: Name of the company to search for

        Returns:
            Tuple of (validated_company_name, linkedin_username) or (None, None) if not found
        """
        self.logger.info(f"Extracting LinkedIn company information for: {company_name}")

        try:
            with MCPAdapt(self.server_params, CrewAIAdapter()) as mcp_tools:
                search_agent = Agent(
                    role="LinkedIn Company Information Extractor",
                    goal=f"Find {company_name} on LinkedIn and extract company name and username",
                    backstory="Expert at finding LinkedIn company pages and extracting accurate information.",
                    tools=mcp_tools,
                    llm=self.llm_manager.llm,
                    max_iter=3,
                    verbose=False,
                )

                search_task = Task(
                    description=self._get_search_task_description(company_name),
                    expected_output="Two lines: 'COMPANY_NAME: [name]' and 'USERNAME: [username]' or 'NOT_FOUND' for both",
                    agent=search_agent,
                )

                search_crew = Crew(
                    agents=[search_agent],
                    tasks=[search_task],
                    process=Process.sequential,
                    verbose=False,
                )

                search_result = search_crew.kickoff()
                return self._parse_search_result(
                    str(search_result).strip(), company_name
                )

        except Exception as e:
            self.logger.error(f"Error extracting company info: {e}")
            return company_name, None

    def _get_search_task_description(self, company_name: str) -> str:
        """Generate the search task description for the agent.

        Args:
            company_name: Name of the company to search for

        Returns:
            Formatted task description string
        """
        return f"""
        Use the search_engine tool to find the LinkedIn company page for "{company_name}".
        
        Search query: "{company_name} site:linkedin.com/company"
        
        From the search results, extract TWO pieces of information:
        1. The EXACT company name as it appears on LinkedIn (display name)
        2. The LinkedIn username/slug from the URL
        
        Return your response in this exact format:
        COMPANY_NAME: [exact company name]
        USERNAME: [linkedin username from URL]
        
        If no LinkedIn company page is found, return:
        COMPANY_NAME: NOT_FOUND
        USERNAME: NOT_FOUND
        """

    def _parse_search_result(
        self, search_result_text: str, original_company_name: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Parse the search result to extract company name and username.

        Args:
            search_result_text: Raw text result from the search agent
            original_company_name: Original company name as fallback

        Returns:
            Tuple of (company_name, username) or appropriate None values
        """
        company_name = None
        username = None

        for line in search_result_text.split("\n"):
            line = line.strip()
            if line.startswith("COMPANY_NAME:"):
                company_name = line.replace("COMPANY_NAME:", "").strip()
            elif line.startswith("USERNAME:"):
                username = line.replace("USERNAME:", "").strip()

        if company_name == "NOT_FOUND" or username == "NOT_FOUND":
            self.logger.warning("Company not found on LinkedIn")
            return None, None

        if company_name and username:
            self.logger.info(
                f"Successfully extracted - Company: {company_name}, Username: {username}"
            )
            return company_name, username
        else:
            self.logger.warning("Could not extract complete company information")
            return original_company_name, None


class BrightDataAPIClient:
    """Handles API communication with Bright Data for LinkedIn scraping."""

    def __init__(self, config: TrendScanConfig, retry_manager, logger: logging.Logger):
        """Initialize the API client.

        Args:
            config: Configuration object containing API keys and settings
            retry_manager: Manager for handling retry logic
            logger: Logger instance for output
        """
        self.config = config
        self.retry_manager = retry_manager
        self.logger = logger

        self.headers = {
            "Authorization": f"Bearer {config.api_keys.bright_data}",
            "Content-Type": "application/json",
        }

    def trigger_jobs_collection(
        self, company_display_name: str, linkedin_username: str
    ) -> Optional[str]:
        """Trigger dataset collection for company job postings.

        Args:
            company_display_name: Display name of the company on LinkedIn
            linkedin_username: LinkedIn username/slug for the company

        Returns:
            Snapshot ID if successful, None otherwise
        """
        self.logger.info(
            f"Triggering jobs collection for: {company_display_name} (@{linkedin_username})"
        )

        api_url = (
            f"https://api.brightdata.com/datasets/v3/trigger?"
            f"dataset_id={self.config.linkedin.jobs_dataset_id}&"
            f"include_errors=true&type=discover_new&discover_by=keyword"
        )

        payload = [
            {
                "location": "worldwide",
                "time_range": "Past 24 hours",
                "company": company_display_name,  # Use display name for better matching
                "keyword": "",
                "country": "",
                "job_type": "",
                "experience_level": "",
                "remote": "",
                "location_radius": "",
            }
        ]

        return self.retry_manager.execute_with_retry(
            "trigger_jobs_collection",
            self._make_trigger_request,
            api_url,
            self.headers,
            payload,
            "jobs",
        )

    def trigger_posts_collection(self, linkedin_username: str) -> Optional[str]:
        """Trigger dataset collection for company posts.

        Args:
            linkedin_username: LinkedIn username/slug for the company

        Returns:
            Snapshot ID if successful, None otherwise
        """
        self.logger.info(f"Triggering posts collection for: {linkedin_username}")

        start_date_iso, end_date_iso = DateRangeManager.get_date_range(
            self.config.linkedin.posts_date_range_days
        )
        self.logger.info(f"Date range: {start_date_iso} to {end_date_iso}")

        api_url = (
            f"https://api.brightdata.com/datasets/v3/trigger?"
            f"dataset_id={self.config.linkedin.posts_dataset_id}&"
            f"include_errors=true&type=discover_new&discover_by=company_url"
        )

        payload = [
            {
                "url": f"https://www.linkedin.com/company/{linkedin_username}",
                "start_date": start_date_iso,
                "end_date": end_date_iso,
            }
        ]

        return self.retry_manager.execute_with_retry(
            "trigger_posts_collection",
            self._make_trigger_request,
            api_url,
            self.headers,
            payload,
            "posts",
        )

    def _make_trigger_request(
        self, api_url: str, headers: dict, payload: list, data_type: str
    ) -> Optional[str]:
        """Make the API request to trigger data collection.

        Args:
            api_url: The API endpoint URL
            headers: Request headers
            payload: Request payload
            data_type: Type of data being collected (for logging)

        Returns:
            Snapshot ID if successful

        Raises:
            Exception: If the API request fails
        """
        self.logger.debug(f"Making API request to trigger {data_type} collection")

        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=self.config.linkedin.api_timeout,
        )

        if response.status_code == 200:
            response_data = response.json()
            snapshot_id = response_data.get("snapshot_id")

            if snapshot_id:
                self.logger.info(
                    f"{data_type.capitalize()} collection triggered. Snapshot ID: {snapshot_id}"
                )
                return snapshot_id
            else:
                self.logger.error(f"No snapshot_id in response: {response_data}")
                raise Exception(f"No snapshot_id in response for {data_type}")
        else:
            self.logger.error(
                f"API request failed with status {response.status_code}: {response.text}"
            )
            raise Exception(f"API request failed: {response.status_code}")

    def wait_for_snapshot_completion(self, snapshot_id: str) -> bool:
        """Wait for snapshot to complete and return success status.

        Args:
            snapshot_id: The snapshot ID to monitor

        Returns:
            True if snapshot completed successfully, False otherwise
        """
        self.logger.info(f"Waiting for snapshot {snapshot_id} to complete...")

        start_time = time.time()
        max_wait_time = self.config.linkedin.max_wait_time

        while time.time() - start_time < max_wait_time:
            current_status = self.retry_manager.execute_with_retry(
                "check_snapshot_status", self._check_snapshot_status, snapshot_id
            )

            elapsed_seconds = int(time.time() - start_time)

            if current_status == ScrapingStatus.READY.value:
                self.logger.info(
                    f"Snapshot is ready! (completed after {elapsed_seconds}s)"
                )
                return True
            elif current_status in [
                ScrapingStatus.FAILED.value,
                ScrapingStatus.ERROR.value,
                ScrapingStatus.CANCELLED.value,
            ]:
                self.logger.error(f"Snapshot failed with status: {current_status}")
                return False
            elif current_status == ScrapingStatus.RUNNING.value:
                self.logger.info(
                    f"Status: {current_status} ({elapsed_seconds}s elapsed)"
                )

            time.sleep(self.config.linkedin.status_check_interval)

        self.logger.error(
            f"Timeout: Snapshot did not complete within {max_wait_time} seconds"
        )
        return False

    def _check_snapshot_status(self, snapshot_id: str) -> Optional[str]:
        """Check the current status of a snapshot.

        Args:
            snapshot_id: The snapshot ID to check

        Returns:
            Current status string or None if request fails
        """
        status_url = f"https://api.brightdata.com/datasets/v3/progress/{snapshot_id}"
        status_headers = {"Authorization": f"Bearer {self.config.api_keys.bright_data}"}

        response = requests.get(
            status_url, headers=status_headers, timeout=self.config.linkedin.api_timeout
        )
        response.raise_for_status()

        status_data = response.json()
        return status_data.get("status")

    def fetch_snapshot_data(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the completed snapshot data.

        Args:
            snapshot_id: The snapshot ID to fetch data for

        Returns:
            JSON data from the snapshot or None if request fails
        """
        self.logger.info(f"Fetching data for snapshot: {snapshot_id}")

        data_url = (
            f"https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}?format=json"
        )
        headers = {"Authorization": f"Bearer {self.config.api_keys.bright_data}"}

        return self.retry_manager.execute_with_retry(
            "fetch_snapshot_data", self._make_data_request, data_url, headers
        )

    def _make_data_request(self, data_url: str, headers: dict) -> Dict[str, Any]:
        """Make the actual data fetch request.

        Args:
            data_url: URL to fetch data from
            headers: Request headers

        Returns:
            JSON response data

        Raises:
            Exception: If the request fails
        """
        response = requests.get(
            data_url, headers=headers, timeout=self.config.linkedin.api_timeout
        )

        if response.status_code == 200:
            return response.json()
        else:
            self.logger.error(
                f"Failed to fetch data: {response.status_code} - {response.text}"
            )
            raise Exception(f"Failed to fetch data: {response.status_code}")


class LinkedInScraper(BaseDataCollector):
    """
    LinkedIn scraper implementing the standardized BaseDataCollector interface.

    Collects both job postings and company posts from LinkedIn using Bright Data APIs.
    """

    def __init__(self, company_name: str, config: TrendScanConfig):
        """Initialize the LinkedIn scraper.

        Args:
            company_name: Name of the company to scrape data for
            config: Configuration object containing settings and API keys
        """
        super().__init__(company_name, config, "linkedin")

        # Initialize helper components
        self.company_extractor = CompanyInfoExtractor(
            config, self.llm_manager, self.logger
        )
        self.api_client = BrightDataAPIClient(config, self.retry_manager, self.logger)

        self.logger.info(f"LinkedInScraper initialized for: {company_name}")
        self.logger.info(
            f"Configuration - Jobs: {config.linkedin.collect_jobs}, "
            f"Posts: {config.linkedin.collect_posts}"
        )

    def collect(self, company_name: str, output_dir: Path) -> CollectionResult:
        """
        Collect LinkedIn data (jobs and/or posts) for the specified company.

        Args:
            company_name: Name of the company to collect data for
            output_dir: Directory to save collected data files

        Returns:
            CollectionResult with status, files, and metadata
        """
        start_time = time.time()

        try:
            self.logger.info(f"Starting LinkedIn collection for: {company_name}")

            # Step 1: Extract company information from LinkedIn
            validated_company_name, linkedin_username = (
                self.company_extractor.extract_company_info(company_name)
            )

            if not linkedin_username or not validated_company_name:
                raise Exception(
                    f"Could not find LinkedIn company information for {company_name}"
                )

            self.logger.info(
                f"Found LinkedIn company: {validated_company_name} (@{linkedin_username})"
            )

            # Step 2: Determine what to collect based on configuration
            collect_jobs = self.config.linkedin.collect_jobs
            collect_posts = self.config.linkedin.collect_posts

            if not collect_jobs and not collect_posts:
                raise Exception(
                    "Both jobs and posts collection are disabled. "
                    "Enable at least one in configuration."
                )

            self.logger.info(
                f"Collection plan - Jobs: {collect_jobs}, Posts: {collect_posts}"
            )

            # Step 3: Execute collections
            collected_files = []
            collection_errors = []

            # Collect jobs if enabled
            if collect_jobs:
                try:
                    self.logger.info("Starting jobs collection...")
                    jobs_file = self._collect_jobs_data(
                        validated_company_name, linkedin_username, output_dir
                    )

                    if jobs_file:
                        collected_files.append(jobs_file)
                        self.logger.info(
                            f"Jobs collection successful: {Path(jobs_file).name}"
                        )
                    else:
                        collection_errors.append("Jobs collection returned no data")
                        self.logger.warning("Jobs collection returned no data")

                except Exception as e:
                    error_msg = f"Jobs collection failed: {str(e)}"
                    collection_errors.append(error_msg)
                    self.logger.error(error_msg)

            # Collect posts if enabled
            if collect_posts:
                try:
                    self.logger.info("Starting posts collection...")
                    posts_file = self._collect_posts_data(
                        validated_company_name, linkedin_username, output_dir
                    )

                    if posts_file:
                        collected_files.append(posts_file)
                        self.logger.info(
                            f"Posts collection successful: {Path(posts_file).name}"
                        )
                    else:
                        collection_errors.append("Posts collection returned no data")
                        self.logger.warning("Posts collection returned no data")

                except Exception as e:
                    error_msg = f"Posts collection failed: {str(e)}"
                    collection_errors.append(error_msg)
                    self.logger.error(error_msg)

            # Step 4: Evaluate results and return appropriate response
            duration = time.time() - start_time

            if collected_files:
                # Success - at least one collection worked
                self.logger.info(
                    f"LinkedIn collection completed! Files: {len(collected_files)}"
                )

                return self._create_collection_result(
                    status=CollectionStatus.COMPLETED,
                    data_file=collected_files[0],  # Primary file
                    duration_seconds=duration,
                    metadata={
                        "company_name": validated_company_name,
                        "linkedin_username": linkedin_username,
                        "files_created": collected_files,
                        "file_count": len(collected_files),
                        "collections_attempted": [
                            "jobs" if collect_jobs else None,
                            "posts" if collect_posts else None,
                        ],
                        "collections_successful": [
                            (
                                "jobs"
                                if any("jobs" in f for f in collected_files)
                                else None
                            ),
                            (
                                "posts"
                                if any("posts" in f for f in collected_files)
                                else None
                            ),
                        ],
                        "collection_errors": (
                            collection_errors if collection_errors else None
                        ),
                    },
                )
            else:
                # Complete failure - no collections succeeded
                error_message = (
                    f"All LinkedIn collections failed. "
                    f"Errors: {'; '.join(collection_errors)}"
                )
                self.logger.error(error_message)

                return self._create_collection_result(
                    status=CollectionStatus.FAILED,
                    error_message=error_message,
                    duration_seconds=duration,
                    metadata={
                        "company_name": validated_company_name,
                        "linkedin_username": linkedin_username,
                        "collection_errors": collection_errors,
                    },
                )

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"LinkedIn collection failed: {e}")

            return self._create_collection_result(
                status=CollectionStatus.FAILED,
                error_message=str(e),
                duration_seconds=duration,
            )

    def _collect_jobs_data(
        self, company_name: str, linkedin_username: str, output_dir: Path
    ) -> Optional[str]:
        """Collect and save job posting data for the company.

        Args:
            company_name: Display name of the company
            linkedin_username: LinkedIn username for the company
            output_dir: Directory to save the data file

        Returns:
            Path to saved file if successful, None otherwise

        Raises:
            Exception: If any step in the collection process fails
        """
        try:
            # Trigger the collection using company display name
            snapshot_id = self.api_client.trigger_jobs_collection(
                company_name, linkedin_username
            )
            if not snapshot_id:
                raise Exception("Failed to trigger jobs collection")

            # Wait for completion
            if not self.api_client.wait_for_snapshot_completion(snapshot_id):
                raise Exception("Jobs collection did not complete successfully")

            # Fetch the data
            data = self.api_client.fetch_snapshot_data(snapshot_id)
            if not data:
                raise Exception("Failed to fetch jobs data")

            # Save to file
            filename = f"{self._sanitize_filename(company_name)}_linkedin_jobs.json"
            output_file = output_dir / filename

            return self.data_saver.save_data(
                data,
                output_file,
                metadata={
                    "company_name": company_name,
                    "linkedin_username": linkedin_username,
                    "data_type": "jobs",
                    "snapshot_id": snapshot_id,
                },
            )

        except Exception as e:
            self.logger.error(f"Jobs collection error: {e}")
            raise

    def _collect_posts_data(
        self, company_name: str, linkedin_username: str, output_dir: Path
    ) -> Optional[str]:
        """Collect and save company posts data.

        Args:
            company_name: Display name of the company
            linkedin_username: LinkedIn username for the company
            output_dir: Directory to save the data file

        Returns:
            Path to saved file if successful, None otherwise

        Raises:
            Exception: If any step in the collection process fails
        """
        try:
            # Trigger the collection
            snapshot_id = self.api_client.trigger_posts_collection(linkedin_username)
            if not snapshot_id:
                raise Exception("Failed to trigger posts collection")

            # Wait for completion
            if not self.api_client.wait_for_snapshot_completion(snapshot_id):
                raise Exception("Posts collection did not complete successfully")

            # Fetch the data
            data = self.api_client.fetch_snapshot_data(snapshot_id)
            if not data:
                raise Exception("Failed to fetch posts data")

            # Save to file
            filename = f"{self._sanitize_filename(company_name)}_linkedin_posts.json"
            output_file = output_dir / filename

            return self.data_saver.save_data(
                data,
                output_file,
                metadata={
                    "company_name": company_name,
                    "linkedin_username": linkedin_username,
                    "data_type": "posts",
                    "snapshot_id": snapshot_id,
                    "date_range_days": self.config.linkedin.posts_date_range_days,
                },
            )

        except Exception as e:
            self.logger.error(f"Posts collection error: {e}")
            raise


def main():
    """Test the LinkedIn scraper functionality."""
    target_company = "Google Deepmind"

    try:
        from config import TrendScanConfig

        # Load configuration and enable both collections for testing
        config = TrendScanConfig.load()
        config.linkedin.collect_jobs = True
        config.linkedin.collect_posts = True

        print(f"Testing LinkedIn scraper for: {target_company}")
        print("Configuration:")
        print(f"   - Collect Jobs: {config.linkedin.collect_jobs}")
        print(f"   - Collect Posts: {config.linkedin.collect_posts}")

        # Initialize and test the scraper
        scraper = LinkedInScraper(target_company, config)
        output_dir = Path("test_output")
        result = scraper.collect(target_company, output_dir)

        # Display results
        print("\nCollection Result:")
        print(f"Status: {result.status.value}")
        print(f"Primary File: {result.data_file}")
        print(f"Duration: {result.duration_seconds:.2f}s")

        if result.error_message:
            print(f"Error: {result.error_message}")

        if result.metadata:
            print("\nMetadata:")
            for key, value in result.metadata.items():
                print(f"   {key}: {value}")

    except Exception as e:
        print(f"Test failed: {e}")


if __name__ == "__main__":
    main()