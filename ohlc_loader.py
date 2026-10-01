import pandas as pd
import numpy as np
from typing import Tuple, Optional
from pathlib import Path


class OHLCDataLoader:
    COLUMN_ALIASES = {
        'time': ['time', 'date', 'datetime', 'timestamp'],
        'open': ['open'],
        'high': ['high'],
        'low': ['low'],
        'close': ['close'],
        'volume': ['volume', 'vol']
    }

    @staticmethod
    def load(filepath: str) -> pd.DataFrame:
        """Load OHLC data from CSV - uses first 5 columns (Time, Open, High, Low, Close)"""
        df = pd.read_csv(filepath)

        # Keep only first 5 columns (standard OHLC format: Time, Open, High, Low, Close)
        if len(df.columns) > 5:
            df = df.iloc[:, :5]

        # Rename columns to lowercase
        df.columns = df.columns.str.lower().str.strip()

        # Map to standard OHLC names based on position
        col_mapping = {}
        for idx, col in enumerate(df.columns):
            if idx == 0:  # First column is always Time/Date
                col_mapping[col] = 'time'
            elif idx == 1:  # Second is Open
                col_mapping[col] = 'open'
            elif idx == 2:  # Third is High
                col_mapping[col] = 'high'
            elif idx == 3:  # Fourth is Low
                col_mapping[col] = 'low'
            elif idx == 4:  # Fifth is Close
                col_mapping[col] = 'close'

        df.rename(columns=col_mapping, inplace=True)

        # Convert time to datetime
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])

        # Add volume column if missing
        if 'volume' not in df.columns:
            df['volume'] = 0

        OHLCDataLoader._validate_ohlc(df)

        return df

    @staticmethod
    def _validate_ohlc(df: pd.DataFrame):
        """Validate OHLC data"""

        if 'high' in df.columns and 'low' in df.columns:
            valid = (df['high'] >= df['low']).all()
            if not valid:
                raise ValueError("High must be >= Low")

        if 'open' in df.columns and 'high' in df.columns:
            valid = (df['high'] >= df['open']).all()
            if not valid:
                raise ValueError("High must be >= Open")

        if 'close' in df.columns and 'low' in df.columns:
            valid = (df['close'] >= df['low']).all()
            if not valid:
                raise ValueError("Close must be >= Low")
