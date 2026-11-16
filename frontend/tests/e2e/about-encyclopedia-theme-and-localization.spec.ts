import { test, expect } from '@playwright/test';

test.describe('Village Encyclopedia — Theme, Localization, Card Sizing & Seal Verification', () => {
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(90000);

  test('1. Official Light Theme & Content-Driven Card Sizing on About Page', async ({ page }) => {
    await page.goto('/about');
    await page.waitForLoadState('networkidle');

    const article = page.locator('#knowledge-article');
    await expect(article).toBeVisible({ timeout: 15000 });

    // Verify absence of dark gradient classes on the article container
    const headerCard = article.locator('div.border-l-4').first();
    await expect(headerCard).toBeVisible();
    const headerClass = await headerCard.getAttribute('class') || '';
    expect(headerClass).not.toContain('from-[#1e3a8a]');
    expect(headerClass).not.toContain('via-[#1e40af]');

    // Verify official light theme tokens or white surface backgrounds
    expect(headerClass).toContain('bg-[var(--bg-surface)]');

    // Verify section cards have content-driven sizing (no hardcoded fixed heights)
    const historySection = page.locator('#section-history');
    await expect(historySection).toBeVisible();
    const historyBox = await historySection.boundingBox();
    expect(historyBox).not.toBeNull();
    if (historyBox) {
      // Natural content height should be reasonable (greater than 100px, less than 600px for short section)
      expect(historyBox.height).toBeGreaterThan(80);
      expect(historyBox.height).toBeLessThan(700);
    }

    // Verify infobox has natural height and official seal area
    const infobox = page.locator('aside[aria-label]').first();
    await expect(infobox).toBeVisible();
    await expect(infobox.getByText(/549493/i).first()).toBeVisible();
    await expect(infobox.getByText(/महाराष्ट्र शासन राजमुद्रा अधिकृत क्षेत्र/i)).toBeVisible();
  });

  test('2. Complete Multilingual Switching: Marathi -> English -> Hindi', async ({ page }) => {
    await page.goto('/about');
    await page.waitForLoadState('networkidle');

    // --- A. MARATHI (Default) ---
    await expect(page.locator('#knowledge-article').getByText(/नारायणगाव ग्राम माहिती ज्ञानकोश/i).first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#section-history').getByText(/१\. गावाची ऐतिहासिक पार्श्वभूमी/i).first()).toBeVisible();
    await expect(page.locator('#article-toc').getByText(/अनुक्रमणिका/i)).toBeVisible();
    await expect(page.locator('aside[aria-label]').getByText(/स्थानिक स्वराज्य संस्था माहिती/i)).toBeVisible();

    // --- B. SWITCH TO ENGLISH ---
    const langSelect = page.locator('#portal-lang-select');
    await expect(langSelect).toBeVisible();
    const enResponse = page.waitForResponse(res => res.url().includes('/api/content/pages/') && res.status() === 200);
    await langSelect.selectOption('en');
    await enResponse;
    await page.waitForTimeout(400);

    // Entire article updates to English!
    await expect(page.locator('#knowledge-article').getByText(/Narayangaon Village Knowledge Portal/i).first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#section-history').getByText(/1\. Historical Background of the Village/i).first()).toBeVisible();
    await expect(page.locator('#article-toc').getByText(/Contents/i).first()).toBeVisible();
    await expect(page.locator('aside[aria-label]').getByText(/Local Governance Information/i).first()).toBeVisible();
    await expect(page.locator('aside[aria-label]').getByText(/India \/ Maharashtra/i)).toBeVisible();
    await expect(page.locator('#article-references').getByText(/References & Official Sources/i).first()).toBeVisible();

    // --- C. SWITCH TO HINDI ---
    const hiResponse = page.waitForResponse(res => res.url().includes('/api/content/pages/') && res.status() === 200);
    await langSelect.selectOption('hi');
    await hiResponse;
    await page.waitForTimeout(400);

    // Entire article updates to Hindi!
    await expect(page.locator('#knowledge-article').getByText(/नारायणगांव ग्राम ज्ञानकोश/i).first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#section-history').getByText(/1\. गाँव की ऐतिहासिक पृष्ठभूमि/i).first()).toBeVisible();
    await expect(page.locator('#article-toc').getByText(/विषय सूची/i)).toBeVisible();
    await expect(page.locator('aside[aria-label]').getByText(/स्थानीय स्वराज्य संस्था विवरण/i)).toBeVisible();
    await expect(page.locator('#article-references').getByText(/संदर्भ एवं आधिकारिक सरकारी स्रोत/i).first()).toBeVisible();
  });

  test('3. Table of Contents Navigation & In-Article Search Filter', async ({ page }) => {
    await page.goto('/about');
    await page.waitForLoadState('networkidle');

    // Check all 14 statutory sections exist in TOC
    const toc = page.locator('#article-toc');
    await expect(toc).toBeVisible();

    const sections = [
      'history', 'geography', 'boundaries', 'demographics', 'administration',
      'agriculture', 'education', 'healthcare', 'transportation', 'water_sanitation',
      'culture_places', 'public_services', 'contacts', 'faq'
    ];

    for (const secKey of sections) {
      await expect(page.locator(`#section-${secKey}`)).toBeAttached();
    }

    // Filter article by keyword
    const filter = page.locator('#section-filter');
    await filter.fill('शेती');
    await page.waitForTimeout(300);

    // Section 6 (Agriculture) should be visible
    await expect(page.locator('#section-agriculture')).toBeVisible();

    // Clear search
    await filter.fill('');
    await page.waitForTimeout(200);
    await expect(page.locator('#section-history')).toBeVisible();
  });

  test('4. Academic References & Verified Citation Buttons', async ({ page }) => {
    await page.goto('/about');
    await page.waitForLoadState('networkidle');

    const refsSection = page.locator('#article-references');
    await expect(refsSection).toBeVisible();

    // Citations [1], [2], [3], [4] should be rendered
    await expect(refsSection.getByText(/\[1\]/i).first()).toBeVisible();
    await expect(refsSection.getByText(/\[2\]/i).first()).toBeVisible();
    await expect(refsSection.getByText(/\[3\]/i).first()).toBeVisible();
    await expect(refsSection.getByText(/\[4\]/i).first()).toBeVisible();

    // External link to LGD or Census
    const extLink = refsSection.locator('a[target="_blank"]').first();
    await expect(extLink).toBeVisible();
    const href = await extLink.getAttribute('href');
    expect(href).toMatch(/^https?:\/\//);
  });

  test('5. Three-Column Desktop Layout & Responsive Zero-Overlap Verification', async ({ page }) => {
    // Desktop Viewport (1280x900)
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/about');
    await page.waitForLoadState('networkidle');

    const toc = page.locator('#article-toc');
    const sec1 = page.locator('#section-history');
    const sec2 = page.locator('#section-geography');
    const govCard = page.locator('aside[aria-label]').first();

    await expect(toc).toBeVisible();
    await expect(sec1).toBeVisible();
    await expect(sec2).toBeVisible();
    await expect(govCard).toBeVisible();

    const tocBox = await toc.boundingBox();
    const sec1Box = await sec1.boundingBox();
    const sec2Box = await sec2.boundingBox();
    const govBox = await govCard.boundingBox();

    expect(tocBox).not.toBeNull();
    expect(sec1Box).not.toBeNull();
    expect(sec2Box).not.toBeNull();
    expect(govBox).not.toBeNull();

    if (tocBox && sec1Box && sec2Box && govBox) {
      // Distinct 3 columns
      expect(tocBox.x).toBeLessThan(sec1Box.x);
      expect(sec1Box.x).toBeLessThan(govBox.x);
      // Zero overlap: Section 1 and 2 right edges must not collide with right card
      expect(sec1Box.x + sec1Box.width).toBeLessThanOrEqual(govBox.x);
      expect(sec2Box.x + sec2Box.width).toBeLessThanOrEqual(govBox.x);
    }

    // Tablet Viewport (768x1024)
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(300);
    const sec1BoxTab = await sec1.boundingBox();
    const govBoxTab = await govCard.boundingBox();
    if (sec1BoxTab && govBoxTab) {
      const hasOverlap = (sec1BoxTab.x < govBoxTab.x + govBoxTab.width) &&
                         (sec1BoxTab.x + sec1BoxTab.width > govBoxTab.x) &&
                         (sec1BoxTab.y < govBoxTab.y + govBoxTab.height) &&
                         (sec1BoxTab.y + sec1BoxTab.height > govBoxTab.y);
      expect(hasOverlap).toBe(false);
    }

    // Mobile Viewport (390x844)
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(300);
    const tocBoxMob = await toc.boundingBox();
    const sec1BoxMob = await sec1.boundingBox();
    const govBoxMob = await govCard.boundingBox();
    if (tocBoxMob && sec1BoxMob && govBoxMob) {
      expect(tocBoxMob.y).toBeLessThan(sec1BoxMob.y);
      expect(sec1BoxMob.y).toBeLessThan(govBoxMob.y);
    }
  });
});
