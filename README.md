# TrendScan 🔍

**Multi‑source company intelligence platform** – automated collection and AI‑powered analysis of company data from Crunchbase, LinkedIn, and Reddit.

<img src="https://github.com/brightdata/trendscan/blob/6e601160eef7759a26ba39751a495b3ce139ff81/assets/trendscan.gif" width="800" alt="TrendScan Dashboard Demo" />

---

## Features

- Aggregates company and social data from Crunchbase, LinkedIn, and Reddit.
- Automates web scraping via CrewAI agents and Bright Data MCP (handles JS rendering, proxy rotation, and CAPTCHAs)
- AI-powered analysis and insight generation with Gemini models
- Real-time visualization in a [Streamlit](https://streamlit.io/) dashboard
- Modular architecture for easy addition of new data sources or workflows

---

## How it works

<img src="https://github.com/brightdata/trendscan/blob/main/assets/trendscan-flowchart.png" width="800" alt="Architecture Diagram" />

1. **Initiate:** Data-retrieval with specialized CrewAI agents.
2. **Orchestrate:** API calls & dynamic scraping with Bright Data MCP – handles JS, proxies, rate limiting, CAPTCHA, more.
3. **Normalize:** Store and send data to Gemini AI for instant analysis.
4. **Display:** Results and actionable insights in Streamlit dashboard.

---

## Technical Stack

- **Language:** Python 3
- **Orchestration:** [CrewAI](https://github.com/crewAIInc/crewAI) multi‑agent framework
- **Protocol:** [Model Context Protocol (MCP)](https://modelcontextprotocol.io/introduction)
- **Scraping:** [Bright Data MCP](https://github.com/brightdata/brightdata-mcp) & [Web Scraper APIs](https://brightdata.com/products/web-scraper)
- **AI:** [Google Gemini models](https://ai.google.dev/gemini-api/docs/models)
- **Dashboard:** [Streamlit](https://streamlit.io/)

---

## Data Sources

| Source      | Data type           | Content                          | Integration         |
|-------------|---------------------|----------------------------------|---------------------|
| Crunchbase  | Company profiles    | Funding, team, metrics, news     | 100% MCP            |
| LinkedIn    | Professional data   | Jobs, updates                    | Hybrid (MCP + API)  |
| Reddit      | Public sentiment    | Discussions, opinions, reviews   | 100% MCP            |


---

## Use Cases

- Competitive intelligence & company research  
- Market trend analysis  
- Real-time sentiment & topic monitoring  
- Investment/M&A targeting  
- Multi-source data discovery for analysts

---

## Prerequisites

- [Python 3](https://www.python.org/downloads/) & [Node.js](https://nodejs.org/en/download)  
- [Bright Data account](https://brightdata.com/) with [API key](https://docs.brightdata.com/api-reference/authentication)  
    - PLUS [Web Unlocker](https://docs.brightdata.com/scraping-automation/web-unlocker/quickstart) and [Browser API](https://docs.brightdata.com/scraping-automation/scraping-browser/quickstart) zones  
- [Gemini API access](https://aistudio.google.com/u/0/apikey)

---

## Installation

```bash
# Clone the repo
git clone https://github.com/brightdata/trendscan.git
cd trendscan

# Create and activate Python virtual environment
uv venv

# Install dependencies
uv pip install -r requirements.txt
```

---

## Configuration

1. Open the `.env` file in your project’s root directory.
2. Fill in your real credentials and API keys.
3. *(Optional)* To use a different Gemini model, set `LLM_MODEL` in `.env`.
   See [Gemini model docs](https://ai.google.dev/gemini-api/docs/models).

**.env Variables (example):**
| Variable                | Description                   |
|-------------------------|-------------------------------|
| BRIGHT_DATA_API_KEY     | Your Bright Data API Key      |
| GEMINI_API_KEY          | Your Gemini API Key           |
| ...                     | ...                           |


---

## Usage

Launch the Streamlit web interface with:

```bash
streamlit run streamlit_trendscan.py
```

You’ll be able to initiate data retrieval, run the pipeline, and interact with the dashboard in your browser.

---

## Contributing

PRs, feedback, and feature suggestions are welcome!  
- [Open an issue](https://github.com/brightdata/trendscan/issues) for bugs and improvements.
- For large contributions, please open a discussion first.

---

## License

Distributed under the MIT License.

---

**Have fun scanning trends and supercharging company intelligence!**
