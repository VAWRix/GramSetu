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

test.describe('Gallery Language Simplification & Cross-Role Governance Suite', () => {
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(90000);

  test('Priority One: Super Admin creates English-primary album, direct publishes, and checks public fallback', async ({ page }) => {
    // 1. Log in as Super Admin
    await loginUser(page, 'local.admin@gramsetu.gov.in');
    await expect(page.getByText('SUPER ADMINISTRATOR', { exact: true })).toBeVisible({ timeout: 10000 });

    // 2. Navigate to CMS Gallery
    await page.goto('/cms/gallery');
    await expect(page.locator('h1')).toBeVisible();

    // 3. Open Create Album Modal
    const createBtn = page.getByRole('button', { name: /\+.*अल्बम|Create Album|अल्बम तयार करा/i }).first();
    await createBtn.click();
    await expect(page.locator('input[placeholder="panchayat-building-inauguration"]')).toBeVisible({ timeout: 10000 });

    // 4. Fill in English-primary details
    const testSlug = `test-eng-e2e-${Date.now()}`;
    await page.locator('input[placeholder="panchayat-building-inauguration"]').fill(testSlug);

    // Switch Primary Language to English
    await page.getByRole('button', { name: 'English (EN)' }).click();

    // Verify English primary title field is visible and fill it
    const engTitleInput = page.locator('input[placeholder*="Gram Panchayat New Administrative Building Inauguration"]');
    await expect(engTitleInput).toBeVisible();
    await engTitleInput.fill('E2E Community Center Inauguration');

    // Handle window.prompt dialog for justification
    page.on('dialog', async (dialog) => {
      await dialog.accept('Direct publication of completed community photo gallery album by Super Admin');
    });

    const engDescInput = page.locator('textarea[placeholder*="Brief summary of the ceremony"]');
    await engDescInput.fill('Official inauguration of the newly built community center.');

    // Save as draft first (albums require at least 1 photo before publication)
    await page.locator('button[type="submit"]:has-text("जतन करा")').click();

    // Verify draft saved successfully without Marathi error
    await expect(page.getByText(/अल्बम मसुदा यशस्वीरीत्या जतन केला|Draft album created successfully/i)).toBeVisible({ timeout: 15000 });

    // 5. Verify card rendering and add a photo
    await expect(page.getByText(`/${testSlug}`).first()).toBeVisible();
    await expect(page.getByText('प्राथमिक: EN').first()).toBeVisible();
    await expect(page.getByText('E2E Community Center Inauguration').first()).toBeVisible();

    // Click Add Photo on the first album
    const addPhotoBtn = page.locator('button:has-text("छायाचित्र जोडा")').first();
    await addPhotoBtn.click();

    // Switch to External Link tab
    await page.getByRole('button', { name: /इमेज लिंक|Google Drive/i }).click();
    await page.locator('input[type="url"]').fill('https://images.unsplash.com/photo-1577495508048-b635879837f1');
    await page.locator('input[placeholder*="उदा. ग्रामपंचायत"]').fill('Community Hall Entrance');
    await page.locator('input[placeholder*="Inauguration ceremony"]').fill('Grand opening ribbon cutting ceremony');

    // Submit photo
    await page.locator('button[type="submit"]:has-text("जतन करा")').click();
    await expect(page.getByText(/Image link successfully added to album|छायाचित्र जोडले/i)).toBeVisible({ timeout: 15000 });

    // 6. Direct Publish by Super Admin now that it has 1 photo
    const publishDirectBtn = page.locator('button:has-text("थेट प्रकाशित करा")').first();
    await expect(publishDirectBtn).toBeVisible();
    await publishDirectBtn.click();

    await expect(page.getByText('published').first()).toBeVisible({ timeout: 15000 });
    await expect(page.locator('button:has-text("मागे घ्या")').first()).toBeVisible();

    // 7. Public Portal Verification (as anonymous citizen)
    await page.goto('/gallery');
    await expect(page.locator('h1').first()).toBeVisible();

    // The English-primary album should be visible on the public portal
    const publicAlbum = page.locator(`text=E2E Community Center Inauguration`).first();
    await expect(publicAlbum).toBeVisible({ timeout: 10000 });

    // Click on the album to open lightbox
    await publicAlbum.click();
    await page.waitForTimeout(1000);
    // Lightbox should display the photo
    await expect(page.locator('img[alt*="Community Hall Entrance"]').or(page.locator('img[alt*="Grand opening"]')).first()).toBeVisible();

    // Close lightbox
    await page.keyboard.press('Escape');
  });

  test('Operator Review Workflow & Anti-Self-Approval Enforcement', async ({ page }) => {
    // 1. Log in as Operator
    await loginUser(page, 'local.operator@gramsetu.gov.in');
    await expect(page.getByText('OPERATOR', { exact: true })).toBeVisible({ timeout: 10000 });

    // 2. Navigate to CMS Gallery
    await page.goto('/cms/gallery');
    await expect(page.locator('h1')).toBeVisible();

    // 3. Open Create Album Modal
    const createBtn = page.getByRole('button', { name: /\+.*अल्बम|Create Album|अल्बम तयार करा/i }).first();
    await createBtn.click();
    await expect(page.locator('input[placeholder="panchayat-building-inauguration"]')).toBeVisible({ timeout: 10000 });

    // Operator does NOT have direct publish checkbox
    await expect(page.locator('#album-publish-now')).not.toBeVisible();

    // Fill in Hindi-primary draft details
    const operatorSlug = `test-op-hi-${Date.now()}`;
    await page.locator('input[placeholder="panchayat-building-inauguration"]').fill(operatorSlug);

    // Switch Primary Language to Hindi
    await page.getByRole('button', { name: 'हिंदी (HI)' }).click();

    const hiTitleInput = page.locator('input[placeholder*="ग्राम पंचायत नवीन प्रशासनिक भवन"]');
    await hiTitleInput.fill('सामुदायिक केंद्र का उद्घाटन');

    // Save as Draft
    await page.locator('button[type="submit"]:has-text("जतन करा")').click();
    await expect(page.getByText(/अल्बम मसुदा यशस्वीरीत्या जतन केला|Draft album created successfully/i)).toBeVisible({ timeout: 15000 });

    // Find the newly created draft album
    await expect(page.getByText(`/${operatorSlug}`).first()).toBeVisible();
    await expect(page.getByText('प्राथमिक: HI').first()).toBeVisible();

    // Verify operator CANNOT directly publish
    await expect(page.locator('button:has-text("थेट प्रकाशित करा")')).not.toBeVisible();

    // Operator submits for review
    const submitBtn = page.locator('button:has-text("मंजुरीसाठी सादर करा")').first();
    await expect(submitBtn).toBeVisible();
    await submitBtn.click();

    await expect(page.getByText(/मंजुरीसाठी सादर करा|पुनरावलोकनासाठी प्रलंबित/i).first()).toBeVisible({ timeout: 15000 });
  });
});
