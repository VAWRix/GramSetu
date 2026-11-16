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

test.describe('GramSetu Hydration and Locale Verification Suite', () => {
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(60000);

  test('Requirement 1-4: Opening /, /cms, /cms/gallery, and /notices produces zero hydration errors', async ({ page }) => {
    const hydrationErrors: string[] = [];

    page.on('console', msg => {
      const text = msg.text();
      if (text.toLowerCase().includes('hydration') || text.includes('did not match') || text.includes('Recoverable Error')) {
        hydrationErrors.push(`[Console ${msg.type()}] ${text}`);
      }
    });

    page.on('pageerror', err => {
      if (err.message.toLowerCase().includes('hydration') || err.message.includes('did not match')) {
        hydrationErrors.push(`[PageError] ${err.message}`);
      }
    });

    const routesToCheck = ['/', '/cms', '/cms/gallery', '/notices'];

    for (const route of routesToCheck) {
      await page.goto(route);
      await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 });
      // Wait for any deferred client updates
      await page.waitForTimeout(1000);
    }

    expect(hydrationErrors).toEqual([]);
  });

  test('Requirement 5: SkipLink renders correctly, remains accessible, and targets valid main content landmarks', async ({ page }) => {
    // 1. Verify Public Portal SkipLink
    await page.goto('/');
    const publicSkipLink = page.locator('a.skip-link').first();
    await expect(publicSkipLink).toBeAttached();
    await expect(publicSkipLink).toHaveAttribute('href', '#main-content');
    await expect(publicSkipLink).toHaveText('मुख्य मजकुराकडे जा');

    // Verify main target landmark exists
    const publicMain = page.locator('#main-content');
    await expect(publicMain).toBeAttached();
    await expect(publicMain).toHaveAttribute('role', 'main');

    // 2. Verify CMS Portal SkipLink
    await page.goto('/cms');
    const cmsSkipLink = page.locator('a.skip-link').first();
    await expect(cmsSkipLink).toBeAttached();
    await expect(cmsSkipLink).toHaveAttribute('href', '#cms-main-content');
    await expect(cmsSkipLink).toHaveText('मुख्य मजकुराकडे जा');
  });

  test('Requirement 6-8: Saved language preferences restore without hydration mismatch across refreshes and direct navigation', async ({ page }) => {
    const hydrationErrors: string[] = [];

    page.on('console', msg => {
      const text = msg.text();
      if (text.toLowerCase().includes('hydration') || text.includes('did not match') || text.includes('Recoverable Error')) {
        hydrationErrors.push(`[Console ${msg.type()}] ${text}`);
      }
    });

    page.on('pageerror', err => {
      if (err.message.toLowerCase().includes('hydration') || err.message.includes('did not match')) {
        hydrationErrors.push(`[PageError] ${err.message}`);
      }
    });

    // 1. Visit with English preference stored in localStorage
    await page.goto('/');
    await page.evaluate(() => {
      localStorage.setItem('gramsetu_lang_pref', 'en');
    });

    // Reload with saved English preference
    await page.reload();
    await expect(page.locator('h1').first()).toBeVisible();

    // Verify SkipLink and portal content updated to English after hydration
    const skipLink = page.locator('a.skip-link').first();
    await expect(skipLink).toHaveText('Skip to main content', { timeout: 5000 });

    const langSelect = page.locator('#portal-lang-select');
    await expect(langSelect).toHaveValue('en');

    // 2. Direct navigation to /cms with English preference preserved
    await page.goto('/cms');
    await expect(page.locator('h1').first()).toBeVisible();

    const cmsSkipLink = page.locator('a.skip-link').first();
    await expect(cmsSkipLink).toHaveText('Skip to main content', { timeout: 5000 });

    // 3. Switch to Hindi
    await page.goto('/');
    await page.locator('#portal-lang-select').selectOption('hi');
    await expect(page.locator('a.skip-link').first()).toHaveText('मुख्य सामग्री पर जाएं', { timeout: 5000 });

    // Refresh and confirm Hindi persistence without hydration error
    await page.reload();
    await expect(page.locator('a.skip-link').first()).toHaveText('मुख्य सामग्री पर जाएं', { timeout: 5000 });
    await expect(page.locator('#portal-lang-select')).toHaveValue('hi');

    // 4. Reset back to Marathi (default)
    await page.locator('#portal-lang-select').selectOption('mr');
    await expect(page.locator('a.skip-link').first()).toHaveText('मुख्य मजकुराकडे जा', { timeout: 5000 });

    expect(hydrationErrors).toEqual([]);
  });

  test('Requirement 9: Authentication, MFA, CMS navigation, and session gates continue to operate reliably', async ({ page }) => {
    const adminPass = getAdminTestPassword();

    await page.goto('/cms');
    await expect(page.locator('#admin-email')).toBeVisible();

    // Fill credentials
    await page.locator('#admin-email').fill('local.admin@gramsetu.gov.in');
    await page.locator('#admin-password').fill(adminPass);
    await page.locator('button[type="submit"]').click();

    // Verify MFA prompt
    await expect(page.locator('#otp-code')).toBeVisible({ timeout: 10000 });
    const adminOtp = getAdminEmailOtp();
    await page.locator('#otp-code').fill(adminOtp);
    await page.locator('button[type="submit"]').click();

    // Verify successful login
    await expect(page.getByText('SUPER ADMINISTRATOR', { exact: true })).toBeVisible({ timeout: 10000 });

    // Navigate to CMS Gallery
    await page.goto('/cms/gallery');
    await expect(page.locator('h1').first()).toBeVisible();
    await expect(page.getByText(/Request failed \(HTTP 500\)/i)).not.toBeVisible();
  });
});
