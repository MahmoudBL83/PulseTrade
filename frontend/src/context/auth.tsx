import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getToken, onUnauthorized, request, setToken, v2 } from "../lib/api";
import type { Meta, User } from "../lib/types";
import { useI18n } from "../i18n";
import { useTheme } from "./theme";

export type LoginResult =
  | { status: "ok"; user: User }
  | { status: "code"; method: "email" | "totp"; message: string };

interface AuthCtx {
  user: User | null;
  loading: boolean;
  meta: Meta | null;
  login: (email: string, password: string, opts?: { totp?: string; remember?: boolean }) => Promise<LoginResult>;
  verify: (code: string) => Promise<User | { admin: true }>;
  register: (body: { email: string; firstName: string; lastName: string; password: string }) => Promise<User | null>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  setUser: (u: User) => void;
}

const Ctx = createContext<AuthCtx | null>(null);

interface LoginResponse {
  ok: boolean;
  otp_required?: boolean;
  method?: "email" | "totp";
  message?: string;
  data?: { access_token: string; user: User };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(!!getToken());
  const [meta, setMeta] = useState<Meta | null>(null);
  const qc = useQueryClient();
  const { setLang } = useI18n();
  const { setTheme } = useTheme();
  const applyPrefs = useRef(true);

  const setUser = useCallback(
    (u: User) => {
      setUserState(u);
      if (applyPrefs.current && u.preferences) {
        applyPrefs.current = false;
        if (u.preferences.lang) setLang(u.preferences.lang);
        if (u.preferences.theme) setTheme(u.preferences.theme);
      }
    },
    [setLang, setTheme],
  );

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUserState(null);
      setLoading(false);
      return;
    }
    try {
      setUser(await v2.get<User>("/auth/me"));
    } catch {
      setToken(null);
      setUserState(null);
    } finally {
      setLoading(false);
    }
  }, [setUser]);

  useEffect(() => {
    onUnauthorized(() => {
      setToken(null);
      setUserState(null);
      qc.clear();
    });
    refresh();
    v2.get<Meta>("/meta").then(setMeta).catch(() => setMeta(null));
  }, [refresh, qc]);

  const finish = useCallback(
    (token: string, u: User) => {
      setToken(token);
      applyPrefs.current = true;
      setUser(u);
      qc.invalidateQueries();
      return u;
    },
    [qc, setUser],
  );

  const login = useCallback<AuthCtx["login"]>(
    async (email, password, opts = {}) => {
      const res = await request<LoginResponse>("/api/v2/auth/login", {
        method: "POST",
        body: { email, password, totp: opts.totp, remember: opts.remember ?? true },
        allowNotOk: true,
      });
      if (res.ok && res.data) return { status: "ok", user: finish(res.data.access_token, res.data.user) };
      if (res.otp_required) return { status: "code", method: res.method ?? "email", message: res.message ?? "" };
      throw new Error(res.message || "Login failed");
    },
    [finish],
  );

  const verify = useCallback<AuthCtx["verify"]>(
    async (code) => {
      const data = await v2.post<{ access_token?: string; user?: User; admin?: boolean }>("/auth/verify", { code });
      if (data.admin) return { admin: true };
      return finish(data.access_token!, data.user!);
    },
    [finish],
  );

  const register = useCallback<AuthCtx["register"]>(
    async (body) => {
      const data = await v2.post<{ access_token?: string; user?: User; verification_required?: boolean }>("/auth/register", {
        ...body,
        confirm_password: body.password,
      });
      if (data.access_token && data.user) return finish(data.access_token, data.user);
      return null;
    },
    [finish],
  );

  const logout = useCallback(async () => {
    try {
      await request("/api/v2/auth/logout", { method: "POST" });
    } catch {
      /* token may already be invalid */
    }
    setToken(null);
    setUserState(null);
    qc.clear();
  }, [qc]);

  const value = useMemo<AuthCtx>(
    () => ({ user, loading, meta, login, verify, register, logout, refresh, setUser }),
    [user, loading, meta, login, verify, register, logout, refresh, setUser],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside provider");
  return v;
}
