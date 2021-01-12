import sys
import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output

import utils

from app import app

args = utils.parse_args()
app.args = args

sys.path.append('backtesting/')

from web import live, backtesting

app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    html.Div(id='page-content')
])


home_page = html.Div([
    dcc.Link('Live trading', href='/live'),
    html.Br(),
    dcc.Link('Backtesting', href='/backtesting'),
])


@app.callback(Output('page-content', 'children'),
              Input('url', 'pathname'))
def display_page(pathname):
    if pathname == '/live':
        return live.layout
    elif pathname == '/backtesting':
        return backtesting.layout
    elif pathname == '/':
        return home_page
    else:
        return '404'

if __name__ == '__main__':
    app.run_server(host='0.0.0.0', port=8080, debug=True)
