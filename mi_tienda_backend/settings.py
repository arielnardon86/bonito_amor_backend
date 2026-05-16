# BONITO_AMOR/backend/bonito_amor/settings.py
import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

# Determinar qué archivo .env cargar según el ambiente
# Detección automática: Si está en Render o tiene DATABASE_URL, asumir producción
ENVIRONMENT = os.environ.get('DJANGO_ENVIRONMENT', '').lower()

# Si no está configurada, intentar detectar automáticamente
if not ENVIRONMENT:
    # Si tiene DATABASE_URL (típico de Render/Heroku), asumir producción
    if 'DATABASE_URL' in os.environ:
        ENVIRONMENT = 'production'
        print("\n⚠️  DJANGO_ENVIRONMENT no configurada, pero DATABASE_URL detectada. Usando: production")
    # Si está en Render (tiene RENDER), asumir producción
    elif 'RENDER' in os.environ:
        ENVIRONMENT = 'production'
        print("\n⚠️  DJANGO_ENVIRONMENT no configurada, pero RENDER detectado. Usando: production")
    else:
        ENVIRONMENT = 'development'
        print("\n⚠️  DJANGO_ENVIRONMENT no configurada. Usando: development (por defecto)")

print(f"\n🔍 Ambiente detectado: {ENVIRONMENT.upper()}")
print(f"🔍 Variables de entorno disponibles:")
print(f"   - DJANGO_ENVIRONMENT: {os.environ.get('DJANGO_ENVIRONMENT', 'NO CONFIGURADA')}")
print(f"   - DATABASE_URL: {'CONFIGURADA' if 'DATABASE_URL' in os.environ else 'NO CONFIGURADA'}")
print(f"   - RENDER: {'CONFIGURADA' if 'RENDER' in os.environ else 'NO CONFIGURADA'}")

if ENVIRONMENT == 'staging':
    env_file = BASE_DIR / '.env.staging'
    if env_file.exists():
        load_dotenv(env_file)
    else:
        load_dotenv()
elif ENVIRONMENT == 'production':
    load_dotenv()
else:  # development
    load_dotenv()

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-tu-clave-secreta-de-desarrollo-aqui')
DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = []
if not DEBUG:
    ALLOWED_HOSTS = [
        '.onrender.com',
        'bonito-amor-backend.onrender.com',
        'bonitoamorstock.onrender.com',
        'totalstock.onrender.com',
        'totalstock.com.ar',
        'www.totalstock.com.ar',
    ]
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = False 
    
    CSRF_COOKIE_DOMAIN = None
    SESSION_COOKIE_DOMAIN = None
    
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_SAMESITE = 'Lax'
    
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'

else: 
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']

INSTALLED_APPS = [
    'inventario',         
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework', 
    'corsheaders',    
    'rest_framework_simplejwt',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', 
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',      # ¡Mover esta línea más arriba!
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',  
    'django.contrib.auth.middleware.AuthenticationMiddleware', 
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mi_tienda_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'mi_tienda_backend.wsgi.application' 

# Configuración de base de datos según el ambiente
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Configuración para diferentes ambientes
if ENVIRONMENT == 'staging':
    # Ambiente de staging: PostgreSQL local sin SSL
    if 'DATABASE_URL' in os.environ:
        DATABASES['default'] = dj_database_url.config(
            conn_max_age=60,
            ssl_require=False  # Sin SSL para PostgreSQL local
        )
        print("\n--- STAGING DATABASE CONFIG ---")
        print(f"Ambiente: STAGING")
        print(f"Base de datos: {DATABASES['default']['ENGINE']}")
        print(f"Nombre: {DATABASES['default'].get('NAME', 'N/A')}")
        print("--- END CONFIG ---\n")
    else:
        # Fallback: PostgreSQL local con configuración manual
        DATABASES['default'] = {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('STAGING_DB_NAME', 'bonito_amor_staging'),
            'USER': os.environ.get('STAGING_DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('STAGING_DB_PASSWORD', 'postgres'),
            'HOST': os.environ.get('STAGING_DB_HOST', 'localhost'),
            'PORT': os.environ.get('STAGING_DB_PORT', '5432'),
            'CONN_MAX_AGE': 60,
        }
        print("\n--- STAGING DATABASE CONFIG (manual) ---")
        print(f"Ambiente: STAGING")
        print(f"Base de datos: PostgreSQL local")
        print(f"Nombre: {DATABASES['default']['NAME']}")
        print("--- END CONFIG ---\n")

elif ENVIRONMENT == 'production':
    # Ambiente de producción: PostgreSQL en la nube con SSL
    if 'DATABASE_URL' in os.environ:
        DATABASES['default'] = dj_database_url.config(
            conn_max_age=60,
            ssl_require=True  # SSL requerido en producción
        )
        print("\n--- PRODUCTION DATABASE CONFIG ---")
        print("✅ DATABASE_URL found in environment variables!")
        print(f"✅ Engine: {DATABASES['default']['ENGINE']}")
        print(f"✅ Database Name: {DATABASES['default'].get('NAME', 'N/A')}")
        print(f"✅ Host: {DATABASES['default'].get('HOST', 'N/A')}")
        print(f"✅ Port: {DATABASES['default'].get('PORT', 'N/A')}")
        print(f"✅ User: {DATABASES['default'].get('USER', 'N/A')}")
        print(f"✅ SSL Required: True")
        print(f"✅ Using Cloud PostgreSQL Database")
        print("--- END CONFIG ---\n")
    else:
        print("\n--- PRODUCTION DATABASE CONFIG ---")
        print("❌ ERROR: DATABASE_URL NOT found in environment variables for production!")
        print("⚠️  WARNING: Falling back to SQLite (NOT RECOMMENDED FOR PRODUCTION)")
        print(f"⚠️  Using local SQLite: {DATABASES['default']['NAME']}")
        print("--- END CONFIG ---\n")

else:  # development
    # Desarrollo siempre usa SQLite (sin PostgreSQL)
    print("\n--- DEVELOPMENT DATABASE CONFIG ---")
    print("Using SQLite for development")
    print(f"Django's DATABASES['default'] configured as: {DATABASES['default']['ENGINE']}")
    print("--- END CONFIG ---\n")

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'es-ar' 
TIME_ZONE = 'America/Argentina/Cordoba' 
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles' 

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://bonitoamorstock.onrender.com",
    "https://bonito-amor-backend.onrender.com",
    "https://totalstock.onrender.com",
    "https://totalstock.com.ar",
    "https://www.totalstock.com.ar",
]
CORS_ALLOW_CREDENTIALS = True 

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "https://bonito-amor-backend.onrender.com",
    "https://bonitoamorstock.onrender.com",
    "https://totalstock.onrender.com",
    "https://totalstock.com.ar",
    "https://www.totalstock.com.ar",
]

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated', 
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication', 
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10 
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=5), 
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),    
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,              
    'UPDATE_LAST_LOGIN': False,                     

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,                      
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=15),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=7),
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler', 
            'formatter': 'verbose', 
        },
    },
    'formatters': { 
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{', 
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',  
            'propagate': False,
        },
        'inventario': { 
            'handlers': ['console'],
            'level': 'INFO', 
            'propagate': False,
        },
        '': { 
            'handlers': ['console'],
            'level': 'INFO', 
            'propagate': False,
        },
    },
}

AUTH_USER_MODEL = 'inventario.User'

# Backend iexact primero: evita fallos por mayúsculas (ej. "ari" vs "Ari" en DB).
AUTHENTICATION_BACKENDS = [
    'inventario.auth_backends.CaseInsensitiveUsernameBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# ── Suscripciones / Mercado Pago ─────────────────────────────────────────────
MP_ACCESS_TOKEN_SUSCRIPCIONES = os.environ.get('MP_ACCESS_TOKEN_SUSCRIPCIONES', '')
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')
# URL pública del backend (para notification_url en MP). Ej: https://bonito-amor-backend.onrender.com
BACKEND_URL = os.environ.get('BACKEND_URL', '')
# Clave secreta para validar firma de webhooks de MP (Configurar notificaciones → clave secreta)
MP_WEBHOOK_SECRET = os.environ.get('MP_WEBHOOK_SECRET', '')