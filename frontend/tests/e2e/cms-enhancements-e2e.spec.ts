import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import path from 'path';

const SCREENSHOTS_DIR = 'C:/Users/Vishal/.gemini/antigravity/brain/84e6dbdc-eff3-4ef4-a44f-854dd46913fd/screenshots/enhancements';

function getAdminTestPassword(): string {
  if (process.env.DEV_ADMIN_PASSWORD) return process.env.DEV_ADMIN_PASSWORD;
  if (process.env.TEST_ADMIN_PASSWORD) return process.env.TEST_ADMIN_PASSWORD;
  const rootDir = path.resolve(__dirname, '../../..');
  const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
  const defaultPass = 'GramSetu@Test2026';
  const cmd = `"${pythonExe}" manage.py shell -c "from apps.identity.models import User; u = User.objects.get(email='local.admin@gramsetu.gov.in'); p = '${defaultPass}'; (None if u.check_password(p) else (u.set_password(p), u.save())); print(p)"`;
  const out = execSync(cmd, { cwd: rootDir, encoding: 'utf-8' });
  const lines = out.trim().split(/\r?\n/);
  const pass = lines[lines.length - 1].trim();
  process.env.TEST_ADMIN_PASSWORD = pass;
  return pass;
}

function getAdminEmailOtp(): string {
  const rootDir = path.resolve(__dirname, '../../..');
  const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
  const cmd = `"${pythonExe}" manage.py shell -c "from apps.identity.models import User; from apps.identity.services import get_or_create_email_device; u = User.objects.get(email='local.admin@gramsetu.gov.in'); print(get_or_create_email_device(u).token)"`;
  const out = execSync(cmd, { cwd: rootDir, encoding: 'utf-8' });
  const lines = out.trim().split(/\r?\n/);
  return lines[lines.length - 1].trim();
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

test.describe('GramSetu Full Enhancements & Governance Verification Suite', () => {
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(90000);

  test('Workstream A: Documents & Disclosures tabbed views, complete inspection, and withdrawal workflow', async ({ page }) => {
    await loginAsAdmin(page);

    await page.goto('/cms/documents');
    await expect(page.locator('h1')).toBeVisible();

    // Verify tabs
    const allTab = page.getByRole('button', { name: /सर्व दस्तऐवज|All/i });
    const publishedTab = page.getByRole('button', { name: /प्रसिद्ध|Published/i });
    const pendingTab = page.getByRole('button', { name: /प्रलंबित|Pending/i });
    const withdrawnTab = page.getByRole('button', { name: /मागे घेतलेले|Withdrawn/i });

    await expect(allTab).toBeVisible();
    await expect(publishedTab).toBeVisible();
    await expect(pendingTab).toBeVisible();
    await expect(withdrawnTab).toBeVisible();

    // Verify search input
    const searchInput = page.locator('input[placeholder*="Search title"]');
    await expect(searchInput).toBeVisible();

    // Capture main page
    await page.screenshot({ path: `${SCREENSHOTS_DIR}/cms-documents-page.png`, fullPage: true });

    // Open Complete Details Modal
    const detailsBtn = page.getByRole('button', { name: /तपशील पहा|View Details/i }).first();
    if (await detailsBtn.isVisible()) {
      await detailsBtn.click();
      await expect(page.getByText(/दस्तऐवज संपूर्ण माहिती|Complete Document Record Details/i)).toBeVisible();
      await page.screenshot({ path: `${SCREENSHOTS_DIR}/cms-documents-details-modal.png` });
      await page.getByRole('button', { name: /बंद करा|Close/i }).last().click();
    }

    // Open Withdrawal Modal
    const withdrawBtn = page.getByRole('button', { name: /मागे घ्या|Withdraw from Portal/i }).first();
    if (await withdrawBtn.isVisible()) {
      await withdrawBtn.click();
      await expect(page.getByText(/दस्तऐवज मागे घेण्याची पुष्टी|Confirm Document Withdrawal/i)).toBeVisible();
      
      const confirmWithdrawBtn = page.getByRole('button', { name: /मागे घ्या \(Confirm Withdrawal\)/i });
      await expect(confirmWithdrawBtn).toBeDisabled();

      // Type short reason (<10 chars) -> remains disabled
      const reasonInput = page.locator('.fixed textarea');
      await reasonInput.fill('Too short');
      await expect(confirmWithdrawBtn).toBeDisabled();

      // Type valid reason (>=10 chars) -> enables
      await reasonInput.fill('नवीन शासन निर्णयानुसार ही नियमावली मागे घेण्यात येत आहे.');
      await expect(confirmWithdrawBtn).toBeEnabled();

      await page.screenshot({ path: `${SCREENSHOTS_DIR}/cms-documents-withdraw-modal.png` });
      await page.getByRole('button', { name: /रद्द करा|Cancel/i }).click();
    }
  });

  test('Workstream B: Schemes & Welfare clickable cards, inspection modal, and public detail page', async ({ page }) => {
    await loginAsAdmin(page);

    await page.goto('/cms/schemes');
    await expect(page.locator('h1')).toBeVisible();

    // Verify tabs
    await expect(page.getByRole('button', { name: /सर्व योजना|All/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /प्रसिद्ध|Published/i })).toBeVisible();

    // Open Scheme Complete Inspection Modal (if records exist)
    const inspectBtn = page.locator('button:has-text("तपशील पहा")').first();
    if (await inspectBtn.isVisible()) {
      await inspectBtn.click();
      await expect(page.getByText(/योजना तपशील|Scheme Details/i)).toBeVisible();
      await expect(page.getByText(/पात्रतेचे निकष|पात्रता निकष|Eligibility/i).first()).toBeVisible();
      await expect(page.getByText(/आवश्यक कागदपत्रे|Required Documents/i).first()).toBeVisible();
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${SCREENSHOTS_DIR}/cms-schemes-inspect-modal.png` });
      await page.getByRole('button', { name: /बंद करा|Close/i }).last().click();
    }

    await page.screenshot({ path: `${SCREENSHOTS_DIR}/cms-schemes-page.png`, fullPage: true });

    // Navigate to public /schemes
    await page.goto('/schemes');
    await expect(page.locator('h1').first()).toBeVisible();

    // Click on scheme card if present
    const schemeCard = page.locator('a[href*="/schemes/"]').first();
    if (await schemeCard.isVisible()) {
      await schemeCard.click();

      // Verify public detail page
      await expect(page).toHaveURL(/\/schemes\/.+/);
      await expect(page.locator('h1').first()).toBeVisible();
      await expect(page.getByText(/पात्रतेचे निकष|पात्रता निकष|Eligibility/i).first()).toBeVisible();
      await expect(page.getByText(/आवश्यक कागदपत्रे|Required Documents/i).first()).toBeVisible();
      await expect(page.getByText(/अर्ज प्रक्रिया|Application Process/i).first()).toBeVisible();
      await expect(page.getByText(/माहितीपर प्रकटीकरण|Official Informational Portal/i).first()).toBeVisible();

      await page.screenshot({ path: `${SCREENSHOTS_DIR}/public-scheme-detail-page.png`, fullPage: true });
    }
  });

  test('Workstream C: Approval Review Screen full submitted-field inspection modal', async ({ page }) => {
    await loginAsAdmin(page);

    await page.goto('/cms/governance');
    await expect(page.locator('h1')).toBeVisible();

    // Click "तपशील (Inspect)" on first available submission if present
    const inspectBtn = page.locator('button:has-text("तपशील")').first();
    if (await inspectBtn.isVisible()) {
      await inspectBtn.click();
      await expect(page.getByText(/तपशीलवार|Inspect Submission|सादर केलेला संपूर्ण मजकूर|तपशीलवार मसुदा/i)).toBeVisible();
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${SCREENSHOTS_DIR}/cms-governance-inspect-modal.png` });
      await page.getByRole('button', { name: /बंद करा|Close/i }).last().click();
    }

    await page.screenshot({ path: `${SCREENSHOTS_DIR}/cms-governance-queue-page.png`, fullPage: true });
  });

  test('Workstream D: Meeting cancellation notification and 6-hour alert banner', async ({ page }) => {
    // Navigate to public citizen events page
    await page.goto('/events');
    await expect(page.locator('h1').first()).toBeVisible();

    // Check for 6-hour emergency cancellation alert banner if present
    const alertBanner = page.locator('.border-rose-500[role="alert"]').first();
    if (await alertBanner.isVisible()) {
      // Verify cancellation reason callout
      await expect(page.getByText(/रद्द करण्याचे अधिकृत कारण|Official Cancellation Reason/i).first()).toBeVisible();
      await page.screenshot({ path: `${SCREENSHOTS_DIR}/public-events-cancellation-alert.png`, fullPage: true });
    }
  });

  test('Workstream E: Photo Gallery dual-source upload/link and accessible public lightbox', async ({ page }) => {
    await loginAsAdmin(page);

    await page.goto('/cms/gallery');
    await expect(page.locator('h1')).toBeVisible();

    // Wait for albums to render (if present)
    const managePhotosBtn = page.locator('button:has-text("Manage Photos")').first();
    if (await managePhotosBtn.isVisible()) {
      await page.screenshot({ path: `${SCREENSHOTS_DIR}/cms-gallery-page.png`, fullPage: true });

      // 1. Open Manage Photos Modal (persistent reordering)
      await managePhotosBtn.click();
      await expect(page.getByText(/अल्बम छायाचित्रे व्यवस्थापन|Manage/i)).toBeVisible();
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${SCREENSHOTS_DIR}/cms-gallery-manage-photos-modal.png` });

      // 2. Open Add Photo Modal (dual-source)
      const addPhotoBtn = page.locator('button:has-text("नवीन फोटो जोडा")').first();
      await addPhotoBtn.click();
      await expect(page.getByText(/छायाचित्र जोडा|Add Photograph/i).first()).toBeVisible();
      await expect(page.getByText(/फाईल अपलोड|Upload File/i).first()).toBeVisible();
      await expect(page.getByText(/इमेज लिंक|Google Drive/i).first()).toBeVisible();

      // Switch to Link tab
      await page.getByRole('button', { name: /इमेज लिंक|Google Drive/i }).click();
      await expect(page.locator('input[placeholder*="drive.google.com"]')).toBeVisible();

      await page.waitForTimeout(300);
      await page.screenshot({ path: `${SCREENSHOTS_DIR}/cms-gallery-add-photo-modal.png` });
      await page.getByRole('button', { name: /रद्द करा|Cancel/i }).last().click();

      // Close Manage Photos Modal
      await page.locator('button[aria-label="Close"]').first().click();
    }

    // 3. Public Gallery & Lightbox
    await page.goto('/gallery');
    await expect(page.locator('h1').first()).toBeVisible();
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${SCREENSHOTS_DIR}/public-gallery-grid.png`, fullPage: true });

    // Open first photo in album to view Lightbox
    const albumCover = page.locator('.group.cursor-pointer, .cursor-pointer').first();
    if (await albumCover.isVisible()) {
      await albumCover.click();
      await page.waitForTimeout(1000);
      await page.screenshot({ path: `${SCREENSHOTS_DIR}/public-gallery-lightbox.png`, fullPage: true });
    }
  });
});
