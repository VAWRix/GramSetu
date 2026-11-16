'use client';

import React, { useEffect, useState } from 'react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { useLanguage } from '@/context/LanguageContext';
import { fetchAuthMe, fetchCmsPanchayatProfile, updateCmsPanchayatProfile, CmsPanchayatProfile } from '@/lib/api';
import type { AuthUser } from '@/lib/types';

export default function CmsProfilePage() {
  const { language } = useLanguage();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [profile, setProfile] = useState<CmsPanchayatProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Form states
  const [sarpanchName, setSarpanchName] = useState('');
  const [gramSevakName, setGramSevakName] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [officeAddressMr, setOfficeAddressMr] = useState('');
  const [officeAddressEn, setOfficeAddressEn] = useState('');
  const [panchayatNameMr, setPanchayatNameMr] = useState('');
  const [panchayatNameEn, setPanchayatNameEn] = useState('');
  const [showArchivedNotices, setShowArchivedNotices] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const me = await fetchAuthMe();
        if (me && me.authenticated) {
          setCurrentUser(me.user);
        }

        const data = await fetchCmsPanchayatProfile();
        if (data?.profile) {
          const p = data.profile;
          setProfile(p);
          setSarpanchName(p.sarpanch_name || (language === 'en' ? '[Name Pending Verification]' : '[नाव प्रलंबित]'));
          setGramSevakName(p.gram_sevak_name || (language === 'en' ? 'ASHOK GANPAT WALE' : 'अशोक गणपत वाले'));
          setContactPhone(p.contact_phone || '');
          setContactEmail(p.contact_email || '');
          setOfficeAddressMr(p.office_address_mr || '');
          setOfficeAddressEn(p.office_address_en || '');
          setPanchayatNameMr(p.panchayat_name_mr || '');
          setPanchayatNameEn(p.panchayat_name_en || '');
          setShowArchivedNotices(p.show_archived_notices_publicly ?? true);
        }
      } catch (err) {
        console.error('Failed to load profile:', err);
        setError('ग्रामपंचायत प्रोफाईल लोड करताना त्रुटी आली.');
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const isSuperAdmin = currentUser?.is_super_admin ?? false;

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!isSuperAdmin) return;

    if (!sarpanchName.trim()) {
      setError(language === 'mr' ? 'सरपंचांचे नाव आवश्यक आहे.' : 'Sarpanch name is required.');
      return;
    }
    if (!gramSevakName.trim()) {
      setError(language === 'mr' ? 'ग्रामसेवकांचे नाव आवश्यक आहे.' : 'Gram Sevak name is required.');
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccessMsg(null);

      const result = await updateCmsPanchayatProfile({
        sarpanch_name: sarpanchName.trim(),
        gram_sevak_name: gramSevakName.trim(),
        contact_phone: contactPhone.trim(),
        contact_email: contactEmail.trim(),
        office_address_mr: officeAddressMr.trim(),
        office_address_en: officeAddressEn.trim(),
        panchayat_name_mr: panchayatNameMr.trim(),
        panchayat_name_en: panchayatNameEn.trim(),
        show_archived_notices_publicly: showArchivedNotices,
      });

      if (result.success && result.data?.profile) {
        setProfile(result.data.profile);
        setSuccessMsg(
          language === 'mr'
            ? 'ग्रामपंचायत प्रोफाईल व पदाधिकारी माहिती यशस्वीरीत्या अद्ययावत झाली.'
            : language === 'hi'
            ? 'ग्राम पंचायत प्रोफ़ाइल और पदाधिकारी विवरण सफलतापूर्वक अद्यतित किए गए।'
            : 'Panchayat profile and official office-holder details updated successfully.'
        );
      } else {
        setError(result.error || 'अद्ययावत करताना त्रुटी आली.');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Server error');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="p-8 text-center text-slate-500">
        <p className="animate-pulse">ग्रामपंचायत प्रोफाईल लोड होत आहे / Loading profile...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Title & Introduction */}
      <div className="border-b border-slate-200 pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
            {language === 'mr' ? 'पंचायत प्रोफाईल व पदाधिकारी व्यवस्थापन' : language === 'hi' ? 'पंचायत प्रोफ़ाइल और पदाधिकारी प्रबंधन' : 'Panchayat Profile & Officials Management'}
          </h1>
          <p className="text-xs text-slate-600 mt-1">
            {language === 'mr'
              ? 'ग्रामपंचायतीची वैधानिक ओळख, संपर्क पत्ते आणि सरपंच / ग्रामसेवक पदाधिकाऱ्यांची अधिकृत माहिती.'
              : language === 'hi'
              ? 'ग्राम पंचायत की वैधानिक पहचान, संपर्क पते और सरपंच / ग्रामसेवक पदाधिकारियों का आधिकारिक विवरण।'
              : 'Statutory identity, official contacts, and Sarpanch/Gram Sevak office-holder records.'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={isSuperAdmin ? 'primary' : 'neutral'}>
            {isSuperAdmin
              ? (language === 'mr' ? 'मुख्य प्रशासक (ग्रामसेवक)' : 'Super Admin (Gram Sevak)')
              : (language === 'mr' ? 'ऑपरेटर (वाचनीय प्रवेश)' : 'Operator (Read-Only)')}
          </Badge>
        </div>
      </div>

      {/* Role Notice */}
      {!isSuperAdmin ? (
        <Alert severity="warning">
          <div className="text-xs space-y-1">
            <p className="font-bold">
              {language === 'mr' ? 'केवळ वाचनीय अधिकार (Read-Only Mode)' : 'Read-Only Administrative Mode'}
            </p>
            <p>
              {language === 'mr'
                ? 'सरपंच हा लोकप्रतिनिधी असतो व त्यांचे नाव, संपर्क किंवा कार्यकाळ बदलण्याचे अधिकार केवळ मुख्य प्रशासक (ग्रामसेवक) यांच्याकडे आहेत. ऑपरेटर केवळ ही माहिती पाहू शकतात.'
                : 'Sarpanch is an elected political position. Updating official leadership records is strictly reserved for the Super Administrator (Gram Sevak). Operators have read-only access.'}
            </p>
          </div>
        </Alert>
      ) : (
        <Alert severity="info">
          <div className="text-xs space-y-1">
            <p className="font-bold">
              {language === 'mr' ? 'निवडणूक व पदाधिकारी अद्ययावतीकरण धोरण' : 'Electoral & Leadership Update Policy'}
            </p>
            <p>
              {language === 'mr'
                ? 'ग्रामपंचायत सार्वत्रिक निवडणुकीनंतर नवीन सरपंच निवडून आल्यावर किंवा पदभार बदलल्यावर आपण येथे थेट नाव व संपर्क बदलू शकता. कोणताही कोड बदल किंवा डेटाबेस मायग्रेशन करण्याची गरज नाही.'
                : 'When elections occur and a new Sarpanch assumes office, update the name and contact details here directly. No code changes or database migrations are required.'}
            </p>
          </div>
        </Alert>
      )}

      {error && <Alert severity="danger">{error}</Alert>}
      {successMsg && <Alert severity="info">{successMsg}</Alert>}

      {/* Statutory Identifiers (Read-Only) */}
      <Card title={language === 'mr' ? 'वैधानिक ओळख व भौगोलिक कोड (LGD & Census)' : 'Statutory Identifiers (LGD & Census)'}>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-xs">
          <div className="bg-slate-50 p-3 rounded border border-slate-200">
            <span className="text-slate-500 font-medium block">LGD कोड / LGD Code:</span>
            <span className="font-mono font-bold text-sm text-blue-800">{profile?.lgd_code}</span>
          </div>
          <div className="bg-slate-50 p-3 rounded border border-slate-200">
            <span className="text-slate-500 font-medium block">जनगणना कोड / Census 2011 Code:</span>
            <span className="font-mono font-bold text-sm text-slate-800">{profile?.census_code}</span>
          </div>
          <div className="bg-slate-50 p-3 rounded border border-slate-200">
            <span className="text-slate-500 font-medium block">तालुका / Taluka:</span>
            <span className="font-bold text-sm text-slate-800">{profile?.taluka_name_mr} ({profile?.taluka_name_en})</span>
          </div>
          <div className="bg-slate-50 p-3 rounded border border-slate-200">
            <span className="text-slate-500 font-medium block">जिल्हा / District:</span>
            <span className="font-bold text-sm text-slate-800">{profile?.district_name_mr} ({profile?.district_name_en})</span>
          </div>
        </div>
      </Card>

      {/* Main Editable Form */}
      <form onSubmit={handleSave} className="space-y-6">
        {/* Office-Holders Section */}
        <Card title={language === 'mr' ? 'ग्रामपंचायत पदाधिकारी (Elected & Executive Officials)' : 'Office-Holders (Elected & Executive)'}>
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-800 mb-1">
                  {language === 'mr' ? 'सरपंचांचे नाव (लोकप्रतिनिधी)' : 'Sarpanch Name (Elected Representative)'} *
                </label>
                <input
                  type="text"
                  value={sarpanchName}
                  onChange={(e) => setSarpanchName(e.target.value)}
                  disabled={!isSuperAdmin}
                  className="w-full px-3 py-2 border border-slate-300 rounded text-xs focus:ring-2 focus:ring-blue-500 disabled:bg-slate-100 disabled:text-slate-600"
                  placeholder="उदा. श्री. / सौ. सरपंच नाव"
                  required
                />
                <p className="text-[11px] text-slate-500 mt-1">
                  {language === 'mr'
                    ? 'सार्वजनिक संकेतस्थळावर (About व Footer) हे नाव थेट प्रदर्शित केले जाते.'
                    : 'Displayed dynamically on public portal About page and Footer.'}
                </p>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-800 mb-1">
                  {language === 'mr' ? 'ग्रामसेवकांचे नाव (प्रशासकीय प्रमुख)' : 'Gram Sevak Name (Administrative Executive)'} *
                </label>
                <input
                  type="text"
                  value={gramSevakName}
                  onChange={(e) => setGramSevakName(e.target.value)}
                  disabled={!isSuperAdmin}
                  className="w-full px-3 py-2 border border-slate-300 rounded text-xs focus:ring-2 focus:ring-blue-500 disabled:bg-slate-100 disabled:text-slate-600"
                  placeholder={language === 'mr' ? 'उदा. अशोक गणपत वाले' : 'e.g. ASHOK GANPAT WALE'}
                  required
                />
                <p className="text-[11px] text-slate-500 mt-1">
                  {language === 'mr'
                    ? 'ग्रामविकास अधिकारी / ग्रामसेवक प्रशासकीय जबाबदारी सांभाळतात.'
                    : 'Village Development Officer / Gram Sevak executive.'}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-800 mb-1">
                  {language === 'mr' ? 'अधिकृत संपर्क दूरध्वनी' : 'Official Contact Phone'}
                </label>
                <input
                  type="text"
                  value={contactPhone}
                  onChange={(e) => setContactPhone(e.target.value)}
                  disabled={!isSuperAdmin}
                  className="w-full px-3 py-2 border border-slate-300 rounded text-xs font-mono focus:ring-2 focus:ring-blue-500 disabled:bg-slate-100 disabled:text-slate-600"
                  placeholder="02431-223022"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-800 mb-1">
                  {language === 'mr' ? 'अधिकृत ईमेल पत्ता' : 'Official Contact Email'}
                </label>
                <input
                  type="email"
                  value={contactEmail}
                  onChange={(e) => setContactEmail(e.target.value)}
                  disabled={!isSuperAdmin}
                  className="w-full px-3 py-2 border border-slate-300 rounded text-xs font-mono focus:ring-2 focus:ring-blue-500 disabled:bg-slate-100 disabled:text-slate-600"
                  placeholder="grampanchayat.narayangaon@gov.in"
                />
              </div>
            </div>
          </div>
        </Card>

        {/* Office Details & Addresses */}
        <Card title={language === 'mr' ? 'कार्यालय पत्ता व नाव (Office Name & Address)' : 'Office Name & Address'}>
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-800 mb-1">
                  {language === 'mr' ? 'ग्रामपंचायत कार्यालय नाव (मराठी)' : 'Panchayat Name (Marathi)'}
                </label>
                <input
                  type="text"
                  value={panchayatNameMr}
                  onChange={(e) => setPanchayatNameMr(e.target.value)}
                  disabled={!isSuperAdmin}
                  className="w-full px-3 py-2 border border-slate-300 rounded text-xs focus:ring-2 focus:ring-blue-500 disabled:bg-slate-100 disabled:text-slate-600"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-800 mb-1">
                  {language === 'mr' ? 'ग्रामपंचायत कार्यालय नाव (इंग्रजी)' : 'Panchayat Name (English)'}
                </label>
                <input
                  type="text"
                  value={panchayatNameEn}
                  onChange={(e) => setPanchayatNameEn(e.target.value)}
                  disabled={!isSuperAdmin}
                  className="w-full px-3 py-2 border border-slate-300 rounded text-xs focus:ring-2 focus:ring-blue-500 disabled:bg-slate-100 disabled:text-slate-600"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-800 mb-1">
                  {language === 'mr' ? 'कार्यालय पत्ता (मराठी)' : 'Office Address (Marathi)'}
                </label>
                <textarea
                  rows={3}
                  value={officeAddressMr}
                  onChange={(e) => setOfficeAddressMr(e.target.value)}
                  disabled={!isSuperAdmin}
                  className="w-full px-3 py-2 border border-slate-300 rounded text-xs focus:ring-2 focus:ring-blue-500 disabled:bg-slate-100 disabled:text-slate-600"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-800 mb-1">
                  {language === 'mr' ? 'कार्यालय पत्ता (इंग्रजी)' : 'Office Address (English)'}
                </label>
                <textarea
                  rows={3}
                  value={officeAddressEn}
                  onChange={(e) => setOfficeAddressEn(e.target.value)}
                  disabled={!isSuperAdmin}
                  className="w-full px-3 py-2 border border-slate-300 rounded text-xs focus:ring-2 focus:ring-blue-500 disabled:bg-slate-100 disabled:text-slate-600"
                />
              </div>
            </div>

            <div className="pt-2 border-t border-slate-100 flex items-center gap-2">
              <input
                type="checkbox"
                id="archivedNotices"
                checked={showArchivedNotices}
                onChange={(e) => setShowArchivedNotices(e.target.checked)}
                disabled={!isSuperAdmin}
                className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
              />
              <label htmlFor="archivedNotices" className="text-xs text-slate-700 font-medium">
                {language === 'mr'
                  ? 'मुदत संपलेल्या सूचना सार्वजनिक ऐतिहासिक पुराभिलेखात दर्शवा (Show expired notices publicly in historical archive)'
                  : 'Display expired notices publicly in historical archive'}
              </label>
            </div>
          </div>
        </Card>

        {/* Audit Metadata */}
        {profile?.updated_at && (
          <div className="text-[11px] text-slate-500 flex flex-wrap items-center gap-4 bg-slate-50 p-3 rounded border border-slate-200">
            <span>
              {language === 'mr' ? 'शेवटचा बदल:' : 'Last Updated:'}{' '}
              <strong className="text-slate-700">{new Date(profile.updated_at).toLocaleString()}</strong>
            </span>
            {profile.updated_by && (
              <span>
                {language === 'mr' ? 'अद्ययावतकर्ता:' : 'Updated By:'}{' '}
                <strong className="text-slate-700 font-mono">{profile.updated_by}</strong>
              </span>
            )}
          </div>
        )}

        {/* Submit Actions */}
        {isSuperAdmin && (
          <div className="flex justify-end gap-3 pt-2">
            <Button
              type="submit"
              variant="primary"
              disabled={saving}
              className="px-6 py-2"
            >
              {saving
                ? (language === 'mr' ? 'जतन करत आहे...' : 'Saving...')
                : (language === 'mr' ? 'बदल जतन करा (Save Changes)' : 'Save Changes')}
            </Button>
          </div>
        )}
      </form>
    </div>
  );
}
