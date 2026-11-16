'use client';

import React from 'react';

interface CardProps {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  badge?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

export function Card({
  title,
  subtitle,
  badge,
  children,
  footer,
  className = '',
}: CardProps) {
  return (
    <article
      className={`bg-[var(--bg-surface)] border border-[var(--border-muted)] rounded-lg shadow-xs overflow-hidden flex flex-col ${className}`}
    >
      {(title || subtitle || badge) && (
        <header className="px-5 py-4 border-b border-[var(--border-muted)] flex items-start justify-between gap-4">
          <div>
            {title && (
              <h3 className="text-base font-semibold text-[var(--text-primary)]">
                {title}
              </h3>
            )}
            {subtitle && (
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                {subtitle}
              </p>
            )}
          </div>
          {badge && <div className="shrink-0">{badge}</div>}
        </header>
      )}
      <div className="p-5 flex-1">{children}</div>
      {footer && (
        <footer className="px-5 py-3 bg-[var(--bg-muted)] border-t border-[var(--border-muted)] text-xs text-[var(--text-muted)]">
          {footer}
        </footer>
      )}
    </article>
  );
}
