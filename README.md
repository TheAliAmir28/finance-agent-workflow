# Finance Agent Workflow

A friendly finance analysis app that turns plain-English stock requests into charts, metrics, dashboards, reports, and optional AI-generated summaries.

Type something like:

```text
Analyze AAPL and NVDA for 1 year with summary
```

The app fetches market data, calculates performance metrics, creates visualizations, and gives you a clean report you can actually read.

![Dashboard demo](assets/dashboard-demo.png.png)

---

## What It Does

Finance Agent Workflow helps automate a small equity research workflow from end to end:

- Parses natural-language analysis requests
- Fetches historical stock price data
- Calculates total return, volatility, and Sharpe ratio
- Generates price charts and normalized comparison charts
- Builds a local HTML dashboard
- Saves structured run history
- Produces a readable text report
- Optionally creates an AI summary using the OpenAI API

It works without an API key. AI summaries are optional and fail safely.

---

## Live App

This project was deployed with AWS Elastic Beanstalk.

If the hosted environment is currently running, the app can be opened from the Elastic Beanstalk environment URL.

```text
Live demo available upon request.
```

---

## Example Prompts

```text
Analyze AAPL for 1 year
Analyze AAPL and NVDA for 1 year
Analyze TSLA for 3 months no summary
Analyze MSFT and GOOGL for 6 months with summary
```

The app currently supports one or two tickers per request.

---

## Features

### Web Interface

- Polished Flask web UI
- Example prompt buttons
- Metrics overview cards
- Chart gallery
- AI summary cards
- Collapsible generated dashboard preview
- Recent run history
- Mobile-responsive styling

### Analysis Pipeline

- Natural-language planner
- Agent-style task execution
- Shared memory store
- Modular tools for data, metrics, charts, reports, and summaries
- Graceful error handling for bad prompts, invalid tickers, and missing AI credentials

### Generated Outputs

The app creates:

- `output/charts/` - chart images
- `output/dashboard/index.html` - generated dashboard
- `output/history/` - saved run history
- `reports/generated/` - text reports

Generated files are ignored by Git so the repository stays clean.

---

## Tech Stack

- **Python**
- **Flask**
- **Pandas**
- **NumPy**
- **Matplotlib**
- **yFinance**
- **OpenAI API**
- **Gunicorn**
- **AWS Elastic Beanstalk**
- **HTML/CSS**

---

## Project Structure

```text
finance-agent-workflow/
├── app.py                 # Flask web app
├── main.py                # Main analysis pipeline
├── planner.py             # Parses user requests into tasks
├── agent.py               # Executes analysis tasks
├── history.py             # Saves and loads recent runs
├── requirements.txt       # Python dependencies
├── Procfile               # Production start command for AWS
├── templates/
│   └── index.html         # Web UI
├── memory/
│   └── store.py           # Shared in-memory data store
├── tools/
│   ├── data_fetch.py      # Market data retrieval
│   ├── metrics.py         # Return, volatility, Sharpe calculations
│   ├── charts.py          # Chart generation
│   └── llm_client.py      # Optional AI summary integration
├── reports/
│   ├── dashboard.py       # HTML dashboard builder
│   └── synthesizer.py     # Text report generator
└── assets/
    └── dashboard-demo.png.png
```

---

## Getting Started

### 1. Clone The Repository

```bash
git clone https://github.com/TheAliAmir28/finance-agent-workflow.git
cd finance-agent-workflow
```

### 2. Create A Virtual Environment

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run The Web App

```bash
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

---

## CLI Usage

You can also run the analysis from the terminal:

```bash
python main.py
```

Then enter a prompt when asked.

---

## Optional AI Summaries

AI summaries use the OpenAI API. The app still works normally without an API key.

To enable AI summaries, set:

```bash
OPENAI_API_KEY=your_api_key_here
```

Windows PowerShell:

```powershell
setx OPENAI_API_KEY "your_api_key_here"
```

Then restart your terminal.

Use prompts like:

```text
Analyze AAPL and NVDA for 1 year with summary
```

To disable AI summaries:

```text
Analyze AAPL and NVDA for 1 year no summary
```

---

## AWS Deployment

This project includes basic Elastic Beanstalk deployment files:

- `Procfile`
- `.ebignore`
- `requirements.txt`

The production command is:

```text
web: gunicorn --bind :8000 app:app
```

Typical deployment flow:

```bash
eb init
eb create finance-agent-workflow-prod --single
eb open
```

To deploy updates:

```bash
eb deploy
```

To shut down the environment and stop AWS resource usage:

```bash
eb terminate finance-agent-workflow-prod
```

---

## Safety Notes

- This project is for learning, demonstration, and research workflow automation.
- It is not financial advice.
- Past performance does not predict future results.
- AI summaries are optional and should be treated as explanatory text, not investment recommendations.
- API keys and credentials should never be committed to GitHub.

---

## Why I Built This

I built this project to practice combining data engineering, automation, financial analysis, AI integration, web development, and cloud deployment in one complete workflow.

The goal was not just to make a stock chart. The goal was to build a small but realistic system that takes a human request, plans the work, executes the analysis, saves artifacts, and presents the result in a clean interface.

---

## Future Improvements

- Support more than two tickers
- Add portfolio-level analytics
- Add user-selectable risk-free rate
- Add more financial metrics
- Add tests and CI
- Add authentication for hosted deployments
- Store generated runs in a database or S3
- Add custom date ranges

---

## License

MIT License

