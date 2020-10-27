# -*- coding: utf-8 -*-
import dash
import dash_daq as daq
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output, State

import IB_trader_multi

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

num_instruments = 0

def instrument_rows(row_num, display='inline-block'):
    row = [
        dcc.Input(
            id=f'{row_num}-row-input-symbol',
            type='text',
            value=None,
            persistence_type='memory',
            persistence=True,
            style={'width': '100px', 'display': display}
        ),
        dcc.Input(
            id=f'{row_num}-row-input-size',
            type='number',
            value=None,
            persistence_type='memory',
            persistence=True,
            style={'width': '100px', 'display': display}
        ),
        dcc.Input(
            id=f'{row_num}-row-input-period',
            type='number',
            value=None,
            persistence_type='memory',
            persistence=True,
            style={'width': '100px', 'display': display}
        ),
        dcc.Dropdown(
            id=f'{row_num}-row-input-order-type',
            options=[
                {'label': 'MKT', 'value': 'market'},
                {'label': 'LMT', 'value': 'limit'},
            ],
            value=None,
            persistence_type='memory',
            persistence=True,
            style={'width': '100px', 'display': display},
        ),
        daq.BooleanSwitch(
            id=f'{row_num}-row-input-start-stop',
            on=False,
            persistence_type='memory',
            persistence=True,
            style={'width': '100px', 'display': display},
        ),
    ]
    return row

app.layout = html.Div([
    html.H1(
        children='Trade Terminal',
        style={
            'textAlign': 'center',
        }
    ),
    html.Div([
	dcc.Dropdown(
	    id='paper_live-dropdown',
	    options=[
		{'label': 'Live', 'value': 'live'},
		{'label': 'Paper', 'value': 'paper'},
	    ],
            placeholder="Account Type",
	    value=None,
            persistence=False,
            style={'width': '35%'}
	),
    ]),
    html.Br(),
    daq.BooleanSwitch(
        id='connect-to-server',
        on=False,
        persistence_type='memory',
        persistence=None,
        label="Connect to server",
        labelPosition="left",
        style={'width': '200px', 'display': 'inline-block'},
    ),
    html.Br(),
    html.Br(),
    # Invisible table to allow give an output target to update_instruments' callback
    html.Table([html.Tr([html.Td(c, style={'display': 'none'}) for c in instrument_rows(n, display='none')]) for n in range(0, 100)]),
    html.Table(id='rows-content'),
    html.Br(),
    html.Button(id='add-instrument-row', n_clicks=0, children='Add instrument'),

    # Invisible div to give an output target to update_instruments' callback
    html.Div(id='dummy-div', style={'display': 'none'})
])

def create_table(num_rows):
    table = [
        html.Tr([html.Td(c, style={'width': '150px'}) for c in instrument_rows(n, display='none')])
        for n in range(0, num_rows)
    ]
    return table

def dynamic_rows(num_rows):
    table = [
        html.Tr([html.Th(c, style={'width': '150px'}) for c in ('Symbol', 'Size', 'Bar period (s)', 'Order type', 'Start/Stop')])
    ] + [
        html.Tr([html.Td(c, style={'width': '150px'}) for c in instrument_rows(n)])
        for n in range(0, num_rows)
    ]
    return table

@app.callback(Output('rows-content', 'children'),
            [Input('add-instrument-row', 'n_clicks')],)
def draw_rows(n_clicks):
    num_instruments = n_clicks # global
    table = dynamic_rows(n_clicks)
    return table

@app.callback(Output('dummy-div', 'title'),
            [Input(f'{n}-row-input-start-stop', 'on') for n in range(0, 100)],
            [State(f'{n}-row-input-symbol', 'value') for n in range(0, 100)]
            + [State(f'{n}-row-input-size', 'value') for n in range(0, 100)]
            + [State(f'{n}-row-input-period', 'value') for n in range(0, 100)]
            + [State(f'{n}-row-input-order-type', 'value') for n in range(0, 100)])
def update_instruments(start_stop, *state):
    print('**', start_stop)
    print('---')
    print('**', state)

if __name__ == '__main__':
    app.run_server(debug=True)
