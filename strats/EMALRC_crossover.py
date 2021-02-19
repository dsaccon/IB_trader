#!/usr/local/bin/python3

import pandas as pd
import datetime as dt
import os, sys
import logging

from talib.abstract import LINEARREG, EMA

from exchanges import ib
from strats.base import IBConnectionError, ApplicationLogicError
from strats.base import DataCollectionError
from strats.base import IBTrader, main_cli, parse_args


class EmaLrcCrossover(IBTrader):
    def __init__(self, client_id, args, start_order_id=None):
        df_cols = {
            'time': [],
            'open': [],
            'high': [],
            'low': [],
            'close': [],
            'ema': [],
            'ema_prev': [],
            'lrc': [],
            'lrc_prev': [],
        }
        self.candles = pd.DataFrame(df_cols)

        super().__init__(client_id, args, start_order_id=start_order_id)
        self.rth = False
        self.historical_end = False # Set to True once last of historical data is received
        self.HISTORICAL_BAR_DATA_TYPE = 'MIDPOINT' # MIDPOINT/TRADES/BID/ASK

        self.best_bid = None
        self.best_ask = None
        self.last = None # Last trade price, as received from RealTimeBars

        self.cancel_enable = False

        if not self.debug_mode:
            # Connect to server and start feeds
            self._connect()
            self._create_contract_obj()
            self._get_positions()
            self._cancel_orders()
            self._subscribe_mktData(tick_list='236,')
            self._get_historical_data()
        else:
            # Run test setup here
            self._connect()
            self._test_setup()


    ### Internal utility functions

    def _get_historical_data(self):
        multiplier = 500 # Add buffer to make sure we have enough data to find last crossover
        interval = multiplier*self.period * max(self.args.ema_periods, self.args.lrc_periods)
        start = dt.datetime.fromtimestamp(dt.datetime.now().timestamp() - interval)
        interval = ib.IbAPI._convert_start_end(start, dt.datetime.now())[0]
        period = ib.IbAPI._convert_period(self.period)

        super()._get_historical_data(
            end='',
            interval=interval,
            period=period,
            rth=int(self.rth),
            time_format=1,
            streaming=True)


    ### Modified EClient/EWrapper functions

    def historicalData(self, reqId, bar):
        super().historicalData(reqId, bar)
        self._on_update(bar)
        
    def historicalDataUpdate(self, reqId, bar):
        super().historicalDataUpdate(reqId, bar)
        self._on_update(bar)

    def historicalDataEnd(self, reqId:int, start:str, end:str):
        self.historical_end = True
        self._on_update(None)
        self._trim_df()


    ### Strategy-specific functions

    def _on_update(self, raw_bar):
        """
	Handling of raw candle updates from API

        If no bar data is provided (raw_bar is None), skip data processing
        and go straight to order execution

        Arguments
        ---------
        raw_bar (BarData): Unprocessed bar data received from API

        Returns
        ---------
        None

        """
        if raw_bar:
            # New candle received by API
            if self.period >= 86400:
                hour = 0
                minute = 0
            else:
                hour = raw_bar.date[10:12]
                minute = raw_bar.date[13:15]
            if len(raw_bar.date) > 16:
                second = raw_bar.date[16:18]
            else:
                second = 0
            date = [
                int(raw_bar.date[:4]),
                raw_bar.date[4:6],
                raw_bar.date[6:8],
                hour,
                minute,
                second
            ]
            date[1] = int(date[1]) if not date[1][0] == '0' else int(date[1][1:])
            date[2] = int(date[2]) if not date[2][0] == '0' else int(date[2][1:])
            if not (hour == 0 and minute == 0):
                date[3] = int(date[3]) if not date[3][0] == '0' else int(date[3][1:])
                date[4] = int(date[4]) if not date[4][0] == '0' else int(date[4][1:])
                date[5] = int(date[5]) if not date[5][0] == '0' else int(date[5][1:])

            _time = dt.datetime(date[0], date[1], date[2], date[3], date[4], date[5])
            candle = {
                'time': _time.timestamp(),
                'open': raw_bar.open,
                'high': raw_bar.high,
                'low': raw_bar.low,
                'close': raw_bar.close,
                'ema': 0,
                'ema_prev': 0,
                'lrc': 0,
                'lrc_prev': 0,
            }
            overnight = int(17.5*3600 + self.period)
            weekend = int(17.5*3600 +48*3600 + self.period)
            if self.historical_end:
                time_diff = int(_time.timestamp() - self.candles.iloc[-1]['time'])
                if not time_diff in (self.period, overnight, weekend):
                    return
            self.candles = self.candles.append(candle, ignore_index=True)
        else:
            # All historical candles fetched. Pass through to process historical data in df
            candle = None

        if self.historical_end:
            lrc_np = LINEARREG(self.candles['close'], timeperiod=self.args.lrc_periods)
            self.candles['lrc'] = lrc_np
            self.candles['lrc_prev'] = self.candles['lrc'].shift(1)
            ema_np = EMA(self.candles['close'], timeperiod=self.args.ema_periods)
            self.candles['ema'] = ema_np
            self.candles['ema_prev'] = self.candles['ema'].shift(1)

            if candle:
                # Write new candle to csv
                csv_row = [
                    candle['time'],
                    self.args.symbol,
                    candle['open'],
                    candle['high'],
                    candle['low'],
                    candle['close'],
                    self.candles['ema'].tolist()[-1],
                    self.candles['ema_prev'].tolist()[-1],
                    self.candles['lrc'].tolist()[-1],
                    self.candles['lrc_prev'].tolist()[-1],
                ]
                self.logger.warning(f'Candle: {csv_row}')
                self._write_csv_row((csv_row,), self.logfile_candles)

                # Execute trade if conditions allow
    #            row = self.candles.iloc[-1]
    #            if row['lrc'] > row['ema'] and not row['lrc_prev'] > row['ema_prev']:
    #                # Crossover. Send Buy order
    #                _side = 'Buy'
    #            elif row['lrc'] < row['ema'] and not row['lrc_prev'] < row['ema_prev']:
    #                # Crossover. Send Sell order
    #                _side = 'Sell'
    #            elif self.first_order:
    #                # Run just started. Go back and find previous crossover
    #                _side = self._find_prev_crossover()
    #                return ### tmp
    #            else:
    #                return
    #
            _hist = True if candle is None else False
            _side, hist_row = self._check_crossovers(hist=_hist)
            if self.first_order:
                # Skip trade if not allowed by existing position from prior run
#                if not self._check_position_status(_side):
#                    self.logger.critical(f'Last crossover side, {_side}, is not as expected, {self.trade_position}')
#                    raise ApplicationLogicError
#                    return ###
                _side = self._check_position_status(_side, live_candle=False)
            if not _side:
                # No crossovers in this candle, or prior agrees with position
                return

            ok_order = self._order_precheck(side=_side)
            if not ok_order:
                # Sell order, shorting not available and 0 trade_position
                return
            order_obj = self._place_order(_side)

            # Write order to csv
            pr = order_obj.lmtPrice if order_obj.orderType == 'LMT' else None
            if not hist_row is None and candle is None:
                candle_time = hist_row['time']
            elif hist_row is None and not candle is None:
                candle_time = candle['time']
            else:
                raise ApplicationLogicError
            csv_row = (
                order_obj.timestamp,
                candle_time,
                order_obj.order_id,
                self.args.symbol,
                _side,
                order_obj.orderType,
                order_obj.totalQuantity,
                pr)
            self._write_csv_row((csv_row,), self.logfile_orders)

    def _check_crossovers(self, hist=True):
        i = 1
        while True:
            row = self.candles.iloc[-i]
            if row['lrc'] > row['ema'] and not row['lrc_prev'] > row['ema_prev']:
                # Crossover. Send Buy order
                _side = 'Buy'
                if hist:
                    self.logger.warning(
                        f"Last crossover from historical data:"
                        f" {self.args.symbol}, {_side},"
                        f" time: {row['time']}"
                        f" open: {row['open']}"
                        f" high: {row['high']}"
                        f" low: {row['low']}"
                        f" close: {row['close']}"
                        f" ema: {row['ema']}"
                        f" ema_prev: {row['ema_prev']}"
                        f" lrc: {row['lrc']}"
                        f" lrc_prev: {row['lrc_prev']}")
            elif row['lrc'] < row['ema'] and not row['lrc_prev'] < row['ema_prev']:
                # Crossover. Send Sell order
                _side = 'Sell'
                if hist:
                    self.logger.warning(
                        f"Last crossover from historical data:"
                        f" {self.args.symbol}, {_side},"
                        f" time: {row['time']}"
                        f" open: {row['open']}"
                        f" high: {row['high']}"
                        f" low: {row['low']}"
                        f" close: {row['close']}"
                        f" ema: {row['ema']}"
                        f" ema_prev: {row['ema_prev']}"
                        f" lrc: {row['lrc']}"
                        f" lrc_prev: {row['lrc_prev']}")
            elif self.first_order:
                # Run just started. Keep iterating
                i += 1
                continue
            else:
                # Live candle that is not a crossover
                _side = None

            if not hist:
                # Only return row if this is hist data (used to write ts in csv)
                row = None
            return (_side, row)

    def _trim_df(self):
        max_len = max(
            self.args.ema_periods,
            self.args.lrc_periods)
        while True:
            if self.candles.shape[0] < max_len:
                raise DataCollectionError
            elif self.candles.shape[0] > max_len:
                trim = self.candles.shape[0] - max_len
                self.candles = self.candles.iloc[trim:]
            else:
                break


if __name__ == "__main__":
    args = parse_args()

    logfile = f'logs/{args.strategy}.log'
    if args.loglevel == 'debug':
        logging.basicConfig(filename=logfile, level=logging.DEBUG)
    elif args.loglevel == 'info':
        logging.basicConfig(filename=logfile, level=logging.INFO)
    elif args.loglevel == 'warning':
        logging.basicConfig(filename=logfile, level=logging.WARNING)
    main_cli(args)
