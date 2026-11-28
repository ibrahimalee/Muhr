import { useEffect, useState } from "react";
import { getFeedEventSourceUrl } from "@/lib/muhrApi";
import type { FeedEvent } from "@/types/api";

const MAX = 200;

/**
 * Subscribes to the registry `/api/feed` SSE. The browser will usually reconnect; we also
 * attach a new EventSource if the old one becomes CLOSED (e.g. dev restart).
 */
export function useRegistryFeed() {
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [status, setStatus] = useState<"connecting" | "open" | "error">("connecting");
  const [reconnects, setReconnects] = useState(0);

  useEffect(() => {
    let es: EventSource | null = null;
    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

    const attach = () => {
      if (cancelled) return;
      es?.close();
      setStatus("connecting");
      const src = new EventSource(getFeedEventSourceUrl());
      es = src;
      src.onopen = () => {
        if (cancelled) return;
        setStatus("open");
      };
      src.onmessage = (msg) => {
        if (cancelled) return;
        try {
          const parsed = JSON.parse(msg.data) as FeedEvent;
          setEvents((prev) => {
            const next = prev.length >= MAX ? prev.slice(prev.length - MAX + 1) : prev;
            return [...next, parsed];
          });
        } catch {
          // ignore
        }
      };
      src.onerror = () => {
        if (cancelled) return;
        if (src.readyState === EventSource.CLOSED) {
          setStatus("error");
          setReconnects((n) => n + 1);
          reconnectTimer = setTimeout(attach, 1_200);
        }
      };
    };

    attach();
    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      es?.close();
    };
  }, []);

  return { events, status, reconnects };
}
