import argparse
import random
import pandas as pd
import datetime as dt
from pytz import timezone

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order

RT_BAR_SIZE = 5

class MarketDataApp(EClient, EWrapper):
    def __init__(self, period, order_type, size):
        EClient.__init__(self, self)
        self.period = period
        self.order_type = order_type
        self.size = size
        self.candles = pd.DataFrame(
            data=[],
            columns=[
                'time',
                'open', 'high', 'low', 'close',
                'ha_open', 'ha_close', 'ha_high', 'ha_low', 'ha_color',
            ])
        self.cache = []
        self.tohlc = tuple()

    def error(self, reqId, errorCode, errorString):
        print("Error: ", reqId, " ", errorCode, " ", errorString)

    def nextValidId(self, orderId: int):
            super().nextValidId(orderId)
            self.nextorderId = orderId
            print('The next valid order id is: ', self.nextorderId)

    def orderStatus(
	    self, orderId, status, filled, remaining, avgFullPrice,
	    permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        print(
            'orderStatus - orderid:', orderId, 'status:', status,
            'filled', filled, 'remaining', remaining,
            'lastFillPrice', lastFillPrice)

    def openOrder(self, orderId, contract, order, orderState):
        print(
            'openOrder id:', orderId, contract.symbol, contract.secType,
            '@', contract.exchange, ':', order.action, order.orderType,
            order.totalQuantity, orderState.status)

    def execDetails(self, reqId, contract, execution):
        print(
            'Order Executed: ', reqId, contract.symbol,
            contract.secType, contract.currency, execution.execId,
            execution.orderId, execution.shares, execution.lastLiquidity)

    def historicalData(self, reqId, bar):
        print(
            "HistoricalData: ", reqId, "Date:", bar.date,
            "Open:", bar.open, "High:", bar.high,
            "Low:", bar.low, "Close:", bar.close)

    def realtimeBar(self, reqId, time, open_, high, low, close, volume, wap, count):
        super().realtimeBar(reqId, time, open_, high, low, close, volume, wap, count)
        self.tohlc = (time, open_, high, low, close)
        print(
            "RealTimeBar. TickerId:", reqId,
            dt.datetime.fromtimestamp(time), -1,
            self.tohlc[1:], volume, wap, count)
        #
        self._on_update()

    def _on_update(self):
        # Process 5s updates as received
        self._cache_update(self.tohlc)
        if self._check_period(self.tohlc):
            self._update_candles()
            self.cache = []
            if self.candles.shape[0] > 0:
                #
                self._check_order_conditions()

    def _check_period(self):
        # Return True if period ends at this update, else False
        _time = dt.datetime.fromtimestamp(self.tohlc[0])
        total_secs = _time.hour*60 + _time.minute*60 + _time.second
        if total_secs % self.period == 0:
            return True
        return False

    def _update_candles(self):
        # Bar completed
        if self.cache[-1][0] - self.cache[0][0] + RT_BAR_SIZE == self.period:
            print('--- Update the candle here')
            self.candles.append(self._calc_new_candle)
        elif self.cache[-1][0] - self.cache[0][0] + RT_BAR_SIZE < self.period:
            # First iteration. Not enough updates for a full period
            print('-- Not enough data for a candle', 'cache len:', len(self.cache))
        else:
            raise ValueError

    def _calc_new_candle(self):
        ohlc = (
            self.cache[0][1],
            max([u[2] for u in self.cache]),
            min([u[3] for u in self.cache]),
            self.cache[-1][4]
        )
        if self.candles.shape[0] > 0:
            # Can only calc heikin-ashi if we have previous data
            ha_ochl = (None, None, None, None) ### Placeholder
            ha_c = (ohlc[0] + ohlc[1] + ohlc[2] + ohlc[3])/4
            ha_o = (self.candles.iloc[-1:]['ha_open'] + self.candles.iloc[-1:]['ha_close'])/2
            ha_h = max(ohlc[1], ha_o, ha_c)
            ha_l = min(ohlc[2], ha_o, ha_c)
            ha_color = 'Red' if self.candles.iloc[-1:]['ha_close'] > ha_c else 'Green'
            ha_ochl = (ha_o, ha_c, ha_h, ha_l, ha_color)
        else:
            ha_ochl = (None, None, None, None, None)
        _pd = (self.cache[-1][0],) + ohlc + ha_ohlc
        return _pd

    def _cache_update(self, ohlc):
        # Still in the middle of a period. Cache data for processing at end of period
        self.cache.append(ohlc)

    def _check_order_conditions(self):
        # Check conditions for placing an order
        if self.candles.iloc[-1:]['ha_color'] == 'Red':
            # Create sell order
            size = 1 ### placeholder
            self._place_order(size)
        else:
            # Create buy order
            size = 2 ### placeholder
            self._place_order(size)

    def _place_order(self, size):
        pass

    def _create_order(self, size, side, price):
        order = Order()
        order.action = side.upper()
        order.totalQuantity(size)
        if self._check_ORH():
            order.orderType = 'LMT'
        else:
            order.orderType = self.order_type
        order.lmtPrice = price

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

def main():
    args = parse_args()

    app = MarketDataApp(args.bar_period, args.order_type, args.size)
    app.connect("127.0.0.1", args.port, random.randint(0, 999))
    app.nextorderId = None

    app.reqRealTimeBars(random.randint(0, 999), get_contract(args), RT_BAR_SIZE, "MIDPOINT", False, [])
    app.run()

def get_contract(args):
    contract = Contract()
    contract.symbol = args.symbol
    contract.secType = args.security_type
    contract.exchange = args.exchange
    contract.currency = args.currency
    return contract

def parse_args():
    argp = argparse.ArgumentParser()
    argp.add_argument("symbol", type=str, default=None)
    argp.add_argument(
        "-d", "--debug", action="store_true", help="turn on debug logging"
    )
    argp.add_argument(
        "-p", "--port", type=int, default=4002, help="local port for TWS connection"
    )
    argp.add_argument(
        "-c", "--currency", type=str, default="USD", help="currency for symbols"
    )
    argp.add_argument(
        "-e", "--exchange", type=str, default="SMART", help="exchange for symbols"
    )
    argp.add_argument(
        "-t", "--security-type", type=str, default="STK", help="security type for symbols"
    )
    argp.add_argument(
        "-b", "--bar-period", type=int, default=60, help="bar time period"
    )
    argp.add_argument(
        "-s", "--size", type=int, default=100, help="Order size"
    )
    argp.add_argument(
        "-o", "--order-type", type=str, default='MKT', help="Order type"
    )

    args = argp.parse_args()
    return args

if __name__ == "__main__":
    main()
