import { test, expect } from '@playwright/test';

test.describe('GramSetu CMS Administrative Workflow End-to-End Suite', () => {
  test('should display CMS login gate when unauthenticated', async ({ page }) => {
    // Intercept auth session check returning unauthenticated
    await page.route('**/api/auth/me/', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ authenticated: false, detail: 'Authentication required' }),
      });
    });

    await page.goto('/cms');

    // Verify login form elements
    await expect(page.locator('#admin-email')).toBeVisible();
    await expect(page.locator('#admin-password')).toBeVisible();
    await expect(page.getByRole('button', { name: /प्रवेश करा|Sign In/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /ग्रामसेतू प्रशासकीय नियंत्रण कक्ष/i })).toBeVisible();
  });

  test('should execute complete authentication, MFA verification, and dashboard loading', async ({ page }) => {
    let authState = 'unauthenticated';

    await page.route('**/api/auth/csrf/', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ csrfToken: 'synthetic-test-csrf-token' }),
      });
    });

    await page.route('**/api/auth/me/', async (route) => {
      if (authState === 'authenticated') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            authenticated: true,
            user: {
              id: '01a152dc-super-admin-uuid',
              email: 'superadmin@gramsetu.gov.in',
              full_name: 'Panchayat Super Administrator',
              role: 'super_admin',
              role_display: 'Super Administrator',
              is_super_admin: true,
              is_operator: false,
            },
            session: {
              expires_in_seconds: 1800,
              mfa_verified: true,
            },
            csrfToken: 'synthetic-test-csrf-token',
          }),
        });
      } else {
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({ authenticated: false }),
        });
      }
    });

    await page.route('**/api/auth/login/', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          mfa_required: true,
          email_masked: 's***@gramsetu.gov.in',
          message: 'MFA verification code sent.',
          expires_in_seconds: 300,
        }),
      });
    });

    await page.route('**/api/auth/mfa/verify/', async (route) => {
      authState = 'authenticated';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          user: {
            id: '01a152dc-super-admin-uuid',
            email: 'superadmin@gramsetu.gov.in',
            full_name: 'Panchayat Super Administrator',
            role: 'super_admin',
            role_display: 'Super Administrator',
            is_super_admin: true,
            is_operator: false,
          },
        }),
      });
    });

    await page.route('**/api/cms/dashboard/', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          overview: {
            pending_review_count: 2,
            drafts_count: 5,
            published_count: 10,
          },
          domains: {
            pages: { pending: 0, drafts: 1, published: 2 },
            notices: { pending: 1, drafts: 2, published: 3 },
            documents: { pending: 1, drafts: 0, published: 2 },
            events: { pending: 0, drafts: 1, published: 1 },
            schemes: { pending: 0, drafts: 1, published: 1 },
            gallery: { pending: 0, drafts: 0, published: 1 },
          },
          recent_events: [],
        }),
      });
    });

    await page.goto('/cms');

    // Step 1: Fill Credentials
    await page.locator('#admin-email').fill('superadmin@gramsetu.gov.in');
    await page.locator('#admin-password').fill('TestPass@12345');
    await page.getByRole('button', { name: /प्रवेश करा|Sign In/i }).click();

    // Step 2: Verify MFA Challenge
    await expect(page.locator('#otp-code')).toBeVisible();
    await expect(page.getByText(/बहु-घटक प्रमाणीकरण कोड पाठवला/i)).toBeVisible();

    // Step 3: Fill OTP
    await page.locator('#otp-code').fill('123456');
    await page.getByRole('button', { name: /कोड प्रमाणित करा|Verify/i }).click();

    // Step 4: Verify Dashboard Loads
    await expect(page.getByRole('heading', { name: /प्रशासकीय नियंत्रण कक्ष/i })).toBeVisible();
    await expect(page.locator('header').getByText('SUPER ADMINISTRATOR', { exact: true })).toBeVisible();
  });

  test('should display unified review queue and enforce governance rules in CMS', async ({ page }) => {
    // Intercept authenticated session
    await page.route('**/api/auth/me/', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          user: {
            id: 'super-admin-id',
            email: 'admin@gramsetu.gov.in',
            full_name: 'Super Admin',
            role: 'super_admin',
            role_display: 'Super Administrator',
            is_super_admin: true,
            is_operator: false,
          },
          session: {
            expires_in_seconds: 1800,
            mfa_verified: true,
          },
        }),
      });
    });

    await page.route('**/api/cms/pending/', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          count: 2,
          results: [
            {
              entity_type: 'notice',
              entity_id: 'notice-123',
              translation_id: 'trans-123',
              revision_id: 'rev-123',
              title: 'तातडीची पाणीपुरवठा दुरुस्ती सूचना',
              language_code: 'mr',
              version_number: 1,
              author_id: 'operator-1',
              author_name: 'Panchayat Operator',
              submitted_at: new Date().toISOString(),
              summary: 'पाणीपुरवठा पाईपलाईन दुरुस्ती कामाबाबत',
            },
            {
              entity_type: 'document',
              entity_id: 'doc-456',
              translation_id: 'trans-456',
              version_id: 'ver-456',
              title: 'वार्षिक जमा-खर्च अंदाजपत्रक २०२६-२७',
              language_code: 'mr',
              version_number: 1,
              author_id: 'super-admin-id',
              author_name: 'Super Admin',
              submitted_at: new Date().toISOString(),
              summary: 'File: budget_2026.pdf (1048576 bytes)',
            },
          ],
        }),
      });
    });

    await page.goto('/cms/governance');

    // Verify Review Queue items
    await expect(page.getByText(/तातडीची पाणीपुरवठा दुरुस्ती सूचना/i)).toBeVisible();
    await expect(page.getByText(/वार्षिक जमा-खर्च अंदाजपत्रक/i)).toBeVisible();

    // Verify Reject modal and minimum 10-char reason validation
    const rejectBtns = page.getByRole('button', { name: /नाकारा|Reject/i });
    await expect(rejectBtns.first()).toBeVisible();

    await rejectBtns.first().click();
    await expect(page.getByRole('heading', { name: /सबमिशन नाकारा|Reject/i })).toBeVisible();

    // Fill short reason (< 10 chars)
    const reasonInput = page.locator('textarea');
    await reasonInput.fill('Short');
    const confirmRejectBtn = page.getByRole('button', { name: /होय, नाकारा|Confirm/i });
    await confirmRejectBtn.click();
    await expect(page.getByText('नकाराचे कारण किमान १० अक्षरांचे असणे बंधनकारक आहे')).toBeVisible();
  });

  test('should handle logout and clear session state', async ({ page }) => {
    let authenticated = true;

    await page.route('**/api/auth/me/', async (route) => {
      if (authenticated) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            authenticated: true,
            user: {
              email: 'admin@gramsetu.gov.in',
              role: 'super_admin',
              role_display: 'Super Administrator',
              is_super_admin: true,
              is_operator: false,
            },
            session: {
              expires_in_seconds: 1800,
              mfa_verified: true,
            },
          }),
        });
      } else {
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({ authenticated: false }),
        });
      }
    });

    await page.route('**/api/auth/logout/', async (route) => {
      authenticated = false;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, message: 'Logged out' }),
      });
    });

    await page.route('**/api/cms/dashboard/', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          overview: { pending_review_count: 0, drafts_count: 0, published_count: 0 },
          domains: {
            pages: { pending: 0, drafts: 0, published: 0 },
            notices: { pending: 0, drafts: 0, published: 0 },
            documents: { pending: 0, drafts: 0, published: 0 },
            events: { pending: 0, drafts: 0, published: 0 },
            schemes: { pending: 0, drafts: 0, published: 0 },
            gallery: { pending: 0, drafts: 0, published: 0 },
          },
          recent_events: [],
        }),
      });
    });

    await page.goto('/cms');
    await expect(page.getByRole('button', { name: /लॉग आऊट|Logout/i })).toBeVisible();

    // Click logout
    await page.getByRole('button', { name: /लॉग आऊट|Logout/i }).click();

    // Verify redirected back to login gate
    await expect(page.locator('#admin-email')).toBeVisible();
  });
});
