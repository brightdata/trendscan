"""
Streamlit web application
"""

import streamlit as st
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from config import TrendScanConfig


load_dotenv()

st.set_page_config(page_title="TrendScan", layout="centered")


CRUNCHBASE_INSIGHTS_PROMPT = """
You are a business analyst creating a concise company profile for decision-makers. Your goal is to distill the most relevant insights from structured Crunchbase data.

CRITICAL ANTI-HALLUCINATION RULES:
- ONLY use information that is explicitly present in the provided data
- If a section cannot be filled with actual data, write "Not available in data" for that section
- Do not make assumptions, estimates, or educated guesses
- Do not add information from your general knowledge about the company
- Quote exact data points when possible
- If data is unclear or ambiguous, state that explicitly

CRITICAL FORMATTING RULES - FOLLOW EXACTLY:
- Put TWO blank lines between each major section (####)
- Put ONE blank line between each field within a section
- Each **bold field:** must be on its own separate line
- Never combine multiple pieces of information on the same line
- Always press Enter after each field before starting the next one

Use this EXACT format with proper spacing. Keep the total length under 200 words.

#### **BUSINESS SNAPSHOT**

**What they do:** [ONLY from "about" or "company_overview" - quote exactly or write "Not specified in data"]

**Status:** [ONLY if acquisition data exists - otherwise write "Not specified"]

**Headquarters:** [ONLY if HQ data exists - otherwise write "Not specified"]

**Employee Count:** [ONLY if employee data exists - otherwise write "Not specified"]


#### **RECENT DEVELOPMENTS**

[ONLY list developments that are explicitly mentioned in "news" or "products_and_services" sections. If none exist, write "No recent developments in data"]

- [Actual development from data]

- [Actual development from data]


#### **COMPETITIVE LANDSCAPE**

**Competitors:** [ONLY from "similar_companies" if it exists, otherwise "Not listed in data"]

**Positioning:** [ONLY if explicitly stated, otherwise "Not specified in data"]

**Competitive Edge:** [ONLY if competitive advantages are explicitly mentioned in data]


#### **PRODUCTS & TECH**

**Core Offerings:** [ONLY from actual "products_and_services" data]

**Notable IP:** [ONLY if patents or IP are explicitly mentioned]

**Scale Metrics:** [ONLY actual numbers from the data - employees, products, etc.]


#### **LEADERSHIP & STRATEGY**

**CEO:** [ONLY from "contacts" or "founders" data - name and background if available]

**Other Key Leaders:** [ONLY if explicitly listed in data]

**Strategic Focus:** [ONLY if strategic priorities are explicitly mentioned]


#### **STRATEGIC SIGNALS**

**Momentum Indicators:** [ONLY from actual "bombora" or news data]

VERIFICATION REQUIREMENT: If any field would require speculation or general knowledge not in the data, replace that field with "Insufficient data available."

Data to analyze:
{crunchbase_data}
"""

REDDIT_INSIGHTS_PROMPT = """
You are a strategic analyst reviewing Reddit discussions to extract public sentiment, discussion themes, and meaningful business insight about a company.

CRITICAL ANTI-HALLUCINATION RULES:
- ONLY analyze the actual Reddit content provided in the data
- Do not add information from your general knowledge about the company
- If you cannot identify clear patterns, state "Insufficient discussion data"
- Quote specific examples from the actual Reddit posts when possible
- Do not make assumptions about sentiment without clear evidence in the posts
- If the company is not clearly mentioned, state that explicitly

CRITICAL FORMATTING RULES - FOLLOW EXACTLY:
- Put TWO blank lines between each major section (####)
- Put ONE blank line between each field within a section
- Each **bold field:** must be on its own separate line
- Never combine multiple pieces of information on the same line
- Always press Enter after each field before starting the next one
- Put blank lines between bullet points

Instructions:
- Analyze ONLY the Reddit discussion data provided below
- Identify sentiment and themes based ONLY on actual post content
- The company may or may not be named explicitly - work only with what's actually there
- Ignore off-topic content, memes, jokes, and low-effort posts

Write a structured summary in under 250 words, using this EXACT format with proper spacing:

#### **PUBLIC PERCEPTION**

[Summarize ONLY based on actual sentiment expressed in the provided Reddit posts.]


#### **KEY DISCUSSION THEMES**

[List ONLY themes that actually appear in the provided Reddit data. If insufficient data, write "Limited discussion themes in data"]

- [Actual theme from Reddit posts]

- [Actual theme from Reddit posts]

- [Actual theme from Reddit posts]


#### **STRATEGIC SIGNALS**

[Highlight ONLY signals that are clearly evident in the actual Reddit discussions. No speculation.]

- [Actual signal from posts]

- [Actual signal from posts]

#### **EMERGING KEYWORDS & TRENDS**

[List ONLY terms that actually appear frequently in the provided Reddit data]

- [Actual recurring term from data]

- [Actual recurring term from data]

- [Actual recurring term from data]

VERIFICATION REQUIREMENT: If any section cannot be filled with concrete evidence from the provided Reddit data, write "Insufficient data in posts" for that section.

Reddit data:
{reddit_data}
"""

LINKEDIN_POSTS_INSIGHTS_PROMPT = """
You are a business analyst reviewing the official LinkedIn posts of a company. Your goal is to extract meaningful insights and summarize recent updates.

CRITICAL ANTI-HALLUCINATION RULES:
- ONLY analyze the actual LinkedIn post content provided in the data
- Do not add information from your general knowledge about the company
- Quote actual post content, engagement numbers, and comment text when available
- If engagement data is missing, state "Engagement data not available"
- Do not speculate about company strategy beyond what's explicitly posted
- If insufficient posts are provided, state that clearly

CRITICAL FORMATTING RULES - FOLLOW EXACTLY:
- Put TWO blank lines between each major section (####)
- Put ONE blank line between each field within a section
- Each **bold field:** must be on its own separate line
- Never combine multiple pieces of information on the same line
- Always press Enter after each field before starting the next one
- Put blank lines between bullet points

Your report should include the following sections using this EXACT format with proper spacing:

#### **STRATEGIC UPDATES**

[Describe ONLY announcements, launches, or initiatives that are actually mentioned in the provided LinkedIn posts. If none exist, write "No strategic updates in provided posts"]


#### **TECHNOLOGY & INNOVATION**

[Summarize ONLY technology mentions that actually appear in the provided LinkedIn posts. If none, write "No technology updates in provided posts"]


#### **BRAND POSITIONING & THOUGHT LEADERSHIP**

[Analyze ONLY the actual messaging and themes present in the provided posts. Base analysis only on actual post content and tone.]


#### **COMMUNITY ENGAGEMENT**

**Engagement Metrics:** [Report ONLY actual engagement numbers from the provided data (likes, comments, shares). If this data is not provided, write "Engagement metrics not available in data"]

**General Sentiment:** [Base only on actual comments and reactions provided in the data]


#### **NOTABLE REACTIONS**

[List ONLY actual comments that are provided in the data. If no comments are included, write "No comment data provided"]

- [Actual comment from data]

- [Actual comment from data]

- [Actual comment from data]

VERIFICATION REQUIREMENT: Base all analysis strictly on the provided LinkedIn post data. If any section cannot be filled with actual data, clearly state "Data not available" for that section.

Here is the input data:
{linkedin_posts_data}
"""

LINKEDIN_JOBS_INSIGHTS_PROMPT = """ 
You are a business and talent strategy analyst reviewing LinkedIn job postings for a company. Your task is to extract meaningful hiring signals, growth focus areas, and strategic direction based on the structured job data provided.

CRITICAL ANTI-HALLUCINATION RULES:
- ONLY analyze the actual job posting data provided
- Do not add information from your general knowledge about the company
- Count only actual job postings in the provided data
- If location/department data is missing, state "Not specified in job data"
- Base observations only on patterns visible in the actual job listings
- Do not speculate about company strategy beyond what job titles/descriptions reveal

CRITICAL FORMATTING RULES - FOLLOW EXACTLY:
- Put TWO blank lines between each major section (####)
- Put ONE blank line between each field within a section
- Each **bold field:** must be on its own separate line
- Never combine multiple pieces of information on the same line
- Always press Enter after each field before starting the next one
- Put blank lines between bullet points

Instructions:
- Analyze ONLY the job postings provided in the data
- Count actual roles and identify patterns based on job titles and descriptions in the data
- Focus only on what the actual hiring data reveals

Write a concise summary using this EXACT format with proper spacing. Keep the full response under 200 words.

#### **HIRING OVERVIEW**

[Provide summary based ONLY on the actual number and types of jobs in the provided data. State exact number of open roles if countable. If insufficient data, write "Limited job posting data available"]


#### **TEAM FOCUS AREAS**

[List ONLY departments/functions that actually appear in the provided job data]

- [Actual department from job data]

- [Actual department from job data]

- [Actual department from job data]


#### **GEOGRAPHIC FOCUS**

[Report ONLY locations that actually appear in the provided job posting data. If location data missing, write "Location data not available"]


#### **STRATEGIC OBSERVATIONS**

[Base ONLY on actual patterns visible in the job titles and descriptions provided]

**Technical Roles:** [Count/pattern from actual job data]

**Business Roles:** [Count/pattern from actual job data]

**Other Patterns:** [Only if clearly evident in data]

VERIFICATION REQUIREMENT: If any section cannot be filled with concrete data from the job postings, write "Insufficient job data" for that section.

LinkedIn jobs data:
{linkedin_jobs_data}
"""

TWITTER_INSIGHTS_PROMPT = """
You are a strategic communications analyst reviewing recent Twitter/X posts from a company account. Your goal is to extract key messaging patterns, engagement signals, and business-relevant insights from the data.

CRITICAL ANTI-HALLUCINATION RULES:
- ONLY analyze the actual Twitter/X posts provided in the data
- Do not add information from your general knowledge about the company
- Quote actual engagement numbers (likes, retweets, replies) from the provided data
- If engagement metrics are missing, state "Engagement data not available"
- Base content analysis only on actual tweet text provided
- Do not speculate about strategy beyond what's evident in the actual posts

CRITICAL FORMATTING RULES - FOLLOW EXACTLY:
- Put TWO blank lines between each major section (####)
- Put ONE blank line between each field within a section
- Each **bold field:** must be on its own separate line
- Never combine multiple pieces of information on the same line
- Always press Enter after each field before starting the next one
- Put blank lines between bullet points

Instructions:
- Analyze ONLY the Twitter/X post data provided below
- Base all observations on actual post content, dates, and engagement metrics in the data
- If the company account is not clearly identified, state that

Write a short, structured narrative summary in under 200 words using this EXACT format with proper spacing:

#### **MESSAGING FOCUS**

[Summarize ONLY themes and topics that actually appear in the provided Twitter posts. If insufficient posts, write "Limited posting activity in data"]


#### **CONTENT CATEGORIES**

[List ONLY content types that actually appear in the provided data]

- [Actual content type from posts]

- [Actual content type from posts]

- [Actual content type from posts]


#### **AUDIENCE ENGAGEMENT**

**Overall Engagement:** [Report ONLY actual engagement numbers from the provided data. If metrics missing, write "Engagement metrics not provided in data"]

**Top Performing Post:** [Actual post with highest engagement if data available, otherwise write "Top post data not available"]


#### **STRATEGIC SIGNALS**

[Identify ONLY patterns clearly evident in the actual post content and timing]

**Posting Frequency:** [Based on actual dates in data]

**Content Focus:** [Based on actual post themes]

**Engagement Pattern:** [Based on actual metrics if available]

VERIFICATION REQUIREMENT: If any section cannot be filled with concrete evidence from the provided Twitter data, write "Insufficient data in posts" for that section.

Twitter/X post data:
{twitter_data}
"""

def load_json_data(file_path: str) -> dict:
    """Load JSON data from file with error handling."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        st.error(f"Error loading {file_path}: {e}")
        return {}


def load_text_data(file_path: str) -> str:
    """Load text data from file with error handling."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = f.read()
        return data
    except Exception as e:
        st.error(f"Error loading {file_path}: {e}")
        return ""


def format_ai_output(text: str) -> str:
    """Post-process AI output to ensure proper formatting with enhanced error handling."""
    if not text or not isinstance(text, str):
        return "WARNING: Invalid or empty response from AI"

    try:
        lines = text.split("\n")
        formatted_lines = []

        for i, line in enumerate(lines):
            line = line.strip()

            if not line:
                formatted_lines.append("")
                continue

            if line.startswith("## "):
                if formatted_lines and formatted_lines[-1] != "":
                    formatted_lines.append("")
                formatted_lines.append(line)
                formatted_lines.append("")
                continue

            if line.startswith("**") and ":" in line:
                formatted_lines.append(line)
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if (
                        next_line
                        and not next_line.startswith("**")
                        and not next_line.startswith("##")
                    ):
                        formatted_lines.append("")
                continue

            if line.startswith("- "):
                formatted_lines.append(line)
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not next_line.startswith("- "):
                        formatted_lines.append("")
                continue

            formatted_lines.append(line)

        cleaned_lines = []
        blank_count = 0

        for line in formatted_lines:
            if line == "":
                blank_count += 1
                if blank_count <= 2:
                    cleaned_lines.append(line)
            else:
                blank_count = 0
                cleaned_lines.append(line)

        while cleaned_lines and cleaned_lines[-1] == "":
            cleaned_lines.pop()

        formatted_output = "\n".join(cleaned_lines)

        if len(formatted_output.strip()) < 10:
            return (
                "WARNING: AI response was too short or contained no meaningful content"
            )

        return formatted_output

    except Exception as e:
        return f"WARNING: Error formatting AI response: {str(e)}\n\nOriginal response:\n{text}"


def truncate_large_data(data: str, max_chars: int = 150000) -> str:
    """Truncate data intelligently while preserving structure."""
    if len(data) <= max_chars:
        return data

    try:
        parsed_data = json.loads(data)

        if isinstance(parsed_data, list):
            truncated_list = []
            current_size = 50

            for item in parsed_data:
                item_json = json.dumps(item, indent=2)
                if current_size + len(item_json) > max_chars:
                    break
                truncated_list.append(item)
                current_size += len(item_json)

            result = json.dumps(truncated_list, indent=2)
            if len(result) < len(data):
                result += f"\n\n[NOTE: Data truncated - showing {len(truncated_list)} of {len(parsed_data)} total entries]"
            return result

        elif isinstance(parsed_data, dict):
            truncated_dict = {}
            current_size = 50

            for key, value in parsed_data.items():
                if isinstance(value, str) and len(value) > 10000:
                    truncated_dict[key] = value[:5000] + "...[truncated]"
                else:
                    truncated_dict[key] = value

                current_size += len(json.dumps({key: truncated_dict[key]}))
                if current_size > max_chars:
                    truncated_dict[key] = "[truncated - too large]"
                    break

            result = json.dumps(truncated_dict, indent=2)
            if len(result) < len(data):
                result += "\n\n[NOTE: Data truncated due to size]"
            return result

    except json.JSONDecodeError:
        truncated = data[:max_chars]
        truncated += "\n\n[NOTE: Data truncated due to size - showing first portion]"
        return truncated

    return data[:max_chars] + "\n\n[NOTE: Data truncated due to size]"

def get_ai_insights(data: str, prompt_template: str, api_key: str) -> str:
    """Get AI insights using NEW Google GenAI SDK."""
    
    try:
        config = TrendScanConfig.load()
        model_name = config.llm.model.replace("gemini/", "") if config.llm.model.startswith("gemini/") else config.llm.model
        temperature = config.llm.temperature
    except:
        model_name = "gemini-2.0-flash-001"
        temperature = 0.0

    if not data or not api_key:
        return "WARNING: No data or API key provided"

    data = truncate_large_data(data, max_chars=100000)

    try:
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=api_key)
        
        prompt = prompt_template.format(
            crunchbase_data=data,
            reddit_data=data,
            linkedin_posts_data=data,
            linkedin_jobs_data=data,
            twitter_data=data,
        )

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=2048,
            )
        )

        # Extract text safely
        if hasattr(response, 'text') and response.text:
            return format_ai_output(response.text)
        elif hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                if hasattr(candidate.content, 'parts') and candidate.content.parts:
                    text_parts = []
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            text_parts.append(part.text)
                    if text_parts:
                        return format_ai_output("".join(text_parts))
        
        return "WARNING: AI model returned empty response"

    except Exception as e:
        return f"ERROR: {str(e)}"
    
def create_basic_summary(data, data_type: str) -> str:
    """Create basic summary without AI analysis."""
    if data_type == "json":
        if isinstance(data, dict):
            return f"""#### **Data Summary (No AI)**

**Data type:** Dictionary with {len(data)} fields

**Sample fields:** {list(data.keys())[:5]}"""
        elif isinstance(data, list):
            return f"""#### **Data Summary (No AI)**

**Data type:** List with {len(data)} items"""
        else:
            return f"""#### **Data Summary (No AI)**

**Data type:** {type(data).__name__}"""
    else:
        lines = data.split("\n") if data else []
        words = data.split() if data else []
        return f"""#### **Data Summary (No AI)**

**Lines:** {len(lines)}

**Words:** {len(words)}

**Characters:** {len(data)}"""


def run_trendscan(company_name: str) -> tuple[bool, str]:
    """Execute TrendScan for the given company."""
    try:
        result = subprocess.run(
            [sys.executable, "trendscan.py", company_name],
            capture_output=True,
            text=True,
            timeout=1000,
        )

        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, "TrendScan execution timed out after 5 minutes"
    except Exception as e:
        return False, f"Error running TrendScan: {str(e)}"


def find_output_directory(company_name: str) -> str:
    """Find the most recent output directory for the company."""
    output_base = Path("output")
    if not output_base.exists():
        return ""

    company_dirs = [
        d
        for d in output_base.iterdir()
        if d.is_dir() and company_name.lower().replace(" ", "_") in d.name.lower()
    ]

    if company_dirs:
        return str(sorted(company_dirs, key=lambda x: x.stat().st_mtime)[-1])

    return ""


def main():
    """Main application function."""
    st.title("TrendScan")
    st.markdown("Multi-Source Company Intelligence Platform")

    company_name = st.text_input(
        "***Enter Company Name**",
        placeholder="e.g., OpenAI, Google DeepMind, Anthropic",
        help="Enter the name of the company you want to analyze",
    )

    st.markdown(
        """
    <style>
    .stButton > button {
        background-color: #0066cc;
        color: white;
        border: none;
        border-radius: 5px;
        padding: 0.5rem 1rem;
        font-weight: bold;
    }
    .stButton > button:hover {
        background-color: #0052a3;
        color: white;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )

    run_scan = st.button("Start TrendScan", type="primary")

    if run_scan and company_name:
        with st.spinner("Running TrendScan... This may take a few minutes."):
            success, output = run_trendscan(company_name)

        if success:
            success_placeholder = st.empty()
            success_placeholder.success("TrendScan completed successfully!")

            time.sleep(10)
            success_placeholder.empty()

            output_dir = find_output_directory(company_name)
            if output_dir:
                st.session_state["output_dir"] = output_dir
                st.session_state["analysis_ready"] = True
            else:
                st.error("Could not find output directory")
        else:
            st.error("TrendScan failed. Please check your configuration and try again.")

            with st.expander("View detailed error (for debugging)"):
                st.text(output)

    if st.session_state.get("analysis_ready", False) and st.session_state.get(
        "output_dir"
    ):
        output_dir = Path(st.session_state["output_dir"])

        try:
            config = TrendScanConfig.load()
            api_key = config.api_keys.gemini
        except:
            api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            api_key = st.text_input(
                "Gemini API Key (Optional for AI analysis)",
                type="password", 
                help="Enter your Google Gemini API key for AI insights. Leave empty for basic summaries.",
            )
        file_mappings = {
            "Crunchbase Profile": {
                "file": f"{company_name.lower().replace(' ', '_')}_crunchbase_profile.json",
                "prompt": CRUNCHBASE_INSIGHTS_PROMPT,
                "type": "json",
            },
            "Reddit Discussions": {
                "file": f"{company_name.lower().replace(' ', '_')}_reddit_discussions.txt",
                "prompt": REDDIT_INSIGHTS_PROMPT,
                "type": "text",
            },
            "LinkedIn Posts": {
                "file": f"{company_name.lower().replace(' ', '_')}_linkedin_posts.json",
                "prompt": LINKEDIN_POSTS_INSIGHTS_PROMPT,
                "type": "json",
            },
            "LinkedIn Jobs": {
                "file": f"{company_name.lower().replace(' ', '_')}_linkedin_jobs.json",
                "prompt": LINKEDIN_JOBS_INSIGHTS_PROMPT,
                "type": "json",
            },
            "Twitter Posts": {
                "file": f"{company_name.lower().replace(' ', '_')}_twitter_posts.json",
                "prompt": TWITTER_INSIGHTS_PROMPT,
                "type": "json",
            },
        }

        tabs = st.tabs(list(file_mappings.keys()))

        for i, (tab_name, config) in enumerate(file_mappings.items()):
            with tabs[i]:
                file_path = output_dir / config["file"]

                if file_path.exists():
                    if config["type"] == "json":
                        data = load_json_data(str(file_path))

                        if (
                            config["file"].endswith("linkedin_jobs.json")
                            and isinstance(data, dict)
                            and "data" in data
                        ):
                            jobs_list = data.get("data", [])
                            sample = jobs_list[:10]
                            data_str = json.dumps(sample, indent=2)
                        else:
                            data_str = json.dumps(data, indent=2) if data else ""

                    else:
                        data_str = load_text_data(str(file_path))
                        data = data_str

                    if data:
                        if api_key and data_str:
                            with st.spinner("Analyzing..."):
                                insights = get_ai_insights(
                                    data_str, config["prompt"], api_key
                                )

                            if (
                                "N/A" in insights
                                or "no public posts" in insights.lower()
                                or "inactive" in insights.lower()
                            ):
                                st.warning(
                                    "No recent activity found for this data source."
                                )
                            else:
                                st.markdown(insights)
                        else:
                            summary = create_basic_summary(data, config["type"])
                            st.markdown(summary)

                        with st.expander("View Raw Data"):
                            if config["type"] == "json":
                                st.json(data)
                            else:
                                st.text(
                                    data_str[:5000] + "..."
                                    if len(data_str) > 5000
                                    else data_str
                                )
                    else:
                        st.warning("No data available for this source.")
                else:
                    st.warning("Data not available for this source.")


if __name__ == "__main__":
    main()
