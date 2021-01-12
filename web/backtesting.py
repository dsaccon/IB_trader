#!/usr/local/bin/python3

# -*- coding: utf-8 -*-
import time
import datetime as dt
import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output, State, ALL

from web import dash_helper
import backtester

from app import app


class Object(object):
    pass


# Layout
layout = html.Div([
    dcc.Store(id='session-state-backtesting'),
    html.H1('Backtesting'),
    dcc.Link('Go back Home', href='/'),
    html.Br(),
    html.Br(),
    html.Div([
        html.Label(
            [
                "Strategy",
                dcc.Dropdown(
                    id='strategy-name',
                    options=[
                        {'label': 'HA', 'value': 'HA'},
                        {'label': 'EMA-LRC', 'value': 'EmaLrc'},
                    ],
                    placeholder="Strategy",
                    value='HA',
                    clearable=False,
                    persistence=False,
                    style={'width': '100px'}
                ),
            ], style={'width': '130px', 'display': 'inline-block', 'vertical-align': 'middle'},
        ),
        html.Label(
            [
                "Symbol",
                dcc.Input(
                    id='symbol-name',
                    type='text',
                    placeholder='AAPL',
                    persistence=False,
                    style={'width': '100px'}
                ),
            ], style={'width': '130px', 'display': 'inline-block', 'vertical-align': 'middle'},
        ),
        html.Label(
            [
                "Bar size",
                dcc.Dropdown(
                    id='bar-size',
                    options=[
                        {'label': '1secs', 'value': '1s'},
                        {'label': '5secs', 'value': '5s'},
                        {'label': '10secs', 'value': '10s'},
                        {'label': '15secs', 'value': '15s'},
                        {'label': '30secs', 'value': '30s'},
                        {'label': '1min', 'value': '1m'},
                        {'label': '2mins', 'value': '2m'},
                        {'label': '3mins', 'value': '3m'},
                        {'label': '5mins', 'value': '5m'},
                        {'label': '10mins', 'value': '10m'},
                        {'label': '15mins', 'value': '15m'},
                        {'label': '20mins', 'value': '20m'},
                        {'label': '30mins', 'value': '30m'},
                        {'label': '1hour', 'value': '1h'},
                        {'label': '2hours', 'value': '2h'},
                        {'label': '3hours', 'value': '3h'},
                        {'label': '4hours', 'value': '4h'},
                        {'label': '8hours', 'value': '8h'},
                        {'label': '1day', 'value': '1d'},
                        {'label': '1week', 'value': '1w'},
                        {'label': '1month', 'value': '1mo'},
                    ],
                    placeholder="Bar size",
                    value='1min',
                    clearable=False,
                    persistence=False,
                    style={'width': '100px'}
                ),
            ], style={'width': '130px', 'display': 'inline-block', 'vertical-align': 'middle'},
        ),
        html.Label(
            [
                "EMA Periods",
                dcc.Input(
                    id='ema-period',
                    type='number',
                    placeholder=30,
                    persistence=False,
                    style={'width': '100px'}
                ),
            ], style={'width': '130px', 'display': 'inline-block', 'vertical-align': 'middle'},
        ),
        html.Label(
            [
                "LRC Periods",
                dcc.Input(
                    id='lrc-period',
                    type='number',
                    placeholder=14,
                    persistence=False,
                    style={'width': '100px'}
                ),
            ], style={'width': '130px', 'display': 'inline-block', 'vertical-align': 'middle'},
        ),
        html.Label(
            [
                "Interval start",
                dcc.DatePickerSingle(
                    id='interval-start',
                    initial_visible_month=dt.date(2020, 9, 1),
                    date=dt.date(2020, 9, 1)
                ),
            ], style={'width': '165px', 'display': 'inline-block', 'vertical-align': 'middle'},
        ),
        html.Label(
            [
                "Start backtest",
                html.Button(
                    'Start',
                    id='start-backtest',
                    n_clicks=0,
                    style={'background-color': '#116AFF', 'color': 'white'}
                ),
            ], style={'width': '120px', 'display': 'inline-block', 'vertical-align': 'middle', 'color': 'white'},
        ),
        html.Label(
            [
                "Backtest running",
                dcc.Loading(
                    id="loading-1",
                    children=[
                        html.Div(id="loading-output")
                    ],
                    type="default"
                ),
            ], style={'width': '120px', 'display': 'inline-block', 'vertical-align': 'middle', 'color': 'white'},
        ),
    ], style={'width': '90%'}),
])

# Callbacks
@app.callback(
            Output('session-state-backtesting', 'data'),
            Output('loading-output', 'children'),
            [Input('strategy-name', 'value'),
            Input('symbol-name', 'value'),
            Input('bar-size', 'value'),
            Input('ema-period', 'value'),
            Input('lrc-period', 'value'),
            Input('interval-start', 'date'),
            Input('start-backtest', 'n_clicks'),],)
def callbacks(strategy_name, symbol_name, bar_size, ema_period, lrc_period, interval_start, start_backtest):
    ema_period = ema_period if ema_period else 30
    lrc_period = lrc_period if lrc_period else 14
    ema_lrc_periods = [ema_period, lrc_period]

    ctx = dash.callback_context

    if ctx.triggered[0]['prop_id'] == 'start-backtest.n_clicks':
        args = Object()
        args.name = strategy_name
        args.exchange = 'ib'
        args.symbol = symbol_name if symbol_name else 'AAPL'
        args.start = [int(n) for n in interval_start.split('-')]
        args.end = None
        args.period = [bar_size]
        args.num_periods = ema_lrc_periods
        args.file = None
        backtester.Backtest(args).run()

    return True, True
