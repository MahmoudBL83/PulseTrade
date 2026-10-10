import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { v2 } from "./api";
import { getSocket } from "./socket";
import type { Analysis, Candle, MarketExchange, OrderBook, Ticker, Trade } from "./types";
import { useAuth } from "../context/auth";

/** Exchange used for public market data: the user's active one, else the server default. */
export function useMarketExchange(): string {
  const { user, meta } = useAuth();
  const active = user?.exchanges.find((e) => e.isActive);
  if (active && !active.paper) return active.name;
  return meta?.default_exchange ?? "binance";
}

export function useTickers(quote = "USDT", limit = 300) {
  const ex = useMarketExchange();
  return useQuery({
    queryKey: ["tickers", ex, quote, limit],
    queryFn: ({ signal }) => v2.get<Ticker[]>("/market/tickers", { exchange: ex, quote, limit }, signal),
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}

export function useTicker(symbol: string, refetch = 5_000) {
  const ex = useMarketExchange();
  return useQuery({
    queryKey: ["ticker", ex, symbol],
    queryFn: ({ signal }) => v2.get<Ticker>("/market/ticker", { exchange: ex, symbol }, signal),
    refetchInterval: refetch,
    enabled: !!symbol,
  });
}

export function useCandles(symbol: string, timeframe: string, limit = 300) {
  const ex = useMarketExchange();
  return useQuery({
    queryKey: ["ohlcv", ex, symbol, timeframe, limit],
    queryFn: ({ signal }) => v2.get<Candle[]>("/market/ohlcv", { exchange: ex, symbol, timeframe, limit }, signal),
    refetchInterval: ["1m", "3m", "5m"].includes(timeframe) ? 10_000 : 30_000,
    enabled: !!symbol,
    placeholderData: (prev) => prev,
  });
}

export function useOrderBook(symbol: string, limit = 15) {
  const ex = useMarketExchange();
  return useQuery({
    queryKey: ["orderbook", ex, symbol, limit],
    queryFn: ({ signal }) => v2.get<OrderBook>("/market/orderbook", { exchange: ex, symbol, limit }, signal),
    refetchInterval: 3_000,
    enabled: !!symbol,
  });
}

export function useTrades(symbol: string, limit = 30) {
  const ex = useMarketExchange();
  return useQuery({
    queryKey: ["trades", ex, symbol, limit],
    queryFn: ({ signal }) => v2.get<Trade[]>("/market/trades", { exchange: ex, symbol, limit }, signal),
    refetchInterval: 3_000,
    enabled: !!symbol,
  });
}

export function useAnalysis(symbol: string, interval: string) {
  const ex = useMarketExchange();
  return useQuery({
    queryKey: ["analysis", ex, symbol, interval],
    queryFn: ({ signal }) => v2.get<Analysis>("/market/analysis", { exchange: ex, symbol, interval }, signal),
    refetchInterval: 60_000,
    enabled: !!symbol,
  });
}

export function useMarketExchanges() {
  return useQuery({
    queryKey: ["market-exchanges"],
    queryFn: () => v2.get<MarketExchange[]>("/market/exchanges"),
    staleTime: 10 * 60_000,
  });
}

export function useSymbols(quote?: string) {
  const ex = useMarketExchange();
  return useQuery({
    queryKey: ["symbols", ex, quote],
    queryFn: () => v2.get<string[]>("/market/symbols", { exchange: ex, quote, limit: 5000 }),
    staleTime: 30 * 60_000,
  });
}

/** Live price overlay pushed by the ccxt.pro streamer (MARKET_STREAM=1). */
export function useLiveTickers(enabled = true) {
  const [live, setLive] = useState<Record<string, { p: number; c: number; v: number }>>({});
  const { meta } = useAuth();
  const on = enabled && meta?.features.realtime !== false;
  useEffect(() => {
    if (!on) return;
    const s = getSocket();
    const onTickers = (rows: { s: string; p: number; c: number; v: number }[]) =>
      setLive((prev) => {
        const next = { ...prev };
        for (const r of rows) next[r.s] = { p: r.p, c: r.c, v: r.v };
        return next;
      });
    const subscribe = () => s.emit("subscribe_market");
    s.on("tickers", onTickers);
    s.on("connect", subscribe);
    if (s.connected) subscribe();
    return () => {
      s.emit("unsubscribe_market");
      s.off("tickers", onTickers);
      s.off("connect", subscribe);
    };
  }, [on]);
  return live;
}

export function mergeLive(t: Ticker, live: Record<string, { p: number; c: number; v: number }>): Ticker {
  const l = live[t.symbol];
  return l ? { ...t, last: l.p, percentage: l.c, quoteVolume: l.v || t.quoteVolume } : t;
}
