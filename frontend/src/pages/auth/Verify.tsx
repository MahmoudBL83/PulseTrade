import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { ShieldCheck } from "lucide-react";
import { useAuth } from "../../context/auth";
import { useT } from "../../i18n";
import { errorMessage } from "../../lib/api";
import { Button, Field, Input, Notice } from "../../components/ui";
import AuthCard from "./AuthCard";
import { safeNext } from "./Login";

export default function Verify() {
  const t = useT();
  const { verify } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [params] = useSearchParams();
  const method = params.get("method") === "totp" ? "totp" : "email";
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const info = (loc.state as { message?: string } | null)?.message;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await verify(code.trim());
      if ("admin" in res) nav("/admin", { replace: true });
      else nav(safeNext(params.get("next")), { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthCard
      title={
        <span className="flex items-center gap-2">
          <ShieldCheck className="size-6 text-primary" />
          {t("auth.verify_title", "Verify it's you")}
        </span>
      }
      subtitle={
        method === "totp"
          ? t("auth.verify_totp", "Enter the 6-digit code from your authenticator app.")
          : t("auth.verify_email", "We emailed you a 6-digit code. It expires in 5 minutes.")
      }
      footer={<Link to="/login" className="text-primary hover:underline">{t("auth.back_login", "Back to login")}</Link>}
    >
      <form onSubmit={submit} className="space-y-4">
        {info && !error && <Notice>{info}</Notice>}
        {error && <Notice tone="error">{error}</Notice>}
        <Field label={t("auth.code", "Code")} htmlFor="code">
          <Input
            id="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            maxLength={8}
            required
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            className="num text-center text-lg tracking-[0.5em]"
          />
        </Field>
        <Button type="submit" loading={busy} disabled={code.length < 6} className="w-full" size="lg">{t("auth.verify", "Verify")}</Button>
      </form>
    </AuthCard>
  );
}
