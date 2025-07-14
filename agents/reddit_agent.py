"""
Reddit Agent - Discussion and Opinion Collection
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from crewai import Agent, Task, Crew, Process
from mcpadapt.core import MCPAdapt
from mcpadapt.crewai_adapter import CrewAIAdapter

from .base_agent import BaseDataCollector, CollectionResult, CollectionStatus
from config import TrendScanConfig


class OutputCapture:
    """Captures and manages tool outputs for Reddit scraping sessions."""

    def __init__(self, output_file: Path):
        self.output_file = output_file
        self.captured_outputs: List[Dict[str, Any]] = []
        self.logger = logging.getLogger(__name__)

        # Create output directory structure if it doesn't exist
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

    def initialize_file(self, company_name: str):
        """Initialize output file with session header."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write(f"REDDIT DISCUSSION CAPTURE SESSION\n")
            f.write(f"Company: {company_name}\n")
            f.write(f"Started: {timestamp}\n")
            f.write(f"{'='*80}\n")

        self.logger.info(f"Output capture initialized: {self.output_file}")

    def capture_output(self, tool_name: str, input_data: Any, output_data: Any):
        """Capture tool output to both file and memory for later analysis."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            # Write immediately to prevent data loss on crashes
            with open(self.output_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"TOOL: {tool_name}\n")
                f.write(f"TIMESTAMP: {timestamp}\n")
                f.write(
                    f"INPUT: {str(input_data)[:200]}...\n"
                )  # Truncate for readability
                f.write(f"OUTPUT LENGTH: {len(str(output_data))} characters\n")
                f.write(f"{'='*80}\n")
                f.write(f"{output_data}\n")

            # Store structured data for programmatic access
            self.captured_outputs.append(
                {
                    "tool": tool_name,
                    "timestamp": timestamp,
                    "input": str(input_data),
                    "output": str(output_data),
                    "output_length": len(str(output_data)),
                }
            )

            self.logger.debug(
                f"Captured {tool_name} output ({len(str(output_data))} chars)"
            )

        except Exception as e:
            self.logger.error(f"Failed to capture output for {tool_name}: {e}")

    def finalize_capture(self):
        """Write session summary and close capture session."""
        try:
            summary = self._generate_summary()

            with open(self.output_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"SESSION SUMMARY\n")
                f.write(f"{'='*80}\n")
                f.write(summary)

            self.logger.info(
                f"Capture finalized with {len(self.captured_outputs)} outputs"
            )

        except Exception as e:
            self.logger.error(f"Failed to finalize capture: {e}")

    def _generate_summary(self) -> str:
        """Generate session statistics for analysis."""
        if not self.captured_outputs:
            return "No outputs captured."

        total_outputs = len(self.captured_outputs)
        total_chars = sum(output["output_length"] for output in self.captured_outputs)
        tools_used = set(output["tool"] for output in self.captured_outputs)

        return f"""
Capture Summary:
- Total outputs captured: {total_outputs}
- Total characters: {total_chars:,}
- Tools used: {', '.join(tools_used)}
- Session duration: {self.captured_outputs[0]['timestamp']} to {self.captured_outputs[-1]['timestamp']}
"""


class ToolWrapper:
    """Wraps MCP tools to add retry logic and output capture functionality."""

    def __init__(self, mcp_tools, retry_manager, output_capture: OutputCapture):
        self.mcp_tools = mcp_tools
        self.retry_manager = retry_manager
        self.output_capture = output_capture
        self.logger = logging.getLogger(__name__)

    def __iter__(self):
        """Make wrapper iterable to maintain compatibility with original tools."""
        for tool in self.mcp_tools:
            yield self._wrap_tool(tool)

    def _wrap_tool(self, tool):
        """Enhance tool with retry logic and output capture."""
        # Handle both _run and run method patterns
        original_run = tool._run if hasattr(tool, "_run") else tool.run

        def enhanced_run(*args, **kwargs):
            tool_name = getattr(tool, "name", str(type(tool).__name__))

            def execute_with_capture():
                self.logger.debug(f"Executing tool: {tool_name}")
                result = original_run(*args, **kwargs)

                # Capture for debugging and analysis
                input_data = {"args": args, "kwargs": kwargs}
                self.output_capture.capture_output(tool_name, input_data, result)

                return result

            # Apply retry logic to handle transient failures
            return self.retry_manager.execute_with_retry(
                f"tool_{tool_name}", execute_with_capture
            )

        # Replace the appropriate method based on tool implementation
        if hasattr(tool, "_run"):
            tool._run = enhanced_run
        else:
            tool.run = enhanced_run

        return tool


class SearchAgent:
    """Manages Reddit search agent creation and task configuration."""

    def __init__(self, company_name: str, llm, max_iterations: int = 5):
        self.company_name = company_name
        self.llm = llm
        self.max_iterations = max_iterations
        self.logger = logging.getLogger(__name__)

    def create_agent(self, tools) -> Agent:
        """Create a specialized agent for Reddit data collection."""
        try:
            agent = Agent(
                role="Reddit Data Collector",
                goal=f"Collect comprehensive Reddit data about {self.company_name}",
                backstory="You are focused on gathering complete, unfiltered data from Reddit searches.",
                tools=list(tools),
                llm=self.llm,
                max_iter=self.max_iterations,
                verbose=True,
            )
            self.logger.info(f"Search agent created for {self.company_name}")
            return agent
        except Exception as e:
            self.logger.error(f"Failed to create search agent: {e}")
            raise

    def create_search_task(self, agent: Agent, search_queries: List[str]) -> Task:
        """Create comprehensive search task with formatted queries."""
        try:
            # Format queries with company name placeholders
            formatted_queries = []
            for query in search_queries:
                formatted_query = query.format(company_name=self.company_name)
                formatted_queries.append(formatted_query)

            task = Task(
                description=f"""
                Perform comprehensive Reddit searches for "{self.company_name}":
                
                Execute these searches in order:
                {chr(10).join(f'{i+1}. Search: "{query}"' for i, query in enumerate(formatted_queries))}
                
                For each search, use the search_engine tool and collect all available data.
                Focus on gathering maximum information rather than analysis.
                """,
                expected_output="Complete Reddit search results for all specified queries",
                agent=agent,
            )
            self.logger.info("Search task created")
            return task
        except Exception as e:
            self.logger.error(f"Failed to create search task: {e}")
            raise


class RedditScraper(BaseDataCollector):
    """Main Reddit scraper orchestrator implementing standardized data collection interface."""

    def __init__(self, company_name: str, config: TrendScanConfig):
        super().__init__(company_name, config, "reddit")

        # Setup output directory structure
        self.output_dir = Path(config.output.base_directory)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Create sanitized filename for company data
        company_slug = self._sanitize_filename(company_name)
        self.output_file = self.output_dir / f"{company_slug}_reddit_discussions.txt"

        self.logger.info(f"RedditScraper initialized for: {company_name}")

    def collect(self, company_name: str, output_dir: Path) -> CollectionResult:
        """
        Main collection method implementing standardized interface.

        This method provides consistent results structure across all collectors.
        """
        start_time = time.time()

        try:
            self.logger.info(f"Starting Reddit collection for: {company_name}")

            # Override output location for this collection run
            company_slug = self._sanitize_filename(company_name)
            self.output_file = output_dir / f"{company_slug}_reddit_discussions.txt"

            # Execute the actual scraping
            result = self.scrape()

            duration = time.time() - start_time

            return self._create_collection_result(
                status=CollectionStatus.COMPLETED,
                data_file=str(self.output_file),
                duration_seconds=duration,
                metadata={
                    "result_type": "captured_outputs",
                    "company_name": company_name,
                    "output_count": len(getattr(self, "_captured_outputs", [])),
                    "search_queries": self.config.reddit.search_queries,
                },
            )

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"Reddit collection failed: {e}")

            return self._create_collection_result(
                status=CollectionStatus.FAILED,
                error_message=str(e),
                duration_seconds=duration,
            )

    def scrape(self):
        """Legacy scraping method maintained for backward compatibility."""
        self.logger.info(f"Starting Reddit scraping for: {self.company_name}")

        try:
            # Initialize output capture system
            output_capture = OutputCapture(self.output_file)
            output_capture.initialize_file(self.company_name)

            # Execute scraping with MCP tools
            result = self._execute_with_mcp(output_capture)

            # Finalize and save session data
            output_capture.finalize_capture()

            # Store outputs for metadata reporting
            self._captured_outputs = output_capture.captured_outputs

            self.logger.info("Scraping completed successfully!")
            self.logger.info(f"Results saved to: {self.output_file}")

            return result

        except Exception as e:
            self.logger.error(f"Scraping failed: {e}")
            raise

    def _execute_with_mcp(self, output_capture: OutputCapture):
        """Execute scraping workflow using MCP adapter and CrewAI."""
        server_params = self.mcp_manager.get_server_parameters()

        # Use context manager to ensure proper cleanup
        with MCPAdapt(server_params, CrewAIAdapter()) as mcp_tools:
            # Enhance tools with retry logic and output capture
            wrapped_tools = ToolWrapper(mcp_tools, self.retry_manager, output_capture)

            # Create search agent with enhanced tools
            search_agent_manager = SearchAgent(
                self.company_name,
                self.llm_manager.llm,
                self.config.reddit.max_iterations,
            )

            agent = search_agent_manager.create_agent(wrapped_tools)
            task = search_agent_manager.create_search_task(
                agent, self.config.reddit.search_queries
            )

            # Execute sequential search workflow
            crew = Crew(
                agents=[agent],
                tasks=[task],
                process=Process.sequential,
                verbose=self.config.reddit.verbose,
            )

            result = crew.kickoff()

            # Capture final execution result
            output_capture.capture_output("crew_final_result", "kickoff()", result)

            return result


def main():
    """Main entry point for testing and standalone execution."""
    company_name = "OpenAI"

    try:
        from config import TrendScanConfig

        config = TrendScanConfig.load()
        logger = logging.getLogger(__name__)

        logger.info("=== Reddit Scraper Starting ===")
        logger.info(f"Company: {company_name}")
        logger.info(f"Output directory: {config.output.base_directory}")

        # Create and execute scraper
        scraper = RedditScraper(company_name, config)

        # Test standardized collection interface
        output_dir = Path("test_output")
        result = scraper.collect(company_name, output_dir)

        # Display results
        print(f"\nCollection Result:")
        print(f"Status: {result.status.value}")
        print(f"File: {result.data_file}")
        print(f"Duration: {result.duration_seconds:.2f}s")
        if result.error_message:
            print(f"Error: {result.error_message}")
        if result.metadata:
            print(f"Metadata: {result.metadata}")

        logger.info("=== Scraping Completed Successfully ===")
        return result

    except Exception as e:
        logging.getLogger(__name__).error(f"Application failed: {e}")
        raise


if __name__ == "__main__":
    main()