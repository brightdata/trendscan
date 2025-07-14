"""
Twitter Agent - Social Media Data Collection
"""

import logging
import re
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

from crewai import Agent, Task, Crew, Process
from mcpadapt.core import MCPAdapt
from mcpadapt.crewai_adapter import CrewAIAdapter

from .base_agent import BaseDataCollector, CollectionResult, CollectionStatus
from config import TrendScanConfig


class PostExtractor:
    """Handles post extraction from BrightData API."""

    def __init__(self, config: TrendScanConfig, retry_manager, logger: logging.Logger):
        self.config = config
        self.retry_manager = retry_manager
        self.logger = logger

        self.headers = {
            "Authorization": f"Bearer {config.api_keys.bright_data}",
            "Content-Type": "application/json",
        }

    def extract_posts(self, username: str) -> Dict[str, Any]:
        """Extract posts for username from specified time range."""
        self.logger.info(
            f"Extracting posts for @{username} (last {self.config.twitter.days_back} days)"
        )

        try:
            # Calculate date range for post extraction
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.config.twitter.days_back)

            start_date_str = start_date.strftime("%Y-%m-%d")
            end_date_str = end_date.strftime("%Y-%m-%d")

            profile_url = f"https://x.com/{username}"

            # Trigger data collection
            snapshot_id = self.retry_manager.execute_with_retry(
                "trigger_twitter_collection",
                self._trigger_collection,
                profile_url,
                start_date_str,
                end_date_str,
            )

            if not snapshot_id:
                raise Exception("Failed to trigger data collection")

            # Wait for completion
            if not self.retry_manager.execute_with_retry(
                "wait_for_twitter_completion", self._wait_for_completion, snapshot_id
            ):
                raise Exception("Data collection failed or timed out")

            # Retrieve the data
            posts_data = self.retry_manager.execute_with_retry(
                "get_twitter_snapshot_data", self._get_snapshot_data, snapshot_id
            )

            return {
                "username": username,
                "snapshot_id": snapshot_id,
                "date_range": f"{start_date_str} to {end_date_str}",
                "posts_count": len(posts_data) if isinstance(posts_data, list) else 0,
                "posts": posts_data,
            }

        except Exception as e:
            self.logger.error(f"Post extraction failed for @{username}: {e}")
            raise Exception(f"Failed to extract posts: {e}")

    def _trigger_collection(
        self, profile_url: str, start_date: str, end_date: str
    ) -> str:
        """Trigger data collection and return snapshot ID."""
        url = "https://api.brightdata.com/datasets/v3/trigger"
        params = {
            "dataset_id": self.config.twitter.dataset_id,
            "include_errors": "true",
            "type": "discover_new",
            "discover_by": "profile_url",
        }

        payload = [{"url": profile_url, "start_date": start_date, "end_date": end_date}]

        self.logger.debug(f"Triggering collection for {profile_url}")

        response = requests.post(
            url,
            headers=self.headers,
            params=params,
            json=payload,
            timeout=self.config.twitter.api_timeout,
        )

        if response.status_code == 200:
            data = response.json()
            snapshot_id = data.get("snapshot_id")
            self.logger.info(
                f"Collection triggered successfully. Snapshot ID: {snapshot_id}"
            )
            return snapshot_id
        else:
            error_msg = f"API request failed: {response.status_code} - {response.text}"
            self.logger.error(error_msg)
            raise Exception(error_msg)

    def _wait_for_completion(self, snapshot_id: str) -> bool:
        """Wait for data collection to complete with polling."""
        url = f"https://api.brightdata.com/datasets/v3/progress/{snapshot_id}"
        max_checks = self.config.twitter.max_wait_minutes * 6  # Check every 10 seconds

        self.logger.info(
            f"Waiting for data collection to complete (max {self.config.twitter.max_wait_minutes} minutes)"
        )

        for i in range(max_checks):
            response = requests.get(
                url, headers=self.headers, timeout=self.config.twitter.api_timeout
            )

            if response.status_code == 200:
                status = response.json().get("status", "unknown")
                self.logger.debug(f"Status check {i+1}/{max_checks}: {status}")

                if status == "ready":
                    self.logger.info("Data collection completed successfully!")
                    return True
                elif status == "failed":
                    self.logger.error("Data collection failed!")
                    return False
                elif status == "running":
                    time.sleep(10)
                else:
                    self.logger.warning(f"Unknown status: {status}")
                    time.sleep(10)
            else:
                error_msg = f"Progress check failed: {response.status_code}"
                self.logger.warning(error_msg)
                time.sleep(10)

        self.logger.error(
            f"Timeout after {self.config.twitter.max_wait_minutes} minutes"
        )
        return False

    def _get_snapshot_data(self, snapshot_id: str) -> List[Dict[str, Any]]:
        """Retrieve the collected post data."""
        url = f"https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}"
        params = {"format": "json"}

        self.logger.debug(f"Downloading post data for snapshot {snapshot_id}")

        response = requests.get(
            url,
            headers=self.headers,
            params=params,
            timeout=self.config.twitter.api_timeout,
        )

        if response.status_code == 200:
            data = response.json()
            posts = data if isinstance(data, list) else [data]
            self.logger.info(f"Downloaded {len(posts)} posts successfully")
            return posts
        else:
            error_msg = (
                f"Failed to download data: {response.status_code} - {response.text}"
            )
            self.logger.error(error_msg)
            raise Exception(error_msg)


class UsernameDetector:
    """Handles username detection using search with AI assistance."""

    def __init__(
        self,
        config: TrendScanConfig,
        llm_manager,
        retry_manager,
        logger: logging.Logger,
    ):
        self.config = config
        self.llm_manager = llm_manager
        self.retry_manager = retry_manager
        self.logger = logger
        self.server_params = self._create_server_params()

    def _create_server_params(self):
        """Create MCP server parameters for BrightData integration."""
        from mcp import StdioServerParameters

        env_vars = {"API_TOKEN": self.config.api_keys.bright_data}

        # Add optional zones if configured
        if self.config.bright_data.web_unlocker_zone:
            env_vars["WEB_UNLOCKER_ZONE"] = self.config.bright_data.web_unlocker_zone
        if self.config.bright_data.browser_zone:
            env_vars["BROWSER_ZONE"] = self.config.bright_data.browser_zone

        return StdioServerParameters(
            command="npx", args=["@brightdata/mcp"], env=env_vars
        )

    def find_username(self, company_name: str) -> str:
        """Find username for company with retry logic."""
        self.logger.info(f"Finding username for company: {company_name}")

        # Format search queries using templates
        search_queries = []
        for query_template in self.config.twitter.username_search_queries:
            formatted_query = query_template.format(company_name=company_name)
            search_queries.append(formatted_query)

        try:
            return self.retry_manager.execute_with_retry(
                "search_for_username",
                self._search_for_username,
                company_name,
                search_queries,
            )
        except Exception as e:
            self.logger.error(f"Failed to find username for {company_name}: {e}")
            raise Exception(f"Username detection failed: {e}")

    def _search_for_username(self, company_name: str, search_queries: List[str]) -> str:
        """Perform username search using AI agent."""
        with MCPAdapt(self.server_params, CrewAIAdapter()) as mcp_tools:
            for i, query in enumerate(search_queries):
                self.logger.debug(
                    f"Trying search query {i+1}/{len(search_queries)}: {query}"
                )

                try:
                    # Create AI agent for username finding
                    agent = Agent(
                        role="Username Finder",
                        goal=f"Find {company_name}'s Twitter/X username",
                        backstory="Expert at finding social media usernames through web search.",
                        tools=mcp_tools,
                        llm=self.llm_manager.llm,
                        max_iter=3,
                        verbose=False,
                    )

                    task = Task(
                        description=f"""
Search for {query} and find the official Twitter/X username.

Look for:
- x.com/username URLs
- @username mentions
- twitter.com/username URLs

Respond with: USERNAME: @username
                        """,
                        expected_output="Username in format: USERNAME: @username",
                        agent=agent,
                    )

                    # Execute search task
                    crew = Crew(
                        agents=[agent],
                        tasks=[task],
                        process=Process.sequential,
                        verbose=False,
                    )

                    result = crew.kickoff()
                    username = self._extract_username(str(result))

                    if username:
                        self.logger.info(f"Found username: @{username}")
                        return username
                    else:
                        self.logger.debug(f"No username found with query: {query}")

                except Exception as e:
                    self.logger.warning(f"Search query failed: {e}")
                    continue

        raise Exception(f"No username found for {company_name}")

    def _extract_username(self, text: str) -> str:
        """Extract username from text using regex patterns."""
        patterns = [
            r"USERNAME:\s*@?([A-Za-z0-9_]{1,15})",
            r"x\.com/([A-Za-z0-9_]{1,15})",
            r"twitter\.com/([A-Za-z0-9_]{1,15})",
            r"@([A-Za-z0-9_]{1,15})\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                username = match.group(1)
                if 1 <= len(username) <= 15:  # Twitter username length validation
                    self.logger.debug(f"Extracted username: {username}")
                    return username

        self.logger.debug("No valid username found in text")
        return ""


class TwitterScraper(BaseDataCollector):
    """Main Twitter scraper orchestrator with standardized interface."""

    def __init__(self, company_name: str, config: TrendScanConfig):
        super().__init__(company_name, config, "twitter")

        # Initialize core components
        self.username_detector = UsernameDetector(
            config, self.llm_manager, self.retry_manager, self.logger
        )
        self.post_extractor = PostExtractor(config, self.retry_manager, self.logger)

        self.logger.info(f"TwitterScraper initialized for: {company_name}")

    def collect(self, company_name: str, output_dir: Path) -> CollectionResult:
        """Collect Twitter data with standardized interface."""
        start_time = time.time()

        try:
            self.logger.info(f"Starting Twitter collection for: {company_name}")

            # Find the company's username
            username = self.username_detector.find_username(company_name)

            # Extract posts for the found username
            posts_data = self.post_extractor.extract_posts(username)

            # Combine all collected data
            final_data = {
                "company": company_name,
                "username": username,
                "scraped_at": datetime.now().isoformat(),
                "days_analyzed": self.config.twitter.days_back,
                "success": True,
                **posts_data,
            }

            # Save data to file
            filename = f"{self._sanitize_filename(company_name)}_twitter_posts.json"
            output_file = output_dir / filename

            filepath = self.data_saver.save_data(
                final_data,
                output_file,
                metadata={
                    "company_name": company_name,
                    "username": username,
                    "data_type": "posts",
                    "days_analyzed": self.config.twitter.days_back,
                },
            )

            duration = time.time() - start_time

            return self._create_collection_result(
                status=CollectionStatus.COMPLETED,
                data_file=filepath,
                duration_seconds=duration,
                metadata={
                    "username": username,
                    "posts_count": posts_data.get("posts_count", 0),
                    "days_analyzed": self.config.twitter.days_back,
                    "company_name": company_name,
                },
            )

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"Twitter collection failed: {e}")

            return self._create_collection_result(
                status=CollectionStatus.FAILED,
                error_message=str(e),
                duration_seconds=duration,
            )

    def scrape_complete_data(self) -> Dict[str, Any]:
        """Legacy method: Find username and extract posts."""
        self.logger.info(f"Starting complete Twitter scraping for: {self.company_name}")

        try:
            # Execute main scraping workflow
            username = self.username_detector.find_username(self.company_name)
            posts_data = self.post_extractor.extract_posts(username)

            # Prepare final result
            final_data = {
                "company": self.company_name,
                "username": username,
                "scraped_at": datetime.now().isoformat(),
                "days_analyzed": self.config.twitter.days_back,
                "success": True,
                **posts_data,
            }

            # Save to legacy output directory
            output_dir = Path("output")
            output_dir.mkdir(exist_ok=True)

            filename = (
                f"{self._sanitize_filename(self.company_name)}_twitter_posts.json"
            )
            output_file = output_dir / filename

            filepath = self.data_saver.save_data(
                final_data,
                output_file,
                metadata={
                    "company_name": self.company_name,
                    "username": username,
                    "data_type": "posts",
                },
            )

            final_data["saved_to"] = filepath

            self.logger.info(f"Scraping completed successfully for {self.company_name}")
            return final_data

        except Exception as e:
            self.logger.error(f"Scraping failed for {self.company_name}: {e}")
            # Return error result for legacy compatibility
            error_data = {
                "company": self.company_name,
                "scraped_at": datetime.now().isoformat(),
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }
            return error_data


def main():
    """Main execution function for testing and demonstration."""
    company_name = "llamaindex"

    try:
        from config import TrendScanConfig

        # Load configuration
        config = TrendScanConfig.load()
        scraper = TwitterScraper(company_name, config)

        # Test new standardized interface
        output_dir = Path("test_output")
        result = scraper.collect(company_name, output_dir)

        print(f"\nCollection Result:")
        print(f"Status: {result.status.value}")
        print(f"File: {result.data_file}")
        print(f"Duration: {result.duration_seconds:.2f}s")
        if result.error_message:
            print(f"Error: {result.error_message}")
        if result.metadata:
            print(f"Metadata: {result.metadata}")

        # Test legacy method for backward compatibility
        print(f"\n--- Testing Legacy Method ---")
        legacy_result = scraper.scrape_complete_data()

        if legacy_result.get("success"):
            print(f"SUCCESS!")
            print(f"Company: {legacy_result['company']}")
            print(f"Username: @{legacy_result['username']}")
            print(f"Posts found: {legacy_result.get('posts_count', 0)}")
            print(f"Saved to: {legacy_result['saved_to']}")
        else:
            print(f"FAILED!")
            print(f"Company: {legacy_result['company']}")
            print(f"Error: {legacy_result['error']}")
            print(f"Error Type: {legacy_result['error_type']}")

    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        logging.error(f"Critical error in main: {e}")


if __name__ == "__main__":
    main()
