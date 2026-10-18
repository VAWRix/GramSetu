"""
Identity models for GramSetu platform.

Implements the official custom User model, RoleAssignment (Super Administrator / Operator),
InvitationToken, and OperatorUrgentAuthorization in accordance with approved architectural
specifications in docs/data-model.md.
"""

from datetime import timedelta
import hashlib
import secrets
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone
from apps.core.utils import generate_uuid7

# Role constants
ROLE_SUPER_ADMIN = 'super_admin'
ROLE_OPERATOR = 'operator'

ROLE_CHOICES = [
    (ROLE_SUPER_ADMIN, 'Super Administrator'),
    (ROLE_OPERATOR, 'Operator'),
]

# Urgent authorization category constants
CATEGORY_DISASTER = 'disaster_alert'
CATEGORY_HEALTH = 'public_health'
CATEGORY_WATER = 'water_supply'
CATEGORY_WEATHER = 'weather_warning'

URGENT_CATEGORY_CHOICES = [
    (CATEGORY_DISASTER, 'Disaster Alert'),
    (CATEGORY_HEALTH, 'Public Health Emergency'),
    (CATEGORY_WATER, 'Critical Water Alert'),
    (CATEGORY_WEATHER, 'Severe Weather Warning'),
]


class UserManager(BaseUserManager):
    """
    Custom user manager for email-based authentication on GramSetu.
    """

    def create_user(self, email, full_name, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set.")
        if not full_name:
            raise ValueError("The Full Name field must be set.")

        email = self.normalize_email(email).lower()
        user = self.model(email=email, full_name=full_name, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, full_name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, full_name, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model for GramSetu portal.
    Uses normalized email as unique username identifier.
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=15, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        default=False,
        help_text="Designates whether the user can log into the Django admin site.",
    )
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        db_table = 'identity_user'
        verbose_name = 'User / वापरकर्ता'
        verbose_name_plural = 'Users / वापरकर्ते'
        ordering = ['-date_joined']
        constraints = [
            models.CheckConstraint(
                check=Q(email=Lower('email')),
                name='check_email_lowercase',
            ),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.email})"

    def clean(self):
        super().clean()
        if self.email:
            self.email = self.email.lower()


class RoleAssignment(models.Model):
    """
    Maps users to approved business roles (Super Administrator or Operator).
    Independent of Django staff/superuser permissions.
    """
    ROLE_SUPER_ADMIN = ROLE_SUPER_ADMIN
    ROLE_OPERATOR = ROLE_OPERATOR
    ROLE_CHOICES = ROLE_CHOICES

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='role_assignment',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='granted_roles',
        null=True,
        blank=True,
        help_text="Super Administrator who assigned this role.",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'identity_role_assignment'
        verbose_name = 'Role Assignment / भूमिका वाटप'
        verbose_name_plural = 'Role Assignments / भूमिका वाटप'
        constraints = [
            models.CheckConstraint(
                check=Q(role__in=[ROLE_SUPER_ADMIN, ROLE_OPERATOR]),
                name='chk_valid_role',
            ),
        ]

    def __str__(self):
        return f"{self.user.email} -> {self.get_role_display()}"

    @property
    def is_super_admin(self) -> bool:
        return self.role == ROLE_SUPER_ADMIN

    @property
    def is_operator(self) -> bool:
        return self.role == ROLE_OPERATOR


class InvitationToken(models.Model):
    """
    Time-limited, single-use invitation tokens for administrative onboarding.
    Stores cryptographically secure SHA-256 token digest to protect secrets.
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    email = models.EmailField()
    target_role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    invited_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='issued_invitations',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    is_revoked = models.BooleanField(default=False)

    class Meta:
        db_table = 'identity_invitation_token'
        verbose_name = 'Invitation Token / निमंत्रण टोकन'
        verbose_name_plural = 'Invitation Tokens / निमंत्रण टोकन'
        constraints = [
            models.CheckConstraint(
                check=Q(expires_at__gt=F('created_at')),
                name='check_token_validity',
            ),
            models.CheckConstraint(
                check=Q(target_role__in=[ROLE_SUPER_ADMIN, ROLE_OPERATOR]),
                name='chk_valid_invitation_role',
            ),
        ]

    def __str__(self):
        return f"Invitation for {self.email} ({self.target_role})"

    @property
    def is_valid(self) -> bool:
        return not self.is_revoked and self.used_at is None and timezone.now() < self.expires_at

    @classmethod
    def create_invitation(cls, email: str, target_role: str, invited_by: User, validity_hours=48):
        """
        Creates an InvitationToken record storing the SHA-256 hash.
        Returns a tuple of (instance, raw_token_string).
        """
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        expires_at = timezone.now() + timedelta(hours=validity_hours)

        invitation = cls(
            email=email.lower(),
            target_role=target_role,
            token_hash=token_hash,
            invited_by=invited_by,
            expires_at=expires_at,
        )
        invitation.save()
        return invitation, raw_token

    @classmethod
    def hash_token(cls, raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


class OperatorUrgentAuthorization(models.Model):
    """
    Time-limited authority granted exclusively by a Super Administrator allowing an Operator
    to publish urgent notices without prior review for predefined disaster/emergency categories.
    """
    CATEGORY_DISASTER = CATEGORY_DISASTER
    CATEGORY_HEALTH = CATEGORY_HEALTH
    CATEGORY_WATER = CATEGORY_WATER
    CATEGORY_WEATHER = CATEGORY_WEATHER
    CATEGORY_CHOICES = URGENT_CATEGORY_CHOICES

    operator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='urgent_authorizations',
    )
    authorized_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='granted_urgent_authorizations',
    )
    allowed_category = models.CharField(max_length=50, choices=URGENT_CATEGORY_CHOICES)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    is_revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'identity_operator_urgent_authorization'
        verbose_name = 'Operator Urgent Authorization / ऑपरेटर तातडीचे अधिकार पत्र'
        verbose_name_plural = 'Operator Urgent Authorizations / ऑपरेटर तातडीचे अधिकार पत्रे'
        constraints = [
            models.CheckConstraint(
                check=Q(valid_to__gt=F('valid_from')),
                name='check_auth_dates',
            ),
            models.CheckConstraint(
                check=Q(allowed_category__in=[
                    CATEGORY_DISASTER,
                    CATEGORY_HEALTH,
                    CATEGORY_WATER,
                    CATEGORY_WEATHER,
                ]),
                name='chk_valid_urgent_category',
            ),
            models.UniqueConstraint(
                fields=['operator', 'allowed_category'],
                condition=Q(is_revoked=False),
                name='uq_active_operator_urgent_auth',
            ),
        ]

    def __str__(self):
        return f"Urgent Auth: {self.operator.email} [{self.allowed_category}] (active={self.is_valid})"

    def clean(self):
        super().clean()
        if self.operator_id and self.authorized_by_id:
            if self.operator_id == self.authorized_by_id:
                raise ValidationError("An operator cannot grant urgent authorization to themselves.")

    @property
    def is_valid(self) -> bool:
        now = timezone.now()
        return not self.is_revoked and (self.valid_from <= now <= self.valid_to)
