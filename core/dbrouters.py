# core/dbrouters.py
class MasterDBRouter:
    """
    DB router that routes all core app models to 'default' DB.
    It allows both reads and writes. Migrations for core are allowed if you want
    Django to manage them (but by default core models should be created by existing DB).
    """
    route_app_labels = {'core'}

    def db_for_read(self, model, **hints):
        return 'default'

    def db_for_write(self, model, **hints):
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # Allow migrations for core and others on default DB. If you want to prevent
        # Django from creating master tables set this to False.
        return db == 'default'
