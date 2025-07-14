# TrendScan 🔍
Multi‑source company intelligence platform – automated collection and AI‑powered analysis of company data from Crunchbase, LinkedIn, Reddit, and Twitter/X.

<img src="https://github.com/triposat/trendscan/blob/6e601160eef7759a26ba39751a495b3ce139ff81/assets/trendscan.gif" width="800" alt="Achitecture Diagram" />

## How it works
<img src="https://github.com/triposat/trendscan/blob/main/assets/trendscan-flowchart.png" width="800" alt="Achitecture Diagram" />


1. **Initiate** data-retrieval tasks via specialized CrewAI agents.
2. **Orchestrate** API calls and dynamic web scraping with Bright Data MCP, handling JavaScript rendering, proxy rotation, rate limiting, and CAPTCHA bypass,
3. **Normalize** and store retrieved data before forwarding it to Gemini AI for analysis,
4. **Display** real-time results and insights in the Streamlit dashboard,

## Technical stack
- **Language** – Python 3
- **Orchestration** – [CrewAI](https://github.com/crewAIInc/crewAI) multi‑agent framework
- **Protocol** – [Model Context Protocol (MCP)](https://modelcontextprotocol.io/introduction)
- **Scraping** – [Bright Data MCP](https://github.com/brightdata/brightdata-mcp) and [Web Scraper APIs](https://brightdata.com/products/web-scraper).
- **AI** – [Google Gemini models](https://ai.google.dev/gemini-api/docs/models)
- **Dashboard** – [Streamlit](https://streamlit.io/)

## Data sources
| Source | Data type | Content | Integration |
| --- | --- | --- | --- |
| Crunchbase | Company profiles | Funding, team, metrics, news | 100% MCP |
| LinkedIn | Professional data | Jobs, updates | Hybrid (MCP + API) |
| Reddit | Public sentiment | Discussions, opinions, reviews | 100% MCP |
| Twitter/X | Social media | Posts, engagement, trends | Hybrid (MCP + API) |


## Prerequisites
- [Python 3](https://www.python.org/downloads/) and [Node.js](https://nodejs.org/en/download) installed.
- [Bright Data](https://brightdata.com/) account with [API key access](https://docs.brightdata.com/api-reference/authentication) Also make sure to create [Web Unlocker](https://docs.brightdata.com/scraping-automation/web-unlocker/quickstart) and [Browser API](https://docs.brightdata.com/scraping-automation/scraping-browser/quickstart) zones.
- [Gemini API access](https://aistudio.google.com/u/0/apikey).

## Installation

```bash
# Clone the repo
git clone https://github.com/triposat/trendscan.git
cd trendscan

# Create and activate Python virtual environment
uv venv

# Install dependencies
uv pip install -r requirements.txt
```

## Configuration
1. Open the `.env` file in your project’s root directory.
2. Replace each placeholder with your real credentials:
3. (Optional) If you’d like to use a different AI model, set the `LLM_MODEL` variable to one of the available Gemini models. See the [Gemini Models documentation](https://ai.google.dev/gemini-api/docs/models) for the full list.


## Usage
Launch the Streamlit web interface with the following command:

```bash
streamlit run streamlit_trendscan.py
```
