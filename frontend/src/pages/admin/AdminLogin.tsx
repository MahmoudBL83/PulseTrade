import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { ShieldCheck } from "lucide-react";
import { useToast } from "../../context/toast";
import { useT } from "../../i18n";
import { request, v2 } from "../../lib/api";
import { Button, Field, Input, Notice } from "../../components/ui";
import AuthCard from "../auth/AuthCard";

interface AdminLoginResponse { ok: boolean; message?: string; otp_required?: boolean; method?: "email" | "totp" }

export default function AdminLogin() {
  const t = useT();
  const toast = useToast();
  const nav = useNavigate();
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<null | "email" | "totp">(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (!step) {
        const r = await request<AdminLoginResponse>("/api/v2/auth/admin", { method: "POST", body: { password } });
        if (r.otp_required) setStep(r.method === "totp" ? "totp" : "email");
        else nav("/admin", { replace: true });
      } else {
        await v2.post("/auth/verify", { code });
        nav("/admin", { replace: true });
      }
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthCard title={t("admin.login", "Admin sign-in")} subtitle={t("admin.login_sub", "Restricted area — every attempt is rate limited.")}>
      <form onSubmit={submit} className="space-y-4">
        {!step ? (
          <Field label={t("auth.password", "Password")}>
            <Input type="password" autoComplete="current-password" autoFocus value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
        ) : (
          <>
            <Notice>{step === "totp" ? t("admin.totp", "Enter the code from your authenticator app.") : t("admin.email_code", "We emailed a sign-in code to the admin address.")}</Notice>
            <Field label={t("settings.2fa_code", "6-digit code")}>
              <Input inputMode="numeric" autoComplete="one-time-code" autoFocus maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
            </Field>
          </>
        )}
        <Button type="submit" className="w-full" loading={busy} icon={<ShieldCheck className="size-4" />} disabled={step ? code.length !== 6 : !password}>
          {step ? t("auth.verify", "Verify") : t("auth.login", "Log in")}
        </Button>
      </form>
    </AuthCard>
  );
}
