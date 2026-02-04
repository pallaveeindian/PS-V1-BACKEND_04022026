# core/api/auth_urls.py
from django.urls import path
from . import auth_views

urlpatterns = [
    # login returns access + refresh (also sets HttpOnly cookie ps_refresh)
    path('login/', auth_views.LoginView.as_view(), name='login'),

    # Keep body-based refresh for backward compatibility
    path('refresh/', auth_views.RefreshTokenView.as_view(), name='token_refresh'),

    # Cookie-based refresh expected by frontend: POST /api/v1/auth/refresh-cookie/
    path('refresh-cookie/', auth_views.RefreshTokenView.as_view(), name='token_refresh_cookie'),

    # logout clears cookie
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # OTP placeholder endpoints
    path('crp/request-otp/', auth_views.CRPRequestOtpView.as_view(), name='crp_request_otp'),
    path('crp/verify-otp/', auth_views.CRPVerifyOtpView.as_view(), name='crp_verify_otp'),
]