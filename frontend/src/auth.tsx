import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  api,
  ROLE_RANK,
  setAuthToken,
  setUnauthorizedHandler,
  type Role,
  type TokenResponse,
} from "./api";

const STORAGE_KEY = "spectra_token";

interface Session {
  token: string;
  username: string;
  role: Role;
  demo: boolean;
  mustChangePassword: boolean;
}

interface AuthContextValue {
  ready: boolean;
  session: Session | null;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  loginDemo: () => Promise<void>;
  quickLogin: (role: Role) => Promise<void>;
  logout: () => void;
  hasRole: (min: Role) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readStoredToken(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(STORAGE_KEY, token);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private mode / storage disabled — session stays in memory only */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);

  const clear = useCallback(() => {
    setAuthToken(null);
    writeStoredToken(null);
    setSession(null);
  }, []);

  // Wire the api layer's 401 handler once.
  useEffect(() => {
    setUnauthorizedHandler(() => clear());
    return () => setUnauthorizedHandler(null);
  }, [clear]);

  // On mount: validate any stored token.
  useEffect(() => {
    const stored = readStoredToken();
    if (!stored) {
      setReady(true);
      return;
    }
    setAuthToken(stored);
    api
      .me()
      .then((me) =>
        setSession({
          token: stored,
          username: me.username,
          role: me.role,
          demo: me.demo,
          mustChangePassword: me.must_change_password,
        }),
      )
      .catch(() => clear())
      .finally(() => setReady(true));
  }, [clear]);

  const login = useCallback(async (username: string, password: string) => {
    setError(null);
    try {
      const r = await api.login(username, password);
      setAuthToken(r.access_token);
      writeStoredToken(r.access_token);
      setSession({
        token: r.access_token,
        username: r.username,
        role: r.role,
        demo: r.demo,
        mustChangePassword: r.must_change_password,
      });
    } catch (e) {
      setError(e instanceof Error ? "Invalid username or password" : String(e));
      throw e;
    }
  }, []);

  const applyToken = useCallback((r: TokenResponse) => {
    setAuthToken(r.access_token);
    writeStoredToken(r.access_token);
    setSession({
      token: r.access_token,
      username: r.username,
      role: r.role,
      demo: r.demo,
      mustChangePassword: r.must_change_password,
    });
  }, []);

  const loginDemo = useCallback(async () => {
    setError(null);
    applyToken(await api.demo());
  }, [applyToken]);

  const quickLogin = useCallback(
    async (role: Role) => {
      setError(null);
      try {
        applyToken(await api.quickLogin(role));
      } catch (e) {
        setError(e instanceof Error ? `Quick sign-in failed (${role})` : String(e));
        throw e;
      }
    },
    [applyToken],
  );

  const logout = useCallback(() => {
    api.logout().catch(() => undefined);
    clear();
  }, [clear]);

  const hasRole = useCallback(
    (min: Role) => !!session && ROLE_RANK[session.role] >= ROLE_RANK[min],
    [session],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ ready, session, error, login, loginDemo, quickLogin, logout, hasRole }),
    [ready, session, error, login, loginDemo, quickLogin, logout, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
