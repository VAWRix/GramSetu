import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import path from 'path';

function runPython(code: string): string {
  const rootDir = path.resolve(__dirname, '../../..');
  const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
  const b64 = Buffer.from(code, 'utf-8').toString('base64');
  const cmd = `"${pythonExe}" manage.py shell -c "import base64; exec(base64.b64decode('${b64}').decode('utf-8'))"`;
  const out = execSync(cmd, { cwd: rootDir, encoding: 'utf-8' });
  const lines = out.trim().split(/\r?\n/);
  return lines[lines.length - 1].trim();
}

function getOperatorPassword(): string {
  if (process.env.DEV_OPERATOR_PASSWORD) return process.env.DEV_OPERATOR_PASSWORD;
  return 'DevOperatorTest2026!';
}

function getOperatorEmailOtp(): string {
  const code = `
from apps.identity.models import User
from apps.identity.services import get_or_create_email_device
u = User.objects.get(email='local.operator@gramsetu.gov.in')
print(get_or_create_email_device(u).token)
`;
  return runPython(code);
}

function approveAndPublishEventViaBackend(title: string): string {
  const code = `
from apps.events.models import PanchayatEvent, EventTranslation
from apps.identity.models import User
from apps.governance.services import approve_and_publish_event

tr = EventTranslation.objects.filter(title='${title}').first()
if not tr:
    print('NOT_FOUND')
else:
    admin = User.objects.get(email='local.admin@gramsetu.gov.in')
    ev, rec, pe = approve_and_publish_event(
        event_id=tr.event_id,
        approver=admin,
        notes='Formal approval and publication verification',
        allow_self_approval=True
    )
    print(f'PUBLISHED:{ev.id}')
`;
  return runPython(code);
}

function cleanupTestEvent(title: string): void {
  const code = `
from django.db import transaction
from apps.events.models import PanchayatEvent, STATUS_DRAFT

with transaction.atomic():
    events = list(PanchayatEvent.objects.filter(translations__title='${title}').distinct())
    for ev in events:
        ev.status = STATUS_DRAFT
        ev.is_published = False
        ev.retention_hold = False
        ev.save()
        ev.delete()
print('CLEANED')
`;
  runPython(code);
}

test.describe('Panchayat Meeting Scheduling & Publishing E2E Workflow', () => {
  const uniqueId = Date.now().toString().slice(-4);
  const testMeetingTitle = `विशेष ग्रामसभा बैठक ${uniqueId}`;

  test.afterAll(async () => {
    // Preserve clean development database state by removing verified test content
    try {
      cleanupTestEvent(testMeetingTitle);
    } catch (e) {
      console.warn('Cleanup warning:', e);
    }
  });

  test('Complete Meeting Lifecycle: Operator Draft Creation, Validation, Submission, Publishing, and Public Verification', async ({ page }) => {
    // 1. Operator Login
    await page.goto('/cms');
    await page.locator('#admin-email').fill('local.operator@gramsetu.gov.in');
    await page.locator('#admin-password').fill(getOperatorPassword());
    await page.locator('button[type="submit"]').click();

    // 2. Submit MFA OTP
    await expect(page.locator('#otp-code')).toBeVisible({ timeout: 10000 });
    const otp = getOperatorEmailOtp();
    await page.locator('#otp-code').fill(otp);
    await page.locator('button[type="submit"]').click();

    // 3. Confirm Operator Dashboard
    await expect(page.getByText('OPERATOR', { exact: true })).toBeVisible({ timeout: 10000 });

    // 4. Navigate to CMS Events & Meetings
    await page.goto('/cms/events');
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });

    // 5. Open Create Meeting Modal
    const createBtn = page.getByRole('button', { name: /नियोजित करा|Schedule Meeting|नवीन बैठक/i });
    await expect(createBtn).toBeVisible({ timeout: 10000 });
    await createBtn.click();

    // 6. Test Client/Server Validation Guard (End Date < Start Date)
    await page.locator('input[placeholder*="विशेष महिला ग्रामसभा"]').fill(testMeetingTitle);
    // Invalid datetime inputs
    await page.locator('input[type="datetime-local"]').first().fill('2026-11-10T14:00');
    await page.locator('input[type="datetime-local"]').nth(1).fill('2026-11-10T10:00'); // End is BEFORE start!
    
    // Submit invalid form
    const saveBtn = page.getByRole('button', { name: /मसुदा जतन करा|Save Draft/i });
    await saveBtn.click();

    // Confirm validation error message appears and NO HTTP 500 occurred
    const errorAlert = page.locator('div[role="alert"], .text-red-700, .bg-red-50, .text-destructive');
    await expect(errorAlert.first()).toBeVisible({ timeout: 5000 });

    // 7. Fix Date to Valid Range (End Date > Start Date)
    await page.locator('input[type="datetime-local"]').nth(1).fill('2026-11-10T16:00');
    await page.locator('textarea[placeholder*="मागील सभेचे इतिवृत्त"]').fill('१. गावविकास आराखडा चर्चा.\n२. पाणीपुरवठा व स्वच्छता नियोजन.');

    // Save Valid Draft
    await saveBtn.click();

    // Modal closes and draft appears in the events list
    await expect(page.getByText(testMeetingTitle).first()).toBeVisible({ timeout: 10000 });

    // 8. Submit Meeting Draft for Review / Approval
    const card = page.locator('div.bg-white.rounded-lg', { hasText: testMeetingTitle }).first();
    const submitReviewBtn = card.getByRole('button', { name: /मंजुरीसाठी सादर करा|Submit for Review/i });
    await expect(submitReviewBtn).toBeVisible({ timeout: 10000 });
    await submitReviewBtn.click();

    // Verify status badge updates to Pending Approval
    await expect(card.getByText(/pending_approval|पुनरावलोकन प्रलंबित/i).first()).toBeVisible({ timeout: 10000 });

    // 9. Approve & Publish Meeting via Super Administrator
    const publishRes = approveAndPublishEventViaBackend(testMeetingTitle);
    expect(publishRes).toContain('PUBLISHED');

    // Reload CMS events page and verify Published badge
    await page.reload();
    const publishedCard = page.locator('div.bg-white.rounded-lg', { hasText: testMeetingTitle }).first();
    await expect(publishedCard.getByText(/published|प्रसिद्ध/i).first()).toBeVisible({ timeout: 10000 });

    // 10. Public Portal Verification
    await page.goto('/events');
    await expect(page.getByText(testMeetingTitle).first()).toBeVisible({ timeout: 10000 });
  });
});
