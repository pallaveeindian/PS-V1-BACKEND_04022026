# LDMS/api/dashboard_views.py

from datetime import datetime, timedelta

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from drf_yasg.utils import swagger_auto_schema

from core.models import MasterUser, MasterDistrict, MasterBlock, MasterPanchayat, MasterVillage
from core.api.lookups import parse_csv_param

from LDMS.models import *
from LDMS.api.serializers import *

# Role Name Helper
def _user_role(user: MasterUser) -> str:
    try:
        role = getattr(user, "role", None)
        if role and getattr(role, "name", None):
            return role.name.lower()
    except Exception:
        pass
    return ""

