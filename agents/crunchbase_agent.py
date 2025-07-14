"""
Crunchbase Agent - Company Data Collection
"""

import json
import logging
import re
import time
from typing import Optional
from pathlib import Path

from crewai import Agent, Task, Crew, Process
from mcpadapt.core import MCPAdapt
from mcpadapt.crewai_adapter import CrewAIAdapter

from .base_agent import BaseDataCollector, CollectionResult, CollectionStatus
from config import TrendScanConfig


class URLFinder:
    """Handles finding Crunchbase URLs for companies using AI-powered search."""

    CRUNCHBASE_BASE_URL = "https://www.crunchbase.com/organization/"
    SEARCH_PATTERN = r"crunchbase\.com/organization/([^/\s\)]+)"

    def __init__(self, config: TrendScanConfig, llm_manager, logger: logging.Logger):
        self.config = config
        self.llm_manager = llm_manager
        self.logger = logger

    def find_company_url(self, mcp_tools, company_name: str) -> Optional[str]:
        """Find the Crunchbase URL for a company using AI-powered search."""
        self.logger.info(f"Searching for Crunchbase URL for: {company_name}")

        try:
            search_agent = Agent(
                role="URL Finder",
                goal=f"Find Crunchbase URL for {company_name}",
                backstory="Specialized in locating company profile URLs on Crunchbase.",
                tools=mcp_tools,
                llm=self.llm_manager.llm,
                max_iter=self.config.crunchbase.max_search_attempts,
                verbose=False,
            )

            search_task = Task(
                description=f'Search for: "{company_name} site:crunchbase.com/organization"',
                expected_output="Crunchbase organization URL",
                agent=search_agent,
            )

            search_crew = Crew(
                agents=[search_agent],
                tasks=[search_task],
                process=Process.sequential,
                verbose=False,
            )

            self.logger.debug("Executing URL search crew")
            search_result = search_crew.kickoff()

            # Extract organization slug from search results using regex
            url_matches = re.findall(self.SEARCH_PATTERN, str(search_result))
            if url_matches:
                found_url = f"{self.CRUNCHBASE_BASE_URL}{url_matches[0]}"
                self.logger.info(f"Found Crunchbase URL: {found_url}")
                return found_url

            self.logger.warning(f"No Crunchbase URL found for {company_name}")
            return None

        except Exception as e:
            self.logger.error(f"URL search failed: {str(e)}")
            raise


class DataExtractor:
    """Handles data extraction from Crunchbase pages using specialized AI agents."""

    def __init__(self, config: TrendScanConfig, llm_manager, logger: logging.Logger):
        self.config = config
        self.llm_manager = llm_manager
        self.logger = logger

    def extract_company_data(self, mcp_tools, company_url: str) -> str:
        """Extract comprehensive company data from Crunchbase using AI."""
        self.logger.info(f"Extracting data from: {company_url}")

        try:
            data_agent = Agent(
                role="Data Extractor",
                goal="Extract comprehensive company data from Crunchbase",
                backstory="You are a data extraction specialist. Your job is to use the web_data_crunchbase_company tool and return exactly what it outputs.",
                tools=mcp_tools,
                llm=self.llm_manager.llm,
                max_iter=3,  # Single iteration to prevent over-processing
                verbose=True,
            )

            extraction_task = Task(
                description=f"""
                Use the web_data_crunchbase_company tool to extract data from: {company_url}
                
                IMPORTANT INSTRUCTIONS:
                1. Call the web_data_crunchbase_company tool with the URL
                2. Return EXACTLY what the tool outputs - no modifications, no formatting
                3. Do not add code blocks, explanations, or any other text
                4. Just return the raw tool response as your final answer
                
                The tool will return JSON data with company information. Simply return that JSON data as-is.
                """,
                expected_output="Raw JSON data from the web_data_crunchbase_company tool",
                agent=data_agent,
            )

            extraction_crew = Crew(
                agents=[data_agent],
                tasks=[extraction_task],
                process=Process.sequential,
                verbose=False,  # Reduce verbosity to minimize agent confusion
            )

            self.logger.debug("Executing data extraction crew")
            extraction_result = extraction_crew.kickoff()

            extracted_data = str(extraction_result).strip()

            # Clean up markdown code blocks if AI agent added them
            if extracted_data.startswith("```") or extracted_data.endswith("```"):
                lines = extracted_data.split("\n")
                cleaned_lines = []

                for line in lines:
                    line_stripped = line.strip()
                    # Skip markdown code block markers
                    if (
                        line_stripped == "```"
                        or line_stripped.startswith("```json")
                        or line_stripped.startswith("```")
                    ):
                        continue
                    cleaned_lines.append(line)

                extracted_data = "\n".join(cleaned_lines).strip()

            # Validate data quality before returning
            if not extracted_data or len(extracted_data) < 50:
                self.logger.error(
                    f"Insufficient data extracted. Got: {extracted_data[:100]}..."
                )
                raise Exception("Data extraction returned insufficient data")

            # Warn if data doesn't appear to be JSON format
            if not (extracted_data.startswith("[") or extracted_data.startswith("{")):
                self.logger.warning(
                    f"Extracted data doesn't look like JSON. First 100 chars: {extracted_data[:100]}"
                )

            self.logger.info(
                f"Successfully extracted {len(extracted_data)} characters of data"
            )
            return extracted_data

        except Exception as e:
            self.logger.error(f"Data extraction failed: {str(e)}")
            raise


class CrunchbaseScraper(BaseDataCollector):
    """Main orchestrator for Crunchbase data collection with retry logic and error handling."""

    def __init__(self, company_name: str, config: TrendScanConfig):
        super().__init__(company_name, config, "crunchbase")

        # Initialize specialized components
        self.url_finder = URLFinder(config, self.llm_manager, self.logger)
        self.data_extractor = DataExtractor(config, self.llm_manager, self.logger)

        self.scraped_data = None

        self.logger.info(f"CrunchbaseScraper initialized for: {company_name}")

    def collect(self, company_name: str, output_dir: Path) -> CollectionResult:
        """Main entry point for collecting Crunchbase data with standardized interface."""
        start_time = time.time()

        try:
            self.logger.info(f"Starting Crunchbase collection for: {company_name}")

            # Execute data extraction with retry logic
            if self.extract_company_data():
                filename = (
                    f"{self._sanitize_filename(company_name)}_crunchbase_profile.json"
                )
                output_file = output_dir / filename
                self.save_data_to_file(str(output_file))

                duration = time.time() - start_time

                return self._create_collection_result(
                    status=CollectionStatus.COMPLETED,
                    data_file=str(output_file),
                    duration_seconds=duration,
                    metadata={
                        "data_length": len(self.scraped_data or ""),
                        "company_name": company_name,
                    },
                )
            else:
                raise Exception("Failed to extract company data")

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"Crunchbase collection failed: {e}")

            return self._create_collection_result(
                status=CollectionStatus.FAILED,
                error_message=str(e),
                duration_seconds=duration,
            )

    def extract_company_data(self) -> bool:
        """Extract company data with built-in retry logic for reliability."""
        self.logger.info(f"Starting data extraction for: {self.company_name}")

        try:
            # Use retry manager for resilient execution
            self.scraped_data = self.retry_manager.execute_with_retry(
                "complete_extraction_process", self._execute_extraction_process
            )

            if self.scraped_data:
                self.logger.info("Data extraction completed successfully")
                return True
            else:
                self.logger.error("Data extraction failed - no data obtained")
                return False

        except Exception as e:
            self.logger.error(f"Data extraction failed with exception: {str(e)}")
            return False

    def _execute_extraction_process(self) -> Optional[str]:
        """Execute the complete extraction workflow: URL finding -> data extraction."""
        server_params = self.mcp_manager.get_server_parameters()

        with MCPAdapt(server_params, CrewAIAdapter()) as mcp_tools:
            self.logger.debug("MCP server connection established")

            # Step 1: Find the company's Crunchbase URL
            company_url = self.url_finder.find_company_url(mcp_tools, self.company_name)
            if not company_url:
                self.logger.error("Could not find company URL")
                return None

            # Step 2: Extract company data from the URL
            extracted_data = self.data_extractor.extract_company_data(
                mcp_tools, company_url
            )
            if not extracted_data:
                self.logger.error("Could not extract company data")
                return None

            return extracted_data

    def save_data_to_file(self, output_filename: str) -> str:
        """Save extracted data to JSON file with metadata."""
        if not self.scraped_data:
            raise ValueError("No data to save. Run extract_company_data() first.")

        # Ensure output directory exists
        output_path = Path(output_filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create structured output with metadata
        file_data = {
            "company_name": self.company_name,
            "extraction_timestamp": time.strftime(
                "%Y-%m-%d %H:%M:%S UTC", time.gmtime()
            ),
            "data_length": len(self.scraped_data),
            "extracted_data": self.scraped_data,
        }

        try:
            with open(output_filename, "w", encoding="utf-8") as output_file:
                json.dump(file_data, output_file, indent=2, ensure_ascii=False)

            self.logger.info(f"Data saved to: {output_filename}")
            return output_filename

        except Exception as e:
            self.logger.error(f"Failed to save data to {output_filename}: {str(e)}")
            raise


def main():
    """Example usage demonstrating the Crunchbase scraper."""
    try:
        from config import TrendScanConfig

        # Load configuration and test scraper
        config = TrendScanConfig.load()
        scraper = CrunchbaseScraper("OpenAI", config)

        # Test the collection workflow
        output_dir = Path("test_output")
        result = scraper.collect("OpenAI", output_dir)

        print(f"\nCollection Result:")
        print(f"Status: {result.status.value}")
        print(f"File: {result.data_file}")
        print(f"Duration: {result.duration_seconds:.2f}s")
        if result.error_message:
            print(f"Error: {result.error_message}")

    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        logging.error(f"Critical error in main: {str(e)}")


if __name__ == "__main__":
    main()
