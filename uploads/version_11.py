"""
Chandelier Exit Strategy v11  (JAS-CE Strategy v11)  -  Python port of the Pine Script v6 source.

Faithful port of:
  * Chandelier Exit core (everget), EMA 9/21 trend filter
  * EMA Freedom Candle filter on its own timeframe (lower / same / higher than the chart)
  * Same-side pyramiding with reversal on opposite valid signals
  * Exit Mode: 'Original (CE Reversal)' or 'Points SL Only (TP via Signal)'
  * Additional Stop-Loss Logic: static ATR, swing, point, breakeven, time stop, EMA follow-through

TradingView broker-emulator behaviour reproduced:
  * Script runs on bar close; market orders (entries, strategy.close) fill at the NEXT bar's open.
  * strategy.exit stop orders become active on the bar after they are placed; a stop fills at the
    stop price, or at the open if the bar gaps through it. The tightest resting stop fills first.
  * An opposite-side entry closes all open trades (reversal) and opens a new one.
  * Fixed quantity 100 per entry, initial capital 100,000,000, pyramiding cap 100, no commission.

Freedom filter data:
  * Same TF   : computed on self.df.
  * Higher TF : pass `freedom_df` (real higher-TF OHLC, most accurate) or it is resampled from
                self.df. Chart bars read the last CLOSED higher-TF bar (lookahead_on + [1]).
  * Lower TF  : requires `freedom_df` with lower-TF OHLC (Pine uses request.security_lower_tf).
                Without it the bias stays 0 and, as in Pine, the filter blocks every trade.
"""

import warnings
import numpy as np
import pandas as pd

try:
    from base_strategy import BaseStrategy  # adjust to your framework's import path
except ImportError:  # minimal fallback so the file runs standalone
    class BaseStrategy:
        def __init__(self, df, params=None):
            self.df = df.copy()
            self.params = params or {}


EXIT_ORIGINAL = 'Original (CE Reversal)'
EXIT_POINTS_SL = 'Points SL Only (TP via Signal)'

# Exact input() defaults from the Pine Script
DEFAULT_PARAMS = {
    # Calculation
    'length': 22,
    'mult': 3.0,
    'useClose': True,
    # Visuals (plot-only in Pine, no effect on trades)
    'showLabels': True,
    'highlightState': True,
    # Alerts (only gates alertcondition() in Pine, no effect on backtest orders)
    'awaitBarConfirmation': True,
    # EMA Trend Filter
    'ema9Len': 9,
    'ema21Len': 21,
    # EMA Freedom Candle Filter
    'useFreedomFilter': False,          # Pine default: true
    'freedomTf': '15',
    'freedomFastLen': 9,
    'freedomSlowLen': 21,
    'showFreedomLevels': False,         # Pine default: true
    # Exit Settings
    'exitMode': EXIT_ORIGINAL,
    'slPoints': 10.0,
    # Pyramiding
    'enablePyramiding': False,          # Pine default: true
    'maxEntries': 10,
    # Additional Stop-Loss Logic
    'useExtraSl': False,
    'useAtrStop': False,
    'atrStopLen': 14,
    'atrStopMult': 2.0,
    'useSwingStop': False,
    'swingLookback': 10,
    'usePointStop': False,
    'slStopPoints': 10.0,
    'useBreakeven': False,
    'breakevenTriggerPoints': 10.0,
    'useTimeStop': False,
    'timeStopBars': 20,
    'timeStopMinPoints': 0.0,
    'useEmaFollowStop': False,
    'slEmaLen': 21,
    # strategy() settings
    'initial_capital': 100_000_000,
    'qty': 100,
    'pyramiding': 100,
    # Optional fix, NOT in the Pine Script (False = identical to Pine). See README note in chat.
    'fixFlatEntryStopReset': False,
}

# Parameter metadata: step size, min, max for numeric parameters
PARAMETER_METADATA = {
    'mult': {'step': 0.1, 'min': 0.1, 'max': 5.0},
    'atrStopMult': {'step': 0.1, 'min': 0.1, 'max': 5.0},
    'slPoints': {'step': 0.5, 'min': 0.5, 'max': 100.0},
    'slStopPoints': {'step': 0.5, 'min': 0.5, 'max': 100.0},
    'breakevenTriggerPoints': {'step': 0.5, 'min': 0.5, 'max': 100.0},
    'timeStopMinPoints': {'step': 0.5, 'min': 0.0, 'max': 50.0},
    # Integer parameters below (for reference)
    'length': {'step': 1, 'min': 1, 'max': 100},
    'ema9Len': {'step': 1, 'min': 1, 'max': 100},
    'ema21Len': {'step': 1, 'min': 1, 'max': 100},
    'atrStopLen': {'step': 1, 'min': 1, 'max': 50},
    'swingLookback': {'step': 1, 'min': 1, 'max': 50},
    'maxEntries': {'step': 1, 'min': 1, 'max': 20},
    'freedomFastLen': {'step': 1, 'min': 1, 'max': 50},
    'freedomSlowLen': {'step': 1, 'min': 1, 'max': 100},
    'timeStopBars': {'step': 1, 'min': 1, 'max': 100},
    'slEmaLen': {'step': 1, 'min': 1, 'max': 100},
}

# The 32 Pine input() names, exactly as declared in the Pine Script
PINE_INPUT_NAMES = [
    'length', 'mult', 'useClose', 'showLabels', 'highlightState', 'awaitBarConfirmation',
    'ema9Len', 'ema21Len', 'useFreedomFilter', 'freedomTf', 'freedomFastLen', 'freedomSlowLen',
    'showFreedomLevels', 'exitMode', 'slPoints', 'enablePyramiding', 'maxEntries', 'useExtraSl',
    'useAtrStop', 'atrStopLen', 'atrStopMult', 'useSwingStop', 'swingLookback', 'usePointStop',
    'slStopPoints', 'useBreakeven', 'breakevenTriggerPoints', 'useTimeStop', 'timeStopBars',
    'timeStopMinPoints', 'useEmaFollowStop', 'slEmaLen',
]

# options=[...] lists of string inputs
PINE_INPUT_OPTIONS = {'exitMode': [EXIT_ORIGINAL, EXIT_POINTS_SL]}


def _to_bool(v):
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ('true', '1', 'yes', 'y', 'on', 't'):
            return True
        if s in ('false', '0', 'no', 'n', 'off', 'f', ''):
            return False
        raise ValueError(f'Cannot interpret {v!r} as a boolean')
    return bool(v)


def _to_int(v):
    return int(round(float(v)))


def _to_exit_mode(v):
    s = str(v).strip()
    if s in (EXIT_ORIGINAL, EXIT_POINTS_SL):
        return s
    low = s.lower()
    if low.startswith('points') or 'sl' in low.split():
        return EXIT_POINTS_SL
    if low.startswith('original') or 'reversal' in low:
        return EXIT_ORIGINAL
    raise ValueError(f"exitMode must be '{EXIT_ORIGINAL}' or '{EXIT_POINTS_SL}', got {v!r}")


def _to_tf(v):
    if isinstance(v, (int, float, np.integer, np.floating)):
        return str(int(v))              # 15 -> '15'
    s = str(v).strip()
    if s.replace('.', '', 1).isdigit():
        return str(int(float(s)))       # '15.0' -> '15'
    return s.upper()


_PARAM_TYPES = {
    'length': _to_int, 'mult': float, 'useClose': _to_bool,
    'showLabels': _to_bool, 'highlightState': _to_bool, 'awaitBarConfirmation': _to_bool,
    'ema9Len': _to_int, 'ema21Len': _to_int,
    'useFreedomFilter': _to_bool, 'freedomTf': _to_tf, 'freedomFastLen': _to_int,
    'freedomSlowLen': _to_int, 'showFreedomLevels': _to_bool,
    'exitMode': _to_exit_mode, 'slPoints': float,
    'enablePyramiding': _to_bool, 'maxEntries': _to_int,
    'useExtraSl': _to_bool, 'useAtrStop': _to_bool, 'atrStopLen': _to_int, 'atrStopMult': float,
    'useSwingStop': _to_bool, 'swingLookback': _to_int, 'usePointStop': _to_bool,
    'slStopPoints': float, 'useBreakeven': _to_bool, 'breakevenTriggerPoints': float,
    'useTimeStop': _to_bool, 'timeStopBars': _to_int, 'timeStopMinPoints': float,
    'useEmaFollowStop': _to_bool, 'slEmaLen': _to_int,
    'initial_capital': float, 'qty': float, 'pyramiding': _to_int, 'fixFlatEntryStopReset': _to_bool,
}


def build_params(params=None):
    """Merge user values over the Pine defaults, coerce types, and flag unknown names."""
    params = dict(params or {})
    params.pop('freedom_df', None)
    unknown = [k for k in params if k not in DEFAULT_PARAMS]
    if unknown:
        warnings.warn(f'Unknown parameter name(s) ignored: {unknown}. '
                      f'Valid Pine names: {PINE_INPUT_NAMES}')
    merged = dict(DEFAULT_PARAMS)
    for k, v in params.items():
        if k in DEFAULT_PARAMS and v is not None:
            merged[k] = _PARAM_TYPES[k](v)
    return merged


# =============================================================================================
# Pine-compatible indicator formulas
# =============================================================================================
def _seeded_smoothing(values, length, alpha):
    """Recursive smoothing seeded with the SMA of the first `length` valid values (ta.ema / ta.rma)."""
    values = np.asarray(values, dtype=float)
    out = np.full(len(values), np.nan)
    valid = np.where(~np.isnan(values))[0]
    if len(valid) < length:
        return out
    start = valid[0]
    seed = start + length - 1
    out[seed] = values[start:seed + 1].mean()
    for i in range(seed + 1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def ema_np(values, length):
    """ta.ema: alpha = 2 / (length + 1)."""
    return _seeded_smoothing(values, length, 2.0 / (length + 1))


def rma_np(values, length):
    """ta.rma (Wilder): alpha = 1 / length."""
    return _seeded_smoothing(values, length, 1.0 / length)


def true_range_np(h, l, c):
    """ta.tr(true): high - low on the first bar, otherwise max of the three ranges."""
    prev_c = np.r_[np.nan, c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    tr[0] = h[0] - l[0]
    return tr


def atr_np(h, l, c, length):
    """ta.atr = ta.rma(ta.tr(true), length)."""
    return rma_np(true_range_np(h, l, c), length)


def highest_np(values, length):
    return pd.Series(values).rolling(length).max().to_numpy()


def lowest_np(values, length):
    return pd.Series(values).rolling(length).min().to_numpy()


def _nan_max(xs):
    xs = [x for x in xs if not np.isnan(x)]
    return max(xs) if xs else np.nan


def _nan_min(xs):
    xs = [x for x in xs if not np.isnan(x)]
    return min(xs) if xs else np.nan


# =============================================================================================
# Timeframe helpers
# =============================================================================================
def tf_to_seconds(tf):
    """Equivalent of timeframe.in_seconds() for strings like '15', '60', '1D', 'D', '1W', '30S'."""
    s = str(tf).strip().upper()
    unit = s[-1] if s[-1].isalpha() else ''
    num = s[:-1] if unit else s
    num = int(num) if num else 1
    if unit == '':
        return num * 60
    if unit == 'S':
        return num
    if unit == 'H':
        return num * 3600
    if unit == 'D':
        return num * 86400
    if unit == 'W':
        return num * 604800
    if unit == 'M':
        return num * 2628003  # Pine's value for 1M
    raise ValueError(f'Unrecognised timeframe: {tf}')


def tf_to_pandas_rule(tf):
    s = str(tf).strip().upper()
    unit = s[-1] if s[-1].isalpha() else ''
    num = s[:-1] if unit else s
    num = int(num) if num else 1
    return {'': f'{num}min', 'S': f'{num}s', 'H': f'{num}h', 'D': f'{num}D',
            'W': f'{num}W-MON', 'M': f'{num}MS'}[unit]


# =============================================================================================
# Freedom Candle state machine (direct port of freedomState())
# =============================================================================================
def freedom_state(o, h, l, c, fast_len, slow_len):
    """Returns (bias, freedomHigh, freedomLow) arrays. bias: 1 LONG, -1 SHORT, 0 none."""
    n = len(c)
    fe, se = ema_np(c, fast_len), ema_np(c, slow_len)
    bias_out = np.zeros(n, dtype=int)
    fh_out = np.full(n, np.nan)
    fl_out = np.full(n, np.nan)

    seek_long = wait_long = False
    freedom_high = np.nan
    long_cross_bar = None
    seek_short = wait_short = False
    freedom_low = np.nan
    short_cross_bar = None
    bias = 0

    def touches(k):  # wick-inclusive touch of the fast EMA; na comparisons are false in Pine
        if k < 0 or np.isnan(fe[k]):
            return False
        return h[k] >= fe[k] and l[k] <= fe[k]

    for i in range(n):
        cross_ok = i > 0 and not np.isnan([fe[i], se[i], fe[i - 1], se[i - 1]]).any()
        bull_cross = cross_ok and fe[i] > se[i] and fe[i - 1] <= se[i - 1]
        bear_cross = cross_ok and fe[i] < se[i] and fe[i - 1] >= se[i - 1]

        all_clear = not touches(i) and not touches(i - 1) and not touches(i - 2)
        ks = [k for k in (i, i - 1, i - 2) if k >= 0]
        has_red = any(c[k] < o[k] for k in ks)
        has_green = any(c[k] > o[k] for k in ks)

        if bull_cross:
            seek_long, wait_long, freedom_high, long_cross_bar = True, False, np.nan, i
            seek_short, wait_short, freedom_low = False, False, np.nan
            bias = 0
        if bear_cross:
            seek_short, wait_short, freedom_low, short_cross_bar = True, False, np.nan, i
            seek_long, wait_long, freedom_high = False, False, np.nan
            bias = 0

        if (seek_long and not wait_long and long_cross_bar is not None
                and i - long_cross_bar >= 3 and all_clear and has_red):
            freedom_high = max(h[i], h[i - 1], h[i - 2])
            wait_long, seek_long = True, False

        if (seek_short and not wait_short and short_cross_bar is not None
                and i - short_cross_bar >= 3 and all_clear and has_green):
            freedom_low = min(l[i], l[i - 1], l[i - 2])
            wait_short, seek_short = True, False

        if wait_long and not np.isnan(freedom_high) and c[i] > freedom_high:
            bias, wait_long = 1, False
        if wait_short and not np.isnan(freedom_low) and c[i] < freedom_low:
            bias, wait_short = -1, False

        bias_out[i], fh_out[i], fl_out[i] = bias, freedom_high, freedom_low

    return bias_out, fh_out, fl_out


def _ensure_datetime_index(df):
    if isinstance(df.index, pd.DatetimeIndex):
        return df
    for col in ('datetime', 'timestamp', 'time', 'date'):
        if col in df.columns:
            ts = df[col]
            if np.issubdtype(ts.dtype, np.number):
                ts = pd.to_datetime(ts, unit='ms' if ts.iloc[0] > 1e11 else 's')
            else:
                ts = pd.to_datetime(ts)
            return df.set_index(pd.DatetimeIndex(ts)).drop(columns=[col], errors='ignore')
    return df


def _prep_ohlc(df):
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    return _ensure_datetime_index(df)


# =============================================================================================
# Strategy
# =============================================================================================
class UploadedStrategy(BaseStrategy):

    def __init__(self, df, params=None, freedom_df=None):
        if params and params.get('freedom_df') is not None:
            freedom_df = params['freedom_df']
        merged = build_params(params)
        super().__init__(df, merged)
        self.params = merged
        self.df = _prep_ohlc(df)
        self.freedom_df = _prep_ohlc(freedom_df) if freedom_df is not None else None
        self.trades = []
        self.open_trades = []

    # ------------------------------------------------------------------------------------------
    def _chart_seconds(self):
        idx = self.df.index
        if not isinstance(idx, pd.DatetimeIndex) or len(idx) < 2:
            return None
        return int(pd.Series(idx).diff().dropna().dt.total_seconds().median())

    def _freedom_filter(self):
        p, df = self.params, self.df
        n = len(df)
        fast, slow = int(p['freedomFastLen']), int(p['freedomSlowLen'])
        f_secs, c_secs = tf_to_seconds(p['freedomTf']), self._chart_seconds()

        def run(frame):
            return freedom_state(*(frame[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')),
                                 fast, slow)

        if c_secs is None:
            warnings.warn('No datetime index: Freedom filter computed on the chart timeframe.')
            return run(df)

        # ---- SAME timeframe ----
        if f_secs == c_secs:
            return run(df)

        chart_t = df.index.values

        # ---- HIGHER timeframe: last CLOSED higher-TF bar (lookahead_on + [1]) ----
        if f_secs > c_secs:
            if self.freedom_df is not None:
                htf = self.freedom_df
            else:
                htf = (df[['open', 'high', 'low', 'close']]
                       .resample(tf_to_pandas_rule(p['freedomTf']), label='left', closed='left')
                       .agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'})
                       .dropna())
            b, fh, fl = run(htf)
            k = np.searchsorted(htf.index.values, chart_t, side='right') - 1  # HTF bar containing chart bar
            prev = k - 1                                                     # previous (closed) HTF bar
            ok = prev >= 0
            bias = np.zeros(n, dtype=int)
            hi, lo = np.full(n, np.nan), np.full(n, np.nan)
            bias[ok], hi[ok], lo[ok] = b[prev[ok]], fh[prev[ok]], fl[prev[ok]]
            return bias, hi, lo

        # ---- LOWER timeframe: state after the last intrabar of each chart bar ----
        bias = np.zeros(n, dtype=int)
        hi, lo = np.full(n, np.nan), np.full(n, np.nan)
        if self.freedom_df is None:
            warnings.warn('freedomTf is lower than the chart timeframe but no freedom_df was given: '
                          'bias stays 0, so the Freedom filter blocks all trades (same as Pine with '
                          'no intrabar history).')
            return bias, hi, lo
        b, fh, fl = run(self.freedom_df)
        bucket = np.searchsorted(chart_t, self.freedom_df.index.values, side='right') - 1
        last_intrabar = np.full(n, -1)
        for j, bk in enumerate(bucket):
            if 0 <= bk < n:
                last_intrabar[bk] = j
        cur_b, cur_h, cur_l = 0, np.nan, np.nan  # Pine `var` values persist when no intrabars
        for i in range(n):
            j = last_intrabar[i]
            if j >= 0:
                cur_b, cur_h, cur_l = b[j], fh[j], fl[j]
            bias[i], hi[i], lo[i] = cur_b, cur_h, cur_l
        return bias, hi, lo

    # ------------------------------------------------------------------------------------------
    def calculate_indicators(self):
        # Re-apply defaults/coercion in case the framework replaced self.params after __init__
        self.params = build_params(self.params)
        p, df = self.params, self.df
        o, h, l, c = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close'))
        n = len(df)
        length = int(p['length'])

        # ---- Freedom Candle filter ----
        f_bias, f_high, f_low = self._freedom_filter()
        df['freedom_bias'] = f_bias
        df['freedom_high'] = f_high
        df['freedom_low'] = f_low

        # ---- EMA trend filter ----
        df['ema9'] = ema_np(c, int(p['ema9Len']))
        df['ema21'] = ema_np(c, int(p['ema21Len']))

        # ---- Chandelier Exit core ----
        atr_ce = p['mult'] * atr_np(h, l, c, length)
        long_raw = (highest_np(c, length) if p['useClose'] else highest_np(h, length)) - atr_ce
        short_raw = (lowest_np(c, length) if p['useClose'] else lowest_np(l, length)) + atr_ce

        long_stop = np.full(n, np.nan)
        short_stop = np.full(n, np.nan)
        direction = np.ones(n, dtype=int)
        d = 1  # var int dir = 1
        for i in range(n):
            ls, ss = long_raw[i], short_raw[i]
            ls_prev = long_stop[i - 1] if i > 0 and not np.isnan(long_stop[i - 1]) else ls  # nz(longStop[1], longStop)
            ss_prev = short_stop[i - 1] if i > 0 and not np.isnan(short_stop[i - 1]) else ss
            c_prev = c[i - 1] if i > 0 else np.nan
            long_stop[i] = max(ls, ls_prev) if c_prev > ls_prev else ls
            short_stop[i] = min(ss, ss_prev) if c_prev < ss_prev else ss
            if c[i] > ss_prev:
                d = 1
            elif c[i] < ls_prev:
                d = -1
            direction[i] = d
        df['ce_long_stop'] = long_stop
        df['ce_short_stop'] = short_stop
        df['ce_dir'] = direction

        # ---- Additional stop-loss helpers ----
        df['atr_stop_val'] = atr_np(h, l, c, int(p['atrStopLen'])) * p['atrStopMult']
        lb = int(p['swingLookback'])
        df['swing_low_before'] = pd.Series(lowest_np(l, lb)).shift(1).to_numpy()    # ta.lowest(low, n)[1]
        df['swing_high_before'] = pd.Series(highest_np(h, lb)).shift(1).to_numpy()  # ta.highest(high, n)[1]
        df['sl_ema'] = ema_np(c, int(p['slEmaLen']))
        return df

    # ------------------------------------------------------------------------------------------
    def generate_signals(self):
        p, df = self.params, self.df
        d = df['ce_dir']
        buy_signal = (d == 1) & (d.shift(1) == -1)
        sell_signal = (d == -1) & (d.shift(1) == 1)

        ema_bull = df['ema9'] > df['ema21']
        ema_bear = df['ema9'] < df['ema21']
        freedom_long_ok = (not p['useFreedomFilter']) | (df['freedom_bias'] == 1)
        freedom_short_ok = (not p['useFreedomFilter']) | (df['freedom_bias'] == -1)

        long_ok = ema_bull & freedom_long_ok
        short_ok = ema_bear & freedom_short_ok

        df['buy_signal'] = buy_signal            # raw CE signals (green or gray label)
        df['sell_signal'] = sell_signal
        df['final_buy'] = buy_signal & long_ok   # green label -> tradable
        df['final_sell'] = sell_signal & short_ok  # red label -> tradable
        df['blocked_signal'] = (buy_signal & ~long_ok) | (sell_signal & ~short_ok)  # gray labels

        df['signal'] = 0
        df.loc[df['final_buy'], 'signal'] = 1
        df.loc[df['final_sell'], 'signal'] = -1
        return df

    # ------------------------------------------------------------------------------------------
    def run_backtest(self):
        p, df = self.params, self.df
        o, h, l, c = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close'))
        final_buy = df['final_buy'].to_numpy(bool)
        final_sell = df['final_sell'].to_numpy(bool)
        atr_sv = df['atr_stop_val'].to_numpy()
        sw_lo = df['swing_low_before'].to_numpy()
        sw_hi = df['swing_high_before'].to_numpy()
        sl_ema = df['sl_ema'].to_numpy()
        times = df.index
        n = len(df)
        qty = p['qty']
        max_same_side = min(int(p['maxEntries']), int(p['pyramiding']))

        open_trades = []       # {'id', 'side', 'price', 'bar'}
        closed = []
        pending_entry = 0      # +1 / -1 market entry to fill at next open
        pending_closes = []    # (reason, set of trade ids) market closes to fill at next open
        stop_orders = {}       # name -> (side, price); resting strategy.exit stops
        long_lvl = short_lvl = np.nan  # var float longStopLevel / shortStopLevel
        realized = 0.0
        equity = np.empty(n)
        next_id = 0

        def side_now():
            return open_trades[0]['side'] if open_trades else 0

        def avg_price():
            return float(np.mean([t['price'] for t in open_trades]))

        def close_trades(victims, price, i, reason):
            nonlocal realized
            for t in victims:
                pnl = (price - t['price']) * t['side'] * qty
                realized += pnl
                closed.append({
                    'side': 'Long' if t['side'] == 1 else 'Short',
                    'entry_time': times[t['bar']], 'exit_time': times[i],
                    'entry_bar': t['bar'], 'exit_bar': i,
                    'entry_price': t['price'], 'exit_price': price,
                    'qty': qty, 'pnl': pnl, 'exit_reason': reason,
                })
                open_trades.remove(t)

        for i in range(n):
            # ---- 1) Market orders created on the previous bar fill at this bar's open ----
            if pending_entry:
                if side_now() == -pending_entry:          # reversal closes every open trade
                    close_trades(list(open_trades), o[i], i, 'Reverse')
                    stop_orders.clear()
                open_trades.append({'id': next_id, 'side': pending_entry, 'price': o[i], 'bar': i})
                next_id += 1
            for reason, ids in pending_closes:
                victims = [t for t in open_trades if t['id'] in ids]
                if victims:
                    close_trades(victims, o[i], i, reason)
            pending_entry, pending_closes = 0, []
            if not open_trades:
                stop_orders.clear()

            # ---- 2) Resting stop orders (placed on earlier bars) ----
            side = side_now()
            live = [(name, px) for name, (s, px) in stop_orders.items() if s == side]
            if side and live:
                if side == 1:
                    name, px = max(live, key=lambda x: x[1])
                    if l[i] <= px:
                        close_trades(list(open_trades), min(o[i], px), i, name)
                else:
                    name, px = min(live, key=lambda x: x[1])
                    if h[i] >= px:
                        close_trades(list(open_trades), max(o[i], px), i, name)
                if not open_trades:
                    stop_orders.clear()

            # ---- 3) Script logic on bar close ----
            pos = side_now()
            n_open = len(open_trades)
            can_add_long = pos <= 0 or (p['enablePyramiding'] and n_open < max_same_side)
            can_add_short = pos >= 0 or (p['enablePyramiding'] and n_open < max_same_side)
            enter_long = final_buy[i] and can_add_long
            enter_short = final_sell[i] and can_add_short
            if enter_long:
                pending_entry = 1
            if enter_short:
                pending_entry = -1

            # Combined stop level (sub-types 1-3), computed from the signal bar's close
            if enter_long:
                cands = []
                if p['useAtrStop']:
                    cands.append(c[i] - atr_sv[i])
                if p['useSwingStop']:
                    cands.append(sw_lo[i])
                if p['usePointStop']:
                    cands.append(c[i] - p['slStopPoints'])
                long_lvl = _nan_max(cands)
            if enter_short:
                cands = []
                if p['useAtrStop']:
                    cands.append(c[i] + atr_sv[i])
                if p['useSwingStop']:
                    cands.append(sw_hi[i])
                if p['usePointStop']:
                    cands.append(c[i] + p['slStopPoints'])
                short_lvl = _nan_min(cands)

            # Sub-type 4: breakeven ratchet
            if p['useBreakeven'] and pos > 0 and not np.isnan(long_lvl):
                if h[i] >= avg_price() + p['breakevenTriggerPoints']:
                    long_lvl = max(long_lvl, avg_price())
            if p['useBreakeven'] and pos < 0 and not np.isnan(short_lvl):
                if l[i] <= avg_price() - p['breakevenTriggerPoints']:
                    short_lvl = min(short_lvl, avg_price())

            # Reset while flat (Pine does this even on the bar an entry from flat is ordered)
            if pos == 0:
                if p['fixFlatEntryStopReset']:
                    long_lvl = long_lvl if enter_long else np.nan
                    short_lvl = short_lvl if enter_short else np.nan
                else:
                    long_lvl = short_lvl = np.nan

            if p['useExtraSl'] and pos > 0 and not np.isnan(long_lvl):
                stop_orders['Long Extra SL'] = (1, long_lvl)
            if p['useExtraSl'] and pos < 0 and not np.isnan(short_lvl):
                stop_orders['Short Extra SL'] = (-1, short_lvl)

            # Sub-type 5: time stop from the oldest open trade
            if p['useExtraSl'] and p['useTimeStop'] and pos != 0:
                t0 = open_trades[0]
                progress = (c[i] - t0['price']) * pos
                if i - t0['bar'] >= p['timeStopBars'] and progress < p['timeStopMinPoints']:
                    pending_closes.append(('Time Stop', {t['id'] for t in open_trades}))

            # Sub-type 6: EMA follow-through reversal
            if p['useExtraSl'] and p['useEmaFollowStop'] and i >= 1 and pos != 0:
                if pos < 0 and c[i - 1] > sl_ema[i - 1] and c[i] > c[i - 1]:
                    pending_closes.append(('EMA Follow-Through SL', {t['id'] for t in open_trades}))
                if pos > 0 and c[i - 1] < sl_ema[i - 1] and c[i] < c[i - 1]:
                    pending_closes.append(('EMA Follow-Through SL', {t['id'] for t in open_trades}))

            # Exit Mode: fixed points stop from the average entry price
            if p['exitMode'] == EXIT_POINTS_SL:
                if pos > 0:
                    stop_orders['Long Exit'] = (1, avg_price() - p['slPoints'])
                if pos < 0:
                    stop_orders['Short Exit'] = (-1, avg_price() + p['slPoints'])

            open_pnl = sum((c[i] - t['price']) * t['side'] * qty for t in open_trades)
            equity[i] = p['initial_capital'] + realized  # Close-to-close: realized P&L only

        df['equity'] = equity
        self.trades = closed
        self.open_trades = [{
            'side': 'Long' if t['side'] == 1 else 'Short', 'entry_time': times[t['bar']],
            'entry_price': t['price'], 'qty': qty,
            'open_pnl': (c[-1] - t['price']) * t['side'] * qty,
        } for t in open_trades]
        return self._summary()

    # ------------------------------------------------------------------------------------------
    def _summary(self):
        t = pd.DataFrame(self.trades)
        eq = self.df['equity']
        open_pnl = sum(x['open_pnl'] for x in self.open_trades)
        base = {'trades': t, 'open_trades': pd.DataFrame(self.open_trades), 'open_pnl': open_pnl,
                'max_drawdown': float((eq.cummax() - eq).max()) if len(eq) else 0.0}
        if t.empty:
            return {**base, 'total_closed_trades': 0, 'net_profit': 0.0}
        wins, losses = t[t['pnl'] > 0], t[t['pnl'] <= 0]
        gross_profit, gross_loss = wins['pnl'].sum(), losses['pnl'].sum()
        return {
            **base,
            'net_profit': float(t['pnl'].sum()),
            'gross_profit': float(gross_profit),
            'gross_loss': float(gross_loss),
            'profit_factor': float(gross_profit / abs(gross_loss)) if gross_loss else np.inf,
            'total_closed_trades': len(t),
            'percent_profitable': len(wins) / len(t) * 100,
            'avg_trade': float(t['pnl'].mean()),
            'exit_reasons': t['exit_reason'].value_counts().to_dict(),
        }

    def run(self):
        self.calculate_indicators()
        self.generate_signals()
        return self.run_backtest()


if __name__ == '__main__':
    # Smoke test on synthetic 5-minute gold-like data
    rng = np.random.default_rng(7)
    idx = pd.date_range('2025-01-01', periods=6000, freq='5min')
    close = 4200 + np.cumsum(rng.normal(0, 1.5, len(idx)))
    open_ = np.r_[close[0], close[:-1]] + rng.normal(0, 0.2, len(idx))
    high = np.maximum(open_, close) + rng.uniform(0, 1.2, len(idx))
    low = np.minimum(open_, close) - rng.uniform(0, 1.2, len(idx))
    data = pd.DataFrame({'open': open_, 'high': high, 'low': low, 'close': close}, index=idx)

    res = UploadedStrategy(data).run()  # Pine defaults: Freedom TF 15 on a 5m chart (higher TF)
    for k, v in res.items():
        if k not in ('trades', 'open_trades'):
            print(f'{k}: {v}')
