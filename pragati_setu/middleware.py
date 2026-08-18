# pragati_setu/middleware.py
"""
API header / JWT-aware middleware.

Rules implemented:
- Allow all non-API paths through.
- Allow all /api/v1/auth/* (login / otp) without headers.
- Require X-API-ID / X-API-KEY ONLY for core master-data lookup endpoints:
    -> paths starting with /api/v1/lookups/
- For other /api/ endpoints:
    -> Require valid JWT
    -> Allow access based on role + API namespace
"""
import os
import json
import base64
import time
from django.core.cache import cache
from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import get_user_model

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

from rest_framework_simplejwt.tokens import AccessToken, TokenError

from core.models import MasterUser
from django.http import HttpResponse

#  AUDIT ADD ONS
from api_audit.models import GlobalApiAudit, AppApiAudit
from api_audit.utils import resolve_operation

API_ID_HEADER = "HTTP_X_API_ID"
API_KEY_HEADER = "HTTP_X_API_KEY"

# -------------------------------------------------
# ROLE DEFINITIONS (AS PROVIDED)
# -------------------------------------------------

# Roles allowed everywhere
COMMON_ROLE_IDS = {1, 2, 3, 8, 9, 10, 12}

# epSakhi-only roles
EPSAKHI_ROLE_IDS = {6}

# TMS-only roles
TMS_ROLE_IDS = {4, 7, 11, 13}

class ApiIdApiKeyMiddleware(MiddlewareMixin):
    """
    Middleware that:
    - Enforces X-API headers for lookup endpoints.
    - Allows auth endpoints openly.
    - Validates JWT for all other APIs.
    - Applies role-based access by API namespace.
    """

    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.get_response = get_response
        self.allowed = getattr(settings, "ALLOWED_API_CREDENTIALS", {})

    # IP Helper
    def _get_client_ip(self, request):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")

    # -------------------------------------------------
    # Lookup header validation 
    # -------------------------------------------------
    def _check_api_headers(self, request):
        api_id = request.META.get(API_ID_HEADER)
        api_key = request.META.get(API_KEY_HEADER)
        if not api_id or not api_key:
            return False, "Missing X-API-ID or X-API-KEY headers"
        expected = self.allowed.get(api_id)
        if not expected or api_key != expected:
            return False, "Invalid API credentials"
        return True, None

    # -------------------------------------------------
    # JWT + MasterUser resolution 
    # -------------------------------------------------
    def _validate_access_token_and_get_role(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header:
            return None, None, "Missing Authorization header"

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None, None, "Invalid Authorization header format"

        token_str = parts[1]
        try:
            access = AccessToken(token_str)
        except TokenError:
            return None, None, "Invalid or expired access token"

        user_id = access.payload.get("user_id") or access.payload.get("id")
        if not user_id:
            return None, None, "Access token missing user_id"

        User = get_user_model()
        try:
            auth_user = User.objects.get(pk=int(user_id))
        except Exception:
            return None, None, "User not found for access token"

        try:
            mu = MasterUser.objects.get(username=auth_user.username)
        except MasterUser.DoesNotExist:
            return None, None, "Master user not found"

        if not getattr(mu, "is_active", 0):
            return None, None, "User inactive"

        role_id = getattr(mu.role, "id", None) or getattr(mu, "role_id", None)
        if not role_id:
            return None, None, "User role missing"

        return int(role_id), mu, None

    # -------------------------------------------------
    # Main request processing
    # -------------------------------------------------
    def process_request(self, request):
        path = request.path or ""

        # ---------------------------------------------
        # Options Method Patch Ref POC7 // SA-Round 2
        # ---------------------------------------------
        if request.method == "OPTIONS":
            response = HttpResponse(status=204)

            response["Access-Control-Allow-Origin"] = "http://72.61.255.170:8080"
            response["Access-Control-Allow-Headers"] = (
                "authorization, content-type, x-api-id, x-api-key"
            )
            response["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, PATCH, DELETE"
            )
            response["Access-Control-Max-Age"] = "86400"
            response.headers.pop("Allow", None)

            return response

        # Non-API paths
        if not path.startswith("/api/"):
            return None

        # PUBLIC APIs (Open for Homepage without JWT or Headers)
        if path.startswith("/api/v1/public/") or path.startswith("/api/v1/support/tickets/create/") or path.startswith("/api/v1/tms/public/training-themes/") or path.startswith("/api/v1/tms/public/training-plans"):
            return None

        # Auth APIs
        if path.startswith("/api/v1/auth/"):
            return None
        
        request._audit_context = None

        # Lookup APIs (API key based)
        if path.startswith("/api/v1/lookups/"):
            ok, reason = self._check_api_headers(request)
            if not ok:
                return JsonResponse({"detail": reason}, status=401)
            
            request._audit_context = ("GLOBAL", None)
            return None

        # All other APIs → JWT required
        role_id, master_user, reason = self._validate_access_token_and_get_role(request)
        if role_id is None:
            return JsonResponse({"detail": reason}, status=401)
        
        # -------------------------------------------------
        # ROLE × API NAMESPACE CHECK 
        # -------------------------------------------------

        if role_id not in COMMON_ROLE_IDS:

            # TMS APIs
            if path.startswith("/api/v1/tms/") and role_id not in TMS_ROLE_IDS:
                return JsonResponse(
                    {"detail": "Unauthorized for TMS"},
                    status=401,
                )

            # epSakhi APIs
            if path.startswith("/api/v1/epsakhi/") and role_id not in EPSAKHI_ROLE_IDS:
                return JsonResponse(
                    {"detail": "Unauthorized for epSakhi"},
                    status=401,
                )

            # LDMS APIs (if restricted later)
            if path.startswith("/api/v1/ldms/") and role_id not in COMMON_ROLE_IDS:
                return JsonResponse(
                    {"detail": "Unauthorized for LDMS"},
                    status=401,
                )

            # Prerna Canteen APIs (if restricted later)
            if path.startswith("/api/v1/prerna/") and role_id not in COMMON_ROLE_IDS:
                return JsonResponse(
                    {"detail": "Unauthorized for Prerna Canteen"},
                    status=401,
                )

        request._audit_context = ("APP", master_user)
        return None

    def process_response(self, request, response):
        
        # ---------------------------------------------
        # No more Allowed Methods exposure Patch Ref POC7 // SA-Round 2
        # ---------------------------------------------
        response.headers.pop("Allow", None)       
        
        ctx = getattr(request, "_audit_context", None)

        if ctx and response.status_code < 400:
            try:
                audit_type, user = ctx

                if audit_type == "GLOBAL":
                    GlobalApiAudit.objects.create(
                        api_id=request.META.get(API_ID_HEADER),
                        endpoint=request.path,
                        method=request.method,
                        operation=resolve_operation(request.method),
                        ip_address=self._get_client_ip(request),
                        user_agent=request.META.get("HTTP_USER_AGENT"),
                    )

                elif audit_type == "APP":
                    AppApiAudit.objects.create(
                        user=user,
                        endpoint=request.path,
                        method=request.method,
                        operation=resolve_operation(request.method),
                        ip_address=self._get_client_ip(request),
                        user_agent=request.META.get("HTTP_USER_AGENT"),
                    )
            except Exception:
                pass  # API is never blocked due to audit failure

        return response

# -------------------------------------------------
# VUN 14 PATCH - AES ENCRYPTED API RESPONSES
# -------------------------------------------------

class ResponseEncryptionMiddleware:
    """
    Surgically intercepts outgoing JSON responses on /api/ paths and encrypts them.
    Requires API_ENCRYPTION_KEY in settings (Must be exactly 32 characters).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Get the generated response from the rest of the stack
        response = self.get_response(request)

        # 2. Skip encryption for Swagger, Health checks, and non-API routes
        if not request.path.startswith('/api/') or '/swagger' in request.path:
            return response

        # 3. Only encrypt JSON responses (protects file downloads/media)
        if 'application/json' in response.get('Content-Type', ''):
            secret_key = getattr(settings, 'API_ENCRYPTION_KEY', None)
            if not secret_key or len(secret_key) != 32:
                raise ValueError("API_ENCRYPTION_KEY must be exactly 32 chars in settings.py")

            # Setup AES-256-CBC
            iv = os.urandom(16)
            cipher = Cipher(
                algorithms.AES(secret_key.encode('utf-8')),
                modes.CBC(iv),
                backend=default_backend()
            )
            encryptor = cipher.encryptor()

            # Pad the JSON string to be AES compliant
            padder = padding.PKCS7(128).padder()
            padded_data = padder.update(response.content) + padder.finalize()
            
            # Encrypt
            ciphertext = encryptor.update(padded_data) + encryptor.finalize()

            # Format the payload for React
            encrypted_payload = {
                "iv": base64.b64encode(iv).decode('utf-8'),
                "data": base64.b64encode(ciphertext).decode('utf-8')
            }

            # Overwrite the response
            response.content = json.dumps(encrypted_payload).encode('utf-8')
            response['Content-Length'] = str(len(response.content))

        return response

# Server Mon Middleware
class SystemTelemetryMiddleware:

  def __init__(self, get_response):
    self.get_response = get_response

  def __call__(self, request):
    start_time = time.time()

    # Increment incoming request counter
    try:
        cache.incr("incoming_requests_count", 1)
    except Exception:
        cache.set("incoming_requests_count", 1, timeout=None)

    response = self.get_response(request)
    duration = (time.time() - start_time) * 1000  # in ms

    # Track latency (moving average or latest)
    cache.set("avg_api_latency_ms", round(duration, 2))

    # Increment outgoing response counter
    try:
      cache.incr("outgoing_responses_count", 1)
    except Exception:
      cache.set("outgoing_responses_count", 1, timeout=None)

    # Track security status codes
    if response.status_code == 401:
      cache.incr("unauthorized_requests_count", 1)
    elif response.status_code in [403, 405, 429]:
      cache.incr("blocked_requests_count", 1)

    return response