import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router";
import { AppShell, FullPageSpinner, PublicShell, RequireAuth } from "./components/layout";
import { useAuth } from "./context/auth";

const Landing = lazy(() => import("./pages/Landing"));
const Login = lazy(() => import("./pages/auth/Login"));
const Register = lazy(() => import("./pages/auth/Register"));
const Verify = lazy(() => import("./pages/auth/Verify"));
const Forgot = lazy(() => import("./pages/auth/Forgot"));
const ResetPassword = lazy(() => import("./pages/auth/ResetPassword"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Markets = lazy(() => import("./pages/Markets"));
const SymbolPage = lazy(() => import("./pages/Symbol"));
const Trade = lazy(() => import("./pages/Trade"));
const SmartTrades = lazy(() => import("./pages/SmartTrades"));
const Bots = lazy(() => import("./pages/bots/Bots"));
const BotForm = lazy(() => import("./pages/bots/BotForm"));
const BotDetail = lazy(() => import("./pages/bots/BotDetail"));
const Backtest = lazy(() => import("./pages/Backtest"));
const Portfolio = lazy(() => import("./pages/Portfolio"));
const Wallet = lazy(() => import("./pages/Wallet"));
const History = lazy(() => import("./pages/History"));
const Exchanges = lazy(() => import("./pages/Exchanges"));
const Watchlist = lazy(() => import("./pages/Watchlist"));
const Alerts = lazy(() => import("./pages/Alerts"));
const Journal = lazy(() => import("./pages/Journal"));
const Insights = lazy(() => import("./pages/Insights"));
const Tools = lazy(() => import("./pages/Tools"));
const Notifications = lazy(() => import("./pages/Notifications"));
const Support = lazy(() => import("./pages/Support"));
const KnowledgeBase = lazy(() => import("./pages/KnowledgeBase"));
const KbPost = lazy(() => import("./pages/KbPost"));
const Pricing = lazy(() => import("./pages/Pricing"));
const Settings = lazy(() => import("./pages/Settings"));
const NotFound = lazy(() => import("./pages/NotFound"));
const AdminLogin = lazy(() => import("./pages/admin/AdminLogin"));
const AdminApp = lazy(() => import("./pages/admin/AdminApp"));

const page = (el: ReactNode) => <Suspense fallback={<FullPageSpinner />}>{el}</Suspense>;
const authed = (el: ReactNode) => <RequireAuth>{page(el)}</RequireAuth>;

function Home() {
  const { user, loading } = useAuth();
  if (loading) return <FullPageSpinner />;
  return user ? <Navigate to="/dashboard" replace /> : page(<Landing />);
}

export default function App() {
  return (
    <Routes>
      <Route element={<PublicShell />}>
        <Route index element={<Home />} />
        <Route path="login" element={page(<Login />)} />
        <Route path="register" element={page(<Register />)} />
        <Route path="verify" element={page(<Verify />)} />
        <Route path="forgot" element={page(<Forgot />)} />
        <Route path="reset/:token" element={page(<ResetPassword />)} />
        <Route path="admin/login" element={page(<AdminLogin />)} />
      </Route>

      {/* The admin console has its own shell (session-based admin login). */}
      <Route path="admin/*" element={page(<AdminApp />)} />

      <Route element={<AppShell />}>
        <Route path="dashboard" element={authed(<Dashboard />)} />
        <Route path="markets" element={page(<Markets />)} />
        <Route path="markets/:slug" element={page(<SymbolPage />)} />
        <Route path="insights" element={page(<Insights />)} />
        <Route path="backtest" element={page(<Backtest />)} />
        <Route path="tools" element={page(<Tools />)} />
        <Route path="kb" element={page(<KnowledgeBase />)} />
        <Route path="kb/:id" element={page(<KbPost />)} />
        <Route path="pricing" element={page(<Pricing />)} />
        <Route path="trade" element={authed(<Trade />)} />
        <Route path="smart-trades" element={authed(<SmartTrades />)} />
        <Route path="bots" element={authed(<Bots />)} />
        <Route path="bots/new" element={authed(<BotForm />)} />
        <Route path="bots/:id" element={authed(<BotDetail />)} />
        <Route path="bots/:id/edit" element={authed(<BotForm />)} />
        <Route path="portfolio" element={authed(<Portfolio />)} />
        <Route path="wallet" element={authed(<Wallet />)} />
        <Route path="history" element={authed(<History />)} />
        <Route path="exchanges" element={authed(<Exchanges />)} />
        <Route path="watchlist" element={authed(<Watchlist />)} />
        <Route path="alerts" element={authed(<Alerts />)} />
        <Route path="journal" element={authed(<Journal />)} />
        <Route path="notifications" element={authed(<Notifications />)} />
        <Route path="support" element={authed(<Support />)} />
        <Route path="settings" element={authed(<Settings />)} />
        <Route path="*" element={page(<NotFound />)} />
      </Route>
    </Routes>
  );
}
