import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { useAuth } from "../../context/auth";
import { useT } from "../../i18n";
import { errorMessage } from "../../lib/api";
import { cn } from "../../lib/utils";
import { Button, Field, Input, Notice } from "../../components/ui";
import AuthCard from "./AuthCard";

export function passwordScore(p: string) {
  let s = 0;
  if (p.length >= 8) s++;
  if (p.length >= 12) s++;
  if (/[A-Z]/.test(p) && /[a-z]/.test(p)) s++;
  if (/\d/.test(p)) s++;
  if (/[^A-Za-z0-9]/.test(p)) s++;
  return Math.min(4, s);
}

export function StrengthMeter({ password }: { password: string }) {
  const t = useT();
  const score = passwordScore(password);
  const labels = [t("pw.weak", "Too weak"), t("pw.weak", "Too weak"), t("pw.fair", "Fair"), t("pw.good", "Good"), t("pw.strong", "Strong")];
  const tone = ["bg-down", "bg-down", "bg-primary", "bg-up", "bg-up"][score];
  if (!password) return null;
  return (
    <div className="flex items-center gap-2">
      <div className="flex flex-1 gap-1">
        {[0, 1, 2, 3].map((i) => <div key={i} className={cn("h-1 flex-1 rounded-full", i < score ? tone : "bg-surface-3")} />)}
      </div>
      <span className="text-xs text-muted">{labels[score]}</span>
    </div>
  );
}

export default function Register() {
  const t = useT();
  const { register } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ firstName: "", lastName: "", email: "", password: "", confirm: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const mismatch = useMemo(() => form.confirm && form.confirm !== form.password, [form]);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (mismatch) return;
    setBusy(true);
    setError(null);
    try {
      const user = await register({ email: form.email.trim(), firstName: form.firstName, lastName: form.lastName, password: form.password });
      if (user) nav("/exchanges?welcome=1", { replace: true });
      else setDone(t("auth.check_email", "Check your inbox to verify your email, then log in."));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthCard
      title={t("auth.create_account", "Create an account")}
      subtitle={t("auth.register_sub", "Start with a free plan and a $10,000 paper-trading account.")}
      footer={
        <>
          {t("auth.have_account", "Already have an account?")}{" "}
          <Link to="/login" className="font-medium text-primary hover:underline">{t("auth.login", "Log in")}</Link>
        </>
      }
    >
      {done ? (
        <Notice tone="success">{done}</Notice>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          {error && <Notice tone="error">{error}</Notice>}
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("auth.first_name", "First name")} htmlFor="fn">
              <Input id="fn" autoComplete="given-name" value={form.firstName} onChange={set("firstName")} />
            </Field>
            <Field label={t("auth.last_name", "Last name")} htmlFor="ln">
              <Input id="ln" autoComplete="family-name" value={form.lastName} onChange={set("lastName")} />
            </Field>
          </div>
          <Field label={t("auth.email", "Email")} htmlFor="email">
            <Input id="email" type="email" autoComplete="email" required value={form.email} onChange={set("email")} />
          </Field>
          <Field label={t("auth.password", "Password")} htmlFor="pw" hint={t("auth.pw_hint", "At least 8 characters.")}>
            <Input id="pw" type="password" autoComplete="new-password" minLength={8} required value={form.password} onChange={set("password")} />
          </Field>
          <StrengthMeter password={form.password} />
          <Field label={t("auth.confirm_password", "Confirm password")} htmlFor="pw2" error={mismatch ? t("auth.pw_mismatch", "Passwords do not match") : undefined}>
            <Input id="pw2" type="password" autoComplete="new-password" required value={form.confirm} onChange={set("confirm")} />
          </Field>
          <p className="text-xs text-muted">
            {t("auth.agree", "By creating an account you agree to the")}{" "}
            <a href="/terms-of-service" className="text-primary hover:underline">{t("legal.terms", "Terms")}</a>{" "}
            {t("common.and", "and")}{" "}
            <a href="/privacy-policy" className="text-primary hover:underline">{t("legal.privacy", "Privacy")}</a>.
          </p>
          <Button type="submit" loading={busy} disabled={!!mismatch} className="w-full" size="lg">{t("auth.signup", "Sign up")}</Button>
        </form>
      )}
    </AuthCard>
  );
}
