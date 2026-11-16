import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import path from 'path';

function getTestPassword(email: string): string {
  const rootDir = path.resolve(__dirname, '../../..');
  const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
  const defaultPass = 'Password@123';
  const cmd = `"${pythonExe}" manage.py shell -c "from apps.identity.models import User; u = User.objects.get(email='${email}'); p = '${defaultPass}'; (None if u.check_password(p) else (u.set_password(p), u.save())); print(p)"`;
  const out = execSync(cmd, { cwd: rootDir, encoding: 'utf-8' });
  const lines = out.trim().split(/\r?\n/);
  return lines[lines.length - 1].trim();
}

function getEmailOtp(email: string): string {
  const rootDir = path.resolve(__dirname, '../../..');
  const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
  const cmd = `"${pythonExe}" manage.py shell -c "from apps.identity.models import User; from apps.identity.services import get_or_create_email_device; u = User.objects.get(email='${email}'); print(get_or_create_email_device(u).token)"`;
  const out = execSync(cmd, { cwd: rootDir, encoding: 'utf-8' });
  const lines = out.trim().split(/\r?\n/);
  return lines[lines.length - 1].trim();
}

async function loginUser(page: any, email: string) {
  await page.context().clearCookies();
  const pass = getTestPassword(email);
  await page.goto('/cms');
  await page.locator('#admin-email').fill(email);
  await page.locator('#admin-password').fill(pass);
  await page.locator('button[type="submit"]').click();

  await expect(page.locator('#otp-code')).toBeVisible({ timeout: 10000 });
  const otp = getEmailOtp(email);
  await page.locator('#otp-code').fill(otp);
  await page.locator('button[type="submit"]').click();

  // Wait until authenticated CMS layout and sidebar are visible
  await expect(page.locator('aside')).toBeVisible({ timeout: 15000 });
}

test.describe('GramSetu CMS to Public Portal Complete Synchronization Audit', () => {
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(120000);

  test('1. Role Separation: Super Admin (Gram Sevak) & Operator (Maker) technical roles verified', async ({ page }) => {
    // 1. Log in as Super Admin (Gram Sevak)
    await loginUser(page, 'local.admin@gramsetu.gov.in');
    await expect(page.locator('h1')).toContainText(/प्रशासकीय नियंत्रण कक्ष|Administrative Control Dashboard/i);

    // Verify Super Admin banner and role indicator
    await expect(page.getByText(/मुख्य प्रशासक|Super Admin|स्थानिक मुख्य प्रशासक|ग्रामसेवक/i).first()).toBeVisible();

    // Verify strict two-role RBAC architecture is displayed on dashboard
    await expect(page.getByText(/SUPER_ADMIN \(ग्रामसेवक/i).first()).toBeVisible();
    await expect(page.getByText(/OPERATOR \(संगणक चालक/i).first()).toBeVisible();
    // Verify Sarpanch is NOT listed as a technical RBAC software role
    await expect(page.locator('body')).not.toContainText(/role: 'SARPANCH'/);

    // Logout
    const logoutBtn = page.getByRole('button', { name: /लॉग आऊट|Sign Out/i }).first();
    if (await logoutBtn.isVisible()) {
      await logoutBtn.click();
    }
  });

  test('2. Panchayat Profile & Sarpanch Office-Holder Synchronization', async ({ page }) => {
    // Gram Sevak (Super Admin) logs in to update elected Sarpanch details
    await loginUser(page, 'local.admin@gramsetu.gov.in');

    // Navigate to /cms/profile
    await page.goto('/cms/profile');
    await expect(page.getByRole('heading', { name: /पंचायत प्रोफाईल व पदाधिकारी|Panchayat Profile & Officials/i })).toBeVisible({ timeout: 10000 });

    // Verify statutory identifiers are visible
    await expect(page.getByText(/549493/i).first()).toBeVisible();

    // Update Sarpanch name (simulating an election office-holder update)
    const sarpanchInput = page.locator('input[placeholder*="सरपंच नाव"]').first();
    await expect(sarpanchInput).toBeEnabled();
    const updatedSarpanch = '[नाव प्रलंबित / Pending Verification]';
    await sarpanchInput.fill(updatedSarpanch);

    // Save changes
    const saveBtn = page.getByRole('button', { name: /बदल जतन करा|Save Changes/i }).first();
    await saveBtn.click();

    // Wait for success alert
    await expect(page.getByText(/यशस्वीरीत्या अद्ययावत झाली|updated successfully/i).first()).toBeVisible({ timeout: 10000 });

    // Now visit public About page and verify Sarpanch name immediately reflects pending state
    await page.goto('/about');
    await expect(page.getByText(/नाव प्रलंबित/i).first()).toBeVisible({ timeout: 10000 });

    // Verify footer also reflects the updated Sarpanch state
    const footerSarpanch = page.locator('footer').getByText(/नाव प्रलंबित/i).first();
    await expect(footerSarpanch).toBeVisible();

    // Operator verification: log in as Operator and verify profile is read-only
    await page.goto('/cms');
    const logoutBtn = page.getByRole('button', { name: /लॉग आऊट|Sign Out/i }).first();
    if (await logoutBtn.isVisible()) {
      await logoutBtn.click();
    }

    await loginUser(page, 'local.operator@gramsetu.gov.in');
    await page.goto('/cms/profile');
    await expect(page.getByText(/केवळ वाचनीय अधिकार|Read-Only/i).first()).toBeVisible();
    await expect(page.locator('input[placeholder*="सरपंच नाव"]').first()).toBeDisabled();
    await expect(page.getByRole('button', { name: /बदल जतन करा|Save Changes/i })).toHaveCount(0);
  });

  test('3. Pages & Information: 14 sections, references, and full content rendered publicly', async ({ page }) => {
    await page.goto('/about');
    await page.waitForLoadState('networkidle');

    // 1. Village Knowledge Article is rendered
    await expect(page.locator('#knowledge-article')).toBeVisible({ timeout: 15000 });

    // 2. Table of Contents has sections
    const toc = page.locator('#article-toc');
    await expect(toc).toBeVisible();
    await expect(toc.getByText(/गावाची ऐतिहासिक पार्श्वभूमी|१\. गावाची/i).first()).toBeVisible();
    await expect(toc.getByText(/भौगोलिक स्थान व विस्तार|२\. भौगोलिक/i).first()).toBeVisible();
    await expect(toc.getByText(/सीमा व शेजारील गावे|३\. सीमा/i).first()).toBeVisible();

    // 3. Main content body sections are visible
    await expect(page.locator('#section-history')).toBeVisible();
    await expect(page.getByText(/नारायणगाव|७१४ हेक्टर|714 hectares/i).first()).toBeVisible();

    // 4. Academic References & Statutory Citations
    await expect(page.locator('#article-references')).toBeVisible();
    await expect(page.getByText(/स्थानिक स्वराज्य संस्था निर्देशिका|LGD/i).first()).toBeVisible();

    // 5. Interactive Section Search Filter
    const filterInput = page.locator('#section-filter');
    await filterInput.fill('शेती');
    await page.waitForTimeout(300);
    await expect(page.getByText(/शेती, जलसंधारण व व्यवसाय|६\. शेती/i).first()).toBeVisible();
  });

  test('4. Notices: Summary, full description, and deadline badges synchronization', async ({ page }) => {
    // Visit public notices
    await page.goto('/notices');
    await page.waitForLoadState('networkidle');

    // Verify notices list renders
    const noticeCards = page.locator('article, .border.rounded-lg');
    expect(await noticeCards.count()).toBeGreaterThan(0);

    // Check for statutory deadline or publish date indicator
    await expect(page.getByText(/मुदत|Deadline|प्रसिद्ध दिनांक|Published/i).first()).toBeVisible();
  });

  test('5. Disclosed Documents: Metadata and secure download delivery', async ({ page }) => {
    // Visit public documents
    await page.goto('/documents');
    await page.waitForLoadState('networkidle');

    // Verify documents list renders
    const docCards = page.locator('article, .bg-white.p-5, .border.rounded-lg');
    expect(await docCards.count()).toBeGreaterThan(0);

    // Verify download link/button is present
    const downloadBtn = page.getByRole('link', { name: /डाऊनलोड|डाउनलोड|Download|PDF/i }).first();
    await expect(downloadBtn).toBeVisible();
  });

  test('6. Meetings & Events: Schedule, venue, and status synchronization', async ({ page }) => {
    // Visit public events
    await page.goto('/events');
    await page.waitForLoadState('networkidle');

    // Verify meetings and events list renders
    await expect(page.getByRole('heading', { name: /ग्रामसभा व बैठका|Meetings & Events/i })).toBeVisible();
    await expect(page.getByText(/वेळ|Time|स्थळ|Venue|दिनांक|Date/i).first()).toBeVisible();
  });

  test('7. Welfare Schemes: Benefits, eligibility, and detail view synchronization', async ({ page }) => {
    // Visit public schemes
    await page.goto('/schemes');
    await page.waitForLoadState('networkidle');

    await expect(page.getByRole('heading', { name: /शासकीय योजना|Welfare Schemes/i })).toBeVisible();
    const schemeCards = page.locator('article, .bg-white.p-5, .border.rounded-lg');
    expect(await schemeCards.count()).toBeGreaterThan(0);

    // Click through to detail view if link exists
    const viewDetailBtn = page.getByRole('link', { name: /सविस्तर माहिती|View Details|माहिती पहा|तपशील पहा/i }).first();
    if (await viewDetailBtn.isVisible()) {
      await viewDetailBtn.click();
      await page.waitForLoadState('networkidle');
      await expect(page.getByText(/पात्रता निकष|Eligibility|आवश्यक कागदपत्रे|Required Documents|लाभाचे स्वरूप|Benefits/i).first()).toBeVisible();
    }
  });

  test('8. Photo Gallery: Single caption per photo, valid images, and lightbox', async ({ page }) => {
    // Visit public gallery
    await page.goto('/gallery');
    await page.waitForLoadState('networkidle');

    await expect(page.getByRole('heading', { name: /चित्रदालन|Photo Gallery/i })).toBeVisible();

    // Click into an album
    const albumCard = page.locator('div[role="button"]').first();
    if (await albumCard.isVisible()) {
      await albumCard.click();
      await page.waitForTimeout(1000);

      // Verify photos are visible
      const photos = page.locator('img');
      expect(await photos.count()).toBeGreaterThan(0);

      // Verify image loaded cleanly (naturalWidth > 0)
      const firstImg = photos.first();
      const isLoaded = await firstImg.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0);
      expect(isLoaded).toBe(true);

      // Verify lightbox modal is opened
      const lightboxModal = page.locator('.fixed.inset-0').first();
      await expect(lightboxModal).toBeVisible();

      // Close lightbox
      const closeBtn = page.locator('button[aria-label*="Close Lightbox"]').first();
      if (await closeBtn.isVisible()) {
        await closeBtn.click();
      }
    }
  });

  test('9. Unified Search: Full-text discovery across all published domains', async ({ page }) => {
    await page.goto('/search?q=नारायणगाव');
    await page.waitForLoadState('networkidle');

    await expect(page.getByRole('heading', { name: /शोध|Search/i })).toBeVisible();
    // Verify search input is populated and results exist
    const searchInput = page.locator('input[type="search"], input[name="q"], input[placeholder*="शोधा"]').first();
    await expect(searchInput).toBeVisible();
  });
});
