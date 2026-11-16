import type { Metadata } from 'next';
import './globals.css';
import { LanguageProvider } from '@/context/LanguageContext';
import { AccessibilityProvider } from '@/context/AccessibilityContext';

export const metadata: Metadata = {
  title: 'GramSetu — Official Gram Panchayat Information Portal | ग्रामसेतू',
  description: 'Official information portal and administrative platform for Gram Panchayats in Maharashtra, India. Developed in compliance with GIGW and WCAG 2.2 AA standards.',
  icons: {
    icon: '/favicon.ico',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="mr" data-theme="light" data-font-size="normal">
      <body className="antialiased min-h-screen flex flex-col">
        <LanguageProvider>
          <AccessibilityProvider>
            {children}
          </AccessibilityProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
