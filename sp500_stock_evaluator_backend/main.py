"""
Main FastAPI app to serve S&P 500 stock analysis and recommendations.
- /stocks [GET]: Returns table view of S&P 500 stocks with aggregated indicators and recommendations.
- /stocks/{ticker} [GET]: Returns detailed breakdown for a single stock.

Start with: python main.py

Depends on yfinance for data, FastAPI for the REST API.
"""

import os
import uvicorn
import yfinance as yf
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel, Field

# --- Load S&P 500 Tickers ---

def load_sp500_tickers():
    """
    Loads the S&P 500 tickers from a static file or dynamic source.
    Returns a list of ticker symbols (str).
    """
    static_file = os.path.join(os.path.dirname(__file__), "sample_sp500_tickers.txt")
    tickers = []

    # Attempt to use static file
    if os.path.exists(static_file):
        with open(static_file) as f:
            for line in f:
                sym = line.strip().upper()
                if sym and sym not in tickers:
                    tickers.append(sym)

    # If less than 100 tickers loaded, try fetching from Wikipedia (fallback)
    if len(tickers) < 100:
        # Minimal requirement: install 'requests' already in requirements.txt
        import requests
        import pandas as pd
        try:
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            tables = pd.read_html(requests.get(url).text)
            df = tables[0]
            if "Symbol" in df.columns:
                symbols = df["Symbol"].tolist()
                # Sometimes Wikipedia may use "." instead of "-" for tickers (e.g., BRK.B)
                tickers = [sym.replace(".", "-").upper() for sym in symbols if isinstance(sym, str)]
        except Exception:
            # Fallback to bundled short list
            if not tickers:
                tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "JPM", "V", "UNH"]
    return tickers

SP500_TICKERS = load_sp500_tickers()

# --- Models ---

class IndicatorBreakdown(BaseModel):
    pe_ratio: Optional[float] = Field(None, description="Price to Earnings Ratio")
    price_to_book: Optional[float] = Field(None, description="Price to Book Ratio")
    debt_to_equity: Optional[float] = Field(None, description="Debt to Equity Ratio")
    return_on_equity: Optional[float] = Field(None, description="Return on Equity (%)")
    profit_margin: Optional[float] = Field(None, description="Profit Margin (%)")
    # Add more indicators as needed

class StockSummary(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol")
    short_name: Optional[str] = Field(None, description="Company name")
    sector: Optional[str] = Field(None, description="Company sector")
    recommendation: str = Field(..., description="System recommendation: BUY/HOLD/SELL")
    indicator_score: float = Field(..., description="Aggregated indicator score, 0-100")
    indicators: IndicatorBreakdown

class StockDetail(StockSummary):
    description: Optional[str] = Field(None, description="Business summary")
    history: Optional[list] = Field(None, description="Historical price/indicator series")  # For future/expansion

# --- FastAPI App Setup ---

app = FastAPI(
    title="S&P 500 Stock Evaluator Backend API",
    description="RESTful API for analyzing S&P 500 stocks with indicator-based BUY/HOLD/SELL recommendations.",
    version="1.0.0",
    openapi_tags=[
        {
            "name": "Stocks",
            "description": "Endpoints returning table and detail data for S&P 500 stocks."
        },
        {
            "name": "System",
            "description": "API health and system status."
        }
    ]
)

# Allow frontend to request from different origin (for development use)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in prod!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Core Logic ---

def fetch_yf_info(ticker: str):
    """
    Fetches yfinance info dictionary for a ticker. Returns (info, error_message)
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return info, None
    except Exception as e:
        return None, f"Error retrieving {ticker}: {str(e)}"

def score_indicators(info: dict) -> (IndicatorBreakdown, float, str):
    """
    Scores the stock's health based on basic indicators and returns
    (IndicatorBreakdown, aggregate_score, recommendation)
    """
    # Fetch indicators safely
    try:
        pe = info.get("trailingPE")
        pb = info.get("priceToBook")
        debt = info.get("debtToEquity")
        roe = info.get("returnOnEquity")  # As fraction, e.g., 0.21 for 21%
        pm = info.get("profitMargins")    # As fraction, e.g., 0.08 for 8%
    except Exception:
        pe, pb, debt, roe, pm = None, None, None, None, None

    # Score logic (simple, for demo purposes. Refine as required.)
    score = 0
    max_score = 5

    if pe is not None:
        if pe < 15: score += 1
        elif pe < 25: score += 0.5
    if pb is not None and pb < 3: score += 1
    if debt is not None and debt < 1: score += 1
    if roe is not None and roe > 0.1: score += 1
    if pm is not None and pm > 0.1: score += 1

    norm_score = (score / max_score) * 100
    if norm_score >= 80:
        reco = "BUY"
    elif norm_score >= 60:
        reco = "HOLD"
    else:
        reco = "SELL"

    indi = IndicatorBreakdown(
        pe_ratio=pe,
        price_to_book=pb,
        debt_to_equity=debt,
        return_on_equity=roe * 100 if roe is not None else None,
        profit_margin=pm * 100 if pm is not None else None
    )
    return indi, norm_score, reco

# --- API Endpoints ---

# PUBLIC_INTERFACE
@app.get(
    "/stocks",
    response_model=List[StockSummary],
    tags=["Stocks"],
    summary="List S&P 500 stocks with analysis",
    description="""
Returns a list of S&P 500 stocks with indicator analysis.

- Optional limit: Number of stocks to return (default all S&P 500).
- Optional page: Page number for pagination (starts at 1; must be >=1).
- Optional search: Filter by ticker or company name substring.

The endpoint is optimized for large result sets. Use `limit` and `page` for efficient data consumption on large data sets.
    """
)
def get_stocks(
    limit: Optional[int] = Query(None, ge=1, le=500, description="Number of stocks to return (max 500; default: all S&P 500)"),
    page: Optional[int] = Query(1, ge=1, description="Page number for pagination (starts at 1)"),
    search: Optional[str] = Query(None, description="Filter by ticker or company name substring"),
):
    """
    Returns a list of S&P 500 stocks with indicator analysis.
    If limit is not supplied, returns all available tickers.
    Use search parameter to filter.
    """
    raw_tickers = SP500_TICKERS[:]
    results = []

    # Apply search filtering
    if search:
        filtered = []
        s_l = search.lower()
        for tkr in raw_tickers:
            info, err = fetch_yf_info(tkr)
            if err or not info or not info.get("shortName"):
                continue
            if s_l in tkr.lower() or s_l in info.get("shortName", "").lower():
                filtered.append(tkr)
        tickers = filtered
    else:
        tickers = raw_tickers

    total = len(tickers)
    # Pagination
    page = page or 1
    if limit is not None:
        start = (page - 1) * limit
        end = min(start + limit, total)
        paged_tickers = tickers[start:end]
    else:
        paged_tickers = tickers

    for tkr in paged_tickers:
        info, err = fetch_yf_info(tkr)
        if err or not info or not info.get("shortName"):
            continue

        indicators, indicator_score, recommendation = score_indicators(info)
        summary = StockSummary(
            ticker=tkr,
            short_name=info.get("shortName"),
            sector=info.get("sector", None),
            indicator_score=indicator_score,
            recommendation=recommendation,
            indicators=indicators
        )
        results.append(summary)

    return results

# PUBLIC_INTERFACE
@app.get(
    "/stocks/{ticker}",
    response_model=StockDetail,
    tags=["Stocks"],
    summary="Detailed ticker info",
    description="Returns detailed stock and indicator analysis for one ticker."
)
def get_stock_detail(ticker: str):
    """
    Returns detailed stock and indicator analysis for one ticker.
    """
    info, err = fetch_yf_info(ticker)
    if err or not info or not info.get("shortName"):
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found or unavailable.")
    indicators, indicator_score, recommendation = score_indicators(info)
    detail = StockDetail(
        ticker=ticker,
        short_name=info.get("shortName"),
        sector=info.get("sector", None),
        indicator_score=indicator_score,
        recommendation=recommendation,
        indicators=indicators,
        description=info.get("longBusinessSummary"),
        history=None  # Expand: can add historic price/indicator chart if needed
    )
    return detail

# Root index for docs/health
# PUBLIC_INTERFACE
@app.get("/", tags=["System"])
def root():
    """
    Returns basic API health/status.
    """
    return {
        "status": "ok",
        "message": "S&P 500 Stock Evaluator Backend is running",
        "endpoints": ["/stocks", "/stocks/{ticker}"],
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
