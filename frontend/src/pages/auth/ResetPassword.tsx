import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { useT } from "../../i18n";
import { errorMessage, v1 } from "../../lib/api";
import { Button, Field, Input, Notice } from "../../components/ui";
import AuthCard from "./AuthCard";
import { StrengthMeter } from "./Register";

export default function ResetPassword() {
  const t = useT();
  const { token = "" } = useParams();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await v1.post(`/reset_password/${encodeURIComponent(token)}`, { password, confirm_password: confirm });
      setDone(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthCard title={t("auth.new_password", "Choose a new password")}>
      {done ? (
        <div className="space-y-4">
          <Notice tone="success">{t("auth.pw_changed", "Your password has been changed.")}</Notice>
          <Link to="/login"><Button className="w-full">{t("auth.login", "Log in")}</Button></Link>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          {error && <Notice tone="error">{error}</Notice>}
          <Field label={t("auth.password", "Password")} htmlFor="pw">
            <Input id="pw" type="password" minLength={8} required autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <StrengthMeter password={password} />
          <Field label={t("auth.confirm_password", "Confirm password")} htmlFor="pw2" error={confirm && confirm !== password ? t("auth.pw_mismatch", "Passwords do not match") : undefined}>
            <Input id="pw2" type="password" required autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </Field>
          <Button type="submit" loading={busy} disabled={!password || password !== confirm} className="w-full" size="lg">{t("auth.save_password", "Save password")}</Button>
        </form>
      )}
    </AuthCard>
  );
}
