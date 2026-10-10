import {
  forwardRef,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { createPortal } from "react-dom";
import { AlertCircle, Inbox, Loader2, X } from "lucide-react";
import { cn } from "../lib/utils";

/* ------------------------------------------------------------------ button */

type Variant = "primary" | "secondary" | "ghost" | "danger" | "up" | "down" | "outline";
type Size = "xs" | "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary: "bg-primary text-primary-fg hover:bg-primary-hover",
  secondary: "bg-surface-2 text-fg hover:bg-surface-3 border border-line",
  outline: "border border-line text-fg hover:bg-surface-2",
  ghost: "text-muted hover:text-fg hover:bg-surface-2",
  danger: "bg-down text-white hover:opacity-90",
  up: "bg-up text-white hover:opacity-90",
  down: "bg-down text-white hover:opacity-90",
};
const sizes: Record<Size, string> = {
  xs: "h-7 px-2 text-xs gap-1 rounded-md",
  sm: "h-8 px-3 text-sm gap-1.5 rounded-lg",
  md: "h-10 px-4 text-sm gap-2 rounded-lg",
  lg: "h-12 px-6 text-base gap-2 rounded-xl",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, icon, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={cn(
        "inline-flex shrink-0 items-center justify-center font-medium whitespace-nowrap transition-colors select-none disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

export function IconButton({ label, className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cn("inline-flex size-9 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-fg", className)}
      {...rest}
    />
  );
}

/* ------------------------------------------------------------------ card */

export function Card({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded-2xl border border-line bg-surface shadow-card", className)} {...rest}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, actions, className }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3 sm:px-5", className)}>
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-fg">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function CardBody({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("p-4 sm:p-5", className)}>{children}</div>;
}

/* ------------------------------------------------------------------ page */

export function PageHeader({ title, subtitle, actions, icon }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="flex min-w-0 items-center gap-3">
        {icon && <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary">{icon}</div>}
        <div className="min-w-0">
          <h1 className="truncate text-xl font-semibold tracking-tight text-fg sm:text-2xl">{title}</h1>
          {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, tone, className }: { label: ReactNode; value: ReactNode; hint?: ReactNode; tone?: string; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <p className="truncate text-xs font-medium text-muted">{label}</p>
      <p className={cn("num mt-1 truncate text-lg font-semibold text-fg sm:text-xl", tone)}>{value}</p>
      {hint && <p className="num mt-0.5 truncate text-xs text-muted">{hint}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ forms */

export function Field({ label, hint, error, children, htmlFor, className }: { label?: ReactNode; hint?: ReactNode; error?: ReactNode; children: ReactNode; htmlFor?: string; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {label && (
        <label htmlFor={htmlFor} className="text-xs font-medium text-muted">
          {label}
        </label>
      )}
      {children}
      {error ? <p className="text-xs text-down">{error}</p> : hint ? <p className="text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

const control =
  "w-full rounded-lg border border-line bg-surface-2 px-3 text-sm text-fg placeholder:text-muted/70 transition-colors focus:border-primary focus:outline-none disabled:opacity-60";

export const Input = forwardRef<HTMLInputElement, Omit<InputHTMLAttributes<HTMLInputElement>, "prefix"> & { suffix?: ReactNode; prefix?: ReactNode }>(
  function Input({ className, suffix, prefix, ...rest }, ref) {
    if (!suffix && !prefix) return <input ref={ref} className={cn(control, "h-10", className)} {...rest} />;
    return (
      <div className={cn("flex h-10 items-center rounded-lg border border-line bg-surface-2 focus-within:border-primary", className)}>
        {prefix && <span className="ps-3 text-sm text-muted">{prefix}</span>}
        <input ref={ref} className="h-full min-w-0 flex-1 bg-transparent px-3 text-sm text-fg placeholder:text-muted/70 focus:outline-none" {...rest} />
        {suffix && <span className="pe-3 text-sm whitespace-nowrap text-muted">{suffix}</span>}
      </div>
    );
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, children, ...rest }, ref) {
  return (
    <select ref={ref} className={cn(control, "h-10 cursor-pointer", className)} {...rest}>
      {children}
    </select>
  );
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={cn(control, "min-h-24 py-2", className)} {...rest} />;
});

export function Switch({ checked, onChange, label, disabled, id }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode; disabled?: boolean; id?: string }) {
  const auto = useId();
  const sid = id ?? auto;
  return (
    <label htmlFor={sid} className={cn("inline-flex cursor-pointer items-center gap-2.5 select-none", disabled && "cursor-not-allowed opacity-60")}>
      <button
        id={sid}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn("relative h-5 w-9 shrink-0 rounded-full transition-colors", checked ? "bg-primary" : "bg-surface-3")}
      >
        <span className={cn("absolute top-0.5 size-4 rounded-full bg-white shadow transition-all", checked ? "start-[18px]" : "start-0.5")} />
      </button>
      {label && <span className="text-sm text-fg">{label}</span>}
    </label>
  );
}

export function Segmented<T extends string>({ value, onChange, options, size = "sm", className }: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode; tone?: "up" | "down" }[];
  size?: "xs" | "sm";
  className?: string;
}) {
  return (
    <div role="radiogroup" className={cn("inline-flex rounded-lg border border-line bg-surface-2 p-0.5", className)}>
      {options.map((o) => {
        const active = o.value === value;
        const tone = active ? (o.tone === "up" ? "bg-up text-white" : o.tone === "down" ? "bg-down text-white" : "bg-surface text-fg shadow-sm") : "text-muted hover:text-fg";
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={cn("flex-1 rounded-md font-medium whitespace-nowrap transition-colors", size === "xs" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm", tone)}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ tabs */

export function Tabs<T extends string>({ value, onChange, tabs, className }: { value: T; onChange: (v: T) => void; tabs: { value: T; label: ReactNode; count?: number }[]; className?: string }) {
  return (
    <div role="tablist" className={cn("flex gap-1 overflow-x-auto border-b border-line", className)}>
      {tabs.map((t) => (
        <button
          key={t.value}
          type="button"
          role="tab"
          aria-selected={t.value === value}
          onClick={() => onChange(t.value)}
          className={cn(
            "-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors",
            t.value === value ? "border-primary text-fg" : "border-transparent text-muted hover:text-fg",
          )}
        >
          {t.label}
          {t.count !== undefined && <span className="num rounded-full bg-surface-3 px-1.5 text-xs text-muted">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ badges */

type Tone = "neutral" | "up" | "down" | "primary" | "info";
const badgeTones: Record<Tone, string> = {
  neutral: "bg-surface-3 text-muted",
  up: "bg-up-soft text-up",
  down: "bg-down-soft text-down",
  primary: "bg-primary-soft text-primary",
  info: "bg-info/15 text-info",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <span className={cn("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium whitespace-nowrap", badgeTones[tone], className)}>{children}</span>;
}

export function Dot({ tone = "neutral" }: { tone?: Tone }) {
  const c = { neutral: "bg-muted", up: "bg-up", down: "bg-down", primary: "bg-primary", info: "bg-info" }[tone];
  return <span className={cn("inline-block size-2 rounded-full", c)} aria-hidden />;
}

/* ------------------------------------------------------------------ feedback */

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("size-5 animate-spin text-muted", className)} aria-label="Loading" />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton rounded-md", className)} aria-hidden />;
}

export function SkeletonRows({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({ icon, title, body, action, className }: { icon?: ReactNode; title: ReactNode; body?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-10 text-center", className)}>
      <div className="mb-3 flex size-12 items-center justify-center rounded-2xl bg-surface-2 text-muted">{icon ?? <Inbox className="size-6" />}</div>
      <p className="text-sm font-medium text-fg">{title}</p>
      {body && <p className="mt-1 max-w-sm text-sm text-muted">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  const msg = error instanceof Error ? error.message : String(error ?? "Something went wrong");
  return (
    <div className={cn("flex flex-col items-center gap-3 px-6 py-8 text-center", className)}>
      <AlertCircle className="size-6 text-down" />
      <p className="max-w-md text-sm text-muted">{msg}</p>
      {onRetry && (
        <Button size="sm" variant="secondary" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function Notice({ tone = "info", children, className }: { tone?: "info" | "warning" | "error" | "success"; children: ReactNode; className?: string }) {
  const t = {
    info: "border-info/30 bg-info/10 text-fg",
    warning: "border-primary/30 bg-primary-soft text-fg",
    error: "border-down/30 bg-down-soft text-fg",
    success: "border-up/30 bg-up-soft text-fg",
  }[tone];
  return <div className={cn("rounded-xl border px-4 py-3 text-sm", t, className)}>{children}</div>;
}

/* ------------------------------------------------------------------ modal */

export function Modal({ open, onClose, title, children, footer, size = "md" }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; size?: "sm" | "md" | "lg" | "xl" }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    setTimeout(() => panel.current?.querySelector<HTMLElement>("input,select,textarea,button:not([aria-label='Close'])")?.focus(), 30);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      prev?.focus?.();
    };
  }, [open, onClose]);
  if (!open) return null;
  const width = { sm: "max-w-md", md: "max-w-lg", lg: "max-w-2xl", xl: "max-w-4xl" }[size];
  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-end justify-center bg-black/60 p-0 backdrop-blur-sm sm:items-center sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={panel} role="dialog" aria-modal="true" className={cn("flex max-h-[92vh] w-full flex-col rounded-t-2xl border border-line bg-surface shadow-2xl sm:rounded-2xl", width)}>
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
          <h2 className="text-base font-semibold text-fg">{title}</h2>
          <IconButton label="Close" onClick={onClose}>
            <X className="size-4" />
          </IconButton>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

export function ConfirmButton({ onConfirm, title, body, confirmLabel = "Confirm", children, variant = "danger", size = "sm", disabled }: {
  onConfirm: () => unknown;
  title: ReactNode;
  body?: ReactNode;
  confirmLabel?: ReactNode;
  children: ReactNode;
  variant?: Variant;
  size?: Size;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <Button variant={variant === "danger" ? "ghost" : variant} size={size} onClick={() => setOpen(true)} disabled={disabled} className={variant === "danger" ? "text-down hover:text-down" : undefined}>
        {children}
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={title}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant={variant === "danger" ? "danger" : "primary"}
              loading={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await onConfirm();
                  setOpen(false);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {confirmLabel}
            </Button>
          </>
        }
      >
        {body && <p className="text-sm text-muted">{body}</p>}
      </Modal>
    </>
  );
}

/* ------------------------------------------------------------------ table */

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className="w-full min-w-max text-sm">{children}</table>
    </div>
  );
}

export function Th({ children, className, align = "start", onClick, sorted }: { children?: ReactNode; className?: string; align?: "start" | "end" | "center"; onClick?: () => void; sorted?: "asc" | "desc" | null }) {
  return (
    <th
      onClick={onClick}
      className={cn(
        "border-b border-line px-3 py-2.5 text-xs font-medium whitespace-nowrap text-muted first:ps-4 last:pe-4 sm:first:ps-5 sm:last:pe-5",
        align === "end" ? "text-end" : align === "center" ? "text-center" : "text-start",
        onClick && "cursor-pointer select-none hover:text-fg",
        className,
      )}
    >
      {children}
      {sorted && <span className="ms-1">{sorted === "asc" ? "▲" : "▼"}</span>}
    </th>
  );
}

export function Td({ children, className, align = "start" }: { children?: ReactNode; className?: string; align?: "start" | "end" | "center" }) {
  return (
    <td className={cn("border-b border-line/60 px-3 py-2.5 whitespace-nowrap first:ps-4 last:pe-4 sm:first:ps-5 sm:last:pe-5", align === "end" ? "text-end" : align === "center" ? "text-center" : "text-start", className)}>
      {children}
    </td>
  );
}

/* ------------------------------------------------------------------ misc */

export function Avatar({ src, name, size = 32 }: { src?: string | null; name: string; size?: number }) {
  const ok = src && !src.endsWith("/avatars/01.png");
  return ok ? (
    <img src={src!} alt="" width={size} height={size} className="shrink-0 rounded-full object-cover" style={{ width: size, height: size }} />
  ) : (
    <span className="flex shrink-0 items-center justify-center rounded-full bg-primary-soft text-xs font-semibold text-primary" style={{ width: size, height: size }}>
      {name}
    </span>
  );
}

export function CoinIcon({ symbol, src, size = 24 }: { symbol: string; src?: string | null; size?: number }) {
  const base = (symbol || "?").split("/")[0];
  if (src) return <img src={src} alt="" width={size} height={size} loading="lazy" className="shrink-0 rounded-full" style={{ width: size, height: size }} />;
  let h = 0;
  for (const c of base) h = (h * 31 + c.charCodeAt(0)) % 360;
  return (
    <span
      aria-hidden
      className="flex shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
      style={{ width: size, height: size, background: `hsl(${h} 55% 45%)` }}
    >
      {base.slice(0, 3)}
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded border border-line bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-muted">{children}</kbd>;
}

