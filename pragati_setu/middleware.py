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

from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import get_user_model

from rest_framework_simplejwt.tokens import AccessToken, TokenError

from core.models import MasterUser

API_ID_HEADER = "HTTP_X_API_ID"
API_KEY_HEADER = "HTTP_X_API_KEY"

# -------------------------------------------------
# ROLE DEFINITIONS (AS PROVIDED)
# -------------------------------------------------

# Roles allowed everywhere
COMMON_ROLE_IDS = {1, 2, 3, 8, 9, 10}

# epSakhi-only roles
EPSAKHI_ROLE_IDS = {5, 6}

# TMS-only roles
TMS_ROLE_IDS = {4, 7, 11}


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
            return None, "Missing Authorization header"

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None, "Invalid Authorization header format"

        token_str = parts[1]
        try:
            access = AccessToken(token_str)
        except TokenError:
            return None, "Invalid or expired access token"

        user_id = access.payload.get("user_id") or access.payload.get("id")
        if not user_id:
            return None, "Access token missing user_id"

        User = get_user_model()
        try:
            auth_user = User.objects.get(pk=int(user_id))
        except Exception:
            return None, "User not found for access token"

        try:
            mu = MasterUser.objects.get(username=auth_user.username)
        except MasterUser.DoesNotExist:
            return None, "Master user not found"

        if not getattr(mu, "is_active", 0):
            return None, "User inactive"

        role_id = getattr(mu.role, "id", None) or getattr(mu, "role_id", None)
        if not role_id:
            return None, "User role missing"

        return int(role_id), None

    # -------------------------------------------------
    # Main request processing
    # -------------------------------------------------
    def process_request(self, request):
        path = request.path or ""

        # Non-API paths
        if not path.startswith("/api/"):
            return None

        # Auth APIs
        if path.startswith("/api/v1/auth/"):
            return None

        # Lookup APIs (API key based)
        if path.startswith("/api/v1/lookups/"):
            ok, reason = self._check_api_headers(request)
            if not ok:
                return JsonResponse({"detail": reason}, status=401)
            return None

        # All other APIs → JWT required
        role_id, reason = self._validate_access_token_and_get_role(request)
        if role_id is None:
            return JsonResponse({"detail": reason}, status=401)

        # -------------------------------------------------
        # ROLE × API NAMESPACE CHECK 
        # -------------------------------------------------

        # Common roles → allow everywhere
        if role_id in COMMON_ROLE_IDS:
            return None

        # epSakhi APIs
        if path.startswith("/api/v1/") and not path.startswith("/api/v1/tms/"):
            if role_id in EPSAKHI_ROLE_IDS:
                return None
            return JsonResponse(
                {"detail": "User role not authorized for epSakhi API"},
                status=401,
            )

        # TMS APIs
        if path.startswith("/api/v1/tms/"):
            if role_id in TMS_ROLE_IDS:
                return None
            return JsonResponse(
                {"detail": "User role not authorized for TMS API"},
                status=401,
            )

        return None

    def process_response(self, request, response):
        return response
