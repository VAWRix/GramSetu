import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import path from 'path';
import fs from 'fs';

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

test.describe('Capture Repaired CMS Visual Evidence in Official Light Theme', () => {
  test.setTimeout(90000);

  test('Capture CMS screenshots across all management interfaces', async ({ page }) => {
    const rootDir = path.resolve(__dirname, '../../..');
    const docsCmsDir = path.join(rootDir, 'docs', 'screenshots', 'cms');
    const brainCmsDir = 'C:\\Users\\Vishal\\.gemini\\antigravity\\brain\\84e6dbdc-eff3-4ef4-a44f-854dd46913fd\\screenshots\\cms';

    if (!fs.existsSync(docsCmsDir)) fs.mkdirSync(docsCmsDir, { recursive: true });
    if (!fs.existsSync(brainCmsDir)) fs.mkdirSync(brainCmsDir, { recursive: true });

    async function saveScreenshot(filename: string) {
      const p1 = path.join(docsCmsDir, filename);
      const p2 = path.join(brainCmsDir, filename);
      await page.screenshot({ path: p1, fullPage: true });
      fs.copyFileSync(p1, p2);
      console.log(`Saved screenshot: ${filename}`);
    }

    // 1. Login as Super Admin
    await loginAsAdmin(page);

    // 2. CMS Dashboard
    await page.goto('/cms');
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);
    await saveScreenshot('cms-dashboard-desktop.png');

    // 3. Governance Queue - Pending Review Tab
    await page.goto('/cms/governance');
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);
    await saveScreenshot('cms-governance-desktop.png');

    // 4. Governance Queue - Approved Tab
    const approvedTab = page.getByRole('button', { name: /मंजूर.*प्रकाशन प्रतीक्षेत|Approved/i });
    if (await approvedTab.isVisible()) {
      await approvedTab.click();
      await page.waitForTimeout(1000);
      await saveScreenshot('cms-governance-approved-desktop.png');

      // 5. Open Publish Modal if publish button exists
      const publishBtn = page.getByRole('button', { name: /प्रसिद्ध करा|Publish/i }).first();
      if (await publishBtn.isVisible()) {
        await publishBtn.click();
        await page.waitForTimeout(500);
        await saveScreenshot('cms-governance-publish-modal-desktop.png');
        await page.getByRole('button', { name: /रद्द करा|Cancel|बंद करा|Close/i }).first().click();
      }
    }

    // 6. CMS Notices
    await page.goto('/cms/notices');
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);
    await saveScreenshot('cms-notices-desktop.png');

    // 7. CMS Events
    await page.goto('/cms/events');
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);
    await saveScreenshot('cms-events-desktop.png');

    // 8. CMS Schemes
    await page.goto('/cms/schemes');
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);
    await saveScreenshot('cms-schemes-desktop.png');

    // 9. CMS Documents
    await page.goto('/cms/documents');
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);
    await saveScreenshot('cms-documents-desktop.png');

    // 10. CMS Gallery
    await page.goto('/cms/gallery');
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);
    await saveScreenshot('cms-gallery-desktop.png');

    // 11. CMS Content (Pages)
    await page.goto('/cms/content');
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);
    await saveScreenshot('cms-content-desktop.png');

    // 12. CMS Audit Logs
    await page.goto('/cms/audit');
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);
    await saveScreenshot('cms-audit-desktop.png');

    // 13. Public Notices (Live Citizen Portal)
    const publicNoticesPath = path.join(rootDir, 'docs', 'screenshots', 'public', 'public-notices-mr-desktop.png');
    const brainPublicNoticesPath = 'C:\\Users\\Vishal\\.gemini\\antigravity\\brain\\84e6dbdc-eff3-4ef4-a44f-854dd46913fd\\screenshots\\public\\public-notices-mr-desktop.png';
    await page.goto('/notices');
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: publicNoticesPath, fullPage: true });
    if (fs.existsSync(path.dirname(brainPublicNoticesPath))) {
      fs.copyFileSync(publicNoticesPath, brainPublicNoticesPath);
    }
  });
});
