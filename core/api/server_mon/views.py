import subprocess
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
import psutil
from rest_framework.response import Response
from rest_framework.views import APIView
import redis
from .serializers import *

# Optional Redis connection check
try:
  redis_client = redis.Redis(
      host="127.0.0.1", port=6379, db=0, socket_timeout=1
  )
except Exception:
  redis_client = None


class ServerHealthAPIView(APIView):

  def get(self, request):
    # 1. Service Status
    services_status = {}

    # Gunicorn status check
    try:
      res = subprocess.run(
          ["systemctl", "is-active", "gunicorn"],
          capture_output=True,
          text=True,
          timeout=2,
      )
      services_status["gunicorn"] = res.stdout.strip() == "active"
    except Exception:
      services_status["gunicorn"] = False

    # Custom Systemd Scripts (Replace with your actual service names)
    custom_scripts = {
        "custom_script_1": "YOUR_SCRIPT_NAME_1.service",
        "custom_script_2": "YOUR_SCRIPT_NAME_2.service",
    }
    for key, service_name in custom_scripts.items():
      try:
        res = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            timeout=2,
        )
        services_status[key] = res.stdout.strip() == "active"
      except Exception:
        services_status[key] = False

    # Redis Cache Status
    try:
      if redis_client:
        services_status["redis"] = redis_client.ping()
      else:
        services_status["redis"] = False
    except Exception:
      services_status["redis"] = False

    # DB Status
    try:
      with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        services_status["database"] = True
    except Exception:
      services_status["database"] = False

    # 2. Resource Utilization
    cpu_usage = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    resources = {
        "cpu_usage_percent": cpu_usage,
        "memory": {
            "total_mb": round(mem.total / (1024 * 1024), 2),
            "used_mb": round(mem.used / (1024 * 1024), 2),
            "usage_percent": mem.percent,
        },
        "disk": {
            "total_gb": round(disk.total / (1024 * 1024 * 1024), 2),
            "covered_used_gb": round(disk.used / (1024 * 1024 * 1024), 2),
            "space_left_gb": round(disk.free / (1024 * 1024 * 1024), 2),
            "usage_percent": disk.percent,
        },
    }

    # 3. Database Size
    db_size_str = "Unknown"
    try:
      with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
          cursor.execute(
              "SELECT pg_size_pretty(pg_database_size(current_database()));"
          )
          row = cursor.fetchone()
          db_size_str = row[0] if row else "Unknown"
        elif connection.vendor == "mysql":
          cursor.execute("""
                        SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) 
                        FROM information_schema.tables 
                        WHERE table_schema = DATABASE();
                    """)
          row = cursor.fetchone()
          db_size_str = f"{row[0]} MB" if row and row[0] else "Unknown"
    except Exception:
      db_size_str = "Error calculating size"

    # 4. Network Telemetry (Backed by cache counters)
    network_telemetry = {
        "api_latency_ms": cache.get("avg_api_latency_ms", 0.0),
        "incoming_requests_total": cache.get("incoming_requests_count", 0),
        "outgoing_responses_total": cache.get("outgoing_responses_count", 0),
        "active_sessions": Session.objects.filter(
            expire_date__gte=timezone.now()
        ).count(),
    }

    # 5. Security Monitoring
    security_monitoring = {
        "blocked_requests_total": cache.get("blocked_requests_count", 0),
        "unauthorized_requests_total": cache.get(
            "unauthorized_requests_count", 0
        ),
        "successful_logins_total": cache.get("successful_logins_count", 0),
    }

    data = {
        "services": services_status,
        "resources": resources,
        "database_size": db_size_str,
        "network_telemetry": network_telemetry,
        "security_monitoring": security_monitoring,
    }

    serializer = SystemHealthSerializer(data)
    return Response(serializer.data)