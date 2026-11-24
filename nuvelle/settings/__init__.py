import os

# Default to dev settings if not specified
env_settings = os.environ.get('DJANGO_SETTINGS_MODULE', 'nuvelle.settings.dev')
if env_settings == 'nuvelle.settings':
    os.environ['DJANGO_SETTINGS_MODULE'] = 'nuvelle.settings.dev'
    from .dev import *  # noqa: F403
