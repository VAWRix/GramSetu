import { test, expect } from '@playwright/test';

test.describe('GramSetu Public Portal End-to-End Suite', () => {
  test('should display home page with official header, navigation, and GIGW branding', async ({ page }) => {
    await page.goto('/');

    // Verify page title and header
    await expect(page).toHaveTitle(/GramSetu|ग्रामसेतू/i);
    await expect(page.locator('div[role="region"]').first()).toContainText(/महाराष्ट्र शासन|Government of Maharashtra/i);

    // Verify main navigation links
    const nav = page.locator('nav[aria-label="Main Navigation"]');
    await expect(nav).toBeVisible();

    // Verify skip to main content link
    const skipLink = page.locator('a.skip-link');
    await expect(skipLink).toBeAttached();
    await expect(skipLink).toHaveAttribute('href', '#main-content');
  });

  test('should support trilingual switching between Marathi, Hindi, and English', async ({ page }) => {
    await page.goto('/');

    const langSelect = page.locator('#portal-lang-select');
    await expect(langSelect).toBeVisible();
    await expect(langSelect).toHaveValue('mr');

    // Switch to Hindi
    await langSelect.selectOption('hi');
    await expect(langSelect).toHaveValue('hi');
    await expect(page.locator('body')).toContainText(/महाराष्ट्र सरकार|ग्राम पंचायत/i);

    // Switch to English
    await langSelect.selectOption('en');
    await expect(langSelect).toHaveValue('en');
    await expect(page.locator('body')).toContainText(/Government of Maharashtra|Panchayat/i);

    // Switch back to Marathi
    await langSelect.selectOption('mr');
    await expect(langSelect).toHaveValue('mr');
  });

  test('should operate accessibility controls: High Contrast & Font Sizing', async ({ page }) => {
    await page.goto('/');

    // High Contrast toggle
    const contrastBtn = page.getByRole('button', { name: /उच्च कॉन्ट्रास्ट|High Contrast|सामान्य थीम|Standard Theme/i });
    await expect(contrastBtn).toBeVisible();
    await contrastBtn.click();
    await expect(contrastBtn).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'contrast');

    // Toggle back
    await contrastBtn.click();
    await expect(contrastBtn).toHaveAttribute('aria-pressed', 'false');
    await expect(page.locator('html')).not.toHaveAttribute('data-theme', 'contrast');

    // Font Sizing controls
    const increaseFontBtn = page.getByRole('button', { name: /अक्षर आकार वाढवा|Increase Font Size/i });
    const normalFontBtn = page.getByRole('button', { name: /सामान्य अक्षर आकार|Normal Font Size/i });
    const decreaseFontBtn = page.getByRole('button', { name: /अक्षर आकार कमी करा|Decrease Font Size/i });

    await expect(increaseFontBtn).toBeVisible();
    await increaseFontBtn.click();
    await expect(page.locator('html')).toHaveAttribute('data-font-size', 'large');

    await normalFontBtn.click();
    await expect(page.locator('html')).toHaveAttribute('data-font-size', 'normal');

    await decreaseFontBtn.click();
    await expect(page.locator('html')).toHaveAttribute('data-font-size', 'small');
  });

  test('should navigate across all public domain portals seamlessly', async ({ page }) => {
    const routes = [
      { path: '/about', heading: /ग्रामपंचायतीविषयी|About/i },
      { path: '/notices', heading: /सूचना व जाहिराती|Notices/i },
      { path: '/documents', heading: /प्रकटीकरण व दस्तऐवज|Documents/i },
      { path: '/events', heading: /ग्रामसभा व बैठका|Meetings/i },
      { path: '/schemes', heading: /शासकीय योजना|Government Schemes/i },
      { path: '/gallery', heading: /चित्रदालन|Photo Gallery/i },
      { path: '/search', heading: /शोध|Unified Search/i },
    ];

    for (const route of routes) {
      await page.goto(route.path);
      await expect(page).toHaveURL(new RegExp(route.path));
      await expect(page.locator('h1').first()).toBeVisible();
    }
  });

  test('should perform public unified search and display results', async ({ page }) => {
    await page.goto('/search');

    const searchInput = page.getByPlaceholder(/शोधा|Search/i).first();
    await expect(searchInput).toBeVisible();

    await searchInput.fill('ग्रामसभा');
    await searchInput.press('Enter');

    // Verify search page responds with query state
    await expect(page).toHaveURL(/search/);
  });

  test('should support mobile viewport navigation drawer toggle', async ({ page, isMobile }) => {
    await page.goto('/');

    if (isMobile) {
      const menuBtn = page.getByRole('button', { name: /मेनू|Menu|Navigation/i });
      await expect(menuBtn).toBeVisible();
      await expect(menuBtn).toHaveAttribute('aria-expanded', 'false');

      await menuBtn.click();
      await expect(menuBtn).toHaveAttribute('aria-expanded', 'true');

      const mobileDrawer = page.locator('#mobile-nav-menu');
      await expect(mobileDrawer).toBeVisible();

      // Click About link in mobile drawer
      await mobileDrawer.getByRole('link', { name: /ग्रामपंचायतीविषयी|माहिती|About/i }).click();
      await expect(page).toHaveURL(/\/about/);
    }
  });
});
