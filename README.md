# Finance Agent Workflow

Turn a plain-English finance request into automated market analysis.

This project takes a natural language request like:

> "Compare AAPL vs MSFT over the last year and summarize the risk and return."

And automatically generates:
- Historical price data
- Normalized comparison charts
- Key financial metrics (total return, volatility, Sharpe ratio)
- A clean HTML dashboard
- A structured text report
- Optional AI-generated summary (fully optional, works without API key)

---

## What This Project Demonstrates

- Data retrieval from financial APIs
- Risk and return metric computation
- Data visualization
- Modular architecture (planner → agent → tools → reports)
- Optional LLM integration with safe fallback
- End-to-end automation from input to report

---

## Features

- Pulls historical stock price data
- Computes:
  - Total Return
  - Annualized Volatility
  - Sharpe Ratio
- Generates:
  - Price charts
  - Normalized performance charts
  - HTML dashboard
  - Text report
- Optional AI summary mode
  - Works without API key
  - Graceful fallback if AI fails
  - AI only receives clean numeric summaries

---

## Quickstart

### 1. Create a virtual environment

```bash
python -m venv .venv
```

Windows:
```bash
.venv\Scripts\activate
```

Mac/Linux:
```bash
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the program

```bash
python main.py
```

Then enter a natural-language request when prompted.

---

## Example Prompt

```
Compare NVDA and AMZN over the last year and summarize which had better risk-adjusted returns.
```

---

## Output

The project generates:

- `/output/` → Reports and dashboards
- `/data/` → Downloaded market data
- Charts saved as image files
- A structured summary report
- Optional AI explanation (if enabled)

---

## Project Structure

```
finance-agent-workflow/
│
├── main.py
├── agent/
├── tools/
├── reports/
├── output/
├── data/
└── requirements.txt
```

---

## Architecture Overview

1. User enters plain-English request  
2. Planner interprets the task  
3. Tools fetch and compute financial metrics  
4. Reports module generates dashboard + text report  
5. Optional AI module produces a summary explanation  

The system is modular and extendable.

---

## Why This Project Matters

This project demonstrates:

- Applied financial analysis
- Clean modular design
- Automation of multi-step workflows
- Practical LLM integration
- Real-world data handling

It simulates how an intelligent finance assistant could automate equity research tasks.

---

## Future Improvements

- CLI interface (run directly with command arguments)
- Caching for faster repeated requests
- Configurable risk-free rate
- Additional financial metrics
- Unit testing + CI pipeline
- Portfolio analytics expansion

---

## License

MIT License
