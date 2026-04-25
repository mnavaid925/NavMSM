"""Test-only settings — fast SQLite + cheap password hashing + in-memory storage."""
from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Don't write uploaded files to disk — keeps the suite self-contained and
# avoids Windows file-locking issues seen during smoke tests.
DEFAULT_FILE_STORAGE = 'django.core.files.storage.InMemoryStorage'

# Speed up tests — skip whitenoise / static collection.
DEBUG = False
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
