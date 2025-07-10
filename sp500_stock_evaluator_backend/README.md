# S&P 500 Stock Evaluator Backend

This backend provides RESTful APIs to analyze S&P 500 stocks using key financial indicators and serve buy/hold/sell recommendations.

## Features

- Analyze all current S&P 500 stocks using yfinance and indicator heuristics
- Recommendation and indicator breakdown (PE, PB, Dividend Yield, Debt/Equity, Current Ratio, Margin, ROE)
- `/stocks` endpoint:
  - List, filter, sort, and search S&P 500 recommendations
- `/stocks/{ticker}`:
  - Get analysis for a specific ticker

## Running

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

API docs available at `/docs` (Swagger UI).

---

This backend is intended for use with the S&P 500 Stock Evaluator React frontend.
