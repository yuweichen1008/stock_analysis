"use client";

import { useState, useEffect, useCallback } from "react";

export interface AuthUser {
  id:           number;
  email:        string | null;
  display_name: string;
  coins:        number;
  avatar_url:   string | null;
  auth_provider: string;
  has_ctbc:     boolean;
  has_moomoo:   boolean;
}

const TOKEN_KEY = "loki_token";
const USER_KEY  = "loki_user";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function setSession(token: string, user: AuthUser): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ── React hook ────────────────────────────────────────────────────────────────

export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    setUser(getUser());
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<void> => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Login failed");
    }
    const data = await res.json();
    setSession(data.access_token, data.user);
    setUser(data.user);
  }, []);

  const register = useCallback(async (
    email: string,
    password: string,
    displayName?: string,
  ): Promise<void> => {
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, display_name: displayName }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Registration failed");
    }
    const data = await res.json();
    setSession(data.access_token, data.user);
    setUser(data.user);
  }, []);

  const logout = useCallback((): void => {
    clearSession();
    setUser(null);
  }, []);

  const refreshUser = useCallback(async (): Promise<void> => {
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch("/api/auth/me", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const u = await res.json();
        localStorage.setItem(USER_KEY, JSON.stringify(u));
        setUser(u);
      }
    } catch {
      // silently ignore
    }
  }, []);

  return { user, login, register, logout, refreshUser, isLoggedIn: !!user };
}
