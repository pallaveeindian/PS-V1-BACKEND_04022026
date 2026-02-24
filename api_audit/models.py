# /api_audit/models.py
from django.db import models
from django.utils import timezone
from core.models import MasterUser

class ApiOperation(models.TextChoices):
    READ = "READ", "READ"
    CREATE = "CREATE", "CREATE"
    UPDATE = "UPDATE", "UPDATE"
    DELETE = "DELETE", "DELETE"


class GlobalApiAudit(models.Model):
    """
    API-key based access (lookups / integrations)
    """
    api_id = models.CharField(max_length=150)
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    operation = models.CharField(
        max_length=10, choices=ApiOperation.choices
    )

    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(null=True, blank=True)

    accessed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "audit_global_api"
        indexes = [
            models.Index(fields=["api_id"]),
            models.Index(fields=["endpoint"]),
            models.Index(fields=["accessed_at"]),
        ]


class AppApiAudit(models.Model):
    """
    JWT-based APIs (epSakhi / TMS / LDMS)
    """
    user = models.ForeignKey(
        MasterUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_constraint=False
    )

    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    operation = models.CharField(
        max_length=10, choices=ApiOperation.choices
    )

    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "audit_app_api"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["endpoint"]),
            models.Index(fields=["created_at"]),
        ]
