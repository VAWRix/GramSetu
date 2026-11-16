'use client';

import React from 'react';
import { useLanguage } from '@/context/LanguageContext';
import { Alert } from '../ui/Alert';

export function SecurityBanner() {
  const { t, language } = useLanguage();

  return (
    <div className="space-y-3 mb-6">
      {/* Session Security Alert */}
      <Alert
        severity="info"
        title={
          language === 'mr'
            ? 'प्रशासकीय सत्र सुरक्षा'
            : language === 'hi'
            ? 'प्रशासनिक सत्र सुरक्षा'
            : 'Administrative Session Security'
        }
      >
        <p>{t.cms.sessionNotice} {t.cms.sessionTimeoutWarning}</p>
        <p className="mt-1 text-xs opacity-90">
          {language === 'mr'
            ? 'प्रशासकीय प्रमाणपत्रे किंवा टोकन्स ब्राउझर LocalStorage मध्ये साठवली जात नाहीत (Strict HttpOnly Cookie Enforcement).'
            : language === 'hi'
            ? 'प्रशासनिक क्रेडेंशियल या टोकन ब्राउज़र LocalStorage में संग्रहीत नहीं किए जाते हैं (Strict HttpOnly Cookie Enforcement)।'
            : 'Administrative credentials or tokens are never stored in browser LocalStorage (Strict HttpOnly Cookie Enforcement).'}
        </p>
      </Alert>

      {/* MFA Active Enforcement Status */}
      <Alert
        severity="info"
        title={
          language === 'mr'
            ? 'बहु-घटक प्रमाणीकरण सक्रिय'
            : language === 'hi'
            ? 'बहु-घटक प्रमाणीकरण सक्रिय'
            : 'Multi-Factor Authentication (MFA) Active'
        }
      >
        <p>
          {language === 'mr'
            ? 'सर्व प्रशासकीय खाती (Super Administrator आणि Operator) अनिवार्य बहु-घटक प्रमाणीकरणाने सुरक्षित आहेत.'
            : language === 'hi'
            ? 'सभी प्रशासनिक खाते अनिवार्य बहु-घटक प्रमाणीकरण (Email OTP और आपातकालीन पुनर्प्राप्ति कोड) द्वारा सुरक्षित हैं।'
            : 'All administrative accounts are protected by mandatory Multi-Factor Authentication (Email OTP and Emergency Recovery Codes).'}
        </p>
        <p className="mt-1 text-xs opacity-90">
          {language === 'mr'
            ? 'केवळ पासवर्डने प्रशासकीय प्रवेश पूर्णपणे प्रतिबंधित आहे.'
            : language === 'hi'
            ? 'केवल पासवर्ड से प्रशासनिक पहुंच पूरी तरह प्रतिबंधित है।'
            : 'Mandatory Multi-Factor Authentication is enforced on all administrative sessions. Password-only administrative access is strictly blocked.'}
        </p>
      </Alert>

      {/* Dual Control & Governance Notice */}
      <Alert
        severity="info"
        title={
          language === 'mr'
            ? 'शासन कार्यप्रवाह नियम'
            : language === 'hi'
            ? 'शासन कार्यप्रवाह नियम'
            : 'Governance Workflow Rules'
        }
      >
        <p>{t.cms.dualApprovalNotice}</p>
        <p className="mt-1 text-xs opacity-90">
          {language === 'mr'
            ? 'कार्यप्रवाह स्थिती चक्र: मसुदा → सादर → मंजूर → प्रसिद्ध. सादर केलेले बदल परस्पर बदलता येत नाहीत.'
            : language === 'hi'
            ? 'कार्यप्रवाह स्थिति चक्र: मसौदा → प्रस्तुत → अनुमोदित → प्रकाशित। प्रस्तुत परिवर्तन बदले नहीं जा सकते।'
            : 'Revisions follow an immutable state machine: Draft → Submitted → Approved → Published. Submitted revisions are locked against alteration.'}
        </p>
      </Alert>
    </div>
  );
}
