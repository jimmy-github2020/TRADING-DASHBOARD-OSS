from models import SymbolSpec


YFINANCE_SYMBOLS: tuple[SymbolSpec, ...] = (
    SymbolSpec("^GSPC", "yfinance", "S&P 500", "index", "SNP", "USD", "America/New_York"),
    SymbolSpec("^NDX", "yfinance", "Nasdaq 100", "index", "NASDAQ", "USD", "America/New_York"),
    SymbolSpec("^DJI", "yfinance", "Dow Jones Industrial Average", "index", "DJI", "USD", "America/New_York"),
    SymbolSpec("^TWII", "yfinance", "Taiwan Weighted Index", "index", "TWSE", "TWD", "Asia/Taipei"),
    SymbolSpec("000001.SS", "yfinance", "SSE Composite Index", "index", "SSE", "CNY", "Asia/Shanghai"),
    SymbolSpec("^HSI", "yfinance", "Hang Seng Index", "index", "HKEX", "HKD", "Asia/Hong_Kong"),
    SymbolSpec("GC=F", "yfinance", "Gold Futures", "commodity", "COMEX", "USD", "America/New_York"),
    SymbolSpec("SI=F", "yfinance", "Silver Futures", "commodity", "COMEX", "USD", "America/New_York"),
    SymbolSpec("CL=F", "yfinance", "WTI Crude Oil Futures", "commodity", "NYMEX", "USD", "America/New_York"),
    SymbolSpec("BZ=F", "yfinance", "Brent Crude Oil Futures", "commodity", "NYMEX", "USD", "America/New_York"),
    SymbolSpec("HG=F", "yfinance", "Copper Futures", "commodity", "COMEX", "USD", "America/New_York"),
    SymbolSpec("^VIX", "yfinance", "CBOE Volatility Index", "volatility", "CBOE", "USD", "America/Chicago"),
    SymbolSpec("DX-Y.NYB", "yfinance", "US Dollar Index", "fx_index", "ICE", "USD", "America/New_York"),
    SymbolSpec("^TNX", "yfinance", "US 10Y Treasury Yield", "yield", "CBOE", "USD", "America/New_York"),
    SymbolSpec("^IRX", "yfinance", "US 13 Week Treasury Bill", "yield", "CBOE", "USD", "America/New_York"),
    SymbolSpec("2330.TW", "yfinance", "TSMC", "equity", "TWSE", "TWD", "Asia/Taipei"),
    SymbolSpec("2317.TW", "yfinance", "Hon Hai Precision", "equity", "TWSE", "TWD", "Asia/Taipei"),
    SymbolSpec("2454.TW", "yfinance", "MediaTek", "equity", "TWSE", "TWD", "Asia/Taipei"),
    SymbolSpec("2382.TW", "yfinance", "Quanta Computer", "equity", "TWSE", "TWD", "Asia/Taipei"),
    SymbolSpec("2308.TW", "yfinance", "Delta Electronics", "equity", "TWSE", "TWD", "Asia/Taipei"),
)

BINANCE_SYMBOLS: tuple[SymbolSpec, ...] = (
    SymbolSpec("BTCUSDT", "binance", "Bitcoin / Tether", "crypto", "Binance", "USDT", "UTC"),
    SymbolSpec("ETHUSDT", "binance", "Ethereum / Tether", "crypto", "Binance", "USDT", "UTC"),
    SymbolSpec("BNBUSDT", "binance", "BNB / Tether", "crypto", "Binance", "USDT", "UTC"),
)

ALL_SYMBOLS: tuple[SymbolSpec, ...] = YFINANCE_SYMBOLS + BINANCE_SYMBOLS
