import yfinance as yf
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel, Field

# App metadata and CORS config
app = FastAPI(
    title="S&P 500 Stock Analysis & Recommendation API",
    description="REST APIs for retrieving S&P 500 stock analysis and algorithmic buy/hold/sell recommendations.",
    version="1.0.0",
    openapi_tags=[
        {"name": "stocks", "description": "Endpoints for stock analysis and recommendations"}
    ]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# S&P 500 tickers are fetched from Wikipedia for the freshest composition.
SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def get_sp500_tickers():
    """Fetch the list of current S&P 500 tickers from Wikipedia."""
    table = pd.read_html(SP500_WIKI_URL)
    df = table[0]
    return df["Symbol"].tolist()


SP500_TICKERS = get_sp500_tickers()


# Pydantic models for response serialization
class IndicatorScores(BaseModel):
    pe_ratio: Optional[float] = Field(None, description="Price/Earnings ratio")
    pb_ratio: Optional[float] = Field(None, description="Price/Book ratio")
    dividend_yield: Optional[float] = Field(None, description="Dividend yield (%)")
    debt_to_equity: Optional[float] = Field(None, description="Debt to equity ratio")
    current_ratio: Optional[float] = Field(None, description="Current ratio (liquidity)")
    profit_margin: Optional[float] = Field(None, description="Profit margin (%)")
    return_on_equity: Optional[float] = Field(None, description="Return on equity (%)")


class StockAnalysis(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol")
    name: Optional[str] = Field(None, description="Company name")
    recommendation: str = Field(..., description="Buy/Hold/Sell recommendation")
    overall_score: float = Field(..., description="Aggregated indicator score (0-100)")
    indicator_scores: IndicatorScores = Field(..., description="Breakdown of indicators")


class StockListResponse(BaseModel):
    stocks: List[StockAnalysis]


def compute_indicator_scores(ticker) -> IndicatorScores:
    """Fetch and calculate key fundamental indicators for a given ticker."""
    info = {}
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info
    except Exception:
        return IndicatorScores()
    pe = info.get("trailingPE")
    pb = info.get("priceToBook")
    div_yield = info.get("dividendYield", 0.0)
    if div_yield is not None:
        div_yield *= 100  # Convert to %
    dte = info.get("debtToEquity")
    curr_ratio = info.get("currentRatio")
    profit_margin = info.get("profitMargins", 0.0)
    if profit_margin is not None:
        profit_margin *= 100  # Convert to %
    roe = info.get("returnOnEquity", 0.0)
    if roe is not None:
        roe *= 100
    return IndicatorScores(
        pe_ratio=pe,
        pb_ratio=pb,
        dividend_yield=div_yield,
        debt_to_equity=dte,
        current_ratio=curr_ratio,
        profit_margin=profit_margin,
        return_on_equity=roe,
    )


def get_recommendation(scores: IndicatorScores) -> (str, float):
    """
    Generate aggregate score and recommendation.
    - Lower PE and PB ratios are favorable (value).
    - Decent dividend yield, lower debt to equity (financial health), higher current ratio, higher profit margin and ROE.
    Return recommendation and normalized score (0-100).
    """
    raw_score = 0.0
    total = 0
    mapping = []

    if scores.pe_ratio and 5 < scores.pe_ratio < 28:
        raw_score += 1.5
    elif scores.pe_ratio and scores.pe_ratio < 40:
        raw_score += 1.0
    total += 1.5

    if scores.pb_ratio and scores.pb_ratio < 4:
        raw_score += 1.0
    total += 1.0

    if scores.dividend_yield and scores.dividend_yield > 1.0:
        raw_score += 1.0
    total += 1.0

    if scores.debt_to_equity and scores.debt_to_equity < 1.5:
        raw_score += 1.0
    total += 1.0

    if scores.current_ratio and scores.current_ratio > 1.1:
        raw_score += 1.0
    total += 1.0

    if scores.profit_margin and scores.profit_margin > 8:
        raw_score += 0.8
    total += 0.8

    if scores.return_on_equity and scores.return_on_equity > 7.0:
        raw_score += 0.7
    total += 0.7

    # Final score normalization
    norm_score = (raw_score / total) * 100 if total else 0
    if norm_score > 65:
        rec = "BUY"
    elif norm_score > 45:
        rec = "HOLD"
    else:
        rec = "SELL"
    return rec, round(norm_score, 2)


def get_company_name(ticker):
    """Fetch the company name for a given ticker."""
    try:
        info = yf.Ticker(ticker).info
        return info.get("shortName", ticker)
    except Exception:
        return ticker


@app.get("/stocks", tags=["stocks"], summary="Get S&P 500 stock recommendations")
# PUBLIC_INTERFACE
async def get_all_stocks(
    filter: Optional[str] = Query(None, description="Buy/Hold/Sell to filter results"),
    search: Optional[str] = Query(None, description="Optional ticker search (prefix or company name)"),
    sort: Optional[str] = Query('descending', description="Sort order: 'descending' or 'ascending' by score"),
    limit: Optional[int] = Query(20, description="Number of results to return (default: 20)")
) -> StockListResponse:
    """
    Retrieve a list of S&P 500 stocks analyzed with indicator breakdowns and overall recommendation.

    Parameters:
      - filter: (optional) Specify 'BUY', 'HOLD', or 'SELL' to limit to those recommendations.
      - search: (optional) Partial ticker or company name match.
      - sort: (optional) Sort by score: 'ascending' (worst first) or 'descending' (best first). Default: descending.
      - limit: (optional) Number of results to return (default: 20, max: 100).
    """
    results = []
    searched = []
    limit = min(max(1, limit), 100)

    for ticker in SP500_TICKERS:
        if search:
            if (search.lower() not in ticker.lower()) and (search.lower() not in get_company_name(ticker).lower()):
                continue
        indicator_scores = compute_indicator_scores(ticker)
        rec, score = get_recommendation(indicator_scores)
        if filter and rec != filter.upper():
            continue
        # Only get name if actually returning this result
        name = get_company_name(ticker)
        results.append(StockAnalysis(
            ticker=ticker,
            name=name,
            recommendation=rec,
            overall_score=score,
            indicator_scores=indicator_scores
        ))

    # Sorting
    results.sort(key=lambda x: x.overall_score, reverse=(sort == "descending"))
    # Apply limit
    results = results[:limit]
    return {"stocks": results}


@app.get("/stocks/{ticker}", tags=["stocks"], summary="Get indicator analysis and recommendation for a single ticker")
# PUBLIC_INTERFACE
async def get_single_stock(
    ticker: str
) -> StockAnalysis:
    """
    Retrieve recommendation and indicator breakdown for a single S&P 500 stock.

    Parameters:
      - ticker: Stock ticker symbol.
    """
    ticker = ticker.upper()
    if ticker not in SP500_TICKERS:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} is not part of S&P 500 index.")
    indicator_scores = compute_indicator_scores(ticker)
    rec, score = get_recommendation(indicator_scores)
    name = get_company_name(ticker)
    return StockAnalysis(
        ticker=ticker,
        name=name,
        recommendation=rec,
        overall_score=score,
        indicator_scores=indicator_scores
    )


@app.get("/", include_in_schema=False)
async def root():
    """Simple root endpoint with a message."""
    return {"message": "S&P 500 Stock Evaluator API. See /docs for API usage."}
