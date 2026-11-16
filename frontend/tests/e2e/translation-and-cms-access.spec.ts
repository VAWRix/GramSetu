import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import path from 'path';
import { mr } from '../../src/lib/i18n/mr';
import { hi } from '../../src/lib/i18n/hi';
import { en } from '../../src/lib/i18n/en';

function getFreshRecoveryCode(): string {
  try {
    const rootDir = path.resolve(__dirname, '../../..');
    const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
    const cmd = `"${pythonExe}" manage.py shell -c "from apps.identity.models import User; from apps.identity.services import generate_recovery_codes; u = User.objects.get(email='local.operator@gramsetu.gov.in'); print(generate_recovery_codes(u, count=5)[0])"`;
    const out = execSync(cmd, { cwd: rootDir, encoding: 'utf-8' });
    const lines = out.trim().split(/\r?\n/);
    return lines[lines.length - 1].trim();
  } catch (err) {
    throw new Error(`Failed to generate dynamic recovery code: ${err}`);
  }
}

function getOperatorTestPassword(): string {
  if (process.env.DEV_OPERATOR_PASSWORD) {
    return process.env.DEV_OPERATOR_PASSWORD;
  }
  if (process.env.TEST_CMS_PASSWORD) {
    return process.env.TEST_CMS_PASSWORD;
  }
  try {
    const rootDir = path.resolve(__dirname, '../../..');
    const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
    const defaultPass = 'DevOperatorTest2026!';
    const cmd = `"${pythonExe}" manage.py shell -c "from apps.identity.models import User; u = User.objects.get(email='local.operator@gramsetu.gov.in'); p = '${defaultPass}'; (None if u.check_password(p) else (u.set_password(p), u.save())); print(p)"`;
    const out = execSync(cmd, { cwd: rootDir, encoding: 'utf-8' });
    const lines = out.trim().split(/\r?\n/);
    const pass = lines[lines.length - 1].trim();
    process.env.TEST_CMS_PASSWORD = pass;
    return pass;
  } catch (err) {
    throw new Error(`Failed to establish test operator password: ${err}`);
  }
}

function getLatestEmailOtp(): string {
  try {
    const rootDir = path.resolve(__dirname, '../../..');
    const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
    const cmd = `"${pythonExe}" manage.py shell -c "from apps.identity.models import User; from apps.identity.services import get_or_create_email_device; u = User.objects.get(email='local.operator@gramsetu.gov.in'); print(get_or_create_email_device(u).token)"`;
    const out = execSync(cmd, { cwd: rootDir, encoding: 'utf-8' });
    const lines = out.trim().split(/\r?\n/);
    return lines[lines.length - 1].trim();
  } catch (err) {
    throw new Error(`Failed to get email OTP: ${err}`);
  }
}

function getAdminTestPassword(): string {
  if (process.env.DEV_ADMIN_PASSWORD) {
    return process.env.DEV_ADMIN_PASSWORD;
  }
  if (process.env.TEST_ADMIN_PASSWORD) {
    return process.env.TEST_ADMIN_PASSWORD;
  }
  try {
    const rootDir = path.resolve(__dirname, '../../..');
    const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
    const defaultPass = 'GramSetu@Test2026';
    const cmd = `"${pythonExe}" manage.py shell -c "from apps.identity.models import User; u = User.objects.get(email='local.admin@gramsetu.gov.in'); p = '${defaultPass}'; (None if u.check_password(p) else (u.set_password(p), u.save())); print(p)"`;
    const out = execSync(cmd, { cwd: rootDir, encoding: 'utf-8' });
    const lines = out.trim().split(/\r?\n/);
    const pass = lines[lines.length - 1].trim();
    process.env.TEST_ADMIN_PASSWORD = pass;
    return pass;
  } catch (err) {
    throw new Error(`Failed to establish test admin password: ${err}`);
  }
}

function getLatestAdminEmailOtp(): string {
  try {
    const rootDir = path.resolve(__dirname, '../../..');
    const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
    const cmd = `"${pythonExe}" manage.py shell -c "from apps.identity.models import User; from apps.identity.services import get_or_create_email_device; u = User.objects.get(email='local.admin@gramsetu.gov.in'); print(get_or_create_email_device(u).token)"`;
    const out = execSync(cmd, { cwd: rootDir, encoding: 'utf-8' });
    const lines = out.trim().split(/\r?\n/);
    return lines[lines.length - 1].trim();
  } catch (err) {
    throw new Error(`Failed to get admin email OTP: ${err}`);
  }
}

test.describe('Milestone Demonstration: Multilingual Parity & Safe CMS Test Access', () => {
  test('1. Translation Dictionary Parity (mr, hi, en)', async () => {
    function getLeafKeys(obj: Record<string, any>, prefix = ''): string[] {
      let keys: string[] = [];
      for (const [k, v] of Object.entries(obj)) {
        const fullKey = prefix ? `${prefix}.${k}` : k;
        if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
          keys = keys.concat(getLeafKeys(v, fullKey));
        } else {
          keys.push(fullKey);
        }
      }
      return keys;
    }

    const mrKeys = getLeafKeys(mr).sort();
    const hiKeys = getLeafKeys(hi).sort();
    const enKeys = getLeafKeys(en).sort();

    expect(mrKeys.length).toBeGreaterThan(120);
    expect(hiKeys.length).toBe(mrKeys.length);
    expect(enKeys.length).toBe(mrKeys.length);

    const missingInHi = mrKeys.filter((k) => !hiKeys.includes(k));
    const missingInEn = mrKeys.filter((k) => !enKeys.includes(k));

    expect(missingInHi).toEqual([]);
    expect(missingInEn).toEqual([]);
  });

  test('2. Public Portal Language Switching (Marathi -> Hindi -> English)', async ({ page }) => {
    await page.goto('/');

    // Verify default Marathi
    await expect(page.locator('header h1')).toBeVisible();
    await page.locator('#portal-lang-select').selectOption('mr');
    await expect(page.locator('#portal-lang-select')).toHaveValue('mr');

    // Switch to Hindi
    await page.locator('#portal-lang-select').selectOption('hi');
    await expect(page.locator('#portal-lang-select')).toHaveValue('hi');
    await expect(page.locator('nav')).toContainText(hi.nav.home);
    await expect(page.locator('nav')).toContainText(hi.nav.about);
    await expect(page.locator('nav')).toContainText(hi.nav.notices);

    // Switch to English
    await page.locator('#portal-lang-select').selectOption('en');
    await expect(page.locator('#portal-lang-select')).toHaveValue('en');
    await expect(page.locator('nav')).toContainText(en.nav.home);
    await expect(page.locator('nav')).toContainText(en.nav.about);
    await expect(page.locator('nav')).toContainText(en.nav.notices);
    await expect(page.locator('header h1')).toContainText(en.header.panchayatOffice);
  });

  test('3. Multilingual Coverage across All Public Routes', async ({ page }) => {
    const routes = [
      { path: '/about', mrText: mr.about.title, enText: en.about.title },
      { path: '/notices', mrText: mr.notices.title, enText: en.notices.title },
      { path: '/documents', mrText: mr.documents.title, enText: en.documents.title },
      { path: '/events', mrText: mr.events.title, enText: en.events.title },
      { path: '/schemes', mrText: mr.schemes.title, enText: en.schemes.title },
      { path: '/gallery', mrText: mr.gallery.title, enText: en.gallery.title },
      { path: '/search', mrText: mr.search.title, enText: en.search.title },
    ];

    for (const r of routes) {
      await page.goto(r.path);

      // Verify Marathi
      await page.locator('#portal-lang-select').selectOption('mr');
      await expect(page.locator('main h1')).toContainText(r.mrText);

      // Verify English
      await page.locator('#portal-lang-select').selectOption('en');
      await expect(page.locator('main h1')).toContainText(r.enText);
    }
  });

  test('4. CMS Auth Gate Localization & Switching', async ({ page }) => {
    await page.goto('/cms');

    // Verify Marathi
    await page.locator('#cms-lang-select').selectOption('mr');
    await expect(page.locator('h1')).toContainText(mr.cmsAuth.loginTitle);
    await expect(page.locator('label[for="admin-email"]')).toContainText(mr.cmsAuth.emailLabel);
    await expect(page.locator('label[for="admin-password"]')).toContainText(mr.cmsAuth.passwordLabel);
    await expect(page.getByRole('button', { name: /प्रवेश करा/ })).toBeVisible();

    // Switch to English
    await page.locator('#cms-lang-select').selectOption('en');
    await expect(page.locator('h1')).toContainText(en.cmsAuth.loginTitle);
    await expect(page.locator('label[for="admin-email"]')).toContainText(en.cmsAuth.emailLabel);
    await expect(page.locator('label[for="admin-password"]')).toContainText(en.cmsAuth.passwordLabel);
    await expect(page.getByRole('button', { name: /Sign In/ })).toBeVisible();

    // Switch to Hindi
    await page.locator('#cms-lang-select').selectOption('hi');
    await expect(page.locator('h1')).toContainText(hi.cmsAuth.loginTitle);
    await expect(page.locator('label[for="admin-email"]')).toContainText(hi.cmsAuth.emailLabel);
    await expect(page.locator('label[for="admin-password"]')).toContainText(hi.cmsAuth.passwordLabel);
  });

  test('5. Safe CMS Test Login with MFA & Recovery Code Authentication', async ({ page }) => {
    const email = process.env.TEST_CMS_EMAIL || 'local.operator@gramsetu.gov.in';
    const password = getOperatorTestPassword();
    const recoveryCode = getFreshRecoveryCode();

    await page.goto('/cms');

    // Fill in test operator credentials
    await page.locator('#admin-email').fill(email);
    await page.locator('#admin-password').fill(password);
    await page.locator('button[type="submit"]').click();

    // Expect MFA challenge screen
    await expect(page.locator('#otp-code')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=l***r@gramsetu.gov.in')).toBeVisible();

    // Switch to Emergency Recovery Code mode
    const recoveryButton = page.getByRole('button', { name: /आपत्कालीन पुनर्प्राप्ती कोड|Use Emergency Recovery Code/i });
    await recoveryButton.click();
    await expect(page.locator('#recovery-code')).toBeVisible();

    // Fill in recovery code
    await page.locator('#recovery-code').fill(recoveryCode);
    await page.locator('button[type="submit"]').click();

    // Verify successful authentication into CMS Dashboard
    await expect(page.getByText('OPERATOR', { exact: true })).toBeVisible({ timeout: 10000 });
    await expect(page.locator('h1')).toBeVisible();

    // Verify authenticated user details in header
    await expect(page.getByRole('banner')).toContainText(email);

    // Test clean logout
    const logoutButton = page.getByRole('button', { name: /लॉग आऊट|Logout/i });
    await logoutButton.click();

    // Expect return to Auth Gate
    await expect(page.locator('#admin-email')).toBeVisible({ timeout: 10000 });
  });

  test('6. Safe CMS Test Login with 6-Digit Email OTP Challenge', async ({ page }) => {
    const email = process.env.TEST_CMS_EMAIL || 'local.operator@gramsetu.gov.in';
    const password = getOperatorTestPassword();

    await page.goto('/cms');

    // Fill in test operator credentials
    await page.locator('#admin-email').fill(email);
    await page.locator('#admin-password').fill(password);
    await page.locator('button[type="submit"]').click();

    // Expect MFA challenge screen
    await expect(page.locator('#otp-code')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=l***r@gramsetu.gov.in')).toBeVisible();

    // Retrieve active OTP delivered to the console email device
    const otp = getLatestEmailOtp();
    expect(otp).toMatch(/^\d{6}$/);

    // Fill in the 6-digit OTP
    await page.locator('#otp-code').fill(otp);
    await page.locator('button[type="submit"]').click();

    // Verify successful authentication into CMS Dashboard
    await expect(page.getByText('OPERATOR', { exact: true })).toBeVisible({ timeout: 10000 });
    await expect(page.locator('h1')).toBeVisible();

    // Verify authenticated user details in header
    await expect(page.getByRole('banner')).toContainText(email);

    // Test clean logout
    const logoutButton = page.getByRole('button', { name: /लॉग आऊट|Logout/i });
    await logoutButton.click();

    // Expect return to Auth Gate
    await expect(page.locator('#admin-email')).toBeVisible({ timeout: 10000 });
  });

  test('7. Safe CMS Test Login as Super Administrator with 6-Digit Email OTP Challenge', async ({ page }) => {
    const email = 'local.admin@gramsetu.gov.in';
    const password = getAdminTestPassword();

    await page.goto('/cms');

    // Fill in test super administrator credentials
    await page.locator('#admin-email').fill(email);
    await page.locator('#admin-password').fill(password);
    await page.locator('button[type="submit"]').click();

    // Expect MFA challenge screen
    await expect(page.locator('#otp-code')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=l***n@gramsetu.gov.in')).toBeVisible();

    // Retrieve active OTP delivered to the console email device
    const otp = getLatestAdminEmailOtp();
    expect(otp).toMatch(/^\d{6}$/);

    // Fill in the 6-digit OTP
    await page.locator('#otp-code').fill(otp);
    await page.locator('button[type="submit"]').click();

    // Verify successful authentication into CMS Dashboard with SUPER ADMINISTRATOR role
    await expect(page.getByText('SUPER ADMINISTRATOR', { exact: true })).toBeVisible({ timeout: 10000 });
    await expect(page.locator('h1')).toBeVisible();

    // Verify authenticated user details in header
    await expect(page.getByRole('banner')).toContainText(email);

    // Test clean logout
    const logoutButton = page.getByRole('button', { name: /लॉग आऊट|Logout/i });
    await logoutButton.click();

    // Expect return to Auth Gate
    await expect(page.locator('#admin-email')).toBeVisible({ timeout: 10000 });
  });
});
