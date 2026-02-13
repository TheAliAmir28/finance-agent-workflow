Finance Agent Workflow

A simple, end-to-end stock analysis tool that turns plain English requests into real insights.

You type a request in plain English, and the program does the rest.

Examples:
- Analyze AAPL for 1y
- Analyze AAPL and NVDA for 1y
- Analyze AAPL for 6 months with summary
- Analyze AAPL and NVDA for 1y no summary

The tool fetches real stock data, calculates useful metrics, creates charts, builds an HTML dashboard, and generates a readable text report.  
It can also optionally use an AI model to write a short summary.

The goal of this project is to turn raw market data into clear, easy-to-understand results without overcomplicating things.


What this project does

For each stock:
- pulls historical price data
- calculates:
  - total return
  - volatility
  - Sharpe ratio
- creates a price chart

For two stocks:
- compares performance and risk
- determines which stock performed better on a risk-adjusted basis
- creates a normalized comparison chart

Outputs:
- text reports saved to reports/generated/
- an HTML dashboard saved to output/dashboard/index.html
- chart images saved to output/charts/


Optional AI summary mode

This project supports an optional AI-generated summary using the OpenAI API.

Important points:
- AI summaries are optional
- the program works fully without an API key
- users control AI usage with simple phrases
- if the AI is disabled or fails, the program falls back to a normal summary

Examples:
- "with summary" turns AI summaries on
- "no summary" turns AI summaries off

The AI only receives clean numeric data (metrics and prices).  
It does not see raw datasets or user files.


How to run the project

1) Install dependencies

pip install -r requirements.txt


2) Optional: set OpenAI API key

Only needed if you want AI summaries.

On Windows (PowerShell):

setx OPENAI_API_KEY "your_api_key_here"

Restart the terminal after setting it.


3) Run the program

python main.py

Then enter a request like:

Analyze AAPL for 1y

or

Analyze AAPL and NVDA for 1y with summary


Project structure (high level)

main.py
- Entry point of the program

planner.py
- Parses the user request and builds a task plan

agent.py
- Executes tasks (fetch data, compute metrics, build charts)

memory/
- Shared in-memory store used across the pipeline

tools/
- data_fetch.py: fetches stock data
- metrics.py: calculates returns, volatility, Sharpe ratio
- charts.py: creates chart images
- llm_client.py: optional AI summary logic

reports/
- synthesizer.py: builds readable text reports
- dashboard.py: builds the HTML dashboard


Why this project exists

This project focuses on:
- clean separation of responsibilities
- safe use of external APIs
- readable output for humans
- realistic error handling
- optional AI integration done responsibly

It is meant to feel like a small real system, not a toy script.


Notes

- This project is for learning and demonstration purposes.
- Generated summaries are not financial advice.
- Past performance does not predict future results.
