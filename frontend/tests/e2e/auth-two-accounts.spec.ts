import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import path from 'path';

const ROOT_DIR = path.resolve(__dirname, '../../..');
const PYTHON_EXE = path.join(ROOT_DIR, '.venv', 'Scripts', 'python.exe');
const PASSWORD = 'GramSetu@Test2026';

function getSuperAdminOtp(): string {
  const cmd = `"${PYTHON_EXE}" manage.py superadmin_otp --raw --fresh`;
  const out = execSync(cmd, { cwd: ROOT_DIR, encoding: 'utf-8' });
  const lines = out.trim().split(/\r?\n/);
  return lines[lines.length - 1].trim();
}

function getOperatorOtp(): string {
  const cmd = `"${PYTHON_EXE}" manage.py operator_otp --raw --fresh`;
  const out = execSync(cmd, { cwd: ROOT_DIR, encoding: 'utf-8' });
  const lines = out.trim().split(/\r?\n/);
  return lines[lines.length - 1].trim();
}

test.describe('Two Permanent Testing Accounts UI Authentication Suite', () => {
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(60000);

  test('1. Super Admin logs into CMS successfully with GramSetu@Test2026 and superadmin_otp', async ({ page }) => {
    await page.goto('/cms');
    await page.waitForLoadState('networkidle');

    // Fill credentials
    await page.locator('#admin-email').fill('local.admin@gramsetu.gov.in');
    await page.locator('#admin-password').fill(PASSWORD);
    await page.locator('button[type="submit"]').click();

    // Verify OTP input becomes visible
    await expect(page.locator('#otp-code')).toBeVisible({ timeout: 10000 });

    // Retrieve and fill Super Admin OTP
    const otp = getSuperAdminOtp();
    expect(otp.length).toBe(6);
    await page.locator('#otp-code').fill(otp);
    await page.locator('button[type="submit"]').click();

    // Verify CMS Dashboard loads and displays Super Admin role
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/ग्रामसेवक|Super Administrator|SUPER_ADMIN/i).first()).toBeVisible();

    // Verify page refresh preserves session
    await page.reload();
    await page.waitForLoadState('networkidle');
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 });

    // Logout
    const logoutBtn = page.getByRole('button', { name: /(बाहेर पडा|Logout|Sign out)/i });
    if (await logoutBtn.isVisible()) {
      await logoutBtn.click();
      await page.waitForLoadState('networkidle');
      await expect(page.locator('#admin-email')).toBeVisible({ timeout: 10000 });
    }
  });

  test('2. Operator logs into CMS successfully with GramSetu@Test2026 and operator_otp', async ({ page }) => {
    await page.goto('/cms');
    await page.waitForLoadState('networkidle');

    await page.locator('#admin-email').fill('local.operator@gramsetu.gov.in');
    await page.locator('#admin-password').fill(PASSWORD);
    await page.locator('button[type="submit"]').click();

    await expect(page.locator('#otp-code')).toBeVisible({ timeout: 10000 });

    const otp = getOperatorOtp();
    expect(otp.length).toBe(6);
    await page.locator('#otp-code').fill(otp);
    await page.locator('button[type="submit"]').click();

    // Verify CMS Dashboard loads and displays Operator role
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/संगणक चालक|Operator/i).first()).toBeVisible();

    // Logout
    const logoutBtn = page.getByRole('button', { name: /(बाहेर पडा|Logout|Sign out)/i });
    if (await logoutBtn.isVisible()) {
      await logoutBtn.click();
      await page.waitForLoadState('networkidle');
      await expect(page.locator('#admin-email')).toBeVisible({ timeout: 10000 });
    }
  });

  test('3. Incorrect password rejection with visible error message', async ({ page }) => {
    await page.goto('/cms');
    await page.waitForLoadState('networkidle');

    await page.locator('#admin-email').fill('local.admin@gramsetu.gov.in');
    await page.locator('#admin-password').fill('CompletelyWrongPassword999!');
    await page.locator('button[type="submit"]').click();

    // Error alert should be displayed
    await expect(page.locator('div[role="alert"]').or(page.locator('.text-red-700')).first()).toBeVisible({ timeout: 5000 });
    // Should NOT advance to OTP step
    await expect(page.locator('#otp-code')).not.toBeVisible();
  });

  test('4. Cross-account OTP rejection in UI', async ({ page }) => {
    await page.goto('/cms');
    await page.waitForLoadState('networkidle');

    // Operator starts login
    await page.locator('#admin-email').fill('local.operator@gramsetu.gov.in');
    await page.locator('#admin-password').fill(PASSWORD);
    await page.locator('button[type="submit"]').click();
    await expect(page.locator('#otp-code')).toBeVisible({ timeout: 10000 });

    // Generate Super Admin's OTP instead
    const saOtp = getSuperAdminOtp();

    // Operator enters Super Admin's OTP
    await page.locator('#otp-code').fill(saOtp);
    await page.locator('button[type="submit"]').click();

    // Must show error alert
    await expect(page.locator('div[role="alert"]').or(page.getByText(/Invalid or expired/i)).first()).toBeVisible({ timeout: 5000 });
    // Must remain on OTP step
    await expect(page.locator('#otp-code')).toBeVisible();
  });
});
