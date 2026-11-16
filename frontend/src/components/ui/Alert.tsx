'use client';

import React from 'react';

export type AlertSeverity = 'info' | 'warning' | 'danger';

interface AlertProps {
  severity?: AlertSeverity;
  title?: string;
  children: React.ReactNode;
  actionUrl?: string;
  actionLabel?: string;
  className?: string;
}

export function Alert({
  severity = 'info',
  title,
  children,
  actionUrl,
  actionLabel,
  className = '',
}: AlertProps) {
  const styles = {
    info: 'bg-[var(--alert-info-bg)] text-[var(--alert-info-text)] border-[var(--alert-info-border)]',
    warning: 'bg-[var(--alert-warning-bg)] text-[var(--alert-warning-text)] border-[var(--alert-warning-border)]',
    danger: 'bg-[var(--alert-danger-bg)] text-[var(--alert-danger-text)] border-[var(--alert-danger-border)]',
  };

  const icons = {
    info: (
      <svg className="w-5 h-5 shrink-0" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
      </svg>
    ),
    warning: (
      <svg className="w-5 h-5 shrink-0" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
        <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
      </svg>
    ),
    danger: (
      <svg className="w-5 h-5 shrink-0" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
      </svg>
    ),
  };

  return (
    <div
      role="alert"
      className={`p-4 rounded-lg border flex items-start gap-3 text-sm ${styles[severity]} ${className}`}
    >
      <div className="mt-0.5">{icons[severity]}</div>
      <div className="flex-1">
        {title && <h4 className="font-semibold text-sm mb-1">{title}</h4>}
        <div className="leading-relaxed">{children}</div>
        {actionUrl && actionLabel && (
          <div className="mt-2">
            <a
              href={actionUrl}
              className="inline-flex items-center font-semibold underline hover:no-underline focus-visible:outline-2 focus-visible:outline-offset-1"
            >
              {actionLabel} &rarr;
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
