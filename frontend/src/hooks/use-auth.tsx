import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { getCurrentUser, login as loginApi, logout as logoutApi, register as registerApi } from "@/api/auth";
import type { User, Credentials } from "@/types";

type AuthState = {
  user: User | null;
  loading: boolean;
};

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  login: (credentials: Credentials) => Promise<User>;
  register: (credentials: Credentials) => Promise<User>;
  logout: () => Promise<void>;
} | null;

const AuthContext = createContext<AuthContextValue>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    loading: true,
  });

  useEffect(() => {
    const controller = new AbortController();
    getCurrentUser()
      .then((user) => setState({ user, loading: false }))
      .catch(() => setState({ user: null, loading: false }));
    return () => controller.abort();
  }, []);

  const login = useCallback(async (credentials: Credentials) => {
    const user = await loginApi(credentials);
    setState({ user, loading: false });
    return user;
  }, []);

  const register = useCallback(async (credentials: Credentials) => {
    const user = await registerApi(credentials);
    setState({ user, loading: false });
    return user;
  }, []);

  const logout = useCallback(async () => {
    await logoutApi();
    setState({ user: null, loading: false });
  }, []);

  const value: AuthContextValue = {
    user: state.user,
    loading: state.loading,
    login,
    register,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth 必须在 AuthProvider 内部使用");
  }
  return context;
}
