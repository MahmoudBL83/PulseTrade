import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { setFormatLocale } from "../lib/format";
import ar from "./ar";

export type Lang = "en" | "ar";
type Vars = Record<string, string | number>;
type T = (key: string, fallback?: string, vars?: Vars) => string;

interface I18n {
  lang: Lang;
  dir: "ltr" | "rtl";
  setLang: (l: Lang) => void;
  t: T;
}

const dictionaries: Record<Lang, Record<string, string>> = { en: {}, ar };

function interpolate(s: string, vars?: Vars) {
  if (!vars) return s;
  return s.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? String(vars[k]) : `{${k}}`));
}

function initialLang(): Lang {
  try {
    const l = localStorage.getItem("pt.lang") || localStorage.getItem("lang");
    return l === "ar" ? "ar" : "en";
  } catch {
    return "en";
  }
}

const Ctx = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  useEffect(() => {
    const el = document.documentElement;
    el.lang = lang;
    el.dir = lang === "ar" ? "rtl" : "ltr";
    setFormatLocale(lang);
    try {
      localStorage.setItem("pt.lang", lang);
      localStorage.setItem("lang", lang); // shared with the classic pages
    } catch {
      /* ignore */
    }
  }, [lang]);

  const t = useCallback<T>(
    (key, fallback, vars) => interpolate(dictionaries[lang][key] ?? fallback ?? key, vars),
    [lang],
  );

  const value = useMemo<I18n>(() => ({ lang, dir: lang === "ar" ? "rtl" : "ltr", setLang: setLangState, t }), [lang, t]);
  setFormatLocale(lang);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useI18n outside provider");
  return v;
}

export function useT() {
  return useI18n().t;
}
