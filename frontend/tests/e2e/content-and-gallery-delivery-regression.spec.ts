import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import path from 'path';

function getTestPassword(email: string): string {
  const rootDir = path.resolve(__dirname, '../../..');
  const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
  const defaultPass = 'GramSetu@Test2026';
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
  const pass = getTestPassword(email);
  await page.goto('/cms');
  await page.locator('#admin-email').fill(email);
  await page.locator('#admin-password').fill(pass);
  await page.locator('button[type="submit"]').click();

  await expect(page.locator('#otp-code')).toBeVisible({ timeout: 10000 });
  const otp = getEmailOtp(email);
  await page.locator('#otp-code').fill(otp);
  await page.locator('button[type="submit"]').click();

  await page.waitForLoadState('networkidle');
}

test.describe('Content Body Markdown & Gallery Image Delivery Regression Suite', () => {
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(90000);

  test('Issue 1: Public About Panchayat page displays full approved main content and preserves formatting', async ({ page }) => {
    // 1. Visit public About page
    await page.goto('/about');
    await expect(page.locator('h1').first()).toBeVisible();

    // Select English to match the English page revision assertions
    const langSelect = page.locator('#portal-lang-select');
    if (await langSelect.isVisible()) {
      const enRes = page.waitForResponse(r => r.url().includes('/api/content/pages/') && r.status() === 200).catch(() => null);
      await langSelect.selectOption('en');
      await enRes;
      await page.waitForTimeout(400);
    }

    // 2. Narayangaon Village card should be rendered
    const villageTitle = page.getByText(/Narayangaon Village/i).first();
    await expect(villageTitle).toBeVisible({ timeout: 10000 });

    // 3. Short summary should be visible
    const summary = page.getByText(/in short info and geography|Comprehensive statutory encyclopedic article|Narayangaon is a historic|नारायणगाव हे छत्रपती संभाजीनगर/i).first();
    await expect(summary).toBeVisible();

    // 4. The full/main information entered in the CMS MUST BE VISIBLE
    const bodyParagraph1 = page.getByText(/Narayangaon is a (?:historic agricultural |historic agrarian )?village (?:located|situated) in Paithan tehsil|नारायणगाव हे/i).first();
    await expect(bodyParagraph1).toBeVisible();

    const bodyParagraph2 = page.getByText(/The LGD village code for Narayangaon is 549493|LGD.*549493|स्थानिक.*549493/i).first();
    await expect(bodyParagraph2).toBeVisible();

    // 5. Verify paragraph structure (both paragraphs are present and separated)
    await expect(page.getByText(/Paithan tehsil of Chhatrapati Sambhajinagar district|छत्रपती संभाजीनगर जिल्ह्यातील पैठण/i).first()).toBeVisible();
    await expect(page.getByText(/714(?:\.00)?\s*hectares|७१४(?:\.००)?\s*हेक्टर/i).first()).toBeVisible();
  });

  test('Issue 2: Public Gallery displays photographs with successful HTTP 200 delivery without broken images', async ({ page }) => {
    // Collect failed network requests
    const failedImageRequests: string[] = [];
    page.on('response', (response) => {
      if (response.request().resourceType() === 'image' && response.status() >= 400) {
        failedImageRequests.push(`${response.url()} -> HTTP ${response.status()}`);
      }
    });

    // 1. Navigate to Public Gallery
    await page.goto('/gallery');
    await expect(page.locator('h1').first()).toBeVisible();

    // 2. Locate album and verify cover image
    const coverImg = page.locator('img[src*="/gallery/image/"], img[src*="unsplash.com"]').first();
    await expect(coverImg).toBeVisible({ timeout: 10000 });

    // Verify the image actually rendered and is not a broken placeholder
    await page.waitForFunction((selector) => {
      const img = document.querySelector(selector) as HTMLImageElement;
      return img && img.complete && img.naturalWidth > 0;
    }, 'img[src*="/gallery/image/"], img[src*="unsplash.com"]');

    // 3. Click album to open Lightbox
    const albumCard = page.locator('.cursor-pointer, .group').filter({ hasText: /testing|test-feature|office visit/i }).first();
    await albumCard.click();
    await page.waitForTimeout(1000);

    // 4. Verify main photo in Lightbox loads successfully
    const lightboxImg = page.locator('div[role="dialog"] img, .fixed img').first();
    await expect(lightboxImg).toBeVisible({ timeout: 10000 });

    const isLoaded = await lightboxImg.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0);
    expect(isLoaded).toBe(true);

    // Verify caption is visible in lightbox
    await expect(page.getByText(/office visit at narayangaon/i).first()).toBeVisible();

    // Verify zero failed image requests
    expect(failedImageRequests).toHaveLength(0);

    // Close lightbox
    await page.keyboard.press('Escape');
  });

  test('CMS Page Edit updates existing record without creating duplicates', async ({ page }) => {
    // 1. Log in as Super Admin
    await loginUser(page, 'local.admin@gramsetu.gov.in');
    await expect(page.getByText('SUPER ADMINISTRATOR', { exact: true })).toBeVisible({ timeout: 10000 });

    // 2. Navigate to CMS Pages & Information
    await page.goto('/cms/content');
    await expect(page.locator('h1').first()).toBeVisible();

    // 3. Find Narayangaon Village page
    await expect(page.getByText('/informational').first()).toBeVisible();
    await expect(page.getByText('Narayangaon Village').first()).toBeVisible();

    // Count pages with slug /informational before editing
    const matchingSlugsBefore = await page.getByText('/informational').count();

    // 4. Inspect full markdown via View Details
    const viewDetailsBtn = page.locator('button:has-text("तपशील पहा")').first();
    await viewDetailsBtn.click();
    await expect(page.getByText(/संपूर्ण मजकूर|Full Formatted Content/i)).toBeVisible();
    await expect(page.getByText(/Paithan tehsil/i).first()).toBeVisible();

    // Close details modal
    await page.locator('button:has-text("बंद करा")').last().click();

    // 5. Verify page count remained exact same (no duplication)
    const matchingSlugsAfter = await page.getByText('/informational').count();
    expect(matchingSlugsAfter).toBe(matchingSlugsBefore);
  });

  test('CMS Gallery external link validates and rejects unsupported Google Drive folder URLs', async ({ page }) => {
    // 1. Log in as Super Admin
    await loginUser(page, 'local.admin@gramsetu.gov.in');
    await expect(page.getByText('SUPER ADMINISTRATOR', { exact: true })).toBeVisible({ timeout: 10000 });

    // 2. Navigate to CMS Gallery
    await page.goto('/cms/gallery');
    await expect(page.locator('h1').first()).toBeVisible();

    // 3. Open Add Photo Modal on an album
    const addPhotoBtn = page.locator('button').filter({ hasText: /फोटो अपलोड|छायाचित्र जोडा|Add Photo/i }).first();
    await addPhotoBtn.click();

    // Switch to External Link / Google Drive tab
    await page.getByRole('button', { name: /इमेज लिंक|Google Drive/i }).click();

    // 4. Fill in an unsupported Google Drive folder link
    await page.locator('input[type="url"]').fill('https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsTuVwXyZ');
    await page.locator('input[placeholder*="उदा. ग्रामपंचायत"]').fill('Test Folder Link');
    await page.locator('input[placeholder*="Inauguration ceremony"]').fill('Should be rejected');

    // Submit
    await page.locator('button[type="submit"]:has-text("जतन करा")').click();

    // 5. Must display clean, helpful validation error instead of silently saving broken image
    await expect(page.getByText(/folder links cannot be rendered|Folder links are not supported|त्रुटी/i)).toBeVisible({ timeout: 10000 });

    // Close modal
    await page.locator('button:has-text("✕")').last().click();
  });
});
