"""
Development-only Authentication and Login Access Management Command for GramSetu.

Provides administrative account verification, role checking, password reset guidance,
and development-only single-use OTP retrieval for local testing.

STRICT SECURITY CONTROLS:
- Hard-locked to settings.DEBUG == True.
- Refuses execution under all circumstances when DEBUG is False.
- Does NOT bypass MFA; works with standard EmailDevice verification.
- Never prints OTP secrets, TOTP seeds, or password hashes.
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from apps.identity.models import User, ROLE_SUPER_ADMIN, ROLE_OPERATOR
from apps.identity.services import get_or_create_email_device
from apps.identity.permissions import is_super_admin, is_operator


class Command(BaseCommand):
    help = (
        "Development-only utility to list administrative accounts, verify roles, "
        "and generate/retrieve single-use login OTPs. Strictly forbidden in production (DEBUG=False)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--list',
            '-l',
            action='store_true',
            help="List all administrative accounts, statutory designations, and assigned roles.",
        )
        parser.add_argument(
            '--otp',
            '-o',
            type=str,
            nargs='?',
            const='local.admin@gramsetu.gov.in',
            metavar='ACCOUNT',
            help="Retrieve or generate a valid 6-digit MFA OTP for an account (by email or role: 'super_admin'/'operator').",
        )
        parser.add_argument(
            '--super-admin',
            '-sa',
            action='store_true',
            help="Retrieve the active login OTP for the Gramsevak (Super Admin) account.",
        )
        parser.add_argument(
            '--operator',
            '-op',
            action='store_true',
            help="Retrieve the active login OTP for the Computer Operator account.",
        )
        parser.add_argument(
            '--check',
            '-c',
            type=str,
            metavar='EMAIL',
            help="Verify that the given email account is active and has an approved administrative role.",
        )
        parser.add_argument(
            '--fresh',
            '-f',
            action='store_true',
            help="Force generation of a brand new OTP challenge even if an active unexpired code exists.",
        )

    def handle(self, *args, **options):
        # 1. HARD SECURITY GATE: Strictly refuse in production
        if not getattr(settings, 'DEBUG', False):
            raise CommandError(
                "\n[SECURITY VIOLATION] 'dev_auth_access' is strictly disabled in production.\n"
                "This management command can only run when settings.DEBUG is True in a local development environment.\n"
            )

        list_requested = options.get('list')
        otp_target = options.get('otp')
        super_admin_flag = options.get('super_admin')
        operator_flag = options.get('operator')
        check_email = options.get('check')
        force_fresh = options.get('fresh', False)

        if not (list_requested or otp_target is not None or super_admin_flag or operator_flag or check_email):
            # Default action: show account list and usage
            self._list_accounts()
            self.stdout.write(self.style.NOTICE(
                "\nExact Development OTP Retrieval Commands:\n"
                "  1. Gramsevak (Super Admin):\n"
                "     python manage.py superadmin_otp\n"
                "     python manage.py dev_auth_access --super-admin\n"
                "\n"
                "  2. Computer Operator (Operator):\n"
                "     python manage.py operator_otp\n"
                "     python manage.py dev_auth_access --operator\n"
                "\n"
                "Seed Testing Accounts Command:\n"
                "     python manage.py seed_testing_accounts\n"
                "\n"
                "Safe Password Reset Command:\n"
                "     python manage.py changepassword <email>\n"
            ))
            return

        if list_requested:
            self._list_accounts()

        if check_email:
            self._check_account(check_email.strip().lower())

        if super_admin_flag:
            self._generate_dev_otp('super_admin', force_fresh=force_fresh)
        elif operator_flag:
            self._generate_dev_otp('operator', force_fresh=force_fresh)
        elif otp_target is not None:
            self._generate_dev_otp(otp_target.strip().lower(), force_fresh=force_fresh)

    def _list_accounts(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== GramSetu Administrative Accounts & Roles ==="))
        users = User.objects.all().order_by('email')

        if not users.exists():
            self.stdout.write(self.style.WARNING("No user accounts found in database."))
            return

        for u in users:
            ra = getattr(u, 'role_assignment', None)
            role_code = ra.role if ra else 'NONE'
            role_display = ra.get_role_display() if ra else 'No Role Assigned'

            if role_code == ROLE_SUPER_ADMIN:
                statutory_designation = "Gramsevak / Village Development Officer (ग्रामसेवक)"
                badge = self.style.SUCCESS("[SUPER ADMIN]")
            elif role_code == ROLE_OPERATOR:
                statutory_designation = "Computer Operator (संगणक चालक)"
                badge = self.style.WARNING("[OPERATOR]")
            else:
                statutory_designation = "Non-Administrative / Unassigned"
                badge = self.style.ERROR("[UNASSIGNED]")

            status_str = "ACTIVE" if u.is_active else "INACTIVE"
            email_device = u.emaildevice_set.filter(name='default').first()
            mfa_status = "Configured" if (email_device and email_device.confirmed) else "Pending Initial Login"

            self.stdout.write(f"\nEmail:       {self.style.NOTICE(u.email)}")
            self.stdout.write(f"Designation: {statutory_designation}")
            self.stdout.write(f"Full Name:   {u.full_name or 'N/A'}")
            self.stdout.write(f"System Role: {badge} {role_code} ({role_display})")
            self.stdout.write(f"Status:      {status_str} | MFA Device: {mfa_status}")

        self.stdout.write("\n" + self.style.MIGRATE_LABEL("Important Note on Political Positions:"))
        self.stdout.write(
            "  The Sarpanch (सरपंच) is an elected political office-holder and NOT a technical software user.\n"
            "  The Sarpanch profile is editable in the CMS by the Gramsevak (Super Admin) at /cms/profile.\n"
        )

    def _check_account(self, email: str):
        try:
            u = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"User account with email '{email}' does not exist.")

        ra = getattr(u, 'role_assignment', None)
        role_code = ra.role if ra else None

        self.stdout.write(f"\nChecking account: {email}")
        self.stdout.write(f"Active Status:    {u.is_active}")
        self.stdout.write(f"Super Admin:      {is_super_admin(u)}")
        self.stdout.write(f"Operator:         {is_operator(u)}")
        self.stdout.write(f"Role Code:        {role_code}")

        if not u.is_active:
            self.stdout.write(self.style.ERROR("[FAILED] Account is inactive and cannot log in."))
        elif not (is_super_admin(u) or is_operator(u)):
            self.stdout.write(self.style.ERROR("[FAILED] Account lacks administrative CMS role."))
        else:
            self.stdout.write(self.style.SUCCESS("[OK] Account is valid and authorized for CMS access."))

    def _resolve_user(self, target: str) -> User:
        low = target.lower()
        if low in ('super_admin', 'superadmin', 'admin', 'gramsevak', 'gram_sevak'):
            user = (
                User.objects.filter(email='local.admin@gramsetu.gov.in', is_active=True).first()
                or User.objects.filter(role_assignment__role=ROLE_SUPER_ADMIN, is_active=True).first()
            )
            if not user:
                raise CommandError("No active Super Admin (Gramsevak) account found.")
            return user

        if low in ('operator', 'maker', 'computer_operator'):
            user = (
                User.objects.filter(email='local.operator@gramsetu.gov.in', is_active=True).first()
                or User.objects.filter(role_assignment__role=ROLE_OPERATOR, is_active=True).first()
            )
            if not user:
                raise CommandError("No active Computer Operator account found.")
            return user

        try:
            return User.objects.get(email=low, is_active=True)
        except User.DoesNotExist:
            raise CommandError(f"Active user account with email '{target}' does not exist.")

    def _generate_dev_otp(self, target: str, force_fresh: bool = False):
        u = self._resolve_user(target)

        if not (is_super_admin(u) or is_operator(u)):
            raise CommandError(f"Account '{u.email}' is not authorized for CMS administrative access.")

        device = get_or_create_email_device(u)

        now = timezone.now()
        is_active = (
            not force_fresh
            and getattr(device, 'token', None)
            and getattr(device, 'valid_until', None)
            and device.valid_until > now
        )

        if is_active:
            token = device.token
            remaining_seconds = max(0, int((device.valid_until - now).total_seconds()))
            status_desc = f"Active verification challenge (valid for {remaining_seconds} more seconds)"
        else:
            device.generate_challenge()
            token = getattr(device, 'token', None)
            remaining_seconds = 300
            status_desc = "Freshly generated challenge (valid for 300 seconds)"

        if not token:
            raise CommandError(f"Failed to extract OTP token for device {device.id}.")

        role_str = "Super Admin (Gramsevak)" if is_super_admin(u) else "Operator"

        self.stdout.write(self.style.SUCCESS(
            f"\n[DEV AUTH OTP] 6-digit login verification code for {u.email} [{role_str}]:"
        ))
        self.stdout.write(self.style.MIGRATE_HEADING(f"  >>>  {token}  <<<"))
        self.stdout.write(
            f"  Status: {status_desc}.\n"
            f"  Enter this code at http://localhost:3005/cms when prompted for MFA verification.\n"
        )
