rm -r dist/tmp
mkdir dist/tmp
mkdir dist/tmp/exchanges
mkdir dist/tmp/strategies
mkdir dist/tmp/web
mkdir dist/tmp/strats

# Backtester
cp backtesting/crypto_momentum/backtester.py dist/tmp/.
cp backtesting/crypto_momentum/config.json dist/tmp/.
cp backtesting/crypto_momentum/exchanges/__init__.py dist/tmp/exchanges/.
cp backtesting/crypto_momentum/exchanges/ib.py dist/tmp/exchanges/.
cp -r backtesting/crypto_momentum/ibapi dist/tmp/.
cp backtesting/crypto_momentum/strategies/__init__.py dist/tmp/strategies/.
cp backtesting/crypto_momentum/strategies/base.py dist/tmp/strategies/.
cp backtesting/crypto_momentum/strategies/ha.py dist/tmp/strategies/.
cp backtesting/crypto_momentum/strategies/ema_lrc.py dist/tmp/strategies/.
cp backtesting/crypto_momentum/strategies/willr_bband.py dist/tmp/strategies/.
cp backtesting/crypto_momentum/strategies/willr_bband_cross_mod.py dist/tmp/strategies/.
cp backtesting/crypto_momentum/strategies/willr_ema.py dist/tmp/strategies/.

# Trader & GUI
cp main.py dist/tmp/.
cp utils.py dist/tmp/.
cp app.py dist/tmp/.
cp web/__init__.py dist/tmp/web/.
cp web/backtesting.py dist/tmp/web/.
cp web/dash_helper.py dist/tmp/web/.
cp web/live_ema_lrc.py dist/tmp/web/.
cp web/live_ha.py dist/tmp/web/.
cp web/live_helper.py dist/tmp/web/.
cp strats/__init__.py dist/tmp/strats/.
cp strats/HA_candles.py dist/tmp/strats/.

cd dist/tmp
zip -r -X IB_trader.zip *
mv IB_trader.zip ../.
