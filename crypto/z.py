import lightweight_charts as lcw
import time
chart = lcw.Chart()

chart.add_price_series("BTCUSDT", source="tradingview")
chart.add_price_series("ETHUSD", source="tradingview")

chart.start()

start_time = time.time()
daily_candles = daily_candles = chart.get_candles("BTCUSDT", interval=lcw.Interval.INTERVAL_1_DAY)
print("Time taken: ", time.time() - start_time)
print(daily_candles)