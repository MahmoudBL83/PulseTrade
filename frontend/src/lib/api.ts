// Thin fetch wrapper for the Flask backend (same origin).
// v2 endpoints answer {ok, data, ...}; legacy v1 endpoints use mixed shapes,
// so both styles are supported. Business errors ({ok:false}) become ApiError.

const TOKEN_KEY = "pt.token";

export class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem("jwt", token); // the classic pages read this key
    } else {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem("jwt");
    }
  } catch {
    /* storage unavailable (private mode) */
  }
}

let unauthorizedHandler: (() => void) | null = null;
export function onUnauthorized(fn: () => void) {
  unauthorizedHandler = fn;
}

type Query = Record<string, string | number | boolean | null | undefined>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Query;
  /** Do not throw when the JSON body says {ok:false} (multi-step flows). */
  allowNotOk?: boolean;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: Query) {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${path}${path.includes("?") ? "&" : "?"}${qs}` : path;
}

export async function request<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), {
      method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
      headers,
      body,
      credentials: "same-origin",
      signal: opts.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("Network error — check your connection.", 0);
  }
  const type = res.headers.get("content-type") ?? "";
  const data: any = type.includes("json") ? await res.json().catch(() => null) : await res.text();

  if (res.status === 401 && token) unauthorizedHandler?.();
  const notOk = data && typeof data === "object" && !Array.isArray(data) && data.ok === false;
  if (!res.ok || (notOk && !opts.allowNotOk)) {
    const message =
      (data && typeof data === "object" && (data.message || data.error)) ||
      (res.status === 429 ? "Too many requests, slow down a little." : `Request failed (${res.status})`);
    throw new ApiError(String(message), res.status, data);
  }
  return data as T;
}

/** v2 helpers unwrap `data`. */
export const v2 = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) =>
    request<{ data: T }>(`/api/v2${path}`, { query, signal }).then((r) => r.data),
  post: <T>(path: string, body: unknown = {}) =>
    request<{ data: T; message?: string }>(`/api/v2${path}`, { method: "POST", body }).then((r) => r.data),
  put: <T>(path: string, body: unknown = {}) =>
    request<{ data: T }>(`/api/v2${path}`, { method: "PUT", body }).then((r) => r.data),
  patch: <T>(path: string, body: unknown = {}) =>
    request<{ data: T }>(`/api/v2${path}`, { method: "PATCH", body }).then((r) => r.data),
  del: <T>(path: string) => request<{ data: T }>(`/api/v2${path}`, { method: "DELETE" }).then((r) => r.data),
  /** Full envelope (for list endpoints that return totals next to data). */
  raw: <T>(path: string, query?: Query) => request<T>(`/api/v2${path}`, { query }),
};

/** Legacy v1 / page endpoints: returned as-is. */
export const v1 = {
  get: <T>(path: string, query?: Query) => request<T>(path, { query }),
  post: <T>(path: string, body: unknown = {}) => request<T>(path, { method: "POST", body }),
  put: <T>(path: string, body: unknown = {}) => request<T>(path, { method: "PUT", body }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

/** Authenticated file download (CSV exports). */
export async function download(path: string, filename: string) {
  const token = getToken();
  const res = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {}, credentials: "same-origin" });
  if (!res.ok) throw new ApiError(`Download failed (${res.status})`, res.status);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}
