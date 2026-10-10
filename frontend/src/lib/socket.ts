import { useEffect, useRef } from "react";
import { io, type Socket } from "socket.io-client";
import { getToken } from "./api";

let socket: Socket | null = null;
let socketToken: string | null = null;

/** One shared Socket.IO connection, authenticated with the JWT. */
export function getSocket(): Socket {
  const token = getToken();
  if (socket && socketToken === token) return socket;
  socket?.disconnect();
  socketToken = token;
  socket = io({
    path: "/socket.io",
    auth: token ? { token } : undefined,
    transports: ["websocket", "polling"],
    reconnectionAttempts: 6,
    reconnectionDelay: 2000,
    autoConnect: true,
  });
  return socket;
}

export function closeSocket() {
  socket?.disconnect();
  socket = null;
  socketToken = null;
}

/** Subscribe to a socket event for the lifetime of the component. */
export function useSocketEvent<T = unknown>(event: string, handler: (payload: T) => void, enabled = true) {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    if (!enabled) return;
    const s = getSocket();
    const fn = (p: T) => ref.current(p);
    s.on(event, fn);
    return () => {
      s.off(event, fn);
    };
  }, [event, enabled]);
}

/**
 * Legacy notification wire format: "userId***text***Type***date***exchange"
 * (or "userId***text***date***exchange" for untyped messages).
 */
export function parseNotification(raw: string) {
  const parts = String(raw).split("***");
  if (parts.length >= 5) return { userId: parts[0], text: parts[1], type: parts[2], exchange: parts[4] };
  return { userId: parts[0], text: parts[1] ?? raw, type: "", exchange: parts[3] ?? null };
}
