import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import path from 'path';
import fs from 'fs';

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

const screenshotsDir = path.resolve(__dirname, '../../../docs/screenshots');

test.describe('Full-Page Screenshot Capture Suite', () => {
  test('1. Capture Desktop Public Pages (1440x1000)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });

    const publicRoutes = [
      { path: '/', name: 'public/public-home-mr-desktop.png' },
      { path: '/about', name: 'public/public-about-mr-desktop.png' },
      { path: '/notices', name: 'public/public-notices-mr-desktop.png' },
      { path: '/documents', name: 'public/public-documents-mr-desktop.png' },
      { path: '/events', name: 'public/public-events-mr-desktop.png' },
      { path: '/schemes', name: 'public/public-schemes-mr-desktop.png' },
      { path: '/gallery', name: 'public/public-gallery-mr-desktop.png' },
      { path: '/search', name: 'public/public-search-mr-desktop.png' },
    ];

    for (const r of publicRoutes) {
      await page.goto(r.path);
      await page.waitForLoadState('networkidle');
      await page.locator('#portal-lang-select').selectOption('mr');
      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(screenshotsDir, r.name),
        fullPage: true,
      });
    }
  });

  test('2. Capture Language Variants (1440x1000)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });

    const langVariants = [
      { path: '/', lang: 'hi', name: 'languages/public-home-hi-desktop.png' },
      { path: '/', lang: 'en', name: 'languages/public-home-en-desktop.png' },
      { path: '/notices', lang: 'hi', name: 'languages/public-notices-hi-desktop.png' },
      { path: '/notices', lang: 'en', name: 'languages/public-notices-en-desktop.png' },
      { path: '/schemes', lang: 'en', name: 'languages/public-schemes-en-desktop.png' },
      { path: '/documents', lang: 'en', name: 'languages/public-documents-en-desktop.png' },
    ];

    for (const item of langVariants) {
      await page.goto(item.path);
      await page.waitForLoadState('networkidle');
      await page.locator('#portal-lang-select').selectOption(item.lang);
      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(screenshotsDir, item.name),
        fullPage: true,
      });
    }
  });

  test('3. Capture Mobile Responsive Views (390x844)', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    // Mobile homepage
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.screenshot({
      path: path.join(screenshotsDir, 'mobile/mobile-home-mr.png'),
      fullPage: true,
    });

    // Mobile navigation drawer open
    const menuBtn = page.getByRole('button', { name: /मेनू|Menu/i });
    if (await menuBtn.isVisible()) {
      await menuBtn.click();
      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(screenshotsDir, 'mobile/mobile-menu-drawer.png'),
        fullPage: false,
      });
    }

    // Mobile notices page
    await page.goto('/notices');
    await page.waitForLoadState('networkidle');
    await page.screenshot({
      path: path.join(screenshotsDir, 'mobile/mobile-notices.png'),
      fullPage: true,
    });

    // Mobile schemes page
    await page.goto('/schemes');
    await page.waitForLoadState('networkidle');
    await page.screenshot({
      path: path.join(screenshotsDir, 'mobile/mobile-schemes.png'),
      fullPage: true,
    });
  });

  test('4. Capture Interactive States (1440x1000)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });

    // High Contrast Mode
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    const contrastBtn = page.getByRole('button', { name: /हाय कॉन्ट्रास्ट|High Contrast/i });
    if (await contrastBtn.isVisible()) {
      await contrastBtn.click();
      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(screenshotsDir, 'interactive/public-home-high-contrast.png'),
        fullPage: true,
      });
      // Revert contrast
      await contrastBtn.click();
    }

    // Large Font Mode
    const fontPlusBtn = page.getByRole('button', { name: /अक्षर आकार वाढवा|Increase font size/i });
    if (await fontPlusBtn.isVisible()) {
      await fontPlusBtn.click();
      await fontPlusBtn.click();
      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(screenshotsDir, 'interactive/public-home-large-font.png'),
        fullPage: true,
      });
    }

    // Search Results Page with Query
    await page.goto('/search?q=%E0%A4%97%E0%A5%8D%E0%A4%B0%E0%A4%BE%E0%A4%AE%E0%A4%B8%E0%A4%AD%E0%A4%BE');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(400);
    await page.screenshot({
      path: path.join(screenshotsDir, 'interactive/public-search-results.png'),
      fullPage: true,
    });

    // Filtered Notices (Tender tab active)
    await page.goto('/notices');
    await page.waitForLoadState('networkidle');
    const tenderFilter = page.getByRole('button', { name: /निविदा|Tender/i });
    if (await tenderFilter.isVisible()) {
      await tenderFilter.click();
      await page.waitForTimeout(400);
      await page.screenshot({
        path: path.join(screenshotsDir, 'interactive/public-notices-filtered-tenders.png'),
        fullPage: true,
      });
    }
  });

  test('5. Capture CMS Authentication & Protected Dashboard Pages (1440x1000)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });

    const email = process.env.TEST_CMS_EMAIL || 'local.operator@gramsetu.gov.in';
    const password = getOperatorTestPassword();
    const recoveryCode = getFreshRecoveryCode();

    // 1. CMS Login Gate
    await page.goto('/cms');
    await page.waitForLoadState('networkidle');
    await page.screenshot({
      path: path.join(screenshotsDir, 'cms/cms-login-gate-desktop.png'),
      fullPage: true,
    });

    // 2. CMS Invalid Credentials Error
    await page.locator('#admin-email').fill(email);
    await page.locator('#admin-password').fill('WrongPassword999!');
    await page.locator('button[type="submit"]').click();
    await expect(page.locator('text=प्रमाणीकरण त्रुटी')).toBeVisible({ timeout: 5000 });
    await page.screenshot({
      path: path.join(screenshotsDir, 'cms/cms-invalid-credentials.png'),
      fullPage: true,
    });

    // 3. CMS MFA Challenge Screen
    await page.locator('#admin-password').fill(password);
    await page.locator('button[type="submit"]').click();
    await expect(page.locator('#otp-code')).toBeVisible({ timeout: 10000 });
    await page.screenshot({
      path: path.join(screenshotsDir, 'cms/cms-mfa-challenge-desktop.png'),
      fullPage: true,
    });

    // 4. CMS Emergency Recovery Code Mode
    const recoveryButton = page.getByRole('button', { name: /आपत्कालीन पुनर्प्राप्ती कोड|Use Emergency Recovery Code/i });
    await recoveryButton.click();
    await expect(page.locator('#recovery-code')).toBeVisible();
    await page.screenshot({
      path: path.join(screenshotsDir, 'cms/cms-recovery-mode-desktop.png'),
      fullPage: true,
    });

    // Authenticate with recovery code
    await page.locator('#recovery-code').fill(recoveryCode);
    await page.locator('button[type="submit"]').click();

    // Verify authenticated in CMS Dashboard
    await expect(page.getByText('OPERATOR', { exact: true })).toBeVisible({ timeout: 10000 });
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    // 5. CMS Dashboard
    await page.screenshot({
      path: path.join(screenshotsDir, 'cms/cms-dashboard-desktop.png'),
      fullPage: true,
    });

    // 6. CMS Content Pages
    await page.goto('/cms/content');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(300);
    await page.screenshot({
      path: path.join(screenshotsDir, 'cms/cms-content-desktop.png'),
      fullPage: true,
    });

    // 7. CMS Notices Management
    await page.goto('/cms/notices');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(300);
    await page.screenshot({
      path: path.join(screenshotsDir, 'cms/cms-notices-desktop.png'),
      fullPage: true,
    });

    // 8. CMS Documents Disclosure
    await page.goto('/cms/documents');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(300);
    await page.screenshot({
      path: path.join(screenshotsDir, 'cms/cms-documents-desktop.png'),
      fullPage: true,
    });

    // 9. CMS Events & Meetings
    await page.goto('/cms/events');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(300);
    await page.screenshot({
      path: path.join(screenshotsDir, 'cms/cms-events-desktop.png'),
      fullPage: true,
    });

    // 10. CMS Schemes Management
    await page.goto('/cms/schemes');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(300);
    await page.screenshot({
      path: path.join(screenshotsDir, 'cms/cms-schemes-desktop.png'),
      fullPage: true,
    });

    // 11. CMS Gallery Management
    await page.goto('/cms/gallery');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(300);
    await page.screenshot({
      path: path.join(screenshotsDir, 'cms/cms-gallery-desktop.png'),
      fullPage: true,
    });

    // 12. CMS Governance & Review Queue
    await page.goto('/cms/governance');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(300);
    await page.screenshot({
      path: path.join(screenshotsDir, 'cms/cms-governance-desktop.png'),
      fullPage: true,
    });

    // 13. CMS Audit Trail Logs
    await page.goto('/cms/audit');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(300);
    await page.screenshot({
      path: path.join(screenshotsDir, 'cms/cms-audit-desktop.png'),
      fullPage: true,
    });
  });
});
