import pandas as pd
import numpy as np
from typing import List, Tuple


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculate Exponential Moving Average"""
    if len(series) < period:
        return pd.Series([np.nan] * len(series), index=series.index)

    multiplier = 2 / (period + 1)
    ema = pd.Series(index=series.index, dtype=float)

    ema.iloc[period - 1] = series.iloc[:period].mean()

    for i in range(period, len(series)):
        ema.iloc[i] = series.iloc[i] * multiplier + ema.iloc[i - 1] * (1 - multiplier)

    return ema


def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    """Calculate Simple Moving Average"""
    return series.rolling(window=period).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate MACD"""
    ema_fast = calculate_ema(series, fast)
    ema_slow = calculate_ema(series, slow)

    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def calculate_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Bollinger Bands"""
    sma = calculate_sma(series, period)
    std = series.rolling(window=period).std()

    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)

    return upper_band, sma, lower_band


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range"""
    df = df.copy()

    df['high_low'] = df['high'] - df['low']
    df['high_close'] = abs(df['high'] - df['close'].shift())
    df['low_close'] = abs(df['low'] - df['close'].shift())

    df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
    atr = df['tr'].rolling(window=period).mean()

    return atr


def calculate_returns(series: pd.Series) -> pd.Series:
    """Calculate returns"""
    return series.pct_change()


def calculate_drawdown(returns: pd.Series) -> Tuple[pd.Series, float]:
    """Calculate drawdown"""
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max

    max_drawdown = drawdown.min()

    return drawdown, max_drawdown
