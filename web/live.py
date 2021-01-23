#!/usr/local/bin/python3

# -*- coding: utf-8 -*-
import dash
import dash_daq as daq
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output, State, ALL
from web import dash_helper
from .live_helper import TraderAction, draw_table, get_instrument_config
from .live_helper import state_to_rows, instrument_rows
from . import MAX_INSTRUMENTS

from app import app

"""
Layout and callbacks for live trading web interface
"""

trader_action = TraderAction(app.args.loglevel)

# Layout
layout = html.Div([
    dcc.Store(id='session-state'),
    dcc.Store(id='tcp-port'),
    html.H1(
        children='Trade Terminal',
    ),
    dcc.Link('Go back', href='/'),
    html.Br(),
    html.Br(),
    html.Div([
        html.Label(
            [
                "Account type",
                dcc.Dropdown(
                    id='paper-live-dropdown',
                    options=[
                        {'label': 'Live', 'value': 'live'},
                        {'label': 'Paper', 'value': 'paper'},
                    ],
                    placeholder="Account Type",
                    value='paper',
                    clearable=False,
                    persistence=False,
                    style={'width': '120px'}
                ),
            ], style={'width': '150px', 'display': 'inline-block'},
        ),
        html.Label(
            [
                "Connection type",
                dcc.Dropdown(
                    id='connection-type',
                    options=[
                        {'label': 'Gateway', 'value': 'gateway'},
                        {'label': 'TWS', 'value': 'tws'},
                    ],
                    placeholder="Connection type",
                    value='gateway',
                    clearable=False,
                    persistence=False,
                    style={'width': '120px'}
                ),
            ], style={'width': '150px', 'display': 'inline-block'},
        ),
    ], style={'width': '70%'}),
    html.Br(),
    html.Table(id='rows-content'),
    html.Br(),
    html.Button(id='add-instrument-row', n_clicks=0, children='Add instrument'),

    # Hidden table to give an output target to update_instruments' callback
    html.Table(
        [
            html.Tr(
                [
                    html.Td(c, style={'display': 'none'})
                    for c in instrument_rows(n, display='none')
                ]
            ) for n in range(0, MAX_INSTRUMENTS)
        ]),
])

# Callbacks
@app.callback(
            Output('tcp-port', 'data'),
            [Input('paper-live-dropdown', 'value'),
            Input('connection-type', 'value')],)
def update_port(paper_live, connection_type):
    if paper_live == 'paper':
        if connection_type == 'gateway':
            _val = 4002
        elif connection_type == 'tws':
            _val = 7497
    elif paper_live == 'live':
        if connection_type == 'gateway':
            _val = 4001
        elif connection_type == 'tws':
            _val = 7496
        _val = 4001
    else:
        raise ValueError
    trader_action.port = _val
    return _val


@app.callback(Output('session-state', 'data'),
            [Input('add-instrument-row', 'n_clicks')]
            + [Input(f'{n}-row-input-start-stop', 'on') for n in range(0, MAX_INSTRUMENTS)],
            [State(f'{n}-row-input-symbol', 'value') for n in range(0, MAX_INSTRUMENTS)]
            + [State(f'{n}-row-input-strategy', 'value') for n in range(0, MAX_INSTRUMENTS)]
            + [State(f'{n}-row-input-size', 'value') for n in range(0, MAX_INSTRUMENTS)]
            + [State(f'{n}-row-input-period', 'value') for n in range(0, MAX_INSTRUMENTS)]
            + [State(f'{n}-row-input-ema-periods', 'value') for n in range(0, MAX_INSTRUMENTS)]
            + [State(f'{n}-row-input-lrc-periods', 'value') for n in range(0, MAX_INSTRUMENTS)]
            + [State(f'{n}-row-input-order-type', 'value') for n in range(0, MAX_INSTRUMENTS)]
            + [State(f'{n}-row-input-start-stop', 'on') for n in range(0, MAX_INSTRUMENTS)])
def update_instruments(n_clicks, *startstop_rows):
    ctx = dash.callback_context
    start_stop = startstop_rows[:MAX_INSTRUMENTS]
    rows = startstop_rows[MAX_INSTRUMENTS:]

    instruments = get_instrument_config(rows, MAX_INSTRUMENTS)
    if '-row-input-start-stop' in ctx.triggered[0]['prop_id']:
        # Pick out updated instrument's row from state
        i = int(ctx.triggered[0]['prop_id'].split('-')[0])
        instrument = rows[i]
        _instruments = {i[0]:i[1:] for i in instruments}
        row_defaults = ('HACandles', 10, 1, 30, 14, 'MKT', True)
        if not instrument:
            # No-op without a user-inputted instrument name
            pass
        else:
            # Stopping: doesn't matter what field vals are
            # Starting: User-inputted instr name + defaults for unfilled fields
            new_row = [
                v if v else row_defaults[i]
                for i, v in enumerate(_instruments[instrument][:-1])
            ]
            new_row = tuple(new_row) + (_instruments[instrument][-1],)
            if not _instruments == {}:
                trader_action.updates((instrument,) + new_row)

    # Trigger new instrument to be added to trader
    rows = state_to_rows(trader_action.state, MAX_INSTRUMENTS)

    if ctx.triggered[0]['prop_id'] == 'add-instrument-row.n_clicks':
        rows = rows + (True,)

    return rows

@app.callback(
            Output('rows-content', 'children'),
            Input('session-state', 'data'),)
def update_rows(session_state):
    instruments = get_instrument_config(session_state, MAX_INSTRUMENTS)
    empty_row = ('', None, '', '', '', '', None, False)
    if instruments == [] or instruments == '':
        instruments = [empty_row]
    if session_state is None:
        pass
    elif len(session_state) == len(empty_row)*MAX_INSTRUMENTS + 1:
        instruments.append(empty_row)
    table = draw_table(instruments, MAX_INSTRUMENTS)
    return table
