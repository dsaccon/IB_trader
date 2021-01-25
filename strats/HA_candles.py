#!/usr/local/bin/python3

import pandas as pd
import datetime as dt
import os, sys
import logging

from strats.base import IBConnectionError, ApplicationLogicError
from strats.base import DataCollectionError
from strats.base import IBTrader, main_cli, parse_args


class HACandles(IBTrader):
    def __init__(self, client_id, args, start_order_id=None):
        df_cols = {
            'time': [],
            'open': [],
            'high': [],
            'low': [],
            'close': [],
            'ha_open': [],
            'ha_close': [],
            'ha_high': [],
            'ha_low': [],
            'ha_color': [],
        }
        self.candles = pd.DataFrame(df_cols)

        super().__init__(client_id, args, start_order_id=start_order_id)

        self.candle_calc_use_prev_ha = True
        self.RT_BAR_PERIOD = 5
        self.RT_BAR_DATA_TYPE = 'MIDPOINT' # MIDPOINT/TRADES/BID/ASK
        self.HISTORICAL_BAR_DATA_TYPE = 'MIDPOINT' # MIDPOINT/TRADES/BID/ASK
        self.cache = []
        self._tohlc = tuple() # Real-time 5s update data from IB

        #
        self.best_bid = None
        self.best_ask = None
        self.last = None # Last trade price, as received from RealTimeBars

        self.cancel_enable = False
        self.contract_details = None

        if not self.debug_mode:
            # Connect to server and start feeds
            self._connect()
            self._create_contract_obj()
            self._get_positions()
            self._cancel_orders()
            self._subscribe_mktData()
            self._subscribe_rtBars()
        else:
            # Run test setup here
            self._connect()
            self._test_setup()


    ### Internal utility functions


    ### Modified EClient/EWrapper functions

    def realtimeBar(self, *args):
        super().realtimeBar(*args)
        if self.last and self.best_bid and self.best_ask:
            # Don't start processing data until we get the first msgs from data feed
            self._on_update()


    ### Strategy-specific functions

    def _on_update(self):
        # Process 5s updates as received
        self._cache_update(self._tohlc)
        if self._check_period():
            # On HA candle tick point
            self._update_candles()
            self.cache = []
            if self.candles.shape[0] > 0:
                #
                self._check_order_conditions()

    def _check_period(self):
        # Return True if period ends at this update, else False
        _time = dt.datetime.fromtimestamp(self._tohlc[0])
        # Add bar period below becoz ts received from IB represents beginning of bar
        total_secs = _time.hour*3600 + _time.minute*60 + _time.second + self.RT_BAR_PERIOD
        if total_secs % self.period == 0:
            return True
        return False

    def _update_candles(self):
        # Bar completed
        if self.cache[-1][0] + self.RT_BAR_PERIOD - self.cache[0][0] == self.period:
            # Hit the candle period boundary. Update HA candles dataframe
            _pd = self._calc_new_candle()
            self.candles = self.candles.append(_pd, ignore_index=True)
            #
            bar_color = None
#            bar_color_prev = None
#            if self.candles.shape[0] > 1:
            if isinstance(self.candles['ha_color'].values[-1], str):
                # Check it is not an indecision candle
                bar_color = self.candles['ha_color'].values[-1].upper()
#            else:
#                # First HA candle not yet available
#                return
#            if self.candles.shape[0] > 2:
#                if isinstance(self.candles['ha_color'].values[-2], str):
#                    # Check it is not an indecision candle
#                    bar_color_prev = self.candles['ha_color'].values[-2].upper()
            self.logger.warning(f'Candle: {self.cache[-1][0]}, {self.args.symbol} - {bar_color}')
            csv_row = [col[1] for col in _pd.items()]
            csv_row.insert(1, self.args.symbol)
            self._write_csv_row((csv_row,), self.logfile_candles)
        elif self.cache[-1][0] + self.RT_BAR_PERIOD - self.cache[0][0] < self.period:
            # First iteration. Not enough updates for a full period
            self.logger.info('Not enough data for a candle')
        else:
            raise ValueError

    def _calc_new_candle(self):
        ohlc = (
            self.cache[0][1],
            max([u[2] for u in self.cache]),
            min([u[3] for u in self.cache]),
            self.cache[-1][4]
        )
        ha_c = (ohlc[0] + ohlc[1] + ohlc[2] + ohlc[3])/4
        if self.candle_calc_use_prev_ha:
            if self.candles.shape[0] == 0:
                # No prior HA candle is available, use prev raw candle open/close
                #ha_o = (self.candles['open'].values[-1] + self.candles['close'].values[-1])/2
                ha_o = (ohlc[0] + ohlc[3])/2
                ha_h = ohlc[1]
                ha_l = ohlc[2]
            else:
                ha_o = (self.candles['ha_open'].values[-1] + self.candles['ha_close'].values[-1])/2
                ha_h = max(ohlc[1], ha_o, ha_c)
                ha_l = min(ohlc[2], ha_o, ha_c)
        else:
            ha_o = (self.candles['open'].values[-1] + self.candles['close'].values[-1])/2
            ha_h = max(ohlc[1], ha_o, ha_c)
            ha_l = min(ohlc[2], ha_o, ha_c)
        if ha_c > ha_o:
            ha_color = 'Green'
        elif ha_c < ha_o:
            ha_color = 'Red'
        else:
            # Indecision candle
            ha_color = None
        ha_ochl = (ha_o, ha_c, ha_h, ha_l, ha_color)
        _pd = {
            'time': self._tohlc[0] ,
            'open': ohlc[0],
            'high': ohlc[1],
            'low': ohlc[2],
            'close': ohlc[3],
            'ha_open': ha_ochl[0],
            'ha_close': ha_ochl[1],
            'ha_high': ha_ochl[2],
            'ha_low': ha_ochl[3],
            'ha_color': ha_ochl[4],
        }
        return _pd

    def _cache_update(self, tohlc):
        # Still in the middle of a period. Cache data for processing at end of period
        self.cache.append(tohlc)

    def _check_order_conditions(self):
        if not isinstance(self.candles['ha_color'].values[-1], str):
            # Skip if first HA candle not yet available, or this is an indecision candle
            return
        #
        _side = 'Buy'
        if self.candles['ha_color'].values[-1] == 'Red':
            _side = 'Sell'
        #
        if self.first_order:
            # Skip trade if not allowed by existing position from prior run
            if not self._check_position_status(_side):
                return
            order_obj = self._place_order(_side)
            if self.args.order_size == self.order_size:
                self.first_order = False
                self.order_size *= 2
            #self.first_order = False
            #self.order_size *= 2
        elif not (
                self.candles['ha_color'].values[-1]
                    == self.candles['ha_color'].values[-2]):
            order_obj = self._place_order(_side)
        else:
            # Candle color same as previous. Do not place an order
            return

        # Write order to csv
        pr = order_obj.lmtPrice if order_obj.orderType == 'LMT' else None
        csv_row = (
            order_obj.timestamp, self.candles['time'].values[-1],
            order_obj.order_id, self.args.symbol,
            _side, order_obj.orderType, order_obj.totalQuantity, pr)
        self._write_csv_row((csv_row,), self.logfile_orders)


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
