# LDMS/apps.py

from django.apps import AppConfig

class LdmsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'LDMS'

    def ready(self):
        # Import the signals file to wake it up when Django starts
        import LDMS.signals