import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import path from 'path';

function getOperatorTestPassword(): string {
  if (process.env.DEV_OPERATOR_PASSWORD) return process.env.DEV_OPERATOR_PASSWORD;
  if (process.env.TEST_CMS_PASSWORD) return process.env.TEST_CMS_PASSWORD;
  const rootDir = path.resolve(__dirname, '../../..');
  const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
  const defaultPass = 'DevOperatorTest2026!';
  const cmd = `"${pythonExe}" manage.py shell -c "from apps.identity.models import User; u = User.objects.get(email='local.operator@gramsetu.gov.in'); p = '${defaultPass}'; (None if u.check_password(p) else (u.set_password(p), u.save())); print(p)"`;
  const out = execSync(cmd, { cwd: rootDir, encoding: 'utf-8' });
  const lines = out.trim().split(/\r?\n/);
  const pass = lines[lines.length - 1].trim();
  process.env.TEST_CMS_PASSWORD = pass;
  return pass;
}

function getOperatorEmailOtp(): string {
  const rootDir = path.resolve(__dirname, '../../..');
  const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
  const cmd = `"${pythonExe}" manage.py shell -c "from apps.identity.models import User; from apps.identity.services import get_or_create_email_device; u = User.objects.get(email='local.operator@gramsetu.gov.in'); print(get_or_create_email_device(u).token)"`;
  const out = execSync(cmd, { cwd: rootDir, encoding: 'utf-8' });
  const lines = out.trim().split(/\r?\n/);
  return lines[lines.length - 1].trim();
}

function getAdminTestPassword(): string {
  if (process.env.DEV_ADMIN_PASSWORD) return process.env.DEV_ADMIN_PASSWORD;
  if (process.env.TEST_ADMIN_PASSWORD) return process.env.TEST_ADMIN_PASSWORD;
  const rootDir = path.resolve(__dirname, '../../..');
  const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
  const defaultPass = 'GramSetu@Test2026';
  const cmd = `"${pythonExe}" manage.py shell -c "from apps.identity.models import User; u = User.objects.get(email='local.admin@gramsetu.gov.in'); p = '${defaultPass}'; (None if u.check_password(p) else (u.set_password(p), u.save())); print(p)"`;
  const out = execSync(cmd, { cwd: rootDir, encoding: 'utf-8' });
  const lines = out.trim().split(/\r?\n/);
  const pass = lines[lines.length - 1].trim();
  process.env.TEST_ADMIN_PASSWORD = pass;
  return pass;
}

function getAdminEmailOtp(): string {
  const rootDir = path.resolve(__dirname, '../../..');
  const pythonExe = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
  const cmd = `"${pythonExe}" manage.py shell -c "from apps.identity.models import User; from apps.identity.services import get_or_create_email_device; u = User.objects.get(email='local.admin@gramsetu.gov.in'); print(get_or_create_email_device(u).token)"`;
  const out = execSync(cmd, { cwd: rootDir, encoding: 'utf-8' });
  const lines = out.trim().split(/\r?\n/);
  return lines[lines.length - 1].trim();
}

async function loginAsOperator(page: any) {
  const operatorPass = getOperatorTestPassword();
  await page.goto('/cms');
  await page.locator('#admin-email').fill('local.operator@gramsetu.gov.in');
  await page.locator('#admin-password').fill(operatorPass);
  await page.locator('button[type="submit"]').click();

  await expect(page.locator('#otp-code')).toBeVisible({ timeout: 10000 });
  const otp = getOperatorEmailOtp();
  await page.locator('#otp-code').fill(otp);
  await page.locator('button[type="submit"]').click();

  await expect(page.getByText('OPERATOR', { exact: true })).toBeVisible({ timeout: 10000 });
}

async function loginAsAdmin(page: any) {
  const adminPass = getAdminTestPassword();
  await page.goto('/cms');
  await page.locator('#admin-email').fill('local.admin@gramsetu.gov.in');
  await page.locator('#admin-password').fill(adminPass);
  await page.locator('button[type="submit"]').click();

  await expect(page.locator('#otp-code')).toBeVisible({ timeout: 10000 });
  const adminOtp = getAdminEmailOtp();
  await page.locator('#otp-code').fill(adminOtp);
  await page.locator('button[type="submit"]').click();

  await expect(page.getByText('SUPER ADMINISTRATOR', { exact: true })).toBeVisible({ timeout: 10000 });
}

test.describe('Full-Stack CMS Governance Repair & Defect Resolution Suite', () => {
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(60000);

  const uniqueId = Date.now().toString().slice(-4);
  const testNoticeTitle = `प्रशासकीय वॉटर शेड सूचना ${uniqueId}`;
  const editedNoticeTitle = `सुधारित प्रशासकीय वॉटर शेड सूचना ${uniqueId}`;
  const testEventTitle = `विशेष ग्रामसभा बैठक ${uniqueId}`;

  test('Workflow Part 1: Operator Draft Creation, PUT Editing, Submission, and Anti-Self-Approval Enforcement', async ({ page }) => {
    // 1. Operator Login
    await loginAsOperator(page);

    // 2. Navigate to /cms/notices
    await page.goto('/cms/notices');
    await expect(page.locator('h1')).toBeVisible();

    // 3. Open Create Notice modal and create draft
    await page.getByRole('button', { name: /नवीन सूचना तयार करा|New Notice/i }).click();
    await page.locator('input[placeholder*="गाव नमुना ८ अ तपासणी"]').fill(testNoticeTitle);
    await page.locator('input[placeholder*="GP/ADM/2026/042"]').fill(`GP/NOT/${uniqueId}`);
    await page.locator('textarea[placeholder*="नागरिकांसाठी संक्षिप्त सारांश"]').fill('जलसंधारण व वॉटरशेड कामांची प्राथमिक सूचना.');
    await page.locator('textarea[placeholder*="संपूर्ण सूचनेचा मजकूर"]').fill('सर्व ग्रामस्थांना कळविण्यात येते की गावातील पाझर तलाव व शेततळे कामांची पाहणी होणार आहे.');
    await page.getByRole('button', { name: /मसुदा तयार करा|मसुदा जतन करा|Save Draft/i }).click();

    // Verify draft appears in list
    await expect(page.getByText(testNoticeTitle)).toBeVisible({ timeout: 8000 });

    // 4. Test Draft Editing (Click "Edit Draft")
    const noticeCard = page.locator('.bg-white', { hasText: testNoticeTitle });
    await noticeCard.getByRole('button', { name: /मसुदा संपादित करा|Edit Draft/i }).click();

    // Modal opens prefilled
    const editTitleInput = page.locator('form input[type="text"]').first();
    await expect(editTitleInput).toHaveValue(testNoticeTitle);

    // Update title and save
    await editTitleInput.fill(editedNoticeTitle);
    await page.getByRole('button', { name: /बदल जतन करा|मसुदा जतन करा|Save Changes|Save Draft/i }).click();

    // Verify updated title is displayed in list
    await expect(page.getByText(editedNoticeTitle)).toBeVisible({ timeout: 8000 });

    // 5. Submit notice for review
    const updatedCard = page.locator('.bg-white', { hasText: editedNoticeTitle });
    await updatedCard.getByRole('button', { name: /मंजुरीसाठी सादर करा|सादर करा/i }).first().click();

    // Verify badge updates
    await expect(page.getByText(/पुनरावलोकन रांगेत पाठवली|submitted/i)).toBeVisible({ timeout: 8000 });

    // 6. Navigate directly to governance within operator session
    await page.goto('/cms/governance');
    await expect(page.locator('h1')).toContainText('प्रकाशन व मंजुरी नियंत्रण');

    // Find the item authored by Operator
    const submissionItem = page.locator('.bg-white', { hasText: editedNoticeTitle });
    await expect(submissionItem).toBeVisible({ timeout: 10000 });

    // Verify Proactive Anti-Self-Approval alert badge is present for author
    await expect(submissionItem.getByText(/स्वतः सादर केलेला मसुदा|Anti-Self-Approval/i)).toBeVisible();

    // Verify the Approve button is strictly disabled for the author
    const approveBtn = submissionItem.getByRole('button', { name: /मंजूर करा|Approve/i });
    await expect(approveBtn).toBeDisabled();

    // Logout operator cleanly
    await page.getByRole('button', { name: /लॉग आऊट|Logout/i }).click();
    await expect(page.locator('#admin-email')).toBeVisible({ timeout: 10000 });
  });

  test('Workflow Part 2: Super Admin Review, Approval, Publication, and Public Portal Verification', async ({ page }) => {
    // 1. Super Administrator Login
    await loginAsAdmin(page);

    // 2. Navigate to /cms/governance
    await page.goto('/cms/governance');
    await expect(page.locator('h1')).toBeVisible();

    // Locate the operator's submission
    const submissionItem = page.locator('.bg-white', { hasText: editedNoticeTitle });
    await expect(submissionItem).toBeVisible({ timeout: 10000 });

    // Super Admin is NOT the author, so Approve button is active
    const approveBtn = submissionItem.getByRole('button', { name: /मंजूर करा|Approve/i });
    await expect(approveBtn).toBeEnabled();

    // 3. Approve submission
    await approveBtn.click();

    // Modal dialog opens
    await expect(page.getByText(/मसुदा मंजुरी पुष्टी|Formal Approval/i)).toBeVisible();
    await page.locator('textarea[placeholder*="मसुद्याची तपासणी केली असून"]').fill('सर्व कागदपत्रे व विषयपत्रिका योग्य असून सूचना अधिकृतपणे मंजूर करण्यात येत आहे.');
    await page.locator('.fixed').getByRole('button', { name: /होय, मंजूर करा|मंजूर करा|Approve/i }).click();

    // Expect success message
    await expect(page.getByText('मसुदा यशस्वीरित्या मंजूर करण्यात आला आहे')).toBeVisible({ timeout: 10000 });

    // 4. Verify item moves to "Approved (Ready to Publish)" tab
    const approvedTab = page.getByRole('button', { name: /मंजूर.*प्रकाशन प्रतीक्षेत|Approved/i });
    await approvedTab.click();

    const approvedItem = page.locator('.bg-white', { hasText: editedNoticeTitle });
    await expect(approvedItem).toBeVisible({ timeout: 8000 });
    await expect(approvedItem.getByText('approved', { exact: true })).toBeVisible();

    // 5. Test "Publish" Action
    const publishBtn = approvedItem.getByRole('button', { name: /प्रसिद्ध करा|Publish/i });
    await expect(publishBtn).toBeVisible();
    await publishBtn.click();

    // Publish Modal opens
    await expect(page.getByRole('heading', { name: /सार्वजनिक.*थेट प्रसिद्ध|Public Disclosure/i })).toBeVisible();
    await page.locator('textarea[placeholder*="नागरिकांच्या माहितीसाठी संकेतस्थळावर"]').fill('ग्रामपंचायत ठराव क्र. १२ अनुसार सूचनेचे सार्वजनिक पोर्टलवर अधिकृत थेट प्रकाशन करण्यात येत आहे.');
    await page.locator('.fixed').getByRole('button', { name: /होय, प्रकाशित करा|प्रसिद्ध करा|Publish/i }).click();

    // Expect publication success message
    await expect(page.getByText('सामग्री सार्वजनिक पोर्टलवर थेट प्रसिद्ध झाली आहे')).toBeVisible({ timeout: 10000 });

    // 6. Navigate to public citizen portal /notices to verify live public visibility
    await page.goto('/notices');
    await expect(page.locator('h1').first()).toBeVisible();
    await expect(page.getByText(editedNoticeTitle)).toBeVisible({ timeout: 10000 });
  });

  test('Workflow Part 3: Anti-Self-Approval Enforced on Super Administrator & Trilingual Theme Switching', async ({ page }) => {
    // 1. Super Admin Login
    await loginAsAdmin(page);

    // 2. Super Admin creates a new event draft in /cms/events
    await page.goto('/cms/events');
    await expect(page.locator('h1')).toContainText('ग्रामसभा व बैठका व्यवस्थापन');

    await page.getByRole('button', { name: /नवीन बैठक नियोजित करा|Schedule Meeting/i }).click();
    await page.locator('input[placeholder*="विशेष महिला ग्रामसभा"]').fill(testEventTitle);

    const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 16);
    const tomorrowEnd = new Date(Date.now() + 90000000).toISOString().slice(0, 16);
    await page.locator('input[type="datetime-local"]').first().fill(tomorrow);
    await page.locator('input[type="datetime-local"]').nth(1).fill(tomorrowEnd);

    await page.locator('textarea[placeholder*="मागील सभेचे इतिवृत्त"]').fill('१. पीक विमा आढावा.\n२. शेततळे वाटप.');
    await page.getByRole('button', { name: /मसुदा जतन करा/i }).click();

    await expect(page.getByText(testEventTitle)).toBeVisible({ timeout: 8000 });

    // Submit event for review
    const eventCard = page.locator('.bg-white', { hasText: testEventTitle });
    await eventCard.getByRole('button', { name: /मंजुरीसाठी सादर करा/i }).click();

    // 3. Navigate to /cms/governance
    await page.goto('/cms/governance');
    await expect(page.locator('h1')).toBeVisible();

    // Find the event authored by Super Admin
    const adminEventItem = page.locator('.bg-white', { hasText: testEventTitle });
    await expect(adminEventItem).toBeVisible({ timeout: 8000 });

    // Under Super Admin Publishing Authority, Super Admin is NOT blocked from self-approval
    const approveBtn = adminEventItem.getByRole('button', { name: /मंजूर करा|Approve/i });
    await expect(approveBtn).toBeEnabled();

    // 4. Language Switching without reload: Switch to English
    await page.locator('#cms-lang-select').selectOption('en');
    await expect(page.locator('h1')).toContainText('Dual-Control Governance Queue');
    await expect(page.getByRole('button', { name: /Pending Review/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Approved/i })).toBeVisible();

    // 5. Switch to Hindi
    await page.locator('#cms-lang-select').selectOption('hi');
    await expect(page.locator('h1')).toContainText('प्रकाशन एवं अनुमोदन नियंत्रण');
    await expect(page.getByRole('button', { name: /समीक्षा हेतु लंबित/i })).toBeVisible();

    // 6. Switch back to Marathi
    await page.locator('#cms-lang-select').selectOption('mr');
    await expect(page.locator('h1')).toContainText('प्रकाशन व मंजुरी नियंत्रण');
  });
});
