from django.apps import AppConfig


class SearchConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.search'
    verbose_name = 'Search / शोध'

    def ready(self):
        from apps.search.signals import connect_search_signals
        connect_search_signals()
