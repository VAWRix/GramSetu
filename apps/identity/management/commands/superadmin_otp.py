"""
Super Admin OTP Command for GramSetu.

Generates or retrieves the active single-use login OTP for the configured
GramSetu Super Administrator (Gramsevak / Village Development Officer).

STRICT SECURITY CONTROLS:
- Hard-locked to settings.DEBUG == True (Refuses execution in production).
- Single-use only (invalidated upon verification).
- Tied exclusively to the Super Admin user account.
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from apps.identity.models import User, ROLE_SUPER_ADMIN
from apps.identity.services import get_or_create_email_device
from apps.identity.permissions import is_super_admin

SUPER_ADMIN_PRIMARY_EMAIL = 'local.admin@gramsetu.gov.in'


class Command(BaseCommand):
    help = "Generate or retrieve the active single-use login OTP for GramSetu Super Administrator (DEBUG mode only)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--fresh',
            '-f',
            action='store_true',
            help="Force generation of a brand new OTP challenge even if an active unexpired code exists.",
        )
        parser.add_argument(
            '--raw',
            '-r',
            action='store_true',
            help="Print ONLY the 6-digit OTP code (useful for automated shell scripting).",
        )

    def handle(self, *args, **options):
        # HARD SECURITY GATE: Strictly refuse in production
        if not getattr(settings, 'DEBUG', False):
            raise CommandError(
                "\n[SECURITY VIOLATION] 'superadmin_otp' is strictly disabled in production.\n"
                "This command can only execute when settings.DEBUG is True in local development environments.\n"
            )

        # Resolve Super Admin user
        user = (
            User.objects.filter(email=SUPER_ADMIN_PRIMARY_EMAIL, is_active=True).first()
            or User.objects.filter(role_assignment__role=ROLE_SUPER_ADMIN, is_active=True).first()
        )

        if not user:
            raise CommandError(f"No active Super Administrator account found with email '{SUPER_ADMIN_PRIMARY_EMAIL}'.")

        if not is_super_admin(user):
            raise CommandError(f"Account '{user.email}' lacks Super Administrator privileges.")

        device = get_or_create_email_device(user)
        force_fresh = options.get('fresh', False)
        raw_output = options.get('raw', False)

        now = timezone.now()
        is_active = (
            not force_fresh
            and getattr(device, 'token', None)
            and getattr(device, 'valid_until', None)
            and device.valid_until > now
        )

        validity_seconds = getattr(settings, 'OTP_EMAIL_TOKEN_VALIDITY', 300)

        if is_active:
            token = device.token
            remaining_seconds = max(0, int((device.valid_until - now).total_seconds()))
            status_desc = f"Active verification challenge (valid for {remaining_seconds} more seconds)"
        else:
            device.generate_challenge()
            token = getattr(device, 'token', None)
            remaining_seconds = validity_seconds
            status_desc = f"Freshly generated challenge (valid for {validity_seconds} seconds)"

        if not token:
            raise CommandError(f"Failed to generate OTP token for device {device.id}.")

        if raw_output:
            self.stdout.write(token)
            return

        self.stdout.write(self.style.MIGRATE_HEADING("\n" + "=" * 60))
        self.stdout.write(self.style.SUCCESS("[GRAMSETU SUPER ADMIN OTP - DEVELOPMENT MODE]"))
        self.stdout.write(f"Account:     {user.email}")
        self.stdout.write(f"Holder:      {user.full_name}")
        self.stdout.write(f"Designation: Gramsevak / Village Development Officer (ग्रामसेवक)")
        self.stdout.write(f"System Role: SUPER_ADMIN (Full Administrative Governance)")
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.NOTICE(f"\n  >>> OTP VERIFICATION CODE: {token} <<<\n"))
        self.stdout.write(f"Status:   {status_desc}")
        self.stdout.write("Security: Account-Specific | Single-Use Only | Cross-Account Rejected")
        self.stdout.write("Portal:   http://localhost:3005/cms")
        self.stdout.write("=" * 60 + "\n")
