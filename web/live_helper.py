#!/usr/local/bin/python3

# -*- coding: utf-8 -*-
import os
import time
import random
import csv
import logging
import threading
import dash_core_components as dcc
import dash_html_components as html
import dash_daq as daq
import strats

from . import MAX_INSTRUMENTS

"""
Helper functions and object for interacting with strategy code
"""

class Object(object):
    pass


class ApplicationLogicError(Exception):
    pass


# Object used for interacting with IB_trader
class TraderAction:
    order_id_offset = 1000
    def __init__(self, loglevel):
        self.loglevel = loglevel
        self.state = {}
        self.port = None # 7496/7497 for TWS prod/paper, 4001/4002 for Gateway prod/paper
#        self.strategy = None
        self.initial_thread = True # After first thread starts, set to False
        self.next_order_id_start = 0
        self.logger = logging.getLogger()

    def updates(self, instrument):
        if not self.state.get(instrument[0]):
            # First time start up for this instrument/symbol
            self.state[instrument[0]] = {}
            self.state[instrument[0]]['args'] = instrument[1:]
            self._session_dump()
            self.state[instrument[0]]['order_id_start'] = self.next_order_id_start
            self.next_order_id_start += TraderAction.order_id_offset
            self.state[instrument[0]]['clientId'] = self._get_new_clientId()
            self._start(instrument[0])
            return
        if not self.state[instrument[0]]['args'][-1] == instrument[-1]:
            # Start/Stop button flipped from previous state
            self.state[instrument[0]]['args'] = instrument[1:]
            self._session_dump()
            if self.state[instrument[0]]['args'][-1]:
                self._start(instrument[0])
            else:
                self._stop(instrument[0])

    def _get_new_clientId(self):
        while True:
            _id = random.randint(0, 2*MAX_INSTRUMENTS)
            if not _id in {self.state[c].get('clientId') for c in self.state}:
                break
        return _id

    def _start(self, instrument):
        self.logger.warning(f"Connecting - {instrument}, {self.state[instrument]['clientId']}")
        if self.state[instrument].get('thread') and self.state[instrument]['thread'].is_alive:
            # Reconnect. Re-init strategy obj to reconnect in existing thread
            _args = self._make_args(instrument)
            self.state[instrument]['client'].__init__(
                self.state[instrument]['clientId'],
                _args,
                start_order_id=0)
            self.state[instrument]['client']._run()
        else:
            # First time connecting. Start new thread and init strategy obj
            _args = self._make_args(instrument)
#            StrategyCls = getattr(strats, self.strategy)
            StrategyCls = getattr(strats, self.state[instrument]['args'][0])
#            self.state[instrument]['client'] = MarketDataApp(
#                self.state[instrument]['clientId'],
#                _args,
#                start_order_id=self.next_order_id_start)
#            self.state[instrument]['client'] = HACandles(
#                self.state[instrument]['clientId'],
#                _args,
#                start_order_id=self.next_order_id_start)
            self.state[instrument]['client'] = StrategyCls(
                self.state[instrument]['clientId'],
                _args,
                start_order_id=self.next_order_id_start)
            if self.initial_thread:
                self.initial_thread = False
                # On startup, cancel any active unfilled orders account-wide
                self.state[instrument]['client'].reqGlobalCancel()
            self.state[instrument]['thread'] = threading.Thread(
                target=self.state[instrument]['client']._run, daemon=True)
            self.state[instrument]['thread'].start()

    def _stop(self, instrument, stop_thread=False):
        # Cancel any outstanding orders
        self.state[instrument]['client']._cancel_orders()

        # First do a disconnect with the server
        self.state[instrument]['client']._disconnect()

        self.logger.warning(f"Disconnected - {instrument}, {self.state[instrument]['clientId']}")
        
        if stop_thread:
            # Not implemented
            while True:
                if not self.state[instrument]['thread'].is_alive:
                    break
                else:
                    self.logger.info(f'WEB: Waiting for thread to stop: {instrument}')
                    time.sleep(0.5)
            self.logger.warning(f'WEB: Thread stopped: {instrument}')

    def _make_args(self, instrument):
        args = Object()
#        args.strategy = self.strategy
        args.strategy = self.state[instrument]['args'][0]
        args.currency = 'USD'
        args.loglevel = 'info'
        args.debug = False
        args.exchange = 'SMART'
        args.port = self.port
        args.security_type = 'STK'
        args.symbol = instrument
        args.order_size = self.state[instrument]['args'][1]
        args.bar_period = f"{str(int(self.state[instrument]['args'][2]*60))}s"
        args.ema_periods = self.state[instrument]['args'][3]
        args.lrc_periods = self.state[instrument]['args'][4]
        args.order_type = self.state[instrument]['args'][5][:3]
        args.inter_day = self.state[instrument]['args'][6]
        if self.state[instrument]['args'][5][4:] in ('last', 'mid'):
            args.quote_type = self.state[instrument]['args'][5][4:]
        else:
            args.quote_type = 'last'
        return args

    def _session_dump(self):
        #if not self.port in (4001, 7496):
        #    return
        session = ([(k,)+tuple(v['args']) for k,v in self.state.items()])
        session = [v for s in session for v in s]
        with open(f'logs/session_state.csv', 'w') as f:
            writer = csv.writer(f)
            writer.writerow(session)

    def _session_load(self):
        #if not self.port in (4001, 7496):
        #    return
        if not os.path.isfile('logs/session_state.csv'):
            # Create empty file
            with open('logs/session_state.csv', 'w') as f:
                pass
        with open(f'logs/session_state.csv', 'r') as f:
            reader = csv.reader(f)
            session = None
            make_row = lambda r: (
                r[0], r[1], int(r[2]), int(r[3]), int(r[4]),
                int(r[5]), r[6],
                True if r[7] == 'True' else False,
                True if r[8] == 'True' else False)
            for row in reader:
                i = 0
                while True:
                    row[i:i+9] = make_row(row[i:i+9])
                    i += 9
                    if i == len(row):
                        break
                session = row
        if not session:
            return session
        return [session[i*9:i*9+9] for i in range(int(len(session)/9))]

# Utility functions
def draw_table(data, len_table):
    cols = (
        'Symbol', 'Strategy', 'Size', 'Period (m)', 'EMA periods',
        'LRC periods', 'Order type', 'Continue', 'Start/Stop')
    table = [
        html.Tr([
            html.Th(c, style={'width': '60px', 'padding-right': '10px', 'padding-left': '0px', 'font-weight': 'normal', 'font-size': 12})
            for c in cols
        ])
    ] + [
        html.Tr([
            html.Td(c, style={'width': '60px', 'padding-right': '10px', 'padding-left': '0px', 'padding-top': '0px', 'padding-bottom': '0px', 'display': 'none'})
            for c in instrument_rows(n, display='none')
        ])
        if n >= len(data)
        else html.Tr([
            html.Td(c, style={'width': '60px', 'padding-right': '10px', 'padding-left': '0px', 'padding-top': '0px', 'padding-bottom': '0px',})
            for c in instrument_rows(n, data=data[n])
        ], style={'height': '5px'})
        for n in range(len_table)
    ]
    return table

def get_instrument_config(state, offset):
    # Parse raw state from update_instruments to get instrument config
    instruments = []
    if state:
        for i in range(offset):
            if state[i]:
                instruments.append((
                    state[i],
                    state[i+offset],
                    state[i+2*offset],
                    state[i+3*offset],
                    state[i+4*offset],
                    state[i+5*offset],
                    state[i+6*offset],
                    state[i+7*offset],
                    state[i+8*offset]))
    else:
        instruments = ''
    return instruments

def state_to_rows(state, offset):
    rows = (
        [None for _ in range(offset)]
        + ['' for _ in range(5*offset)]
        + [None for _ in range(offset)]
        + [False for _ in range(offset)]
        + [False for _ in range(offset)])
    for i, instrument in enumerate(state):
        rows[i] = instrument
        rows[i + offset] = state[instrument]['args'][0]
        rows[i + 2*offset] = state[instrument]['args'][1]
        rows[i + 3*offset] = state[instrument]['args'][2]
        rows[i + 4*offset] = state[instrument]['args'][3]
        rows[i + 5*offset] = state[instrument]['args'][4]
        rows[i + 6*offset] = state[instrument]['args'][5]
        rows[i + 7*offset] = state[instrument]['args'][6]
        rows[i + 8*offset] = state[instrument]['args'][7]
    return tuple(rows)

def instrument_rows(
        row_num,
        data=None,
        display='inline-block',
        persistence=False):
    if data is None:
        data=('', None, '', '', '', '', None, False, False)
    row = [
        dcc.Input(
            id=f'{row_num}-row-input-symbol',
            type='text',
            placeholder="AAPL",
            value=data[0],
            persistence_type='memory',
            persistence=persistence,
            style={'font-size': '10px', 'height': '25px', 'width': '60px', 'display': display}
        ),
        dcc.Dropdown(
            id=f'{row_num}-row-input-strategy',
            options=[
                {'label': 'EMA-LRC', 'value': 'EmaLrcCrossover'},
                {'label': 'HA', 'value': 'HACandles'},
            ],
            placeholder="EMA-LRC",
            value=data[1],
            persistence_type='memory',
            persistence=persistence,
            style={'vertical-align': 'middle', 'font-size': '10px', 'height': '25px', 'width': '60px', 'padding-right': '0px', 'display': display},
        ),
        dcc.Input(
            id=f'{row_num}-row-input-size',
            type='number',
            placeholder=10,
            value=data[2],
            persistence_type='memory',
            persistence=persistence,
            style={'font-size': '10px', 'height': '25px', 'width': '60px', 'padding-right': '0px', 'display': display}
        ),
        dcc.Input(
            id=f'{row_num}-row-input-period',
            type='number',
            placeholder=1,
            value=data[3],
            persistence_type='memory',
            persistence=persistence,
            style={'font-size': '10px', 'height': '25px', 'width': '60px', 'padding-right': '0px', 'display': display}
        ),
        dcc.Input(
            id=f'{row_num}-row-input-ema-periods',
            type='number',
            placeholder=30,
            value=data[4],
            persistence_type='memory',
            persistence=persistence,
            style={'font-size': '10px', 'height': '25px', 'width': '60px', 'padding-right': '0px', 'display': display}
        ),
        dcc.Input(
            id=f'{row_num}-row-input-lrc-periods',
            type='number',
            placeholder=14,
            value=data[5],
            persistence_type='memory',
            persistence=persistence,
            style={'font-size': '10px', 'height': '25px', 'width': '60px', 'padding-right': '0px', 'display': display}
        ),
        dcc.Dropdown(
            id=f'{row_num}-row-input-order-type',
            options=[
                {'label': 'MKT', 'value': 'MKT'},
                {'label': 'LMT (last)', 'value': 'LMT_last'},
                {'label': 'LMT (mid)', 'value': 'LMT_mid'},
            ],
            placeholder='MKT',
            value=data[6],
            persistence_type='memory',
            persistence=persistence,
            style={'vertical-align': 'middle', 'font-size': '10px', 'height': '25px', 'width': '60px', 'padding-right': '0px', 'display': display},
        ),
        daq.BooleanSwitch(
            id=f'{row_num}-row-input-continue-session',
            on=data[7],
            persistence_type='memory',
            persistence=True,
            style={'font-size': '10px', 'height': '25px', 'width': '60px', 'padding-right': '0px', 'display': display},
        ),
        daq.BooleanSwitch(
            id=f'{row_num}-row-input-start-stop',
            on=data[8],
            persistence_type='memory',
            persistence=persistence,
            style={'font-size': '10px', 'height': '25px', 'width': '60px', 'padding-right': '0px', 'display': display},
        ),
    ]
    return row

def _instrument_rows(
        row_num,
        data=None,
        display='inline-block',
        persistence=False,
        strategy_name='HACandles'):
    if strategy_name == 'HACandles':
        if data is None:
            data=('', '', '', None, False)
        row = [
            dcc.Input(
                id=f'{row_num}-row-input-symbol',
                type='text',
                value=data[0],
                persistence_type='memory',
                persistence=persistence,
                style={'width': '100px', 'display': display}
            ),
            dcc.Input(
                id=f'{row_num}-row-input-size',
                type='number',
                value=data[1],
                persistence_type='memory',
                persistence=persistence,
                style={'width': '100px', 'display': display}
            ),
            dcc.Input(
                id=f'{row_num}-row-input-period',
                type='number',
                value=data[2],
                persistence_type='memory',
                persistence=persistence,
                style={'width': '100px', 'display': display}
            ),
            dcc.Dropdown(
                id=f'{row_num}-row-input-order-type',
                options=[
                    {'label': 'MKT', 'value': 'MKT'},
                    {'label': 'LMT (last)', 'value': 'LMT_last'},
                    {'label': 'LMT (mid)', 'value': 'LMT_mid'},
                ],
                value=data[3],
                persistence_type='memory',
                persistence=persistence,
                style={'width': '100px', 'display': display},
            ),
            daq.BooleanSwitch(
                id=f'{row_num}-row-input-start-stop',
                on=data[4],
                persistence_type='memory',
                persistence=persistence,
                style={'width': '100px', 'display': display},
            ),
        ]
    elif strategy_name == 'EMALRCCrossover':
        if data is None:
            data=('', '', '', '', '', None, False)
        row = [
            dcc.Input(
                id=f'{row_num}-row-input-symbol',
                type='text',
                value=data[0],
                persistence_type='memory',
                persistence=persistence,
                style={'width': '100px', 'display': display}
            ),
            dcc.Input(
                id=f'{row_num}-row-input-size',
                type='number',
                value=data[1],
                persistence_type='memory',
                persistence=persistence,
                style={'width': '100px', 'display': display}
            ),
            dcc.Input(
                id=f'{row_num}-row-input-period',
                type='number',
                value=data[2],
                persistence_type='memory',
                persistence=persistence,
                style={'width': '100px', 'display': display}
            ),
            dcc.Input(
                id=f'{row_num}-row-input-ema-period',
                type='number',
                value=data[3],
                persistence_type='memory',
                persistence=persistence,
                style={'width': '100px', 'display': display}
            ),
            dcc.Input(
                id=f'{row_num}-row-input-lrc-period',
                type='number',
                value=data[4],
                persistence_type='memory',
                persistence=persistence,
                style={'width': '100px', 'display': display}
            ),
            dcc.Dropdown(
                id=f'{row_num}-row-input-order-type',
                options=[
                    {'label': 'MKT', 'value': 'MKT'},
                    {'label': 'LMT (last)', 'value': 'LMT_last'},
                    {'label': 'LMT (mid)', 'value': 'LMT_mid'},
                ],
                value=data[5],
                persistence_type='memory',
                persistence=persistence,
                style={'width': '100px', 'display': display},
            ),
            daq.BooleanSwitch(
                id=f'{row_num}-row-input-start-stop',
                on=data[6],
                persistence_type='memory',
                persistence=persistence,
                style={'width': '100px', 'display': display},
            ),
        ]
    return row
