# core/backends.py
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import User
from core.models import MasterUser

class MasterUserBackend(BaseBackend):
    """
    Authenticate using master_user table (not Django users).
    - Accepts Django-compatible hashed password (check_password).
    - Falls back to raw comparison only if check_password failed (for legacy).
    - Creates/updates a local Django User record so Django admin can work.
      The Django user will have is_staff=True ONLY if master role name == 'pmu_admin'.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        try:
            mu = MasterUser.objects.get(username=username)
        except MasterUser.DoesNotExist:
            return None

        if not mu.is_active:
            return None

        # Try bcrypt / django hash check first
        try:
            if check_password(password, mu.password):
                return self._sync_django_user(mu)
        except Exception:
            # check_password may raise if password format unknown; ignore and fallback
            pass

        # fallback raw compare (only if legacy plaintext stored)
        if password == mu.password:
            return self._sync_django_user(mu)

        return None

    def _sync_django_user(self, master_user):
        """
        Create or update a Django User that mirrors master_user.
        Grant is_staff only when master_user.get_role_name() == 'pmu_admin'
        """
        username = master_user.username
        user, created = User.objects.get_or_create(username=username)
        # set minimal flags; do NOT set Django password (master_user is source of truth)
        role_name = master_user.get_role_name() if hasattr(master_user, 'get_role_name') else None
        if role_name == 'pmu_admin':
            user.is_staff = True
            # you may also grant superuser if you want full admin powers:
            # user.is_superuser = True
        else:
            user.is_staff = False
            user.is_superuser = False
        user.save()
        return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
