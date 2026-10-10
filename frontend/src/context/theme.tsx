import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type ThemeChoice = "dark" | "light" | "system";

interface ThemeCtx {
  theme: ThemeChoice;
  resolved: "dark" | "light";
  setTheme: (t: ThemeChoice) => void;
}

const Ctx = createContext<ThemeCtx | null>(null);

function read(): ThemeChoice {
  try {
    const v = localStorage.getItem("pt.theme");
    return v === "light" || v === "system" ? v : "dark";
  } catch {
    return "dark";
  }
}

function systemDark() {
  return typeof matchMedia !== "undefined" && matchMedia("(prefers-color-scheme: dark)").matches;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ThemeChoice>(read);
  const [sys, setSys] = useState(systemDark);

  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const fn = () => setSys(mq.matches);
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, []);

  const resolved: "dark" | "light" = theme === "system" ? (sys ? "dark" : "light") : theme;

  useEffect(() => {
    document.documentElement.classList.toggle("dark", resolved === "dark");
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", resolved === "dark" ? "#0b0e14" : "#f5f6f8");
    try {
      localStorage.setItem("pt.theme", theme);
      localStorage.setItem("theme", resolved); // shared with the classic pages
    } catch {
      /* ignore */
    }
  }, [theme, resolved]);

  return <Ctx.Provider value={{ theme, resolved, setTheme }}>{children}</Ctx.Provider>;
}

export function useTheme() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useTheme outside provider");
  return v;
}
