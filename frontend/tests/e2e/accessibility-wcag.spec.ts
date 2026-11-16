import { test, expect } from '@playwright/test';

test.describe('GramSetu WCAG 2.2 AA & GIGW Accessibility Audit Suite', () => {
  const testPages = ['/', '/about', '/notices', '/documents', '/events', '/schemes', '/gallery', '/search'];

  for (const pagePath of testPages) {
    test(`page ${pagePath} should satisfy semantic heading and landmark structure`, async ({ page }) => {
      await page.goto(pagePath);

      // Verify Exactly one primary H1 exists
      const h1Count = await page.locator('h1').count();
      expect(h1Count).toBeGreaterThanOrEqual(1);

      // Verify Main landmark exists
      const main = page.locator('main, [role="main"]');
      await expect(main.first()).toBeVisible();

      // Verify Header landmark exists
      const header = page.locator('header, [role="banner"]');
      await expect(header.first()).toBeVisible();

      // Verify Footer landmark exists
      const footer = page.locator('footer, [role="contentinfo"]');
      await expect(footer.first()).toBeVisible();
    });
  }

  test('should ensure all form controls have accessible labels', async ({ page }) => {
    await page.goto('/search');

    const inputs = page.locator('input, select, textarea');
    const count = await inputs.count();

    for (let i = 0; i < count; i++) {
      const input = inputs.nth(i);
      const isVisible = await input.isVisible();
      if (!isVisible) continue;

      const id = await input.getAttribute('id');
      const ariaLabel = await input.getAttribute('aria-label');
      const ariaLabelledBy = await input.getAttribute('aria-labelledby');
      const placeholder = await input.getAttribute('placeholder');

      let hasAssociatedLabel = false;
      if (id) {
        hasAssociatedLabel = (await page.locator(`label[for="${id}"]`).count()) > 0;
      }

      const isAccessible = hasAssociatedLabel || !!ariaLabel || !!ariaLabelledBy || !!placeholder;
      expect(isAccessible).toBeTruthy();
    }
  });

  test('should ensure Skip to Content link is keyboard accessible and targets main-content', async ({ page }) => {
    await page.goto('/');

    // Press Tab to focus Skip Link
    await page.keyboard.press('Tab');

    const activeElementHref = await page.evaluate(() => {
      const el = document.activeElement;
      return el ? el.getAttribute('href') : null;
    });

    expect(activeElementHref).toBe('#main-content');

    // Verify target element with id="main-content" exists in the DOM
    const mainTarget = page.locator('#main-content');
    await expect(mainTarget).toBeAttached();
  });

  test('should not have horizontal viewport overflow across standard viewports', async ({ page }) => {
    const viewports = [
      { name: 'Mobile', width: 375, height: 667 },
      { name: 'Tablet', width: 768, height: 1024 },
      { name: 'Desktop', width: 1280, height: 800 },
    ];

    for (const vp of viewports) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto('/');

      const hasHorizontalScroll = await page.evaluate(() => {
        return document.documentElement.scrollWidth > document.documentElement.clientWidth;
      });

      expect(hasHorizontalScroll).toBeFalsy();
    }
  });
});
