// Shapes returned by the Flask API (see crypto/api_v2.py and crypto/models.py).

export interface Plan {
  id: number;
  type: string;
  type_ar?: string | null;
  price: number | null;
  duration?: number | null;
  max_bots: number;
  max_sma: number;
  trial_days: number | null;
  stripe_id?: string | null;
}

export interface ExchangeConn {
  id: number;
  name: string;
  isActive: boolean;
  demo: boolean;
  paper: boolean;
  has_api_key: boolean;
  has_api_secret: boolean;
  has_password: boolean;
}

export interface Preferences {
  theme: "dark" | "light" | "system";
  lang: "en" | "ar";
  currency: string;
  channels?: Record<string, unknown>;
}

export interface User {
  id: number;
  email: string;
  firstName: string | null;
  lastName: string | null;
  img: string | null;
  balance_usd: number;
  balance_btc: number;
  is_verified: boolean;
  ip_check: boolean;
  totp_enabled: boolean;
  demo: boolean;
  created_at: string | null;
  last_login_at: string | null;
  preferences: Preferences;
  subType: Plan | null;
  plan: Plan | null;
  plan_expires: string | null;
  exchanges: ExchangeConn[];
  active_exchange: string | null;
  unread_notifications: number;
  is_admin: boolean;
}

export interface Ticker {
  symbol: string;
  last: number;
  bid: number;
  ask: number;
  high: number;
  low: number;
  open: number;
  change: number;
  percentage: number;
  baseVolume: number;
  quoteVolume: number;
  timestamp: number;
  source?: string;
}

export type Candle = [number, number, number, number, number, number];

export interface OrderBook {
  symbol: string;
  bids: [number, number][];
  asks: [number, number][];
  timestamp: number;
  source?: string;
}

export interface Trade {
  id: string;
  timestamp: number;
  price: number;
  amount: number;
  side: "buy" | "sell";
}

export type Recommendation = "STRONG_BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG_SELL";

export interface AnalysisBlock {
  RECOMMENDATION: Recommendation;
  BUY: number;
  SELL: number;
  NEUTRAL: number;
  COMPUTE?: Record<string, "BUY" | "SELL" | "NEUTRAL">;
}

export interface Analysis {
  symbol: string;
  interval: string;
  price: number;
  summary: AnalysisBlock;
  oscillators: AnalysisBlock;
  moving_averages: AnalysisBlock;
  indicators: Record<string, number | null>;
}

export interface Signal {
  symbol: string;
  price: number;
  RECOMMENDATION: Recommendation;
  BUY: number;
  SELL: number;
  NEUTRAL: number;
  oscillators: Recommendation;
  moving_averages: Recommendation;
  rsi: number | null;
}

export interface Overview {
  gainers: Ticker[];
  losers: Ticker[];
  volume: Ticker[];
  breadth: { up: number; down: number; flat: number };
  source?: string;
}

export interface PortfolioAsset {
  currency: string;
  free: number;
  used: number;
  total: number;
  price: number;
  value: number;
  value_btc: number;
  share: number;
  exchanges: string[];
}

export interface Portfolio {
  assets: PortfolioAsset[];
  total_usd: number;
  total_btc: number;
  errors: { exchange: string; error: string }[];
  updated_at: string;
  stats: Record<string, number>;
}

export interface Performance {
  sharpe: number;
  sortino: number;
  volatility: number;
  max_drawdown: number;
  cagr: number;
  calmar: number;
  best_day: number;
  worst_day: number;
  return_pct: number;
  days: number;
  bots_total: number;
  bots_active: number;
  bot_profit: number;
  bot_deals: number;
  bot_win_rate: number;
  best_bot: { id: number; name: string; profit: number } | null;
  worst_bot: { id: number; name: string; profit: number } | null;
  smart_trades_total: number;
  smart_trades_active: number;
  smart_trade_profit: number;
  trades_30d: number;
  volume_30d: number;
}

export interface Bot {
  id: number;
  name: string;
  strategy: string;
  exchange: string;
  symbol: string;
  symbols: string[] | null;
  pair_type: string;
  base_currency: string;
  quote_currency: string;
  start_order_type: string;
  isActive: boolean;
  is_hidden: boolean;
  deal_started: boolean;
  take_profit: boolean;
  buy_price: number;
  deal_start_price: number;
  price_now: number;
  last_price: number;
  sell_price: number;
  amount: number;
  units: number;
  total_volume: number;
  tp_type: string;
  tp_percent: number;
  tp_percent_type: string;
  tp_price: number;
  stop_loss: boolean;
  stop_loss_price: number;
  stop_loss_price_percent: number;
  trailing_take_profit: boolean;
  trailing_stop_loss: boolean;
  trailing_deviation: number;
  safety_orders_count: number;
  safety_orders_count_active: number;
  safety_orders_filled: number;
  total_trades: number;
  total_profit: number;
  conds: Condition[];
  tp_conds: Condition[];
  auto_restart: boolean;
  cooldown_between_deals: number;
  open_deals_and_stop: number;
  last_open_trade_time: string | null;
  last_error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface BotDetail extends Bot {
  safety_orders_size: number;
  safety_orders_size_scale: number;
  safety_orders_deviation: number;
  safety_orders_deviation_scale: number;
  safety_orders_count_max_active: number;
  max_price: number | null;
  min_price: number | null;
  min_volume: number | null;
  min_profit: boolean;
  min_profit_type: string;
  min_profit_percent: number;
  close_deal_action: number;
  timeout: number;
  timeout_type: number;
  Close_deal_after_timeout: boolean;
  stop_loss_time_out: boolean;
  stop_loss_time_out_time: number;
  amount_type: number;
  safety_orders_size_type: number;
  safety_orders: { id: number; isOpened: boolean; isClosed: boolean; isFilled: boolean; orderId: string | null; amount: number | null; price: number | null }[];
  transactions: Transaction[];
}

export interface Condition {
  indicator: string;
  conds: Record<string, string | number>;
  value?: number | string | null;
}

export interface BotTemplate {
  id: string;
  name: string;
  description: string;
  [key: string]: unknown;
}

export interface SmartTrade {
  id: number;
  name: string | null;
  trade_type: string;
  exchange: string;
  symbol: string;
  base_currency: string;
  quote_currency: string;
  buy_price: number;
  bought_price: number;
  order_type: string;
  units: number;
  amount: number;
  stop_loss: boolean;
  take_profit: boolean;
  last_price: number;
  price_now: number;
  stop_loss_price: number;
  stop_loss_price_percent: number;
  trailing_take_profit: boolean;
  trailing_stop_loss: boolean;
  trailing_deviation: number;
  take_profit_quantities: [number, number][];
  take_profit_index: number;
  tpTriggerType: string;
  isActive: boolean;
  deal_started: boolean;
  buy_trigger_price: number;
  move_to_break_even: boolean;
  total_profit: number;
  use_assets: boolean;
  created_at: string | null;
  transactions?: Transaction[];
}

export interface Transaction {
  id: number;
  timestamp: string | null;
  created_at: string | null;
  value: number;
  price: number | null;
  type: string;
  exchange: string;
  amount: number;
  symbol: string;
  status: boolean;
  err_msg: unknown;
  bot_id: number | null;
  sma_id: number | null;
}

export interface Notification {
  id: number;
  content: string;
  type: string;
  date: string;
  exchange: string | null;
  read: boolean;
}

export interface WatchItem {
  id: number;
  exchange: string;
  symbol: string;
  note: string | null;
  position: number;
  ticker: Ticker | null;
}

export interface PriceAlert {
  id: number;
  exchange: string;
  symbol: string;
  condition: "above" | "below" | "change_pct";
  target: number;
  reference_price: number | null;
  note: string | null;
  repeat: boolean;
  active: boolean;
  triggered_at: string | null;
  trigger_count: number;
  last_price: number | null;
  created_at: string | null;
}

export interface JournalEntry {
  id: number;
  title: string;
  body: string | null;
  symbol: string | null;
  side: string | null;
  entry_price: number | null;
  exit_price: number | null;
  amount: number | null;
  tags: string[];
  mood: string | null;
  pnl: number | null;
  created_at: string | null;
}

export interface PaperSummary {
  connected: boolean;
  account: null | {
    starting_balance: number;
    equity: number;
    pnl: number;
    pnl_pct: number;
    fee_rate: number;
    assets: { currency: string; free: number; used: number; total: number; price: number; value: number }[];
    reset_at: string | null;
    open_orders: number;
  };
}

export interface BacktestDeal {
  open_time: string;
  close_time: string;
  entry: number;
  average: number;
  exit: number;
  safety_orders: number;
  invested: number;
  pnl: number;
  pnl_pct: number;
  reason: "take_profit" | "stop_loss";
  fees: number;
  duration_h: number;
}

export interface BacktestResult {
  params: Record<string, number | string>;
  stats: {
    deals: number;
    wins: number;
    losses: number;
    win_rate: number;
    realized_pnl: number;
    return_pct: number;
    max_capital: number;
    max_drawdown_pct: number;
    avg_duration_h: number;
    avg_safety_orders: number;
    buy_and_hold_pct: number;
    candles: number;
    from: string | null;
    to: string | null;
    profit_factor: number | null;
    expectancy: number;
    avg_win: number;
    avg_loss: number;
    calmar: number;
    exposure_pct: number;
  };
  deals: BacktestDeal[];
  open_deal: null | { open_time: string; average: number; safety_orders: number; invested: number; unrealized: number };
  equity: { t: number; equity: number }[];
  source: string;
}

export interface OptimizeResult {
  metric: string;
  runs: number;
  best: OptimizeRow | null;
  top: OptimizeRow[];
  heatmap: null | { x: string; y: string; xs: number[]; ys: number[]; cells: [number, number, number][] };
  candles: number;
}

export interface OptimizeRow {
  params: Record<string, number>;
  score: number;
  stats: { deals: number; win_rate: number; return_pct: number; max_drawdown_pct: number; profit_factor: number | null; calmar: number; realized_pnl: number };
}

export interface Insights {
  global: {
    total_market_cap_usd: number;
    total_volume_usd: number;
    market_cap_change_24h: number;
    btc_dominance: number;
    eth_dominance: number;
    active_cryptocurrencies: number;
    markets: number;
    source: string;
  };
  fear_greed: { current: FngPoint; history: FngPoint[]; source: string };
  trending: { id: string; symbol: string; name: string; image: string | null; rank: number | null; price: number | null; change_24h: number | null; source: string }[];
  defi: { total_tvl: number; stablecoin_supply: number | null; chains: { name: string; tvl: number; symbol: string | null; share: number }[]; source: string };
  attribution: Record<string, { name: string; url: string | null }>;
  updated_at: string;
}

export interface FngPoint {
  value: number;
  classification: string;
  timestamp: number;
}

export interface Coin {
  id: string;
  symbol: string;
  name: string;
  image: string | null;
  rank: number | null;
  price: number;
  market_cap: number;
  volume: number;
  change_24h: number;
  change_7d: number;
  source: string;
}

export interface Ticket {
  id: number;
  subject: string;
  status: string;
  user_id: number;
  user: User | null;
  messages: TicketMessage[];
  created_at: string | null;
  updated_at: string | null;
}

export interface TicketMessage {
  id: number;
  content: string;
  is_admin: boolean;
  user_id: number;
  created_at: string;
  subject?: string;
}

export interface KbCategory {
  id: number;
  title: string;
  title_ar: string | null;
  img: string | null;
  views: number;
  post_count: number;
}

export interface KbPost {
  id: number;
  title: string;
  content: string | null;
  excerpt?: string;
  writer: string;
  img: string | null;
  views: number;
  lang: string;
  category_id: number | null;
  created_at: string | null;
}

export interface Meta {
  name: string;
  build: string;
  demo: boolean;
  serverless: boolean;
  engine: string;
  market_data: string;
  default_exchange: string;
  features: { mail: boolean; stripe: boolean; tap: boolean; telegram: boolean; paper: boolean; realtime: boolean };
}

export interface MarketExchange {
  id: string;
  name: string;
  active: boolean;
  paper?: boolean;
}

export interface LoginEvent {
  id: number;
  event: string;
  success: boolean;
  ip: string | null;
  user_agent: string | null;
  created_at: string | null;
}
