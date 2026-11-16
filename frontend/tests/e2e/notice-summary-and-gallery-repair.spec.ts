import { test, expect } from '@playwright/test';
import { execFileSync } from 'child_process';
import path from 'path';

function runDjango(script: string): string {
  const rootDir = path.resolve(__dirname, '../../..');
  const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
  const wrapper = `
import os, sys, django
sys.path.insert(0, r'${rootDir}')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
${script}
`;
  const out = execFileSync(pythonExe, ['-c', wrapper], {
    cwd: rootDir,
    encoding: 'utf-8',
  });
  return out.trim();
}

function getAdminTestPassword(): string {
  if (process.env.DEV_ADMIN_PASSWORD) return process.env.DEV_ADMIN_PASSWORD;
  if (process.env.TEST_ADMIN_PASSWORD) return process.env.TEST_ADMIN_PASSWORD;
  const defaultPass = 'GramSetu@Test2026';
  const script = `
from apps.identity.models import User
u = User.objects.get(email='local.admin@gramsetu.gov.in')
p = '${defaultPass}'
if not u.check_password(p):
    u.set_password(p)
    u.save()
print('PASS:' + p)
`;
  const out = runDjango(script);
  const match = out.match(/PASS:(.+)/);
  const pass = match ? match[1].trim() : defaultPass;
  process.env.TEST_ADMIN_PASSWORD = pass;
  return pass;
}

function getAdminEmailOtp(): string {
  const script = `
from apps.identity.models import User
from apps.identity.services import get_or_create_email_device
u = User.objects.get(email='local.admin@gramsetu.gov.in')
print('OTP:' + str(get_or_create_email_device(u).token))
`;
  const out = runDjango(script);
  const match = out.match(/OTP:(\d+)/);
  return match ? match[1].trim() : '';
}

async function loginAsAdmin(page: any) {
  const adminPass = getAdminTestPassword();
  await page.goto('/cms');
  await page.locator('#admin-email').fill('local.admin@gramsetu.gov.in');
  await page.locator('#admin-password').fill(adminPass);
  await page.locator('button[type="submit"]').click();

  await expect(page.locator('#otp-code')).toBeVisible({ timeout: 10000 });
  const adminOtp = getAdminEmailOtp();
  await page.locator('#otp-code').fill(adminOtp);
  await page.locator('button[type="submit"]').click();

  await expect(page.getByText('SUPER ADMINISTRATOR', { exact: true })).toBeVisible({ timeout: 10000 });
}

test.describe('Notice Summaries and Gallery Album HTTP 500 Repair Suite', () => {
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(60000);

  test.beforeEach(async () => {
    // Seed 2 published test notices before each test so each browser project has fresh data
    const seedScript = `
from django.utils import timezone
from datetime import timedelta
from apps.identity.models import User
from apps.notices.models import Notice, NoticeTranslation, NoticeRevision
u = User.objects.get(email='local.admin@gramsetu.gov.in')
Notice.objects.filter(reference_number__in=['E2E-NOT-01', 'E2E-NOT-02']).delete()

n1 = Notice.objects.create(
    notice_type='statutory', urgency='standard', reference_number='E2E-NOT-01',
    effective_from=timezone.now() - timedelta(hours=1),
    issue_date=timezone.now().date()
)
t1 = NoticeTranslation.objects.create(notice=n1, language_code='mr', slug=f'e2e-not-01-{n1.id.hex}', status='published')
r1 = NoticeRevision.objects.create(
    translation=t1, revision_number=1, title='पाणी पुरवठा पाइपलाइन दुरुस्ती',
    summary='मुख्य जलवाहिनीच्या आवश्यक दुरुस्ती कामामुळे उद्या पाणीपुरवठा बंद राहील.',
    body_markdown='# महत्त्वाची दुरुस्ती सूचना\\n\\nसर्व ग्रामस्थांना कळविण्यात येते की पाइपलाइन दुरुस्ती होणार आहे.',
    editorial_status='approved', created_by=u
)
t1.current_approved_revision = r1
t1.save()

n2 = Notice.objects.create(
    notice_type='gram_sabha', urgency='urgent', reference_number='E2E-NOT-02',
    effective_from=timezone.now() - timedelta(hours=1),
    issue_date=timezone.now().date()
)
t2 = NoticeTranslation.objects.create(notice=n2, language_code='mr', slug=f'e2e-not-02-{n2.id.hex}', status='published')
r2 = NoticeRevision.objects.create(
    translation=t2, revision_number=1, title='विशेष ग्रामसभा कार्यक्रम २०२६',
    summary='',
    body_markdown='## विशेष ग्रामसभा सूचना\\n\\n**सर्व ग्रामस्थांना कळविण्यात येते** की वार्षिक विकास आराखड्यावर चर्चा करण्यासाठी ग्रामसभेचे आयोजन करण्यात आले आहे.',
    editorial_status='approved', created_by=u
)
t2.current_approved_revision = r2
t2.save()
print('SUCCESS_SEED')
`;
    runDjango(seedScript);
  });

  test.afterAll(async () => {
    // Clean up test data
    const cleanupScript = `
from apps.notices.models import Notice
from apps.gallery.models import GalleryAlbum
Notice.objects.filter(reference_number__in=['E2E-NOT-01', 'E2E-NOT-02']).delete()
GalleryAlbum.objects.filter(slug__in=['e2e-test-cultural-fest', 'e2e-dup-slug-test']).delete()
print('SUCCESS_CLEANUP')
`;
    runDjango(cleanupScript);
  });

  test('Task 1: Public notice listing displays brief descriptions and opening notice shows full markdown', async ({ page }) => {
    await page.goto('/notices');
    await expect(page.locator('h1').first()).toBeVisible();

    // 1. Notice with explicit summary should display that summary
    const card1 = page.locator('article', { hasText: 'पाणी पुरवठा पाइपलाइन दुरुस्ती' });
    await expect(card1).toBeVisible({ timeout: 15000 });
    await expect(card1.getByText('मुख्य जलवाहिनीच्या आवश्यक दुरुस्ती कामामुळे उद्या पाणीपुरवठा बंद राहील.')).toBeVisible();

    // 2. Notice without explicit summary should display derived preview (markdown stripped)
    const card2 = page.locator('article', { hasText: 'विशेष ग्रामसभा कार्यक्रम २०२६' });
    await expect(card2).toBeVisible({ timeout: 10000 });
    // The derived text should contain the words from body without markdown ## or **
    await expect(card2.getByText(/विशेष ग्रामसभा सूचना/i)).toBeVisible();
    await expect(card2.getByText(/सर्व ग्रामस्थांना कळविण्यात येते/i)).toBeVisible();
    // Verify no raw markdown syntax leaked
    const card2Text = await card2.innerText();
    expect(card2Text).not.toContain('##');
    expect(card2Text).not.toContain('**');

    // 3. Click "संपूर्ण सूचना पहा" to open the detail modal
    const openBtn = card2.getByRole('button', { name: /संपूर्ण सूचना पहा|View Notice/i });
    await expect(openBtn).toBeVisible();
    await openBtn.click();

    // 4. Modal should be visible with full published content
    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible();
    await expect(modal.locator('#public-notice-modal-title')).toHaveText('विशेष ग्रामसभा कार्यक्रम २०२६');
    await expect(modal.getByText('E2E-NOT-02')).toBeVisible();
    await expect(modal.getByText(/वार्षिक विकास आराखड्यावर चर्चा करण्यासाठी/i)).toBeVisible();

    // 5. Close modal via Close button
    const closeBtn = modal.getByRole('button', { name: /बंद करा|Close/i }).first();
    await closeBtn.click();
    await expect(modal).not.toBeVisible();

    // 6. Test language fallback: switch to English via accessibility/language selector
    const langSelect = page.locator('#portal-lang-select');
    await expect(langSelect).toBeVisible();
    await langSelect.selectOption('en');

    // Both notices authored in Marathi should display with fallback indicator
    const card1En = page.locator('article', { hasText: 'पाणी पुरवठा पाइपलाइन दुरुस्ती' });
    await expect(card1En).toBeVisible({ timeout: 15000 });
    await expect(card1En.getByText('Marathi Record')).toBeVisible();
  });

  test('Task 2: CMS Gallery loads without HTTP 500 and album creation succeeds with persistence', async ({ page }) => {
    await loginAsAdmin(page);

    // 1. Navigate to Gallery Management
    await page.goto('/cms/gallery');
    await expect(page.locator('h1').first()).toBeVisible();

    // 2. Verify no HTTP 500 error alert exists on page load
    const alert500 = page.getByText(/Request failed \(HTTP 500\)/i);
    await expect(alert500).not.toBeVisible();

    // 3. Click "Create New Album" button
    const createBtn = page.getByRole('button', { name: /नवीन अल्बम तयार करा|Create New Album/i });
    await expect(createBtn).toBeVisible();
    await createBtn.click();

    // 4. Fill in album form with category "Cultural" (formerly value="culture" which triggered HTTP 500 CheckViolation)
    const slugInput = page.locator('input[placeholder="panchayat-building-inauguration"]');
    await slugInput.fill('e2e-test-cultural-fest');

    const titleInput = page.locator('input[placeholder*="प्रशासकीय इमारत लोकार्पण"], input[placeholder="Gram Panchayat Administrative Building Inauguration"]');
    await titleInput.fill('वार्षिक सांस्कृतिक महोत्सव २०२६');

    const categorySelect = page.locator('#album-category-select');
    await categorySelect.selectOption('cultural');

    const descTextarea = page.locator('textarea').first();
    await descTextarea.fill('ग्रामपंचायतीचा वार्षिक सांस्कृतिक आणि क्रीडा महोत्सव');

    // 5. Submit album form
    const submitBtn = page.locator('button[type="submit"]');
    await submitBtn.click();

    // 6. Verify successful creation feedback (NO HTTP 500!)
    await expect(alert500).not.toBeVisible();
    await expect(page.getByText(/वार्षिक सांस्कृतिक महोत्सव २०२६/i).first()).toBeVisible({ timeout: 10000 });

    // 7. Test Duplicate Slug validation error (should return clean 400 with friendly message, NOT 500!)
    await createBtn.click();
    await slugInput.fill('e2e-test-cultural-fest');
    await titleInput.fill('Duplicate Title');
    await submitBtn.click();

    // Verify clean validation error inside form or page
    await expect(page.getByText(/आधीच अस्तित्वात आहे|already exists/i).first()).toBeVisible({ timeout: 5000 });
    await expect(alert500).not.toBeVisible();

    // Close modal
    await page.locator('button:has-text("✕")').first().click();

    // 8. Refresh page to confirm persistence in PostgreSQL
    await page.reload();
    await expect(page.locator('h1').first()).toBeVisible();
    await expect(page.getByText('वार्षिक सांस्कृतिक महोत्सव २०२६').first()).toBeVisible();
  });
});

