# sp500_stock_evaluator_backend

## Overview

This backend exposes a RESTful API for evaluating S&P 500 stocks using fundamental analysis with yfinance. It returns buy/hold/sell recommendations, financial indicator breakdowns, and scoring for each ticker.

Built with [FastAPI](https://fastapi.tiangolo.com/).

## Key Endpoints

- `GET /stocks`: Returns a list of S&P 500 stocks with summary recommendation and scores.
    - Query parameter: `limit` (int, optional, default 50)
- `GET /stocks/{ticker}`: Returns detailed metrics, indicator breakdown, and scoring for a specific ticker.

## Quick Start

1. **Install dependencies:**
    ```
    pip install -r requirements.txt
    ```

2. **Run development server:**
    ```
    uvicorn main:app --reload
    ```

3. **Interact with the API:**
    - Open [http://localhost:8000/docs](http://localhost:8000/docs) for interactive OpenAPI UI.
    - Use `/stocks` and `/stocks/{ticker}` to fetch data.

## API Response Format

- All responses are JSON.
- Recommendations include 'BUY', 'HOLD', or 'SELL'.
- The indicator `breakdown` field shows individual P/E, profit margin, debt/equity, ROE, dividend yield, and current ratio values.

## Notes

- The backend fetches S&P 500 ticker list from Wikipedia on demand.
- Stock data is fetched live using `yfinance`, so the initial loading may take time.
- Endpoints are documented via Swagger/OpenAPI at `/docs`.
