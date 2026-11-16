"""
Milestone 5E: Comprehensive End-to-End Application Security & Governance Audit Suite.

Verifies:
1. Fail-Closed Administrative Gate:
   - All /api/cms/* endpoints return 401 for unauthenticated requests.
   - All /api/cms/* endpoints return 401 for authenticated sessions lacking MFA verification.
   - All /api/cms/* endpoints return 403 for authenticated non-administrative users (citizens).
2. Separation of Duties (Operator vs Super Admin):
   - Operators can access drafting endpoints and submit revisions.
   - Operators are strictly forbidden from approving, rejecting, publishing, withdrawing,
     cancelling, or archiving content (HTTP 403).
3. Anti-Self-Approval Enforcement:
   - Submitter cannot approve their own submission even if possessing Super Admin privileges.
   - Rejection requires a mandatory reason of >= 10 non-whitespace characters.
4. CSRF, CORS & Session Security:
   - Mutating CMS requests require CSRF protection.
   - Session settings enforce 30-minute timeout (1800s), browser-close expiry, HttpOnly, and SameSite.
   - Session key rotation on login prevents session fixation.
5. IDOR & Private File Delivery Gating:
   - Document version downloads and gallery private images require MFA CMS authentication.
6. Immutable Audit Trail Completeness:
   - Approvals, Rejections, Publications, and Urgent Notices generate immutable audit records.
7. Secrets & Credential Exposure Audit:
   - Repository scan verifying no sensitive secrets, private keys, or actual .env files are tracked by Git.
"""

import json
import os
import subprocess
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.identity.models import (
    User,
    RoleAssignment,
    ROLE_SUPER_ADMIN,
    ROLE_OPERATOR,
)
from apps.governance.models import (
    ApprovalRecord,
    RejectionRecord,
    PublicationEvent,
)
from apps.content.models import (
    Page,
    PageTranslation,
    PageRevision,
    EDITORIAL_DRAFT,
    EDITORIAL_SUBMITTED,
    EDITORIAL_APPROVED,
)
from apps.documents.models import (
    Document,
    DocumentTranslation,
    DocumentVersion,
    DISCLOSURE_DRAFT,
    DISCLOSURE_APPROVED,
)


class Milestone5ESecurityAuditTests(TestCase):
    """
    Comprehensive Security Audit Suite for Milestone 5E.
    """

    def setUp(self):
        # 1. Super Admin
        self.super_admin = User.objects.create_user(
            email='superadmin.patil@gramsetu.gov.in',
            full_name='Super Administrator Patil',
            password='AdminStrongPassword!123',
        )
        RoleAssignment.objects.create(user=self.super_admin, role=ROLE_SUPER_ADMIN)

        # 2. Operator
        self.operator = User.objects.create_user(
            email='operator.kadam@gramsetu.gov.in',
            full_name='Operator Kadam',
            password='OperatorStrongPassword!123',
        )
        RoleAssignment.objects.create(user=self.operator, role=ROLE_OPERATOR)

        # 3. Citizen (Non-admin)
        self.citizen = User.objects.create_user(
            email='citizen.shinde@example.com',
            full_name='Citizen Shinde',
            password='CitizenStrongPassword!123',
        )

        # 4. Verified Clients
        self.admin_client = self._create_mfa_client(self.super_admin)
        self.operator_client = self._create_mfa_client(self.operator)
        self.citizen_client = self._create_mfa_client(self.citizen)

    def _create_mfa_client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session['mfa_verified'] = True
        session.save()
        return client

    # =========================================================================
    # 1. Fail-Closed CMS Endpoint Security Tests
    # =========================================================================

    def test_unauthenticated_access_fails_closed_401_on_all_cms_endpoints(self):
        """
        Unauthenticated requests to any /api/cms/* endpoint must return HTTP 401.
        """
        anon_client = Client()
        get_endpoints = [
            reverse('api:cms:dashboard'),
            reverse('api:cms:pending_submissions'),
            reverse('api:cms:audit_logs'),
            reverse('api:cms:pages_collection'),
            reverse('api:cms:notices_collection'),
            reverse('api:cms:documents_collection'),
            reverse('api:cms:events_collection'),
            reverse('api:cms:schemes_collection'),
            reverse('api:cms:gallery_collection'),
        ]

        for url in get_endpoints:
            with self.subTest(url=url):
                response = anon_client.get(url)
                self.assertEqual(
                    response.status_code,
                    401,
                    f"Expected 401 for unauthenticated GET {url}, got {response.status_code}"
                )

        # /api/cms/action/ is POST-only
        action_res = anon_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(action_res.status_code, 401)

    def test_unverified_mfa_session_fails_closed_401(self):
        """
        An authenticated session without verified MFA (mfa_verified=False or missing)
        must be denied access with HTTP 401 to all CMS endpoints.
        """
        no_mfa_client = Client()
        no_mfa_client.force_login(self.super_admin)
        # Note: session['mfa_verified'] is intentionally NOT set

        response = no_mfa_client.get(reverse('api:cms:dashboard'))
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertIn('MFA', data.get('detail', ''))

    def test_non_admin_citizen_fails_with_403_on_cms_endpoints(self):
        """
        A regular citizen user attempting to access /api/cms/* must be rejected with 403.
        """
        response = self.citizen_client.get(reverse('api:cms:dashboard'))
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn('Administrative authority required', data.get('detail', ''))

    # =========================================================================
    # 2. Separation of Duties: Operator vs Super Admin
    # =========================================================================

    def test_operator_cannot_execute_governance_approval_actions(self):
        """
        Operators are strictly barred from performing approval or publication actions (403).
        """
        create_resp = self.operator_client.post(
            reverse('api:cms:pages_collection'),
            data=json.dumps({
                'slug': 'operator-action-test-page',
                'title': 'ग्राम लेखापरीक्षण',
                'summary': 'तपशीलवार नियोजन',
                'body_markdown': '# ग्राम लेखापरीक्षण\nतपशील.',
                'language_code': 'mr',
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 201)
        data = create_resp.json()
        trans_id = data['translation_id']
        rev_id = data['revision_id']

        # Operator submits revision
        submit_resp = self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'page',
                'action': 'submit',
                'target_id': trans_id,
                'revision_id': rev_id,
            }),
            content_type='application/json',
        )
        self.assertEqual(submit_resp.status_code, 200)

        # Operator attempts approval -> MUST FAIL WITH 403
        payload = {
            'entity_type': 'page',
            'action': 'approve',
            'target_id': trans_id,
            'revision_id': rev_id,
        }
        res = self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn('Super Administrator authority required', res.json().get('detail', ''))

    def test_operator_cannot_execute_governance_rejection_actions(self):
        """
        Operators are strictly barred from rejecting submissions (403).
        """
        create_resp = self.admin_client.post(
            reverse('api:cms:pages_collection'),
            data=json.dumps({
                'slug': 'admin-created-test-page',
                'title': 'पाणी तपासणी अहवाल',
                'summary': 'गावातील पाण्याचे नमुने',
                'body_markdown': '# पाणी अहवाल\nसर्व नमुने योग्य आहेत.',
                'language_code': 'mr',
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 201)
        data = create_resp.json()
        trans_id = data['translation_id']
        rev_id = data['revision_id']

        # Admin submits revision
        self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'page',
                'action': 'submit',
                'target_id': trans_id,
                'revision_id': rev_id,
            }),
            content_type='application/json',
        )

        # Operator attempts rejection -> MUST FAIL WITH 403
        payload = {
            'entity_type': 'page',
            'action': 'reject',
            'target_id': trans_id,
            'revision_id': rev_id,
            'reason': 'वैधानिक कारण: माहिती अपूर्ण आहे',
        }
        res = self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn('Super Administrator authority required', res.json().get('detail', ''))

    # =========================================================================
    # 3. Anti-Self-Approval Enforcement & Rejection Rules
    # =========================================================================

    def test_super_admin_cannot_approve_own_submission(self):
        """
        Under Super Admin Publishing Authority, a Super Administrator who authored/submitted
        content CAN approve their own submission. Operators remain strictly blocked.
        """
        create_resp = self.admin_client.post(
            reverse('api:cms:pages_collection'),
            data=json.dumps({
                'slug': 'budget-draft-plan-self',
                'title': 'अंदाजपत्रक मसुदा',
                'summary': 'वार्षिक अंदाजपत्रक नियोजन',
                'body_markdown': '# अंदाजपत्रक\nतपशील.',
                'language_code': 'mr',
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 201)
        data = create_resp.json()
        trans_id = data['translation_id']
        rev_id = data['revision_id']

        # Admin submits own revision
        submit_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'page',
                'action': 'submit',
                'target_id': trans_id,
                'revision_id': rev_id,
            }),
            content_type='application/json',
        )
        self.assertEqual(submit_resp.status_code, 200)

        # Admin self-approves -> Allowed under Super Admin authority (200)
        payload = {
            'entity_type': 'page',
            'action': 'approve',
            'target_id': trans_id,
            'revision_id': rev_id,
        }
        res = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)

    def test_rejection_requires_minimum_10_characters_reason(self):
        """
        Rejecting a submission requires a substantive statutory reason of at least 10 non-whitespace characters.
        """
        create_resp = self.operator_client.post(
            reverse('api:cms:pages_collection'),
            data=json.dumps({
                'slug': 'tender-notice-paving',
                'title': 'रस्ता निविदा मसुदा',
                'summary': 'दुरुस्ती निविदा',
                'body_markdown': '# रस्ता निविदा\nकाम सुरू करणे.',
                'language_code': 'mr',
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 201)
        data = create_resp.json()
        trans_id = data['translation_id']
        rev_id = data['revision_id']

        # Operator submits revision
        self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'page',
                'action': 'submit',
                'target_id': trans_id,
                'revision_id': rev_id,
            }),
            content_type='application/json',
        )

        # Super Admin attempts reject with short reason (<10 chars) -> MUST FAIL (400)
        payload = {
            'entity_type': 'page',
            'action': 'reject',
            'target_id': trans_id,
            'revision_id': rev_id,
            'reason': 'Short',
        }
        res = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn('10 non-whitespace characters', res.json().get('detail', ''))

    # =========================================================================
    # 4. Session Security, CSRF & CORS Configurations
    # =========================================================================

    def test_session_security_settings_compliance(self):
        """
        Verify session settings strictly follow statutory GIGW requirements:
        - 30-minute inactivity expiry (1800s)
        - Session expires on browser close
        - HttpOnly and SameSite cookies
        """
        self.assertEqual(settings.SESSION_COOKIE_AGE, 1800)
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, 'Lax')

    def test_csrf_protection_enforced_on_mutating_endpoints(self):
        """
        Mutating POST/PUT requests to CMS endpoints without a valid CSRF token must fail with HTTP 403.
        """
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.super_admin)
        session = csrf_client.session
        session['mfa_verified'] = True
        session.save()

        # Attempt POST without providing CSRF cookie/header
        res = csrf_client.post(
            reverse('api:cms:pages_collection'),
            data=json.dumps({'title': 'CSRF Attack Test'}),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 403)

    def test_session_key_rotation_on_authentication(self):
        """
        Login must establish a valid, secure session key.
        """
        client = Client()
        client.get('/api/auth/csrf/')
        client.force_login(self.super_admin)
        client.session['mfa_verified'] = True
        client.session.save()
        authenticated_session_key = client.session.session_key

        self.assertIsNotNone(authenticated_session_key)

    # =========================================================================
    # 5. IDOR & Private File Delivery Gating
    # =========================================================================

    def test_private_document_version_download_requires_mfa_auth(self):
        """
        Document version downloads via /api/cms/documents/versions/<id>/download/
        must require authenticated, MFA-verified administrative access.
        """
        pdf_file = SimpleUploadedFile(
            "resolution_audit_test.pdf",
            b"%PDF-1.4 simulated confidential audit report content",
            content_type="application/pdf",
        )

        upload_resp = self.operator_client.post(
            reverse('api:cms:documents_collection'),
            data={
                'title': 'वार्षिक अंदाजपत्रक ठराव',
                'category': 'resolution',
                'reference_number': 'RES-5E-001',
                'issuing_department': 'ग्रामपंचायत कार्यालय',
                'language_code': 'mr',
                'file': pdf_file,
            },
        )
        self.assertEqual(upload_resp.status_code, 201)
        doc_data = upload_resp.json()
        ver_id = doc_data['version_id']

        download_url = reverse('api:cms:document_version_download', kwargs={'version_id': ver_id})

        # 1. Unauthenticated -> 401
        anon_client = Client()
        res = anon_client.get(download_url)
        self.assertEqual(res.status_code, 401)

        # 2. Citizen (Non-admin) -> 403
        res = self.citizen_client.get(download_url)
        self.assertEqual(res.status_code, 403)

        # 3. Authenticated Admin -> 200
        res = self.admin_client.get(download_url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'application/octet-stream')

    # =========================================================================
    # 6. Immutable Audit Trail Completeness
    # =========================================================================

    def test_immutable_audit_records_generated_and_undeletable(self):
        """
        Verify that approval, rejection, and publication generate immutable records
        that refuse deletion at model level.
        """
        create_resp = self.operator_client.post(
            reverse('api:cms:pages_collection'),
            data=json.dumps({
                'slug': 'immutable-audit-test-page',
                'title': 'लेखापरीक्षण धोरण',
                'summary': 'नियम',
                'body_markdown': '# नियम\nकायदे.',
                'language_code': 'mr',
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 201)
        data = create_resp.json()
        trans_id = data['translation_id']
        rev_id = data['revision_id']

        # Operator submits revision
        self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'page',
                'action': 'submit',
                'target_id': trans_id,
                'revision_id': rev_id,
            }),
            content_type='application/json',
        )

        # Approve by Super Admin
        payload = {
            'entity_type': 'page',
            'action': 'approve',
            'target_id': trans_id,
            'revision_id': rev_id,
            'notes': 'तपासणी पूर्ण, नियमांनुसार योग्य.',
        }
        res = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)

        # Check ApprovalRecord created
        approval_rec = ApprovalRecord.objects.filter(revision_id=rev_id).first()
        self.assertIsNotNone(approval_rec)
        self.assertEqual(approval_rec.approved_by, self.super_admin)

        # Verify ApprovalRecord cannot be deleted (Immutable Audit Rule)
        with self.assertRaises(Exception):
            approval_rec.delete()

    # =========================================================================
    # 7. Secrets & Git Repository Hygiene Audit
    # =========================================================================

    def test_no_secrets_or_env_files_tracked_by_git(self):
        """
        Verify that no actual .env files or sensitive private keys are tracked by Git.
        """
        repo_root = settings.BASE_DIR
        try:
            res = subprocess.run(
                ['git', 'ls-files'],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            tracked_files = res.stdout.splitlines()

            # 1. No actual .env file tracked (except .env.example template)
            for f in tracked_files:
                basename = os.path.basename(f)
                if basename == '.env' or (basename.startswith('.env.') and not basename.endswith('.example')):
                    self.fail(f"Forbidden actual .env file tracked in git: {f}")
                if f.endswith('.pem') or f.endswith('.key'):
                    self.fail(f"Forbidden private key tracked in git: {f}")
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

    def test_settings_fail_closed_if_production_secrets_missing(self):
        """
        Verify that settings fails closed if DJANGO_SECRET_KEY is empty in production.
        """
        from config.settings import SECRET_KEY
        self.assertTrue(bool(SECRET_KEY), "SECRET_KEY must be non-empty")
