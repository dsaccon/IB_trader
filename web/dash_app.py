# -*- coding: utf-8 -*-
import dash
import dash_daq as daq
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output, State

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

instrument_rows = [
    dcc.Input(id='input-symbol', type='text', value=None, style={'width': '100px', 'display': 'inline-block'}),
    dcc.Input(id='input-size', type='text', value=None, style={'width': '100px', 'display': 'inline-block'}),
    dcc.Input(id='input-period', type='text', value=None, style={'width': '100px', 'display': 'inline-block'}),
    dcc.Dropdown(
        id='order-type',
        options=[
            {'label': 'MKT', 'value': 'market'},
            {'label': 'LMT', 'value': 'limit'},
        ],
        value=None,
        persistence_type='memory',
        persistence=True,
        style={'width': '100px', 'display': 'inline-block'},
    ),
    daq.BooleanSwitch(
        id='start-stop',
        on=False,
        persistence_type='memory',
        persistence=True,
        style={'width': '100px', 'display': 'inline-block'},
    ),
]

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
#    html.Tr([
#        html.Td(
#    html.Div(id='rows-content'),
    html.Table(id='rows-content'),
    html.Br(),
    html.Button(id='add-instrument-row', n_clicks=0, children='Add instrument'),
])


def _dynamic_rows(num_rows):
    _ = html.Div(className='row', children=[
        html.Div(instrument_rows)
        for n in range(0, num_rows)
    ])
    return _

def dynamic_rows(num_rows):
    table = [
        html.Tr([html.Th(c, style={'width': '150px'}) for c in ('Symbol', 'Size', 'Bar period (s)', 'Order type', 'Start/Stop')])
    ] + [
        html.Tr([html.Td(c, style={'width': '150px'}) for c in instrument_rows])
        for n in range(0, num_rows)
    ]
    return table

@app.callback(Output('rows-content', 'children'),
              [Input('add-instrument-row', 'n_clicks')],)
def update_output(n_clicks):
    return dynamic_rows(n_clicks)

if __name__ == '__main__':
    app.run_server(debug=True)
