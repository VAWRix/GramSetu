'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useAuth } from '@/context/AuthContext';
import { useLanguage } from '@/context/LanguageContext';
import { Alert } from '@/components/ui/Alert';

export function CmsAuthGate({ children }: { children: React.ReactNode }) {
  const {
    user,
    loading,
    isAuthenticated,
    mfaPending,
    maskedEmail,
    authError,
    clearAuthError,
    login,
    verifyMfa,
    resendMfa,
    recoverMfa,
    cancelMfa,
  } = useAuth();
  const { t } = useLanguage();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [recoveryCode, setRecoveryCode] = useState('');
  const [isRecoveryMode, setIsRecoveryMode] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  // Handle resend countdown timer
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const interval = setInterval(() => {
      setResendCooldown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(interval);
  }, [resendCooldown]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] p-8 text-center" role="status" aria-live="polite">
        <div className="w-12 h-12 border-4 border-amber-500 border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-sm font-semibold text-slate-300">
          {t.cmsAuth.sessionVerifying}
        </p>
        <p className="text-xs text-slate-500 mt-1">
          {t.cmsAuth.sessionVerifyingSub}
        </p>
      </div>
    );
  }

  if (isAuthenticated && user) {
    return <>{children}</>;
  }

  // Handle Login submission
  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) return;
    setSubmitting(true);
    setInfoMessage(null);
    const res = await login(email.trim(), password);
    setSubmitting(false);
    if (res.success) {
      setResendCooldown(60);
    }
  };

  // Handle MFA OTP submission
  const handleOtpSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otpCode.trim()) return;
    setSubmitting(true);
    setInfoMessage(null);
    await verifyMfa(otpCode.trim());
    setSubmitting(false);
  };

  // Handle Resend OTP
  const handleResendOtp = async () => {
    if (resendCooldown > 0 || submitting) return;
    setSubmitting(true);
    const res = await resendMfa();
    setSubmitting(false);
    if (res.success) {
      setResendCooldown(60);
      setInfoMessage(res.message || 'नवीन पडताळणी कोड पाठवला गेला आहे.');
    }
  };

  // Handle Emergency Recovery Code submission
  const handleRecoverySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!recoveryCode.trim()) return;
    setSubmitting(true);
    setInfoMessage(null);
    await recoverMfa(recoveryCode.trim());
    setSubmitting(false);
  };

  return (
    <div className="min-h-[80vh] flex flex-col justify-center items-center px-4 py-8 bg-slate-100">
      <div className="w-full max-w-md bg-white border border-slate-200 rounded-xl shadow-xl p-6 sm:p-8 text-slate-900">
        {/* Emblem & Portal Header */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-blue-50 border-2 border-blue-200 text-3xl mb-3 shadow-inner">
            🏛️
          </div>
          <h1 className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight">
            {t.cmsAuth.loginTitle}
          </h1>
          <p className="text-xs text-blue-800 font-bold mt-0.5">
            {t.cms.portalTitle}
          </p>
          <p className="text-[11px] text-slate-600 mt-1">
            {t.cmsAuth.loginSubtitle}
          </p>
        </div>

        {/* Informational Message */}
        {infoMessage && (
          <div className="mb-4">
            <Alert severity="info" title={t.cmsAuth.noticeTitle}>
              {infoMessage}
            </Alert>
          </div>
        )}

        {/* Error Alert */}
        {authError && (
          <div className="mb-4">
            <Alert severity="danger" title={t.cmsAuth.authErrorTitle}>
              <div className="flex justify-between items-start">
                <span>{authError}</span>
                <button
                  type="button"
                  onClick={clearAuthError}
                  className="text-xs text-red-700 underline hover:text-red-900 ml-2 font-semibold"
                >
                  {t.cmsAuth.dismiss}
                </button>
              </div>
            </Alert>
          </div>
        )}

        {/* STEP 1: Email & Password Login Form */}
        {!mfaPending ? (
          <form onSubmit={handleLoginSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="admin-email"
                className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1"
              >
                {t.cmsAuth.emailLabel}
              </label>
              <input
                id="admin-email"
                type="email"
                required
                autoComplete="email"
                placeholder="officer@grampanchayat.gov.in"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={submitting}
                className="w-full px-3.5 py-2.5 rounded-lg bg-white border border-slate-300 text-slate-900 placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent transition-all shadow-sm"
              />
            </div>

            <div>
              <label
                htmlFor="admin-password"
                className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1"
              >
                {t.cmsAuth.passwordLabel}
              </label>
              <input
                id="admin-password"
                type="password"
                required
                autoComplete="current-password"
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={submitting}
                className="w-full px-3.5 py-2.5 rounded-lg bg-white border border-slate-300 text-slate-900 placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent transition-all shadow-sm"
              />
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={submitting || !email.trim() || !password}
                className="w-full py-2.5 px-4 rounded-lg bg-[#1e3a8a] hover:bg-blue-800 text-white font-bold text-sm tracking-wide transition-all shadow-md hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {submitting ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>{t.cmsAuth.verifyingButton}</span>
                  </>
                ) : (
                  <>
                    <span>{t.cmsAuth.signInButton}</span>
                    <span>&rarr;</span>
                  </>
                )}
              </button>
            </div>

            <div className="pt-4 border-t border-slate-200 text-center">
              <p className="text-[11px] text-slate-600">
                {t.cmsAuth.mfaPolicyNote}
              </p>
            </div>
          </form>
        ) : isRecoveryMode ? (
          /* STEP 2B: Emergency Recovery Code */
          <form onSubmit={handleRecoverySubmit} className="space-y-4">
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-900">
              <p className="font-bold mb-1">
                ⚠️ {t.cmsAuth.recoveryTitle}
              </p>
              <p className="text-[11px] text-red-800">
                {t.cmsAuth.recoveryDesc}
              </p>
            </div>

            <div>
              <label
                htmlFor="recovery-code"
                className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1"
              >
                {t.cmsAuth.recoveryCodeLabel}
              </label>
              <input
                id="recovery-code"
                type="text"
                required
                autoFocus
                placeholder="उदा. A1B2C3D4"
                value={recoveryCode}
                onChange={(e) => setRecoveryCode(e.target.value.toUpperCase())}
                disabled={submitting}
                className="w-full px-3.5 py-2.5 rounded-lg bg-white border border-slate-300 text-slate-900 placeholder-slate-400 text-center font-mono tracking-widest text-base focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent uppercase shadow-sm"
              />
            </div>

            <div className="space-y-2 pt-2">
              <button
                type="submit"
                disabled={submitting || !recoveryCode.trim()}
                className="w-full py-2.5 px-4 rounded-lg bg-red-700 hover:bg-red-800 text-white font-bold text-sm tracking-wide transition-all shadow-md disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {submitting ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>{t.cmsAuth.verifyingButton}</span>
                  </>
                ) : (
                  <span>{t.cmsAuth.recoveryTitle}</span>
                )}
              </button>

              <button
                type="button"
                onClick={() => setIsRecoveryMode(false)}
                className="w-full py-2 text-xs text-slate-600 hover:text-slate-900 transition-colors font-semibold"
              >
                &larr; {t.cmsAuth.backToOtpLink}
              </button>
            </div>
          </form>
        ) : (
          /* STEP 2A: Email OTP MFA Verification Form */
          <form onSubmit={handleOtpSubmit} className="space-y-4">
            <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-900">
              <p className="font-bold mb-1">
                🔐 {t.cmsAuth.mfaChallengeTitle}
              </p>
              <p className="text-[11px] text-blue-800">
                {t.cmsAuth.mfaChallengeDesc} <strong className="font-mono text-blue-950 font-bold">{maskedEmail}</strong>
              </p>
            </div>

            <div>
              <label
                htmlFor="otp-code"
                className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1"
              >
                {t.cmsAuth.otpLabel}
              </label>
              <input
                id="otp-code"
                type="text"
                required
                autoFocus
                maxLength={8}
                placeholder="123456"
                value={otpCode}
                onChange={(e) => setOtpCode(e.target.value.replace(/[^0-9]/g, ''))}
                disabled={submitting}
                className="w-full px-3.5 py-2.5 rounded-lg bg-white border border-slate-300 text-slate-900 placeholder-slate-400 text-center font-mono tracking-widest text-lg sm:text-xl font-bold focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent shadow-sm"
              />
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={submitting || otpCode.trim().length < 6}
                className="w-full py-2.5 px-4 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-white font-bold text-sm tracking-wide transition-all shadow-md hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {submitting ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>{t.cmsAuth.verifyingButton}</span>
                  </>
                ) : (
                  <span>{t.cmsAuth.verifyOtpButton}</span>
                )}
              </button>
            </div>

            {/* Resend & Recovery Options */}
            <div className="flex flex-col gap-2 pt-3 border-t border-slate-200 text-center text-xs">
              <div className="flex items-center justify-between text-slate-600">
                <span>{t.cmsAuth.otpLabel}?</span>
                <button
                  type="button"
                  onClick={handleResendOtp}
                  disabled={resendCooldown > 0 || submitting}
                  className="text-blue-700 hover:text-blue-900 disabled:opacity-50 disabled:cursor-not-allowed underline font-semibold"
                >
                  {resendCooldown > 0
                    ? `${t.cmsAuth.resendWait} (${resendCooldown}s)`
                    : t.cmsAuth.resendOtpButton}
                </button>
              </div>

              <div className="flex items-center justify-between pt-1">
                <button
                  type="button"
                  onClick={() => setIsRecoveryMode(true)}
                  className="text-red-700 hover:text-red-900 underline text-[11px] font-semibold"
                >
                  {t.cmsAuth.useRecoveryLink}
                </button>

                <button
                  type="button"
                  onClick={cancelMfa}
                  className="text-slate-600 hover:text-slate-900 text-[11px] font-semibold"
                >
                  {t.cmsAuth.cancelButton}
                </button>
              </div>
            </div>
          </form>
        )}

        {/* Back to Public Portal Link */}
        <div className="mt-6 pt-4 border-t border-slate-200 text-center">
          <Link
            href="/"
            className="text-xs text-blue-700 hover:text-blue-900 hover:underline inline-flex items-center gap-1.5 focus-visible:outline-blue-600 font-semibold"
          >
            &larr; {t.cms.backToPublic}
          </Link>
        </div>
      </div>
    </div>
  );
}
