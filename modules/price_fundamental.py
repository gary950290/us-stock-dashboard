import yfinance as yf
import pandas as pd

def get_price(symbol):
    info = yf.Ticker(symbol).info
    return {
        "price": info.get("currentPrice"),
        "change": info.get("regularMarketChangePercent")
    }

def get_fundamentals(symbol):
    info = yf.Ticker(symbol).info
    data = {
        "股價": info.get("currentPrice"),
        "PE": info.get("trailingPE"),
        "Forward PE": info.get("forwardPE"),
        "EPS": info.get("trailingEps"),
        "ROE": info.get("returnOnEquity"),
        "市值": info.get("marketCap"),
        "FCF": info.get("freeCashflow")
    }
    return pd.DataFrame(data.items(), columns=["指標", "數值"])
