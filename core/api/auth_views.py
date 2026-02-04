# core/api/auth_views.py
from django.conf import settings
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken, TokenError
from core.models import MasterUser
from .serializers import MasterUserSerializer

# Cookie name for storing refresh token (httpOnly)
REFRESH_COOKIE_NAME = 'ps_refresh'

# Calculate cookie max_age from SIMPLE_JWT setting if present (seconds)
def _get_refresh_cookie_max_age():
    # SIMPLE_JWT 'REFRESH_TOKEN_LIFETIME' is a datetime.timedelta
    delta = getattr(settings, 'SIMPLE_JWT', {}).get('REFRESH_TOKEN_LIFETIME', None)
    if delta:
        try:
            # may be timedelta
            return int(delta.total_seconds())
        except Exception:
            pass
    # fallback: 7 days
    return 7 * 24 * 3600

class LoginView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        if not username or not password:
            return Response({'detail':'username and password required'}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(request, username=username, password=password)
        if not user:
            return Response({'detail':'invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        # Create tokens
        refresh = RefreshToken.for_user(user)
        access_token = refresh.access_token

        try:
            # Get master user record
            mu = MasterUser.objects.get(username=user.username)
        except MasterUser.DoesNotExist:
            return Response({'detail': 'master user missing'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        s = MasterUserSerializer(mu)

        response_data = {
            'access': str(access_token),
            'refresh': str(refresh),   # keep returning refresh to preserve backward compatibility
            'user': s.data
        }

        response = Response(response_data, status=status.HTTP_200_OK)

        # Set HttpOnly refresh cookie for browser clients (secure flag only when not DEBUG)
        cookie_max_age = _get_refresh_cookie_max_age()
        # If DEBUG True, secure=False to allow local HTTP; in production secure=True recommended.
        secure_flag = not getattr(settings, 'DEBUG', False)
        # Path is limited to auth endpoints; change as needed.
        response.set_cookie(
            REFRESH_COOKIE_NAME,
            str(refresh),
            max_age=cookie_max_age,
            httponly=True,
            secure=secure_flag,
            samesite='Lax',
            path='/api/v1/auth/'
        )

        return response


class RefreshTokenView(APIView):
    """
    Obtain a new access token by reading the refresh token from an HttpOnly cookie.
    This allows browser clients to keep refresh tokens out of JS.
    """
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
        if not refresh_token:
            return Response({'detail': 'Missing refresh token cookie'}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            refresh = RefreshToken(refresh_token)
        except TokenError:
            return Response({'detail': 'Invalid or expired refresh token'}, status=status.HTTP_401_UNAUTHORIZED)

        # Create a fresh access token
        access = refresh.access_token
        return Response({'access': str(access)}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    Logout for browser clients: clear the refresh cookie.
    Note: This does not invalidate the token server-side (RefreshToken.blacklist requires additional setup).
    """
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        response = Response({'detail': 'logged out'}, status=status.HTTP_200_OK)
        # Delete cookie by setting it expired
        response.delete_cookie(REFRESH_COOKIE_NAME, path='/api/v1/auth/')
        return response


class CRPRequestOtpView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        return Response({'detail':'OTP feature currently disabled (placeholder).'}, status=status.HTTP_200_OK)


class CRPVerifyOtpView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        return Response({'detail':'OTP verification disabled (placeholder).'}, status=status.HTTP_200_OK)
