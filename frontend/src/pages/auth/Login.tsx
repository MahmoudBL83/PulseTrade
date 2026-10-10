import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { Eye, EyeOff } from "lucide-react";
import { useAuth } from "../../context/auth";
import { useT } from "../../i18n";
import { errorMessage } from "../../lib/api";
import { Button, Field, Input, Notice } from "../../components/ui";
import AuthCard from "./AuthCard";

export function safeNext(next: string | null) {
  // only same-app relative paths (no protocol-relative or absolute URLs)
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
}

export default function Login() {
  const t = useT();
  const { login } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await login(email.trim(), password);
      const next = safeNext(params.get("next"));
      if (res.status === "ok") nav(next, { replace: true });
      else nav(`/verify?method=${res.method}&next=${encodeURIComponent(next)}`, { state: { message: res.message } });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthCard
      title={t("auth.welcome_back", "Welcome back")}
      subtitle={t("auth.login_sub", "Log in to manage your bots, trades and portfolio.")}
      footer={
        <>
          {t("auth.no_account", "New to PulseTrade?")}{" "}
          <Link to="/register" className="font-medium text-primary hover:underline">{t("auth.create_account", "Create an account")}</Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        {error && <Notice tone="error">{error}</Notice>}
        <Field label={t("auth.email", "Email")} htmlFor="email">
          <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label={t("auth.password", "Password")} htmlFor="password">
          <div className="relative">
            <Input id="password" type={show ? "text" : "password"} autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} className="pe-10" />
            <button type="button" onClick={() => setShow((s) => !s)} className="absolute inset-y-0 end-0 flex w-10 items-center justify-center text-muted hover:text-fg" aria-label={show ? t("auth.hide", "Hide password") : t("auth.show", "Show password")}>
              {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </Field>
        <div className="flex items-center justify-between text-sm">
          <Link to="/forgot" className="text-primary hover:underline">{t("auth.forgot", "Forgot password?")}</Link>
          <Link to="/admin/login" className="text-muted hover:text-fg">{t("auth.admin", "Admin")}</Link>
        </div>
        <Button type="submit" loading={busy} className="w-full" size="lg">{t("auth.login", "Log in")}</Button>
      </form>
    </AuthCard>
  );
}
