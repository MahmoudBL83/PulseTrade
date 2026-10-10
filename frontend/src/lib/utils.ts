import { useEffect, useRef, useState } from "react";

export function cn(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

export function useLocalStorage<T>(key: string, initial: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? initial : (JSON.parse(raw) as T);
    } catch {
      return initial;
    }
  });
  const set = (v: T) => {
    setValue(v);
    try {
      localStorage.setItem(key, JSON.stringify(v));
    } catch {
      /* ignore */
    }
  };
  return [value, set];
}

/** Returns "up" | "down" for one render after a numeric value changes. */
export function useFlash(value: number | null | undefined): string {
  const prev = useRef(value);
  const [cls, setCls] = useState("");
  useEffect(() => {
    if (prev.current !== undefined && prev.current !== null && value !== undefined && value !== null && value !== prev.current) {
      setCls(value > prev.current ? "flash-up" : "flash-down");
      const id = setTimeout(() => setCls(""), 900);
      prev.current = value;
      return () => clearTimeout(id);
    }
    prev.current = value;
  }, [value]);
  return cls;
}

export function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

export function toNumber(v: string | number | null | undefined, fallback = 0): number {
  if (v === null || v === undefined || v === "") return fallback;
  const n = typeof v === "number" ? v : Number(String(v).replace(",", "."));
  return Number.isFinite(n) ? n : fallback;
}

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/* Allow-list sanitizer for admin-authored knowledge-base HTML. */
const SAFE_TAGS = new Set([
  "a", "b", "blockquote", "br", "code", "div", "em", "figcaption", "figure", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i",
  "img", "li", "mark", "ol", "p", "pre", "s", "small", "span", "strong", "sub", "sup", "table", "tbody", "td", "th", "thead",
  "tr", "u", "ul",
]);
const DROP_TAGS = new Set(["script", "style", "iframe", "object", "embed", "noscript", "template", "svg", "math", "form", "input", "button", "textarea", "select", "link", "meta", "base", "frame", "frameset"]);
const SAFE_ATTRS = new Set(["href", "src", "alt", "title", "colspan", "rowspan", "width", "height", "dir"]);

export function sanitizeHtml(html: string): string {
  const doc = new DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
  const root = doc.body.firstElementChild;
  if (!root) return "";
  const walk = (el: Element) => {
    for (const child of Array.from(el.children)) {
      const tag = child.tagName.toLowerCase();
      if (DROP_TAGS.has(tag)) {
        child.remove();
        continue;
      }
      walk(child);
      if (!SAFE_TAGS.has(tag)) {
        child.replaceWith(...Array.from(child.childNodes));
        continue;
      }
      for (const attr of Array.from(child.attributes)) {
        const name = attr.name.toLowerCase();
        const value = attr.value.trim();
        const okUrl = /^(https?:|mailto:|\/|#)/i.test(value) || (tag === "img" && name === "src" && /^data:image\/(png|jpe?g|gif|webp);/i.test(value));
        if (!SAFE_ATTRS.has(name) || ((name === "href" || name === "src") && !okUrl)) child.removeAttribute(attr.name);
      }
      if (tag === "a") {
        child.setAttribute("rel", "noopener noreferrer");
        if (/^https?:/i.test(child.getAttribute("href") ?? "")) child.setAttribute("target", "_blank");
      }
    }
  };
  walk(root);
  return root.innerHTML;
}

export function initials(first?: string | null, last?: string | null, email?: string) {
  const a = (first || "").trim()[0] || (email || "?")[0];
  const b = (last || "").trim()[0] || "";
  return (a + b).toUpperCase();
}
