'use client';

import React from 'react';
import { AccessibilityBar } from '@/components/public/AccessibilityBar';
import { GovernmentHeader } from '@/components/public/GovernmentHeader';
import { Navigation } from '@/components/public/Navigation';
import { EmergencyBanner } from '@/components/public/EmergencyBanner';
import { PublicFooter } from '@/components/public/PublicFooter';

export default function PublicLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col min-h-screen">
      {/* Top GIGW Accessibility & Language Selector Bar */}
      <AccessibilityBar />

      {/* Official Government Identity Header */}
      <GovernmentHeader />

      {/* Responsive Navigation Bar */}
      <Navigation />

      {/* Emergency Alert Broadcast (inactive by default; rendered conditionally) */}
      <EmergencyBanner />

      {/* Main Content Landmark for WCAG 2.2 AA */}
      <main id="main-content" role="main" className="flex-1 py-6 px-4 sm:px-6 max-w-7xl w-full mx-auto">
        {children}
      </main>

      {/* GIGW-Compliant Public Footer */}
      <PublicFooter />
    </div>
  );
}
