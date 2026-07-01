import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const raw = localStorage.getItem("elite_user");
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(false);

  const persist = useCallback((token, userObj) => {
    localStorage.setItem("elite_token", token);
    localStorage.setItem("elite_user", JSON.stringify(userObj));
    setUser(userObj);
  }, []);

  const login = useCallback(async (email, password) => {
    setLoading(true);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      persist(data.access_token, data.user);
      return data.user;
    } finally {
      setLoading(false);
    }
  }, [persist]);

  const signup = useCallback(async (email, password, full_name, honeypot = "") => {
    setLoading(true);
    try {
      const { data } = await api.post("/auth/signup", { email, password, full_name, website: honeypot });
      persist(data.access_token, data.user);
      return data.user;
    } finally {
      setLoading(false);
    }
  }, [persist]);

  const logout = useCallback(() => {
    localStorage.removeItem("elite_token");
    localStorage.removeItem("elite_user");
    setUser(null);
  }, []);

  // Used by /reset-password after a successful token exchange — persists the
  // freshly-issued access_token + user so the visitor is logged in immediately.
  const setAuthFromResponse = useCallback((data) => {
    if (data?.access_token && data?.user) {
      persist(data.access_token, data.user);
    }
  }, [persist]);

  useEffect(() => {
    // verify token on mount
    if (user && localStorage.getItem("elite_token")) {
      api.get("/auth/me")
        .then(({ data }) => {
          persist(localStorage.getItem("elite_token"), data);
        })
        .catch(() => logout());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AuthContext.Provider value={{ user, login, signup, logout, loading, setAuthFromResponse }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
