import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ResetBody, type SimState } from "./api";

export interface SimControls {
  state: SimState | null;
  connected: boolean;
  streaming: boolean;
  busy: boolean;
  error: string | null;
  playing: boolean;
  speed: number; // steps per tick
  setSpeed: (n: number) => void;
  play: () => void;
  pause: () => void;
  reset: (body: ResetBody) => Promise<void>;
  stepOnce: () => Promise<void>;
  runN: (n: number) => Promise<void>;
  refresh: () => Promise<void>;
}

const TICK_MS = 700;

export function useSim(): SimControls {
  const [state, setState] = useState<SimState | null>(null);
  const [connected, setConnected] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(5);

  const inflight = useRef(false);
  const speedRef = useRef(speed);
  speedRef.current = speed;

  const call = useCallback(async (fn: () => Promise<SimState>) => {
    setBusy(true);
    setError(null);
    try {
      const s = await fn();
      setState(s);
      setConnected(true);
      return s;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setConnected(false);
      throw e;
    } finally {
      setBusy(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      setState(await api.state());
      setConnected(true);
      setError(null);
    } catch (e) {
      setConnected(false);
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Live updates over /ws (server-push refresh); polling stays as the fallback.
  useEffect(() => {
    let token: string | null = null;
    try {
      token = window.localStorage.getItem("spectra_token");
    } catch {
      token = null;
    }
    if (!token) return;

    let ws: WebSocket | null = null;
    let closed = false;
    let retry = 0;
    const connect = () => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(
        `${proto}://${window.location.host}/ws?token=${encodeURIComponent(token!)}`,
      );
      ws.onopen = () => setStreaming(true);
      ws.onmessage = (e) => {
        try {
          const evt = JSON.parse(e.data);
          if (evt.type === "state" && !inflight.current) refresh();
        } catch {
          /* ignore malformed frame */
        }
      };
      ws.onclose = () => {
        setStreaming(false);
        if (!closed) retry = window.setTimeout(connect, 2500);
      };
      ws.onerror = () => ws?.close();
    };
    connect();
    return () => {
      closed = true;
      window.clearTimeout(retry);
      ws?.close();
    };
  }, [refresh]);

  // play loop
  useEffect(() => {
    if (!playing) return;
    let stop = false;
    const tick = async () => {
      if (stop || inflight.current) return;
      inflight.current = true;
      try {
        const s = await api.step(Math.max(1, Math.round(speedRef.current)));
        setState(s);
        setConnected(true);
        if (s.done) setPlaying(false);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setConnected(false);
        setPlaying(false);
      } finally {
        inflight.current = false;
      }
    };
    const id = window.setInterval(tick, TICK_MS);
    tick();
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, [playing]);

  const reset = useCallback(
    async (body: ResetBody) => {
      setPlaying(false);
      await call(() => api.reset(body));
    },
    [call],
  );

  const stepOnce = useCallback(async () => {
    await call(() => api.step(1));
  }, [call]);

  const runN = useCallback(
    async (n: number) => {
      setPlaying(false);
      await call(() => api.step(n));
    },
    [call],
  );

  return {
    state,
    connected,
    streaming,
    busy,
    error,
    playing,
    speed,
    setSpeed,
    play: () => setPlaying(true),
    pause: () => setPlaying(false),
    reset,
    stepOnce,
    runN,
    refresh,
  };
}
