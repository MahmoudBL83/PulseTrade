import { Plus, Trash2 } from "lucide-react";
import { useT } from "../../i18n";
import type { Condition } from "../../lib/types";
import { Button, Field, Input, Select } from "../../components/ui";

const TF = ["5m", "15m", "30m", "1h", "4h", "1d"];
const CMP = ["Greater than", "Less than", "Crossing Up", "Crossing Down"];
const CMP2 = ["Greater Than", "Less Than", "Crossing Up", "Crossing Down"];

type Param = { key: string; kind: "number" | "select"; options?: string[]; def: string | number };

/** Same indicator vocabulary the engine (crypto/bots.py) understands. */
export const INDICATORS: Record<string, Param[]> = {
  RSI: [
    { key: "Timeframe", kind: "select", options: TF, def: "1h" },
    { key: "RSI Length", kind: "number", def: 14 },
    { key: "Condition", kind: "select", options: CMP, def: "Less than" },
    { key: "Signal Value", kind: "number", def: 30 },
  ],
  MACD: [
    { key: "Timeframe", kind: "select", options: TF, def: "1h" },
    { key: "Fast Length", kind: "number", def: 12 },
    { key: "Slow Length", kind: "number", def: 26 },
    { key: "Signal Length", kind: "number", def: 9 },
    { key: "MACD Trigger", kind: "select", options: ["Crossing Up", "Crossing Down"], def: "Crossing Up" },
    { key: "Line Trigger", kind: "select", options: ["Greater Than 0", "Less Than 0"], def: "Less Than 0" },
  ],
  "Commodity Channel Index": [
    { key: "Timeframe", kind: "select", options: TF, def: "1h" },
    { key: "Length", kind: "number", def: 20 },
    { key: "Condition", kind: "select", options: CMP2, def: "Less Than" },
    { key: "Signal Value", kind: "number", def: -100 },
  ],
  "Bollinger Bands": [
    { key: "Timeframe", kind: "select", options: TF, def: "1h" },
    { key: "BB% Period", kind: "number", def: 20 },
    { key: "Deviation", kind: "number", def: 2 },
    { key: "Condition", kind: "select", options: ["Greather Than", "Less Than", "Crossing Up", "Crossing Down"], def: "Less Than" },
    { key: "Signal Value", kind: "number", def: 0 },
  ],
  "Ultimate Oscillator": [
    { key: "Timeframe", kind: "select", options: TF, def: "1h" },
    { key: "Fast Length", kind: "number", def: 7 },
    { key: "Middle Length", kind: "number", def: 14 },
    { key: "Slow Length", kind: "number", def: 28 },
    { key: "Condition", kind: "select", options: CMP2, def: "Less Than" },
    { key: "Signal Value", kind: "number", def: 30 },
  ],
  "Average Directional Index": [
    { key: "Timeframe", kind: "select", options: TF, def: "1h" },
    { key: "ADX and DI Length", kind: "number", def: 14 },
    { key: "Condition", kind: "select", options: CMP2, def: "Greater Than" },
    { key: "Signal Value", kind: "number", def: 25 },
  ],
  "Money Flow Index": [
    { key: "Timeframe", kind: "select", options: TF, def: "1h" },
    { key: "MFI Length", kind: "number", def: 14 },
    { key: "Condition", kind: "select", options: ["Crossing Up", "Crossing Down"], def: "Crossing Up" },
    { key: "Signal Value", kind: "number", def: 20 },
  ],
  "Parabolic SAR": [
    { key: "Timeframe", kind: "select", options: TF, def: "1h" },
    { key: "Start", kind: "number", def: 0.02 },
    { key: "Maximum", kind: "number", def: 0.2 },
    { key: "Condition", kind: "select", options: ["Crossing Up (Long)", "Crossing Down (Short)"], def: "Crossing Up (Long)" },
  ],
  "TradingView Crypto Screener": [
    { key: "Timeframe", kind: "select", options: TF, def: "1h" },
    { key: "Signal Value", kind: "select", options: ["STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"], def: "STRONG_BUY" },
  ],
};

export function defaultCondition(indicator = "RSI"): Condition {
  const conds: Record<string, string | number> = {};
  for (const p of INDICATORS[indicator]) conds[p.key] = p.def;
  return { indicator, conds };
}

export function ConditionsBuilder({ value, onChange, emptyHint }: { value: Condition[]; onChange: (c: Condition[]) => void; emptyHint: string }) {
  const t = useT();
  const update = (i: number, c: Condition) => onChange(value.map((x, j) => (j === i ? c : x)));
  return (
    <div className="space-y-3">
      {!value.length && <p className="text-sm text-muted">{emptyHint}</p>}
      {value.map((c, i) => {
        const params = INDICATORS[c.indicator] ?? [];
        return (
          <div key={i} className="rounded-xl border border-line p-3">
            <div className="flex items-center gap-2">
              <Select
                value={c.indicator}
                onChange={(e) => update(i, defaultCondition(e.target.value))}
                className="flex-1"
                aria-label={t("bots.indicator", "Indicator")}
              >
                {Object.keys(INDICATORS).map((k) => <option key={k} value={k}>{k}</option>)}
              </Select>
              {c.value !== undefined && c.value !== null && (
                <span className="num rounded-md bg-surface-2 px-2 py-1 text-xs text-muted" title={t("bots.last_value", "Last value")}>
                  {typeof c.value === "number" ? c.value.toFixed(2) : c.value}
                </span>
              )}
              <Button variant="ghost" size="sm" onClick={() => onChange(value.filter((_, j) => j !== i))} aria-label={t("common.remove", "Remove")}>
                <Trash2 className="size-4" />
              </Button>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {params.map((p) => (
                <Field key={p.key} label={p.key}>
                  {p.kind === "select" ? (
                    <Select value={String(c.conds[p.key] ?? p.def)} onChange={(e) => update(i, { ...c, conds: { ...c.conds, [p.key]: e.target.value } })}>
                      {p.options!.map((o) => <option key={o} value={o}>{o}</option>)}
                    </Select>
                  ) : (
                    <Input
                      inputMode="decimal"
                      value={String(c.conds[p.key] ?? p.def)}
                      onChange={(e) => update(i, { ...c, conds: { ...c.conds, [p.key]: e.target.value } })}
                    />
                  )}
                </Field>
              ))}
            </div>
          </div>
        );
      })}
      <Button variant="outline" size="sm" icon={<Plus className="size-4" />} onClick={() => onChange([...value, defaultCondition()])} disabled={value.length >= 6}>
        {t("bots.add_condition", "Add condition")}
      </Button>
    </div>
  );
}
