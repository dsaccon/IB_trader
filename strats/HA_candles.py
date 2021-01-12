#!/usr/local/bin/python3

import argparse
import random
import pandas as pd
import numpy as np
import datetime as dt
import os, sys
import csv
import time
from pytz import timezone
import logging
import copy
import concurrent.futures

from talib.abstract import LINEARREG, EMA

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.ticktype import TickTypeEnum
from ibapi.order import Order

from exchanges import ib

pd.set_option('display.max_colwidth', 10)
pd.set_option('display.float_format', lambda x: '%.f' % x)


class IBConnectionError(Exception):
    pass


class ApplicationLogicError(Exception):
    pass


class DataCollectionError(Exception):
    pass


def codes(code):
    # https://interactivebrokers.github.io/tws-api/message_codes.html
    if len(str(code)) == 4 and str(code).startswith('1'):
        return 'SYSTEM'
    elif len(str(code)) == 4 and str(code).startswith('21'):
        return 'WARNING'
    elif len(str(code)) == 3 and str(code).startswith('5'):
        return 'CLIENT ERROR'
    elif len(str(code)) == 3 and int(str(code)[0]) in {1,2,3,4,5} or len(str(code)) == 5:
        return 'TWS ERROR'
    else:
        raise ValueError


class IBTrader(EClient, EWrapper):
    """
        IB client for interacting with Gateway and TWS

        Arguments
        ---------
        client_id (int):      unique client ID per instrument traded
        args (obj):           runtime args, passed in from user (cli/gui)
        start_order_id (int): order IDs are incremented starting from this
            If start_order_id == None, then use self.reqIds() to increment order Ids
    """

    def __init__(self, client_id, args, start_order_id=None):
        EClient.__init__(self, self)
        self.start_time = dt.datetime.now().timestamp()
        self.client_id = client_id
        self.args = args
        self.start_order_id = start_order_id
        self.logger = logging.getLogger(__name__)

        self.debug_mode = False
        if args.debug:
            self.debug_mode = True

        self.logger.info(
            f'Starting with args -'
            f' symbol: {self.args.strategy},'
            f' symbol: {self.args.symbol},'
            f' order_type: {self.args.order_type},'
            f' quote_type: {self.args.quote_type},'
            f' order_size: {self.args.order_size},'
            f' bar_period: {self.args.bar_period}')

        self._setup_csv_logs()

        if args.bar_period.endswith('s'):
            self.period = int(args.bar_period[:-1])
        elif args.bar_period.endswith('m'):
            self.period = int(args.bar_period[:-1])*60
        elif args.bar_period.endswith('h'):
            self.period = int(args.bar_period[:-1])*60*60
        elif args.bar_period.endswith('d'):
            self.period = int(args.bar_period[:-1])*60*60*24
        elif args.bar_period.endswith('w'):
            self.period = int(args.bar_period[:-1])*60*60*24*7
        self.order_type = args.order_type
        self.order_size = args.order_size

        #
        if not hasattr(self, 'mktData_reqId'):
            # First time init of object
            self.mktData_reqId = random.randint(0, 999)
        if not hasattr(self, 'rtBars_reqId'):
            # First time init of object
            while True:
                self.rtBars_reqId = random.randint(0, 999)
                if not self.rtBars_reqId == self.mktData_reqId:
                    break
        if not hasattr(self, 'historicalData_reqId'):
            # First time init of object
            while True:
                self.historicalData_reqId = random.randint(0, 999)
                if not self.historicalData_reqId in (self.mktData_reqId, self.mktData_reqId):
                    break

        if not hasattr(self, 'order_id'):
            # Allow for obj to re __init__() and not reset self.order_id
            if self.start_order_id is not None:
                self.order_id = self.start_order_id
            else:
                self._update_order_id()
                #self.order_id = 0 # Placeholder. Will get updated prior to any order, via _place_order()
        else:
            pass
            #self._update_order_id()


    def _run(self):
        self.run()


    ### Internal utility functions

    def _setup_csv_logs(self):
        self.logfile_candles = f'logs/{self.args.strategy}_candles.csv'
        self.logfile_orders = f'logs/{self.args.strategy}_orders.csv'
        logfile_candles_rows = ('time', 'symbol') + tuple([c for c in self.candles.columns[1:]])
        logfile_orders_rows = ('time', 'order_id', 'symbol', 'side', 'order_type', 'size', 'price')
        if not os.path.isdir('logs/'):
            os.makedirs('logs')
        if not os.path.exists(self.logfile_candles):
            self._write_csv_row((logfile_candles_rows,), self.logfile_candles, newfile=True)
        else:
            self._write_csv_row(
                ([self.start_time, '', self.args.symbol] + ['' for _ in logfile_candles_rows][3:],),
                self.logfile_candles)
        if not os.path.exists(self.logfile_orders):
            self._write_csv_row((logfile_orders_rows,), self.logfile_orders, newfile=True)
        else:
            self._write_csv_row(
                ([self.start_time, '', self.args.symbol] + ['' for _ in logfile_orders_rows][3:],),
                self.logfile_orders,)

    def _cancel_orders(self, cycle_all=False):
        # 2 methods below for canceling orders

        if cycle_all:
            # Cycle through all possible orders from this session and cancel
            for _id in range(self.start_order_id, self.order_id + 1):
                self.cancelOrder(_id)
        else:
            self.cancel_enable = True
            self.reqOpenOrders() # openOrder() will receive all open orders and do cancelOrder() there

    def _connect(self):
        self.logger.info(f'port: {self.args.port}, client_id {self.client_id}')
        self.connect("127.0.0.1", self.args.port, self.client_id)
        while not self.isConnected():
            self.logger.info(f'Connecting to IB.. {self.args.symbol}, {self.client_id}')
            time.sleep(0.5)
        self.logger.info(f'Connected - {self.args.symbol}, {self.client_id}')

    def _disconnect(self):
        self.disconnect()
        while self.isConnected():
            self.logger.info(f'Disconnecting from IB.. {self.args.symbol}, {self.client_id}')
            time.sleep(0.5)
        self.logger.info(f'Disconnected - {self.args.symbol}, {self.client_id}')

    def _subscribe_mktData(self):
        self.reqMktData(self.mktData_reqId, self.contract, '', False, False, [])

    def _subscribe_rtBars(self):
        self.reqRealTimeBars(
            self.rtBars_reqId,
            self.contract,
            self.RT_BAR_PERIOD,
            self.RT_BAR_DATA_TYPE, False, [])

    def _get_historical_data(
            self,
            end='',
            interval='1 M',
            period='1 min',
            rth=1,
            time_format=1,
            streaming=False):
        self.reqHistoricalData(
            self.historicalData_reqId,
            self.contract,
            end,
            interval,
            period,
            self.HISTORICAL_BAR_DATA_TYPE,
            rth,
            time_format,
            streaming,
            [])

    def _get_positions(self): ### tmp
        self.reqPositions()

    def _test_setup(self):
        # Sandbox to set up test env

        #self.reqOpenOrders()
        self._get_historical_data()
#        self._get_positions() ### tmp
#        self._get_contract_details(random.randint(0,9999), self.contract)
#        self._create_test_order()
#        self._create_test_order()
#        self._create_test_order()
#        self._create_test_order()
#        self._create_test_order()

    def _create_test_order(self, side='Buy'):
        # Easy way to tweak order obj params to create contrived test orders
        obj = self._create_order_obj(side)
        obj.orderType = 'LMT'
        obj.lmtPrice = round(0.01 + random.randint(1,100)/100, 2)
        self._place_order('Buy', order_obj=obj)

    def _get_contract_details(self, reqId, contract):
        self.reqContractDetails(reqId, contract)
        #Error checking loop - breaks from loop once contract details are obtained
#        for err_check in range(50):
#            if not self.contract_details[reqId]:
#                time.sleep(0.1)
#            else:
#                break
        #Raise if error checking loop count maxed out (contract details not obtained)
#        if err_check == 49:
#            raise Exception('error getting contract details')

    def _place_order(self, side, order_obj=None):
        if not order_obj:
            order_obj = self._create_order_obj(side)
        self.logger.warning(
            f'Order: {order_obj.order_id},'
            f' {self.contract.symbol}, {order_obj.action},'
            f' {order_obj.orderType}, {order_obj.totalQuantity},'
            f' {order_obj.lmtPrice}')
        self.placeOrder(order_obj.order_id, self.contract, order_obj)
        return order_obj

    def _update_order_id(self):
        # The proper way to do this is call self.reqIds(), but have seen issues here
        # Use manual option for now
        if self.start_order_id is not None:
            self.order_id += 1
        else:
            #
            _order_id = self.order_id
            self.reqIds(1) # Initiate update to self.order_id, will be done in nextValidId()
            if _order_id == self.order_id:
                time.sleep(5.0) # Give time for self.order_id to update

    def _check_ORH(self):
        # return True if outside regular hours, else False
        now = dt.datetime.now(timezone('US/Eastern'))
        if now.hour*60 + now.minute < 570:
            # Pre-market
            return True
        elif now.hour >= 16:
            # After-market
            return True
        else:
            # Regular trading hours
            return False

    def _create_order_obj(self, side):
        order = Order()
        order.action = side.upper()
        order.totalQuantity = self.order_size
        if self._check_ORH():
            # Note here: self.order_type can deviate from self.args.order_type
            order.orderType = self.order_type = 'LMT'
            order.outsideRth = True # Do to avoid seeing warning msg
        else:
            order.orderType = self.order_type = self.args.order_type
        price = 0
        if self.order_type == 'LMT':
            order.sweepToFill = True
            if self.args.quote_type == 'mid':
                price = round((self.best_bid + self.best_ask)/2, 2)
            elif self.args.quote_type == 'last':
                price = self.last
        order.lmtPrice = price
        #
        self._update_order_id()
        order.order_id = self.order_id
        order.timestamp = dt.datetime.now().timestamp()
        return order

    def _create_contract_obj(self):
        contract = Contract()
        contract.symbol = self.args.symbol
        contract.secType = self.args.security_type
        contract.exchange = self.args.exchange
        contract.currency = self.args.currency
        return contract


    ### Modified EClient/EWrapper functions

    def error(self, reqId, errorCode, errorString):
        self.logger.warning(f'{codes(errorCode)}, {errorCode}, {errorString}')

    def tickPrice(self, reqId, tickType, price, attrib):
        if tickType == 1 and reqId == self.mktData_reqId:
            # Bid
            self.best_bid = price
            self.logger.info(f'Bid update: {price}')
        if tickType == 2 and reqId == self.mktData_reqId:
            # Ask
            self.best_ask = price
            self.logger.info(f'Ask update: {price}')
        if tickType == 4 and reqId == self.mktData_reqId:
            # Last
            self.last = price
            self.logger.info(f'Last trade update: {price}')

    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)
        #self.order_id = orderId
        #logger.info(f'The next valid order id is: {self.order_id}')

    def orderStatus(
	    self, orderId, status, filled, remaining, avgFullPrice,
	    permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        self.logger.info(
            f'orderStatus - orderid: {orderId}, status: {status}'
            f'filled: {filled}, remaining: {remaining}'
            f'lastFillPrice: {lastFillPrice}')

    def openOrder(self, orderId, contract, order, orderState):
        if self.cancel_enable:
            self.logger.warning(
                f'Canceling Order: {orderId}, {contract.symbol}, {contract.secType},'
                f'@, {contract.exchange}, {order.action}, {order.orderType},'
                f'{order.totalQuantity}, {orderState.status}')
            self.cancelOrder(orderId)
            return
        self.logger.info(
            f'openOrder id: {orderId}, {contract.symbol}, {contract.secType},'
            f'@, {contract.exchange}, {order.action}, {order.orderType},'
            f'{order.totalQuantity}, {orderState.status}')

    def openOrderEnd(self):
        """This is called at the end of a given request for open orders."""
        super().openOrderEnd()
        self.cancel_enable = False

    def execDetails(self, reqId, contract, execution):
        self.logger.warning(
            f'Order Executed: {reqId}, {contract.symbol},'
            f'{contract.secType}, {contract.currency}, {execution.execId},'
            f'{execution.orderId}, {execution.shares}, {execution.lastLiquidity}')

    def historicalData(self, reqId, bar):
        self.logger.info(
            f'HistoricalData: {reqId}, Date: {bar.date},'
            f'Open: {bar.open}, High: {bar.high},'
            f'Low: {bar.low}, Close: {bar.close}')

    def historicalDataUpdate(self, reqId, bar):
        self.logger.info(
            f'HistoricalDataUpdate: {reqId}, Date: {bar.date},'
            f'Open: {bar.open}, High: {bar.high},'
            f'Low: {bar.low}, Close: {bar.close}')

    def position(self, account:str, contract:Contract, position:float, avgCost:float):
        self.logger.info(
            f'account: {account}',
            f'contract: {contract}',
            f'position: {position}',
            f'avgCost: {avgCost}')

    def realtimeBar(self, reqId, time, open_, high, low, close, volume, wap, count):
        super().realtimeBar(reqId, time, open_, high, low, close, volume, wap, count)
        self._tohlc = (time, open_, high, low, close)
        self.logger.warning(
            f'RealTimeBar. TickerId: {reqId}, {self.args.symbol}, '
            f'{dt.datetime.fromtimestamp(time)}, OHLC: '
            f'{self._tohlc[1:]}, {volume}, {wap}, {count}')
        #
#        if self.last and self.best_bid and self.best_ask:
#            # Don't start processing data until we get the first msgs from data feed
#            self._on_update()


    ### Strategy-specific functions

    def _on_update(self):
        pass

    def _write_csv_row(self, row, filename, newfile=False):
        if newfile:
            mode = 'w'
        else:
            mode = 'a'
        with open(filename, mode) as csvfile:
            csvwriter = csv.writer(csvfile)
            csvwriter.writerows(row)


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
        self.first_order = True # Set to False after first order

        #
        self.best_bid = None
        self.best_ask = None
        self.last = None # Last trade price, as received from RealTimeBars

        self.cancel_enable = False

        self.contract = self._create_contract_obj()
        self.contract_details = None

        if not self.debug_mode:
            # Connect to server and start feeds
            self._connect()
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
            order_obj = self._place_order(_side)
            self.first_order = False
            self.order_size *= 2
        elif not self.candles['ha_color'].values[-1] == self.candles['ha_color'].values[-2]:
            order_obj = self._place_order(_side)
        else:
            # Candle color same as previous. Do not place an order
            return

        # Write order to csv
        pr = order_obj.lmtPrice if order_obj.orderType == 'LMT' else None
        csv_row = (order_obj.timestamp, order_obj.order_id, self.args.symbol, _side, order_obj.orderType, order_obj.totalQuantity, pr)
        self._write_csv_row((csv_row,), self.logfile_orders)


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

        self.contract = self._create_contract_obj()

        if not self.debug_mode:
            # Connect to server and start feeds
            self._connect()
            self._cancel_orders()
            self._subscribe_mktData()
            self._get_historical_data()
        else:
            # Run test setup here
            self._connect()
            self._test_setup()


    ### Internal utility functions

    def _get_historical_data(self):
        interval = self.period * max(self.args.ema_periods, self.args.lrc_periods)
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
        self._trim_df()


    ### Strategy-specific functions

    def _on_update(self, bar):
        if self.period >= 86400:
            hour = 0
            minute = 0
        else:
            hour = bar.date[10:12]
            minute = bar.date[13:15]
        if len(bar.date) > 16:
            second = bar.date[16:18]
        else:
            second = 0
        date = [
            int(bar.date[:4]),
            bar.date[4:6],
            bar.date[6:8],
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
        row = {
            'time': _time.timestamp(),
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
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
        self.candles = self.candles.append(row, ignore_index=True)

        if self.historical_end:
            lrc_np = LINEARREG(self.candles['close'], timeperiod=self.args.lrc_periods)
            self.candles['lrc'] = lrc_np
            self.candles['lrc_prev'] = self.candles['lrc'].shift(1)
            ema_np = EMA(self.candles['close'], timeperiod=self.args.ema_periods)
            self.candles['ema'] = ema_np
            self.candles['ema_prev'] = self.candles['ema'].shift(1)

            # Write new candle to csv
            csv_row = [
                row['time'],
                self.args.symbol,
                row['open'],
                row['high'],
                row['low'],
                row['close'],
                self.candles['ema'].tolist()[-1],
                self.candles['ema_prev'].tolist()[-1],
                self.candles['lrc'].tolist()[-1],
                self.candles['lrc_prev'].tolist()[-1],
            ]
            self._write_csv_row((csv_row,), self.logfile_candles)

            # Execute trade if conditions allow
            row = self.candles.iloc[-1]
            if row['lrc'] > row['ema'] and not row['lrc_prev'] > row['ema_prev']:
                # Crossover. Send Buy order
                _side = 'Buy'
                #self._place_order('Buy')
            elif row['lrc'] < row['ema'] and not row['lrc_prev'] < row['ema_prev']:
                # Crossover. Send Sell order
                _side = 'Sell'
                #self._place_order('Sell')
            else:
                return

            order_obj = self._place_order(_side)

            # Write order to csv
            pr = order_obj.lmtPrice if order_obj.orderType == 'LMT' else None
            csv_row = (
                order_obj.timestamp,
                order_obj.order_id,
                self.args.symbol,
                _side,
                order_obj.orderType,
                order_obj.totalQuantity,
                pr)
            self._write_csv_row((csv_row,), self.logfile_orders)

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

def main_cli(args):
    # For running the app from the command line

    while True:
        clientIds = list({random.randint(0, 999) for _ in args.symbol})
        if len(clientIds) == len(args.symbol):
            break
    objs = {}
    cls = getattr(sys.modules['__main__'], args.strategy)
    for i, instr in enumerate(args.symbol):
        _args = copy.deepcopy(args)
        _args.symbol = instr
        objs[instr] = cls(clientIds[i], _args, start_order_id=1000*i)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(args.symbol)) as executor:
        futures = []
        for instr in args.symbol:
            futures.append(executor.submit(objs[instr]._run))


def parse_args():
    argp = argparse.ArgumentParser()
    argp.add_argument("symbol", type=str, default=None, nargs='+')
    argp.add_argument(
        "-l", "--loglevel", type=str, default='warning',
        help="Logging options: debug/info/warning"
    )
    argp.add_argument(
        "-d", "--debug", action='store_const', const=True, default=False,
        help="Run in debug mode. IBTrader will init but not start feeds. And open up a debugger"
    )
    argp.add_argument(
        "--strategy", type=str, default='HACandles',
        help="Strategy name ('HACandles', 'EmaLrcCrossover')"
    )
    argp.add_argument(
        "-p", "--port", type=int, default=4002,
        help="local port for connection: 7496/7497 for TWS prod/paper, 4001/4002 for Gateway prod/paper"
    )
    argp.add_argument(
        "-c", "--currency", type=str, default="USD",
        help="currency for symbols"
    )
    argp.add_argument(
        "-e", "--exchange", type=str, default="SMART",
        help="exchange for symbols"
    )
    argp.add_argument(
        "-t", "--security-type", type=str, default="STK",
        help="security type for symbols"
    )
    argp.add_argument(
        "-b", "--bar-period", type=str, default='1m',
        help="bar time period (suffix as 's', 'm', 'h', 'd', 'w')"
    )
    argp.add_argument(
        "-s", "--order-size", type=int, default=100,
        help="Order size"
    )
    argp.add_argument(
        "-o", "--order-type", type=str, default='MKT',
        help="Order type (MKT/LMT)"
    )
    argp.add_argument(
        "-q", "--quote-type", type=str, default='last',
        help="Quote type (mid/last). Only used with LMT order type"
    )

    args = argp.parse_args()
    return args


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
