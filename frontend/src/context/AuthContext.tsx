'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import {
  AuthUser,
  fetchAuthMe,
  loginAdmin,
  verifyMfa as apiVerifyMfa,
  resendMfa as apiResendMfa,
  recoverMfa as apiRecoverMfa,
  logoutAdmin,
  fetchCsrfToken,
} from '@/lib/api';

interface AuthContextType {
  user: AuthUser | null;
  loading: boolean;
  isAuthenticated: boolean;
  mfaPending: boolean;
  maskedEmail: string | null;
  mfaExpiresIn: number | null;
  authError: string | null;
  clearAuthError: () => void;
  login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  verifyMfa: (code: string) => Promise<{ success: boolean; error?: string }>;
  resendMfa: () => Promise<{ success: boolean; message?: string; error?: string }>;
  recoverMfa: (recoveryCode: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => Promise<void>;
  cancelMfa: () => void;
  checkSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [mfaPending, setMfaPending] = useState<boolean>(false);
  const [maskedEmail, setMaskedEmail] = useState<string | null>(null);
  const [mfaExpiresIn, setMfaExpiresIn] = useState<number | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  const clearAuthError = useCallback(() => {
    setAuthError(null);
  }, []);

  const checkSession = useCallback(async () => {
    try {
      await fetchCsrfToken();
      const me = await fetchAuthMe();
      if (me && me.authenticated && me.user) {
        setUser(me.user);
        setMfaPending(false);
      } else {
        setUser(null);
      }
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let isMounted = true;
    const init = async () => {
      try {
        await fetchCsrfToken();
        const me = await fetchAuthMe();
        if (isMounted) {
          if (me && me.authenticated && me.user) {
            setUser(me.user);
            setMfaPending(false);
          } else {
            setUser(null);
          }
        }
      } catch {
        if (isMounted) {
          setUser(null);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    init();

    return () => {
      isMounted = false;
    };
  }, []);

  const login = async (email: string, password: string): Promise<{ success: boolean; error?: string }> => {
    setAuthError(null);
    const result = await loginAdmin({ email, password });
    if (result.success && result.data) {
      if (result.data.mfa_required) {
        setMfaPending(true);
        setMaskedEmail(result.data.email_masked);
        setMfaExpiresIn(result.data.expires_in_seconds);
        return { success: true };
      }
    }
    const errMsg = result.error || 'Authentication failed. Please verify credentials.';
    setAuthError(errMsg);
    return { success: false, error: errMsg };
  };

  const verifyMfa = async (code: string): Promise<{ success: boolean; error?: string }> => {
    setAuthError(null);
    const result = await apiVerifyMfa(code);
    if (result.success && result.data && result.data.user) {
      setUser(result.data.user);
      setMfaPending(false);
      setMaskedEmail(null);
      setMfaExpiresIn(null);
      return { success: true };
    }
    const errMsg = result.error || 'Verification failed. Please check the code.';
    setAuthError(errMsg);
    return { success: false, error: errMsg };
  };

  const resendMfa = async (): Promise<{ success: boolean; message?: string; error?: string }> => {
    setAuthError(null);
    const result = await apiResendMfa();
    if (result.success && result.data) {
      if (result.data.expires_in_seconds) {
        setMfaExpiresIn(result.data.expires_in_seconds);
      }
      return { success: true, message: result.data.message };
    }
    const errMsg = result.error || 'Failed to resend code. Please wait before retrying.';
    setAuthError(errMsg);
    return { success: false, error: errMsg };
  };

  const recoverMfa = async (recoveryCode: string): Promise<{ success: boolean; error?: string }> => {
    setAuthError(null);
    const result = await apiRecoverMfa(recoveryCode);
    if (result.success && result.data && result.data.user) {
      setUser(result.data.user);
      setMfaPending(false);
      setMaskedEmail(null);
      setMfaExpiresIn(null);
      return { success: true };
    }
    const errMsg = result.error || 'Invalid or previously used recovery code.';
    setAuthError(errMsg);
    return { success: false, error: errMsg };
  };

  const logout = async (): Promise<void> => {
    await logoutAdmin();
    setUser(null);
    setMfaPending(false);
    setMaskedEmail(null);
    setMfaExpiresIn(null);
    setAuthError(null);
  };

  const cancelMfa = () => {
    setMfaPending(false);
    setMaskedEmail(null);
    setMfaExpiresIn(null);
    setAuthError(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isAuthenticated: !!user,
        mfaPending,
        maskedEmail,
        mfaExpiresIn,
        authError,
        clearAuthError,
        login,
        verifyMfa,
        resendMfa,
        recoverMfa,
        logout,
        cancelMfa,
        checkSession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
