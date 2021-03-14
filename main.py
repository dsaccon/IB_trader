import sys, os
import datetime as dt
import logging
import argparse


def main_web():
    import dash
    import dash_core_components as dcc
    import dash_html_components as html
    from dash.dependencies import Input, Output

    from app import app

    args = parse_args_web()
    app.args = args

    sys.path.append('backtesting/crypto_momentum')

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

    logging.warning(f'Starting: {dt.datetime.now().timestamp()}')
    app.run_server(host='0.0.0.0', port=8080, debug=True)


def parse_args_web():
    argp = argparse.ArgumentParser()
    argp.add_argument(
        "-l", "--loglevel", type=str, default='error', help="Logging options: debug/info/warning"
    )
    args = argp.parse_args()

    logfile = 'logs/IB_trader.log'
    if not os.path.isdir('logs/'):
        os.makedirs('logs')
    if args.loglevel.lower() == 'info':
        logging.basicConfig(filename=logfile, level=logging.INFO)
    elif args.loglevel.lower() == 'warning':
        logging.basicConfig(filename=logfile, level=logging.WARNING)
    elif args.loglevel.lower() == 'debug':
        logging.basicConfig(filename=logfile, level=logging.DEBUG)
    elif args.loglevel.lower() == 'error':
        logging.basicConfig(filename=logfile, level=logging.ERROR)
    else:
        raise ValueError

    return args


if __name__ == '__main__':
    argp = argparse.ArgumentParser()
    argp.add_argument("symbol", type=str, default=None, nargs='?')
    argp.add_argument("-l", "--loglevel", type=str, default=None)
    args = argp.parse_args()
    if args.symbol:
        # Run in CLI
        from strats import base, HACandles, EmaLrcCrossover

        args = base.parse_args()
        logfile = f'logs/IB_trader.log'
        if args.loglevel == 'debug':
            logging.basicConfig(filename=logfile, level=logging.DEBUG)
        elif args.loglevel == 'info':
            logging.basicConfig(filename=logfile, level=logging.INFO)
        elif args.loglevel == 'warning':
            logging.basicConfig(filename=logfile, level=logging.WARNING)
        base.main_cli(args)
    else:
        # Run in web browser
        main_web()
