# core/api/auth_views.py
import random
import string
import io
import base64
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken, TokenError
from core.models import MasterUser
from .serializers import MasterUserSerializer
from django.contrib.auth.models import User

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

# Captcha for Login
class CaptchaView(APIView):
    permission_classes = (permissions.AllowAny,)

    CAPTCHA_SESSION_KEY = "login_captcha"
    CAPTCHA_EXPIRY_SECONDS = 180  # 3 minutes

    def get(self, request):
        # Generate random text
        captcha_text = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )

        # Save to session
        request.session[self.CAPTCHA_SESSION_KEY] = {
            "value": captcha_text,
            "expires": (timezone.now() + timedelta(seconds=self.CAPTCHA_EXPIRY_SECONDS)).timestamp(),
        }

        # Create image
        image = Image.new("RGB", (180, 50), (255, 255, 255))
        draw = ImageDraw.Draw(image)

        # Optional: use default font
        draw.text((40, 10), captcha_text, fill=(0, 0, 0))

        # Add noise lines
        for _ in range(5):
            draw.line(
                (
                    random.randint(0, 180),
                    random.randint(0, 50),
                    random.randint(0, 180),
                    random.randint(0, 50),
                ),
                fill=(0, 0, 0),
                width=1,
            )

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        img_str = base64.b64encode(buffer.getvalue()).decode()

        return Response({"image": f"data:image/png;base64,{img_str}"})

class LoginView(APIView):
    permission_classes = (permissions.AllowAny,)
    MAX_LOGIN_ATTEMPTS = 4
    
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        
        app_client = request.headers.get("X-App-Client")
        CAPTCHA_ENABLED_APPS = {"TMS_WEB"} 

        if app_client in CAPTCHA_ENABLED_APPS:
            captcha_input = request.data.get("captcha")
            captcha_data = request.session.get("login_captcha")

            if not captcha_input or not captcha_data:
                return Response(
                    {"detail": "Captcha required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # expiry check
            if timezone.now().timestamp() > captcha_data.get("expires", 0):
                return Response(
                    {"detail": "Captcha expired"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if captcha_input.strip().upper() != captcha_data.get("value"):
                return Response(
                    {"detail": "Invalid captcha"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # one-time use
            request.session.pop("login_captcha", None)

        if not username or not password:
            return Response(
                {"detail": "username and password required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---------------------------------
        # Resolve MasterUser first
        # ---------------------------------
        try:
            mu = MasterUser.objects.get(username=username)
        except MasterUser.DoesNotExist:
            # Do not reveal user existence
            return Response(
                {"detail": "invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # ---------------------------------
        # Hard account blocks
        # ---------------------------------
        if mu.is_active != 1:
            return Response(
                {"detail": "account inactive"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if mu.is_suspended == 1:
            return Response(
                {"detail": "account suspended"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if mu.is_locked == 1:
            return Response(
                {"detail": "account locked"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ---------------------------------
        # Authenticate credentials
        # ---------------------------------
        user = authenticate(request, username=username, password=password)

        if not user:
            attempts = mu.pass_attempt_no or 0
            attempts += 1

            mu.pass_attempt_no = attempts
            mu.last_active_on = timezone.now()

            if attempts >= self.MAX_LOGIN_ATTEMPTS:
                mu.is_locked = 1
                mu.locked_on = timezone.now()

            mu.save(
                update_fields=[
                    "pass_attempt_no",
                    "is_locked",
                    "locked_on",
                    "last_active_on",
                ]
            )

            return Response(
                {"detail": "invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # ---------------------------------
        # Successful login → reset attempts
        # ---------------------------------
        if mu.pass_attempt_no:
            mu.pass_attempt_no = 0

        mu.last_active_on = timezone.now()
        mu.save(update_fields=["pass_attempt_no", "last_active_on"])

        # ---------------------------------
        # Issue JWT tokens
        # ---------------------------------

        auth_user, _ = User.objects.get_or_create(
            username=mu.username,
            defaults={"is_active": True},
        )
        
        refresh = RefreshToken.for_user(auth_user)
        access_token = refresh.access_token

        serializer = MasterUserSerializer(mu)

        response = Response(
            {
                "access": str(access_token),
                "refresh": str(refresh),  # backward compatibility
                "user": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

        response.set_cookie(
            REFRESH_COOKIE_NAME,
            str(refresh),
            max_age=_get_refresh_cookie_max_age(),
            httponly=True,
            secure=True,
            samesite="Lax",
            path="/",
        )

        return response

class RefreshTokenView(APIView):
    """
    Obtain a new access token by reading the refresh token from an HttpOnly cookie.
    This allows browser clients to keep refresh tokens out of JS.
    """
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        
        refresh_token = (
            request.COOKIES.get(REFRESH_COOKIE_NAME)
            or request.data.get("refresh")
        )
        
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
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME)

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist() 
            except TokenError:
                # token already expired or invalid
                pass

        response = Response({"detail": "logged out"}, status=status.HTTP_200_OK)
        response.delete_cookie(
            REFRESH_COOKIE_NAME,
            path="/",
        )
        return response



class CRPRequestOtpView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        return Response({'detail':'OTP feature currently disabled (placeholder).'}, status=status.HTTP_200_OK)


class CRPVerifyOtpView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        return Response({'detail':'OTP verification disabled (placeholder).'}, status=status.HTTP_200_OK)
