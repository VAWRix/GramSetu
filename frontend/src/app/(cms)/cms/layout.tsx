'use client';

import React from 'react';
import { AuthProvider } from '@/context/AuthContext';
import { CmsHeader } from '@/components/cms/CmsHeader';
import { CmsSidebar } from '@/components/cms/CmsSidebar';
import { SecurityBanner } from '@/components/cms/SecurityBanner';
import { CmsAuthGate } from '@/components/cms/CmsAuthGate';
import { SkipLink } from '@/components/ui/SkipLink';

function CmsLayoutContent({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col min-h-screen bg-slate-100 text-slate-900 font-sans">
      <SkipLink targetId="cms-main-content" />

      {/* Dedicated Administrative Header */}
      <CmsHeader />

      <CmsAuthGate>
        {/* Main CMS Layout with Sidebar (only rendered when authenticated) */}
        <div className="flex-1 flex flex-col md:flex-row">
          {/* Sidebar Navigation */}
          <CmsSidebar />

          {/* CMS Main Content Area */}
          <main
            id="cms-main-content"
            role="main"
            className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full bg-slate-50 overflow-y-auto"
          >
            {/* Statutory Security & Governance Notice Banner */}
            <SecurityBanner />

            {/* Child Page Content */}
            {children}
          </main>
        </div>
      </CmsAuthGate>

      {/* CMS Administrative Footer */}
      <footer className="bg-white border-t border-slate-200 py-3 px-4 text-center text-xs text-slate-600 shadow-sm">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2">
          <span className="font-semibold text-slate-700">GramSetu Administrative Backoffice v1.0.0</span>
          <span className="text-slate-500">Dual-Control Governance Architecture • Immutable Audit Logging • Mandatory MFA</span>
        </div>
      </footer>
    </div>
  );
}

export default function CmsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthProvider>
      <CmsLayoutContent>{children}</CmsLayoutContent>
    </AuthProvider>
  );
}
