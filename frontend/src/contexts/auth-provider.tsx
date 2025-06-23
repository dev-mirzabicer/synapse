"use client";

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { UserRead } from '@/types';
import { JWT_TOKEN_KEY } from '@/lib/constants';
import { fetchWithAuth } from '@/lib/api';

interface AuthContextType {
  isAuthenticated: boolean;
  user: UserRead | null;
  token: string | null;
  login: (token: string) => void;
  logout: () => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserRead | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  const fetchUser = useCallback(async (authToken: string) => {
    try {
      const userData = await fetchWithAuth('/auth/me', { token: authToken });
      setUser(userData);
      setToken(authToken);
    } catch (error) {
      console.error('Failed to fetch user', error);
      localStorage.removeItem(JWT_TOKEN_KEY);
      setToken(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const storedToken = localStorage.getItem(JWT_TOKEN_KEY);
    if (storedToken) {
      fetchUser(storedToken);
    } else {
      setIsLoading(false);
    }
  }, [fetchUser]);

  const login = (newToken: string) => {
    localStorage.setItem(JWT_TOKEN_KEY, newToken);
    setIsLoading(true);
    fetchUser(newToken);
  };

  const logout = () => {
    localStorage.removeItem(JWT_TOKEN_KEY);
    setUser(null);
    setToken(null);
    router.push('/login');
  };

  const value = {
    isAuthenticated: !!token,
    user,
    token,
    login,
    logout,
    isLoading,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
