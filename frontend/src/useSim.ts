import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ResetBody, type SimState } from "./api";

export interface SimControls {
  state: SimState | null;
  connected: boolean;
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
