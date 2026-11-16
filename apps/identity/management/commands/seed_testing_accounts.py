"""
Seed Testing Accounts Management Command for GramSetu.

Configures the authorized testing accounts for the CMS Staff Portal:
1. Super Admin:
   - Email: local.admin@gramsetu.gov.in
   - Role: SUPER_ADMIN (Gramsevak / Village Development Officer Ashok Ganpat Wale)
   - Password: GramSetu@Test2026
   - Full administrative and governance privileges.

2. Operator:
   - Email: local.operator@gramsetu.gov.in
   - Role: OPERATOR (Computer Operator / Sangnak Chalak)
   - Password: GramSetu@Test2026
   - Content drafting and submission privileges (no approval/publishing).

Features:
- Idempotent: safe to run multiple times without duplicating or corrupting records.
- Preserves existing historical audit logs and foreign keys (does not delete referenced records).
- Synchronizes the common password 'GramSetu@Test2026' securely using PBKDF2 SHA-256.
- Sets confirmed EmailDevice for MFA on both accounts.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from apps.identity.models import User, RoleAssignment, ROLE_SUPER_ADMIN, ROLE_OPERATOR
from apps.identity.services import get_or_create_email_device

COMMON_TEST_PASSWORD = 'GramSetu@Test2026'

TEST_ACCOUNTS = [
    {
        'email': 'local.admin@gramsetu.gov.in',
        'full_name': 'अशोक गणपत वाले (ASHOK GANPAT WALE)',
        'phone_number': '02431-223022',
        'role': ROLE_SUPER_ADMIN,
        'is_staff': True,
        'is_superuser': False,
    },
    {
        'email': 'local.operator@gramsetu.gov.in',
        'full_name': 'संगणक चालक / ऑपरेटर (Computer Operator)',
        'phone_number': '02431-223023',
        'role': ROLE_OPERATOR,
        'is_staff': False,
        'is_superuser': False,
    },
]

# Aliases that should also carry the testing password to preserve audit integrity
LEGACY_ALIASES = [
    {
        'email': 'gram.sevak@gramsetu.gov.in',
        'role': ROLE_SUPER_ADMIN,
        'full_name': 'अशोक गणपत वाले (ASHOK GANPAT WALE)',
    },
    {
        'email': 'operator@gramsetu.gov.in',
        'role': ROLE_OPERATOR,
        'full_name': 'संगणक चालक / ऑपरेटर (Computer Operator)',
    },
]


class Command(BaseCommand):
    help = "Seed or reset the GramSetu CMS testing accounts with password GramSetu@Test2026."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== GramSetu: Seeding Authorized Testing Accounts ==="))

        with transaction.atomic():
            # 1. Primary Testing Accounts
            for acc in TEST_ACCOUNTS:
                email = acc['email'].lower()

                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        'full_name': acc['full_name'],
                        'phone_number': acc['phone_number'],
                        'is_active': True,
                        'is_staff': acc['is_staff'],
                        'is_superuser': acc['is_superuser'],
                    },
                )

                user.full_name = acc['full_name']
                user.phone_number = acc['phone_number']
                user.is_active = True
                user.is_staff = acc['is_staff']
                user.is_superuser = acc['is_superuser']
                user.set_password(COMMON_TEST_PASSWORD)
                user.save()

                ra, _ = RoleAssignment.objects.get_or_create(
                    user=user,
                    defaults={'role': acc['role']},
                )
                if ra.role != acc['role']:
                    ra.role = acc['role']
                    ra.save()

                dev = get_or_create_email_device(user)
                dev.confirmed = True
                dev.save()

                action_str = "Created" if created else "Updated/Verified"
                self.stdout.write(self.style.SUCCESS(
                    f"[{action_str} Primary] {email} -> Role: {acc['role']} | Active: True | Password: {COMMON_TEST_PASSWORD}"
                ))

            # 2. Synchronize Legacy Aliases to prevent authentication friction
            for alias in LEGACY_ALIASES:
                user = User.objects.filter(email=alias['email']).first()
                if user:
                    user.set_password(COMMON_TEST_PASSWORD)
                    user.is_active = True
                    user.save()
                    ra, _ = RoleAssignment.objects.get_or_create(
                        user=user,
                        defaults={'role': alias['role']},
                    )
                    if ra.role != alias['role']:
                        ra.role = alias['role']
                        ra.save()
                    dev = get_or_create_email_device(user)
                    dev.confirmed = True
                    dev.save()
                    self.stdout.write(self.style.NOTICE(
                        f"[Synchronized Alias] {user.email} -> Role: {alias['role']} | Password: {COMMON_TEST_PASSWORD}"
                    ))

        # Final verification
        self.stdout.write(self.style.MIGRATE_HEADING("\nAuthorized Testing Accounts Ready for Testing:"))
        for acc in TEST_ACCOUNTS:
            u = User.objects.get(email=acc['email'])
            ra = getattr(u, 'role_assignment', None)
            role_code = ra.role if ra else 'NONE'
            self.stdout.write(
                f"  • Email:    {self.style.NOTICE(u.email)}\n"
                f"    Role:     {role_code}\n"
                f"    Password: {COMMON_TEST_PASSWORD}\n"
                f"    Holder:   {u.full_name}\n"
            )

        self.stdout.write(self.style.SUCCESS("[SUCCESS] Testing accounts successfully initialized and secured.\n"))
