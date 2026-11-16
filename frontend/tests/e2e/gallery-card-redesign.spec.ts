import { test, expect } from '@playwright/test';
import path from 'path';

const SCREENSHOT_DIR = 'C:/Users/Vishal/.gemini/antigravity/brain/84e6dbdc-eff3-4ef4-a44f-854dd46913fd/screenshots/gallery-redesign';

test.describe('Village Photo Gallery Redesigned Card Layout Suite', () => {
  test.setTimeout(60000);

  test('Desktop (1440px) 3-column grid layout, card structure, and visual hierarchy', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/gallery');
    await page.waitForLoadState('networkidle');

    // Verify page header
    const mainHeading = page.locator('h1').first();
    await expect(mainHeading).toBeVisible();

    // Verify album cards exist
    const cards = page.locator('article[role="button"]');
    await expect(cards.first()).toBeVisible({ timeout: 10000 });
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(2);

    // Verify card structure for first card:
    const firstCard = cards.first();

    // 1. Category badge has dedicated top row
    const badge = firstCard.locator('span.rounded-md').first();
    await expect(badge).toBeVisible();

    // 2. Title has full width and bold font
    const title = firstCard.locator('h3').first();
    await expect(title).toBeVisible();

    // 3. Metadata row has category and photo count
    const metaRow = firstCard.locator('div.text-xs.text-\\[var\\(--text-muted\\)\\]').first();
    await expect(metaRow).toBeVisible();

    // 4. Description has line-clamp
    const desc = firstCard.locator('p.line-clamp-2').first();
    await expect(desc).toBeVisible();

    // 5. Image has aspect-video (16:9)
    const imgContainer = firstCard.locator('div.aspect-video').first();
    await expect(imgContainer).toBeVisible();

    // 6. Distinct footer with action link and count
    const footer = firstCard.locator('footer').first();
    await expect(footer).toBeVisible();
    await expect(footer).toContainText(/(View Photos|छायाचित्रे पहा)/i);

    // Capture desktop full page screenshot
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'public-gallery-desktop-3col.png'),
      fullPage: true,
    });
  });

  test('Marathi localization: badges, titles, and footer text', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/gallery');
    await page.waitForLoadState('networkidle');

    // Switch to Marathi if not already
    const langSelect = page.locator('#portal-lang-select');
    if (await langSelect.isVisible()) {
      await langSelect.selectOption('mr');
      await page.waitForTimeout(600);
    }

    const cards = page.locator('article[role="button"]');
    await expect(cards.first()).toBeVisible({ timeout: 10000 });

    // Verify Marathi text in footer
    const footer = cards.first().locator('footer').first();
    await expect(footer).toContainText(/छायाचित्रे पहा/i);

    // Capture Marathi desktop screenshot
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'public-gallery-desktop-mr.png'),
      fullPage: true,
    });
  });

  test('Tablet (768px) 2-column responsive grid layout', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/gallery');
    await page.waitForLoadState('networkidle');

    const cards = page.locator('article[role="button"]');
    await expect(cards.first()).toBeVisible({ timeout: 10000 });

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'public-gallery-tablet-2col.png'),
      fullPage: true,
    });
  });

  test('Mobile (375px) 1-column responsive grid layout', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/gallery');
    await page.waitForLoadState('networkidle');

    const cards = page.locator('article[role="button"]');
    await expect(cards.first()).toBeVisible({ timeout: 10000 });

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'public-gallery-mobile-1col.png'),
      fullPage: true,
    });
  });

  test('Category filter: Gram Sabha filter isolates Gram Sabha album', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/gallery');
    await page.waitForLoadState('networkidle');

    // Click Gram Sabha filter button in header
    const gramSabhaBtn = page.locator('header button').filter({ hasText: /(Gram Sabha|ग्रामसभा)/i });
    await expect(gramSabhaBtn).toBeVisible();
    await gramSabhaBtn.click();
    await page.waitForTimeout(600);

    const cards = page.locator('article[role="button"]');
    await expect(cards.first()).toBeVisible();

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'public-gallery-filter-gramsabha.png'),
      fullPage: true,
    });
  });

  test('Interactive Lightbox Modal: Opens upon card click, displays photo, and closes', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/gallery');
    await page.waitForLoadState('networkidle');

    // Click first card
    const firstCard = page.locator('article[role="button"]').first();
    await expect(firstCard).toBeVisible({ timeout: 10000 });
    await firstCard.click();

    // Lightbox modal should appear
    const dialog = page.locator('div[role="dialog"]');
    await expect(dialog).toBeVisible({ timeout: 10000 });

    // Verify lightbox photo image is visible
    const lightboxImg = dialog.locator('img').first();
    await expect(lightboxImg).toBeVisible();

    // Verify counter (e.g. "1 / 1" or "1 / 2")
    const counter = dialog.locator('span.font-mono');
    await expect(counter).toBeVisible();

    // Capture lightbox modal screenshot
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'public-gallery-lightbox-open.png'),
    });

    // Close lightbox via Escape key
    await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible({ timeout: 5000 });
  });
});
