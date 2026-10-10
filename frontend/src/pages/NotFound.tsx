import { Link } from "react-router";
import { Compass } from "lucide-react";
import { useAuth } from "../context/auth";
import { useT } from "../i18n";
import { Button } from "../components/ui";

export default function NotFound() {
  const t = useT();
  const { user } = useAuth();
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <div className="mb-5 flex size-16 items-center justify-center rounded-2xl bg-primary-soft text-primary">
        <Compass className="size-8" />
      </div>
      <p className="num text-5xl font-bold text-fg">404</p>
      <h1 className="mt-2 text-lg font-semibold text-fg">{t("404.title", "This page does not exist")}</h1>
      <p className="mt-1 max-w-sm text-sm text-muted">{t("404.body", "The link may be old, or the page moved in the new interface.")}</p>
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        <Link to={user ? "/dashboard" : "/"}><Button>{user ? t("nav.dashboard", "Dashboard") : t("404.home", "Home")}</Button></Link>
        <Link to="/markets"><Button variant="secondary">{t("nav.markets", "Markets")}</Button></Link>
      </div>
    </div>
  );
}
