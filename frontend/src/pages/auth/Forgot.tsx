import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { useT } from "../../i18n";
import { errorMessage, v2 } from "../../lib/api";
import { Button, Field, Input, Notice } from "../../components/ui";
import AuthCard from "./AuthCard";

export default function Forgot() {
  const t = useT();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await v2.post("/auth/forgot", { email: email.trim() });
      setSent(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthCard
      title={t("auth.reset_title", "Reset your password")}
      subtitle={t("auth.reset_sub", "We'll email you a link to choose a new password.")}
      footer={<Link to="/login" className="text-primary hover:underline">{t("auth.back_login", "Back to login")}</Link>}
    >
      {sent ? (
        <Notice tone="success">{t("auth.reset_sent", "If that email is registered, reset instructions are on their way.")}</Notice>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          {error && <Notice tone="error">{error}</Notice>}
          <Field label={t("auth.email", "Email")} htmlFor="email">
            <Input id="email" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Button type="submit" loading={busy} className="w-full" size="lg">{t("auth.send_link", "Send reset link")}</Button>
        </form>
      )}
    </AuthCard>
  );
}
