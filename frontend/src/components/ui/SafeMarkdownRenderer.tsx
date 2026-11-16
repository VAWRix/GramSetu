'use client';

import React from 'react';

interface SafeMarkdownRendererProps {
  content?: string | null;
  className?: string;
}

export function SafeMarkdownRenderer({ content, className = '' }: SafeMarkdownRendererProps) {
  if (!content || !content.trim()) {
    return null;
  }

  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let inList: 'ul' | 'ol' | null = null;
  let listItems: string[] = [];

  function flushList() {
    if (inList === 'ul' && listItems.length > 0) {
      elements.push(
        <ul key={`ul-${elements.length}`} className="list-disc list-inside space-y-1 my-2 pl-2 text-[var(--text-primary)]">
          {listItems.map((li, idx) => (
            <li key={idx}>{renderInline(li)}</li>
          ))}
        </ul>
      );
    } else if (inList === 'ol' && listItems.length > 0) {
      elements.push(
        <ol key={`ol-${elements.length}`} className="list-decimal list-inside space-y-1 my-2 pl-2 text-[var(--text-primary)]">
          {listItems.map((li, idx) => (
            <li key={idx}>{renderInline(li)}</li>
          ))}
        </ol>
      );
    }
    inList = null;
    listItems = [];
  }

  function renderInline(text: string): React.ReactNode {
    const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match;

    while ((match = linkRegex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(renderTextDecorations(text.substring(lastIndex, match.index)));
      }
      const label = match[1];
      const href = match[2];
      const isExternal = href.startsWith('http://') || href.startsWith('https://');
      parts.push(
        <a
          key={`link-${match.index}`}
          href={href}
          target={isExternal ? '_blank' : undefined}
          rel={isExternal ? 'noopener noreferrer' : undefined}
          className="text-[#1e3a8a] dark:text-blue-400 underline hover:text-blue-900 dark:hover:text-blue-300 font-medium"
        >
          {label}
        </a>
      );
      lastIndex = match.index + match[0].length;
    }
    if (lastIndex < text.length) {
      parts.push(renderTextDecorations(text.substring(lastIndex)));
    }
    return parts.length > 0 ? parts : renderTextDecorations(text);
  }

  function renderTextDecorations(text: string): React.ReactNode {
    const boldParts = text.split(/(\*\*[^*]+\*\*)/g);
    return boldParts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="font-bold text-[var(--text-primary)]">{part.slice(2, -2)}</strong>;
      }
      return part;
    });
  }

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const line = rawLine.trim();

    if (!line) {
      flushList();
      continue;
    }

    if (line.startsWith('# ')) {
      flushList();
      elements.push(
        <h1 key={i} className="text-xl sm:text-2xl font-bold text-[var(--text-primary)] mt-4 mb-2 border-b border-[var(--border-muted)] pb-1">
          {renderInline(line.substring(2))}
        </h1>
      );
    } else if (line.startsWith('## ')) {
      flushList();
      elements.push(
        <h2 key={i} className="text-lg sm:text-xl font-bold text-[var(--text-primary)] mt-3 mb-1.5 border-b border-[var(--border-muted)] pb-0.5">
          {renderInline(line.substring(3))}
        </h2>
      );
    } else if (line.startsWith('### ')) {
      flushList();
      elements.push(
        <h3 key={i} className="text-sm sm:text-base font-bold text-[var(--text-primary)] mt-2.5 mb-1">
          {renderInline(line.substring(4))}
        </h3>
      );
    } else if (line.startsWith('> ')) {
      flushList();
      elements.push(
        <blockquote key={i} className="border-l-4 border-blue-600 bg-blue-50/50 dark:bg-blue-950/30 pl-3 py-1.5 my-2 text-xs italic text-[var(--text-secondary)] rounded-r">
          {renderInline(line.substring(2))}
        </blockquote>
      );
    } else if (/^[-*]\s+/.test(line)) {
      if (inList !== 'ul') flushList();
      inList = 'ul';
      listItems.push(line.replace(/^[-*]\s+/, ''));
    } else if (/^\d+\.\s+/.test(line)) {
      if (inList !== 'ol') flushList();
      inList = 'ol';
      listItems.push(line.replace(/^\d+\.\s+/, ''));
    } else {
      flushList();
      elements.push(
        <p key={i} className="my-1.5 text-xs sm:text-sm text-[var(--text-secondary)] leading-relaxed">
          {renderInline(line)}
        </p>
      );
    }
  }
  flushList();

  return <div className={`space-y-1 ${className}`}>{elements}</div>;
}

export default SafeMarkdownRenderer;
