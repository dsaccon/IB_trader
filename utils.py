import os
import argparse
import logging

def parse_args():
    argp = argparse.ArgumentParser()
    argp.add_argument(
        "-l", "--loglevel", type=str, default='warning', help="Logging options: debug/info/warning"
    )
    args = argp.parse_args()

    logfile = 'logs/IB_trader.log'
    if not os.path.isdir('logs/'):
        os.makedirs('logs')
    if args.loglevel == 'info':
        logging.basicConfig(filename=logfile, level=logging.INFO)
    elif args.loglevel == 'warning':
        logging.basicConfig(filename=logfile, level=logging.WARNING)
        #logging.basicConfig(level=logging.WARNING)
    else:
        raise ValueError

    return args
