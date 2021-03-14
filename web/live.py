#!/usr/local/bin/python3

import random
import time
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
            ], style={'width': '120px', 'display': 'inline-block'},
        ),
    ], style={'width': '70%'}),
    html.Br(),
    daq.BooleanSwitch(
        id='load-previous-session',
        on=False,
        label="Load previous session",
        persistence_type='memory',
        persistence=False,
        style={'width': '150px'},
    ),
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
            [Input('add-instrument-row', 'n_clicks'),
            Input('load-previous-session', 'on')]
            + [Input(f'{n}-row-input-start-stop', 'on') for n in range(0, MAX_INSTRUMENTS)]
            + [Input(f'{n}-row-input-continue-session', 'on') for n in range(0, MAX_INSTRUMENTS)],
            [State(f'{n}-row-input-symbol', 'value') for n in range(0, MAX_INSTRUMENTS)]
            + [State(f'{n}-row-input-strategy', 'value') for n in range(0, MAX_INSTRUMENTS)]
            + [State(f'{n}-row-input-size', 'value') for n in range(0, MAX_INSTRUMENTS)]
            + [State(f'{n}-row-input-period', 'value') for n in range(0, MAX_INSTRUMENTS)]
            + [State(f'{n}-row-input-ema-periods', 'value') for n in range(0, MAX_INSTRUMENTS)]
            + [State(f'{n}-row-input-lrc-periods', 'value') for n in range(0, MAX_INSTRUMENTS)]
            + [State(f'{n}-row-input-order-type', 'value') for n in range(0, MAX_INSTRUMENTS)]
            + [State(f'{n}-row-input-continue-session', 'on') for n in range(0, MAX_INSTRUMENTS)]
            + [State(f'{n}-row-input-start-stop', 'on') for n in range(0, MAX_INSTRUMENTS)])
def update_instruments(n_clicks, load_previous_session, *args):
    load_previous_session = args[:MAX_INSTRUMENTS]
    startstop_rows = args[MAX_INSTRUMENTS:]
    ctx = dash.callback_context
    start_stop = startstop_rows[:MAX_INSTRUMENTS]
    rows = startstop_rows[MAX_INSTRUMENTS:]
    instruments = get_instrument_config(rows, MAX_INSTRUMENTS) ### new

    if 'row-input-continue-session' in ctx.triggered[0]['prop_id']:
        i = int(ctx.triggered[0]['prop_id'].split('-')[0])
        continue_session = instruments[i][-2]
        instrument = rows[i]

        # Check if live session (trade_action) has been created
        _instrument = trader_action.state.get(instrument)
        if _instrument:
            prev_state = trader_action.state.get(instrument)['args']
            new_state = tuple(prev_state[:-2]) + (continue_session, prev_state[-1])
            trader_action.state[instrument]['args'] = new_state
            trader_action._session_dump()

        # Update rows state for browser to persist selection
        _state = {k:{'args':v['args']} for k,v in trader_action.state.items()}
        _state[instrument] = {'args': instruments[i][1:]}
        rows = state_to_rows(_state, MAX_INSTRUMENTS)
        return rows

    if 'load-previous-session' in ctx.triggered[0]['prop_id']:
        sessions = trader_action._session_load()
        if sessions:
            state = {
                sess[0]:{'args': sess[1:]}
                for sess in sessions
                if sess[-2]
            }
            rows = state_to_rows(state, MAX_INSTRUMENTS)
            for i, sess in enumerate(sessions):
                if sess[-2]:
                    time.sleep(0.2 + random.random()/5) # Throttle to ease load on system
                    trader_action.updates(sess)
            return rows

    #instruments = get_instrument_config(rows, MAX_INSTRUMENTS)
    if '-row-input-start-stop' in ctx.triggered[0]['prop_id']:
        # Pick out updated instrument's row from state
        i = int(ctx.triggered[0]['prop_id'].split('-')[0])
        instrument = rows[i]
        _instruments = {i[0]:i[1:] for i in instruments}
        row_defaults = ('EmaLrcCrossover', 10, 1, 30, 14, 'MKT', False, True)
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
    empty_row = ('', None, '', '', '', '', None, False, False)
    if instruments == [] or instruments == '':
        instruments = [empty_row]
    if session_state is None:
        pass
    elif len(session_state) == len(empty_row)*MAX_INSTRUMENTS + 1:
        instruments.append(empty_row)
    table = draw_table(instruments, MAX_INSTRUMENTS)
    return table
