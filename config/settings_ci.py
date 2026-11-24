"""CI-only settings: the normal settings with an in-memory SQLite database.

Used by .github/workflows/tests.yml (DJANGO_SETTINGS_MODULE=config.settings_ci) so the test
suite runs without a MySQL server. Tests that need row locks (select_for_update) skip
themselves on SQLite. Never use this module to run the application.
"""

from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
