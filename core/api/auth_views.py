# core/api/auth_views.py
import random
import string
import io
import base64
import json
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from PIL import Image, ImageDraw, ImageFont, ImageFilter
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
from django.http import Http404
from django.contrib.auth.signals import user_logged_in

# Cookie name for storing refresh token (httpOnly)
REFRESH_COOKIE_NAME = 'ps_refresh'

# Calculate cookie max_age from SIMPLE_JWT setting if present (seconds)
def _get_refresh_cookie_max_age():
    delta = getattr(settings, 'SIMPLE_JWT', {}).get('REFRESH_TOKEN_LIFETIME', None)
    if delta:
        try:
            return int(delta.total_seconds())
        except Exception:
            pass
    return 7 * 24 * 3600

# Captcha for Login
class CaptchaView(APIView):
    permission_classes = (permissions.AllowAny,)
    CAPTCHA_SESSION_KEY = "login_captcha"
    CAPTCHA_EXPIRY_SECONDS = 180  # 3 minutes

    def get(self, request):
        captcha_text = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )

        request.session[self.CAPTCHA_SESSION_KEY] = {
            "value": captcha_text,
            "expires": (
                timezone.now() + timedelta(seconds=self.CAPTCHA_EXPIRY_SECONDS)
            ).timestamp(),
        }

        width, height = 300, 100
        image = Image.new("RGB", (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/fira-code/FiraCode-Bold.ttf", 64
            )
        except:
            font = ImageFont.load_default()

        char_width = width // 8
        x = 25

        for char in captcha_text:
            y_offset = random.randint(-5, 5)
            char_image = Image.new("RGBA", (80, 80), (255, 255, 255, 0))
            char_draw = ImageDraw.Draw(char_image)
            char_draw.text((10, 5), char, font=font, fill=(20, 20, 20))

            rotated = char_image.rotate(random.randint(-15, 15), expand=1)
            image.paste(rotated, (x, 15 + y_offset), rotated)

            x += char_width

        for _ in range(150):
            draw.point(
                (random.randint(0, width), random.randint(0, height)),
                fill=(180, 180, 180),
            )

        draw.line(
            (0, random.randint(30, 70), width, random.randint(30, 70)),
            fill=(200, 200, 200),
            width=2,
        )
        
        image = image.filter(ImageFilter.SMOOTH)

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        img_str = base64.b64encode(buffer.getvalue()).decode()

        return Response({"image": f"data:image/png;base64,{img_str}"})

class LoginView(APIView):
    permission_classes = (permissions.AllowAny,)
    MAX_LOGIN_ATTEMPTS = 4

    @staticmethod
    def get_client_ip(request):
        """Accurately extract client IP, handling proxies like Nginx."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def get(self, request):
        raise Http404()

    def post(self, request):
        # -------------------------------------------------
        # VUN 14 PATCH - AES DECRYPTION OF INCOMING PAYLOAD
        # -------------------------------------------------
        payload = request.data
        decrypted_data = payload  # Fallback to raw data if not encrypted

        if 'iv' in payload and 'data' in payload:
            try:
                secret_key = getattr(settings, 'API_ENCRYPTION_KEY', None)
                if not secret_key or len(secret_key) != 32:
                    return Response(
                        {"detail": "Server encryption key misconfigured."},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

                iv = base64.b64decode(payload['iv'])
                ciphertext = base64.b64decode(payload['data'])

                cipher = Cipher(
                    algorithms.AES(secret_key.encode('utf-8')),
                    modes.CBC(iv),
                    backend=default_backend()
                )
                decryptor = cipher.decryptor()
                
                padded_data = decryptor.update(ciphertext) + decryptor.finalize()

                unpadder = padding.PKCS7(128).unpadder()
                unpadded_data = unpadder.update(padded_data) + unpadder.finalize()

                decrypted_data = json.loads(unpadded_data.decode('utf-8'))

            except Exception as e:
                return Response(
                    {"detail": "Failed to decrypt payload or invalid format."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        username = decrypted_data.get("username")
        password = decrypted_data.get("password")
        
        app_client = request.headers.get("X-App-Client")
        CAPTCHA_ENABLED_APPS = {"TMS_WEB", "CRP-EP_APP"}

        if app_client in CAPTCHA_ENABLED_APPS:
            captcha_input = decrypted_data.get("captcha")
            captcha_data = request.session.get("login_captcha")

            if not captcha_input or not captcha_data:
                return Response(
                    {"detail": "Captcha required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

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

            request.session.pop("login_captcha", None)

        if not username or not password:
            return Response(
                {"detail": "username and password required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            mu = MasterUser.objects.get(username=username)
        except MasterUser.DoesNotExist:
            return Response(
                {"detail": "invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

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
        # TMS First Login Tracking
        # ---------------------------------
        if app_client == "TMS_WEB":
            # Inline import prevents circular dependency between core & tms
            from TMS.models import TMSFirstLoginTracker 
            ip_addr = self.get_client_ip(request)
            
            # get_or_create ensures this runs ONLY if it doesn't already exist
            TMSFirstLoginTracker.objects.get_or_create(
                master_user=mu,
                defaults={
                    'ip_address': ip_addr,
                    'must_change_password': True
                }
            )

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

        user_logged_in.send(sender=auth_user.__class__, request=request, user=auth_user)

        response = Response(
            {
                "access": str(access_token),
                "refresh": str(refresh), 
                "user": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

        response.set_cookie(
            REFRESH_COOKIE_NAME,
            str(refresh),
            max_age=_get_refresh_cookie_max_age(),
            httponly=True,
            secure=False,
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
