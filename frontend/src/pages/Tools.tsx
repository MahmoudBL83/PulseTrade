import { useMemo, type ReactNode } from "react";
import { Calculator, Coins, Layers, Percent, Scale, Target, TrendingUp } from "lucide-react";
import { useT } from "../i18n";
import { fmtAmount, fmtFixed, fmtPct, fmtPrice, fmtUsd, trendClass } from "../lib/format";
import { cn, toNumber, useLocalStorage } from "../lib/utils";
import { Card, CardBody, CardHeader, Field, Input, Notice, PageHeader, Segmented, Table, Td, Th } from "../components/ui";
import { AreaChart } from "../components/charts";
import { DealBar } from "../components/trading";

type Tool = "position" | "dca" | "pnl" | "breakeven" | "rr" | "compound";

/* ------------------------------------------------------------------ helpers */

function Num({ label, value, onChange, suffix, hint }: { label: ReactNode; value: string; onChange: (v: string) => void; suffix?: ReactNode; hint?: ReactNode }) {
  return (
    <Field label={label} hint={hint}>
      <Input inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)} suffix={suffix} />
    </Field>
  );
}

function Result({ label, value, tone, big }: { label: ReactNode; value: ReactNode; tone?: string; big?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line/60 py-2 last:border-0">
      <span className="text-sm text-muted">{label}</span>
      <span className={cn("num text-end font-semibold text-fg", big ? "text-lg" : "text-sm", tone)}>{value}</span>
    </div>
  );
}

/** Form state persisted per calculator so numbers survive navigation. */
function useForm<T extends Record<string, string>>(key: string, initial: T) {
  const [v, setV] = useLocalStorage<T>(`pt.tools.${key}`, initial);
  const merged = { ...initial, ...v };
  const set = (k: keyof T) => (val: string) => setV({ ...merged, [k]: val });
  return [merged, set, (next: Partial<T>) => setV({ ...merged, ...next })] as const;
}

function Layout({ form, results, children }: { form: ReactNode; results: ReactNode; children?: ReactNode }) {
  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card><CardBody className="grid gap-4 sm:grid-cols-2">{form}</CardBody></Card>
        <Card><CardBody>{results}</CardBody></Card>
      </div>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ position size */

function PositionSize() {
  const t = useT();
  const [f, set] = useForm("position", { balance: "1000", risk: "1", entry: "100", stop: "95", fee: "0.1" });
  const r = useMemo(() => {
    const balance = toNumber(f.balance), risk = toNumber(f.risk), entry = toNumber(f.entry), stop = toNumber(f.stop), fee = toNumber(f.fee) / 100;
    if (!balance || !entry || !stop || entry === stop) return null;
    const riskAmount = (balance * risk) / 100;
    const perUnit = Math.abs(entry - stop) + (entry + stop) * fee;
    const units = riskAmount / perUnit;
    const notional = units * entry;
    return { riskAmount, units, notional, leverage: notional / balance, dist: (Math.abs(entry - stop) / entry) * 100, long: stop < entry };
  }, [f]);
  return (
    <Layout
      form={
        <>
          <Num label={t("tools.balance", "Account balance")} value={f.balance} onChange={set("balance")} suffix="USDT" />
          <Num label={t("tools.risk", "Risk per trade")} value={f.risk} onChange={set("risk")} suffix="%" hint={t("tools.risk_hint", "Most traders risk 0.5–2%.")} />
          <Num label={t("bt.entry", "Entry")} value={f.entry} onChange={set("entry")} />
          <Num label={t("order.stop", "Stop loss")} value={f.stop} onChange={set("stop")} />
          <Num label={t("tools.fee", "Fee per side")} value={f.fee} onChange={set("fee")} suffix="%" />
        </>
      }
      results={
        r ? (
          <>
            <Result big label={t("tools.pos_size", "Position size")} value={`${fmtAmount(r.units)} ${t("tools.units", "units")}`} />
            <Result label={t("tools.notional", "Position value")} value={fmtUsd(r.notional)} />
            <Result label={t("tools.at_risk", "Amount at risk")} value={fmtUsd(r.riskAmount)} tone="text-down" />
            <Result label={t("tools.stop_dist", "Stop distance")} value={fmtPct(r.dist, 2, false)} />
            <Result label={t("order.side", "Side")} value={r.long ? t("bots.long", "Long") : t("bots.short", "Short")} tone={r.long ? "text-up" : "text-down"} />
            <Result label={t("tools.leverage", "Leverage needed")} value={r.leverage > 1 ? `${fmtFixed(r.leverage, 2)}×` : t("tools.none", "None")} tone={r.leverage > 1 ? "text-primary" : undefined} />
          </>
        ) : <p className="text-sm text-muted">{t("tools.fill", "Fill in the fields to see the result.")}</p>
      }
    />
  );
}

/* ------------------------------------------------------------------ DCA ladder */

function DcaPlanner() {
  const t = useT();
  const [f, set] = useForm("dca", { price: "60000", base: "100", so: "100", count: "5", dev: "1.5", step: "1.2", vol: "1.5", tp: "1.5", side: "long" });
  const plan = useMemo(() => {
    const price = toNumber(f.price), base = toNumber(f.base), so = toNumber(f.so), dev = toNumber(f.dev), step = toNumber(f.step, 1), vol = toNumber(f.vol, 1), tp = toNumber(f.tp);
    const count = Math.max(0, Math.min(50, Math.floor(toNumber(f.count))));
    const long = f.side !== "short";
    if (!price) return null;
    // Same math as the bot engine / POST /api/v2/bots/preview.
    let cum = 0, qty = base / price, cost = base;
    const rows = [{ index: 0, deviation: 0, price, size: base, total: cost, average: price, tp: long ? price * (1 + tp / 100) : price * (1 - tp / 100) }];
    for (let i = 0; i < count; i++) {
      cum += dev * step ** i;
      const level = long ? price * (1 - cum / 100) : price * (1 + cum / 100);
      const size = so * vol ** i;
      qty += level > 0 ? size / level : 0;
      cost += size;
      const avg = qty ? cost / qty : 0;
      rows.push({ index: i + 1, deviation: cum, price: level, size, total: cost, average: avg, tp: long ? avg * (1 + tp / 100) : avg * (1 - tp / 100) });
    }
    return { rows, capital: cost, coverage: cum, long };
  }, [f]);
  return (
    <Layout
      form={
        <>
          <Field label={t("order.side", "Side")} className="sm:col-span-2">
            <Segmented value={f.side} onChange={set("side")} options={[{ value: "long", label: t("bots.long", "Long"), tone: "up" }, { value: "short", label: t("bots.short", "Short"), tone: "down" }]} />
          </Field>
          <Num label={t("tools.start_price", "Start price")} value={f.price} onChange={set("price")} />
          <Num label={t("bots.base_order", "Base order")} value={f.base} onChange={set("base")} suffix="USDT" />
          <Num label={t("bots.so_size", "Safety order size")} value={f.so} onChange={set("so")} suffix="USDT" />
          <Num label={t("bots.so_count", "Max safety orders")} value={f.count} onChange={set("count")} />
          <Num label={t("bots.so_dev", "Price deviation")} value={f.dev} onChange={set("dev")} suffix="%" />
          <Num label={t("bots.so_step", "Step scale")} value={f.step} onChange={set("step")} suffix="×" />
          <Num label={t("bots.so_vol", "Volume scale")} value={f.vol} onChange={set("vol")} suffix="×" />
          <Num label={t("bots.tp", "Take profit")} value={f.tp} onChange={set("tp")} suffix="%" />
        </>
      }
      results={
        plan ? (
          <>
            <Result big label={t("bots.max_capital", "Max capital needed")} value={fmtUsd(plan.capital)} />
            <Result label={t("bots.coverage", "Price drop covered")} value={fmtPct(plan.coverage, 2, false)} />
            <Result label={t("tools.last_level", "Last safety order at")} value={fmtPrice(plan.rows[plan.rows.length - 1].price)} />
            <Result label={t("tools.final_avg", "Average after all fills")} value={fmtPrice(plan.rows[plan.rows.length - 1].average)} />
            <Result label={t("tools.final_tp", "Take profit after all fills")} value={fmtPrice(plan.rows[plan.rows.length - 1].tp)} tone="text-up" />
            {plan.coverage >= 100 && plan.long && <Notice tone="error" className="mt-3">{t("tools.over100", "The ladder goes below zero — reduce the deviation or step scale.")}</Notice>}
          </>
        ) : <p className="text-sm text-muted">{t("tools.fill", "Fill in the fields to see the result.")}</p>
      }
    >
      {plan && (
        <Card>
          <CardHeader title={t("bots.ladder", "Safety-order ladder")} />
          <Table>
            <thead>
              <tr>
                <Th>#</Th><Th align="end">{t("tools.deviation", "Deviation")}</Th><Th align="end">{t("order.price", "Price")}</Th><Th align="end">{t("tools.size", "Size")}</Th>
                <Th align="end">{t("tools.invested", "Total invested")}</Th><Th align="end">{t("tools.average", "Average price")}</Th><Th align="end">{t("tools.tp_price", "TP price")}</Th>
              </tr>
            </thead>
            <tbody>
              {plan.rows.map((r) => (
                <tr key={r.index}>
                  <Td className="text-muted">{r.index === 0 ? t("tools.base", "Base") : `SO ${r.index}`}</Td>
                  <Td align="end" className="num">{r.index === 0 ? "—" : fmtPct(plan.long ? -r.deviation : r.deviation)}</Td>
                  <Td align="end" className="num">{fmtPrice(r.price)}</Td>
                  <Td align="end" className="num">{fmtUsd(r.size)}</Td>
                  <Td align="end" className="num">{fmtUsd(r.total)}</Td>
                  <Td align="end" className="num">{fmtPrice(r.average)}</Td>
                  <Td align="end" className="num text-up">{fmtPrice(r.tp)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}
    </Layout>
  );
}

/* ------------------------------------------------------------------ P&L */

function ProfitLoss() {
  const t = useT();
  const [f, set] = useForm("pnl", { side: "long", entry: "100", exit: "110", amount: "10", fee: "0.1" });
  const r = useMemo(() => {
    const entry = toNumber(f.entry), exit = toNumber(f.exit), amount = toNumber(f.amount), fee = toNumber(f.fee) / 100;
    if (!entry || !exit || !amount) return null;
    const dir = f.side === "short" ? -1 : 1;
    const gross = (exit - entry) * amount * dir;
    const fees = (entry + exit) * amount * fee;
    const net = gross - fees;
    return { gross, fees, net, cost: entry * amount, roi: (net / (entry * amount)) * 100 };
  }, [f]);
  return (
    <Layout
      form={
        <>
          <Field label={t("order.side", "Side")} className="sm:col-span-2">
            <Segmented value={f.side} onChange={set("side")} options={[{ value: "long", label: t("bots.long", "Long"), tone: "up" }, { value: "short", label: t("bots.short", "Short"), tone: "down" }]} />
          </Field>
          <Num label={t("bt.entry", "Entry")} value={f.entry} onChange={set("entry")} />
          <Num label={t("bt.exit", "Exit")} value={f.exit} onChange={set("exit")} />
          <Num label={t("order.amount", "Amount")} value={f.amount} onChange={set("amount")} suffix={t("tools.units", "units")} />
          <Num label={t("tools.fee", "Fee per side")} value={f.fee} onChange={set("fee")} suffix="%" />
        </>
      }
      results={
        r ? (
          <>
            <Result big label={t("tools.net", "Net profit")} value={fmtUsd(r.net)} tone={trendClass(r.net)} />
            <Result label={t("tools.roi", "Return on cost")} value={fmtPct(r.roi)} tone={trendClass(r.roi)} />
            <Result label={t("tools.gross", "Gross profit")} value={fmtUsd(r.gross)} />
            <Result label={t("tools.fees", "Fees")} value={fmtUsd(r.fees)} tone="text-down" />
            <Result label={t("tools.cost", "Position cost")} value={fmtUsd(r.cost)} />
          </>
        ) : <p className="text-sm text-muted">{t("tools.fill", "Fill in the fields to see the result.")}</p>
      }
    />
  );
}

/* ------------------------------------------------------------------ break-even */

function BreakEven() {
  const t = useT();
  const [f, set] = useForm("breakeven", { entry: "100", buyFee: "0.1", sellFee: "0.1", target: "2" });
  const r = useMemo(() => {
    const entry = toNumber(f.entry), fb = toNumber(f.buyFee) / 100, fs = toNumber(f.sellFee) / 100, x = toNumber(f.target) / 100;
    if (!entry || fs >= 1) return null;
    return {
      long: (entry * (1 + fb)) / (1 - fs),
      short: (entry * (1 - fs)) / (1 + fb),
      longTarget: (entry * (1 + fb) * (1 + x)) / (1 - fs),
      shortTarget: (entry * (1 - fs) * (1 - x)) / (1 + fb),
    };
  }, [f]);
  return (
    <Layout
      form={
        <>
          <Num label={t("bt.entry", "Entry")} value={f.entry} onChange={set("entry")} />
          <Num label={t("tools.target_net", "Desired net profit")} value={f.target} onChange={set("target")} suffix="%" />
          <Num label={t("tools.buy_fee", "Buy fee")} value={f.buyFee} onChange={set("buyFee")} suffix="%" />
          <Num label={t("tools.sell_fee", "Sell fee")} value={f.sellFee} onChange={set("sellFee")} suffix="%" />
        </>
      }
      results={
        r ? (
          <>
            <Result big label={t("tools.be_long", "Break-even (long)")} value={fmtPrice(r.long)} />
            <Result label={t("tools.be_short", "Break-even (short)")} value={fmtPrice(r.short)} />
            <Result label={t("tools.tg_long", "Exit for target (long)")} value={fmtPrice(r.longTarget)} tone="text-up" />
            <Result label={t("tools.tg_short", "Exit for target (short)")} value={fmtPrice(r.shortTarget)} tone="text-up" />
            <Result label={t("tools.be_move", "Move needed to break even")} value={fmtPct(((r.long - toNumber(f.entry)) / toNumber(f.entry)) * 100, 3, false)} />
          </>
        ) : <p className="text-sm text-muted">{t("tools.fill", "Fill in the fields to see the result.")}</p>
      }
    />
  );
}

/* ------------------------------------------------------------------ risk / reward */

function RiskReward() {
  const t = useT();
  const [f, set] = useForm("rr", { entry: "100", stop: "95", target: "112" });
  const r = useMemo(() => {
    const entry = toNumber(f.entry), stop = toNumber(f.stop), target = toNumber(f.target);
    if (!entry || !stop || !target || entry === stop) return null;
    const risk = Math.abs(entry - stop), reward = Math.abs(target - entry);
    const ratio = reward / risk;
    const short = stop > entry;
    const valid = short ? target < entry : target > entry;
    return { risk, reward, ratio, winRate: (1 / (1 + ratio)) * 100, short, valid, riskPct: (risk / entry) * 100, rewardPct: (reward / entry) * 100 };
  }, [f]);
  return (
    <Layout
      form={
        <>
          <Num label={t("bt.entry", "Entry")} value={f.entry} onChange={set("entry")} />
          <Num label={t("order.stop", "Stop loss")} value={f.stop} onChange={set("stop")} />
          <Num label={t("tools.target", "Target")} value={f.target} onChange={set("target")} />
          {r && <div className="pt-6 sm:col-span-2"><DealBar sl={toNumber(f.stop)} entry={toNumber(f.entry)} price={toNumber(f.entry)} tp={toNumber(f.target)} short={r.short} /></div>}
        </>
      }
      results={
        r ? (
          <>
            {!r.valid && <Notice tone="warning" className="mb-3">{t("tools.rr_invalid", "Target and stop are on the same side of the entry.")}</Notice>}
            <Result big label={t("tools.rr", "Reward / risk")} value={`1 : ${fmtFixed(r.ratio, 2)}`} tone={r.ratio >= 2 ? "text-up" : r.ratio < 1 ? "text-down" : undefined} />
            <Result label={t("tools.min_wr", "Win rate needed to break even")} value={fmtPct(r.winRate, 1, false)} />
            <Result label={t("tools.risk_u", "Risk per unit")} value={`${fmtPrice(r.risk)} (${fmtPct(r.riskPct, 2, false)})`} tone="text-down" />
            <Result label={t("tools.reward_u", "Reward per unit")} value={`${fmtPrice(r.reward)} (${fmtPct(r.rewardPct, 2, false)})`} tone="text-up" />
          </>
        ) : <p className="text-sm text-muted">{t("tools.fill", "Fill in the fields to see the result.")}</p>
      }
    />
  );
}

/* ------------------------------------------------------------------ compounding */

const usdFormat = (v: number) => fmtUsd(v, 0);

function Compound() {
  const t = useT();
  const [f, set] = useForm("compound", { start: "1000", monthly: "3", months: "24", add: "100" });
  const r = useMemo(() => {
    const start = toNumber(f.start), rate = toNumber(f.monthly) / 100, add = toNumber(f.add);
    const months = Math.max(1, Math.min(600, Math.floor(toNumber(f.months, 12))));
    const now = new Date();
    let v = start;
    const points = [{ t: now.getTime(), v }];
    for (let m = 1; m <= months; m++) {
      v = v * (1 + rate) + add;
      points.push({ t: new Date(now.getFullYear(), now.getMonth() + m, now.getDate()).getTime(), v });
    }
    const contributed = start + add * months;
    return { final: v, contributed, profit: v - contributed, points, yearly: ((1 + rate) ** 12 - 1) * 100 };
  }, [f]);
  return (
    <Layout
      form={
        <>
          <Num label={t("tools.start_cap", "Starting capital")} value={f.start} onChange={set("start")} suffix="USDT" />
          <Num label={t("tools.monthly", "Monthly return")} value={f.monthly} onChange={set("monthly")} suffix="%" />
          <Num label={t("tools.months", "Months")} value={f.months} onChange={set("months")} />
          <Num label={t("tools.add", "Monthly deposit")} value={f.add} onChange={set("add")} suffix="USDT" />
        </>
      }
      results={
        <>
          <Result big label={t("tools.final", "Final balance")} value={fmtUsd(r.final)} tone="text-up" />
          <Result label={t("tools.contributed", "Total deposited")} value={fmtUsd(r.contributed)} />
          <Result label={t("tools.growth", "Growth from returns")} value={fmtUsd(r.profit)} tone={trendClass(r.profit)} />
          <Result label={t("tools.yearly", "Equivalent yearly return")} value={fmtPct(r.yearly, 1)} />
          <p className="mt-3 text-xs text-muted">{t("tools.compound_note", "Illustration only — real returns are never constant.")}</p>
        </>
      }
    >
      <Card>
        <CardHeader title={t("tools.projection", "Projection")} />
        <CardBody className="pt-2"><AreaChart points={r.points} height={260} tone="up" valueFormat={usdFormat} /></CardBody>
      </Card>
    </Layout>
  );
}

/* ------------------------------------------------------------------ page */

export default function Tools() {
  const t = useT();
  const [tool, setTool] = useLocalStorage<Tool>("pt.tools.tab", "position");
  const tools: { value: Tool; label: string; icon: ReactNode; desc: string }[] = [
    { value: "position", label: t("tools.t_position", "Position size"), icon: <Scale className="size-4" />, desc: t("tools.d_position", "How much to buy so a stop-out costs exactly your planned risk.") },
    { value: "dca", label: t("tools.t_dca", "DCA ladder"), icon: <Layers className="size-4" />, desc: t("tools.d_dca", "Plan safety orders: prices, sizes, average and capital needed.") },
    { value: "pnl", label: t("tools.t_pnl", "Profit & loss"), icon: <Coins className="size-4" />, desc: t("tools.d_pnl", "Net result of a trade after fees.") },
    { value: "breakeven", label: t("tools.t_be", "Break-even"), icon: <Percent className="size-4" />, desc: t("tools.d_be", "The exit price that covers both fees.") },
    { value: "rr", label: t("tools.t_rr", "Risk / reward"), icon: <Target className="size-4" />, desc: t("tools.d_rr", "Compare the upside to the downside before entering.") },
    { value: "compound", label: t("tools.t_compound", "Compounding"), icon: <TrendingUp className="size-4" />, desc: t("tools.d_compound", "Project growth with monthly returns and deposits.") },
  ];
  const active = tools.find((x) => x.value === tool) ?? tools[0];
  return (
    <div className="space-y-5">
      <PageHeader icon={<Calculator className="size-5" />} title={t("nav.tools", "Calculators")} subtitle={t("tools.subtitle", "Quick maths for planning trades — nothing is sent to the server.")} />
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
        {tools.map((x) => (
          <button
            key={x.value}
            type="button"
            onClick={() => setTool(x.value)}
            className={cn(
              "flex items-center gap-2 rounded-xl border px-3 py-2.5 text-start text-sm font-medium transition-colors",
              x.value === active.value ? "border-primary bg-primary-soft text-fg" : "border-line bg-surface text-muted hover:text-fg",
            )}
          >
            <span className={x.value === active.value ? "text-primary" : undefined}>{x.icon}</span>
            {x.label}
          </button>
        ))}
      </div>
      <p className="text-sm text-muted">{active.desc}</p>
      {active.value === "position" && <PositionSize />}
      {active.value === "dca" && <DcaPlanner />}
      {active.value === "pnl" && <ProfitLoss />}
      {active.value === "breakeven" && <BreakEven />}
      {active.value === "rr" && <RiskReward />}
      {active.value === "compound" && <Compound />}
    </div>
  );
}
