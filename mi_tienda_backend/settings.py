import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Configuración de Seguridad y Entorno ---
# Siempre usa una clave secreta fuerte y guárdala de forma segura.
# En producción, asegúrate de que DJANGO_SECRET_KEY esté definida en tus variables de entorno.
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-tu-clave-secreta-de-desarrollo-aqui')

# DEBUG debe ser False en producción por seguridad y rendimiento.
# Se obtiene de la variable de entorno DJANGO_DEBUG, por defecto True para desarrollo.
DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() == 'true'

# ALLOWED_HOSTS define qué nombres de host puede servir tu aplicación.
# CRÍTICO para la seguridad en producción.
ALLOWED_HOSTS = []
if not DEBUG:
    # Hosts permitidos para despliegue en Render.
    ALLOWED_HOSTS = [
        '.onrender.com',                      # Permite cualquier subdominio de onrender.com
        'bonito-amor-backend.onrender.com',   # Tu backend específico
        'bonitoamorstock.onrender.com',       # Tu frontend si está en el mismo dominio
    ]
    # Redirecciona automáticamente a HTTPS y asegura el uso de HTTPS.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True # Agregado: Redirige todo el tráfico HTTP a HTTPS
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = False # Necesario si tu frontend JS lee la cookie CSRF
    
    # CSRF_COOKIE_DOMAIN y SESSION_COOKIE_DOMAIN generalmente no se necesitan si frontend y backend
    # están en el mismo dominio principal o dominios diferentes pero no subdominios relacionados.
    # Si los necesitaras, sería para compartir cookies entre subdominios (ej. .tudominio.com).
    CSRF_COOKIE_DOMAIN = None
    SESSION_COOKIE_DOMAIN = None
    
    # SAMESITE es importante para la seguridad CSRF. 'Lax' es un buen equilibrio.
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_SAMESITE = 'Lax'
    
    # Configuraciones adicionales de seguridad recomendadas para producción:
    SECURE_HSTS_SECONDS = 31536000 # Un año
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY' # Previene clickjacking

else: 
    # Hosts para desarrollo local
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# --- Aplicaciones Instaladas ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework', 
    'corsheaders',    
    'inventario',     # Tu única app personalizada
    'rest_framework_simplejwt',
]

# --- Middleware ---
# El orden es importante para el procesamiento de solicitudes.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # Debe ir después de SecurityMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',      # Debe ir lo más alto posible, antes de CommonMiddleware
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',  # Debe ir después de AuthenticationMiddleware si usas CSRF con sesión
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

# --- Configuración de Base de Datos ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Configuración de base de datos para producción (Render)
if 'DATABASE_URL' in os.environ:
    DATABASES['default'] = dj_database_url.config(
        conn_max_age=600,
        ssl_require=True
    )
    print("\n--- DEBUG DATABASE CONFIG ---")
    print("DATABASE_URL found in environment variables!")
    # No imprimir el valor real de DATABASE_URL en logs de producción por seguridad
    # print(f"DATABASE_URL value: {os.environ.get('DATABASE_URL')}") 
    print(f"Django's DATABASES['default'] configured as: {DATABASES['default']['ENGINE']} (SSL: True)")
    print("--- END DEBUG ---\n")
else:
    print("\n--- DEBUG DATABASE CONFIG ---")
    print("WARNING: DATABASE_URL NOT found in environment variables. Falling back to SQLite.")
    print(f"Django's DATABASES['default'] configured as: {DATABASES['default']['ENGINE']}")
    print("--- END DEBUG ---\n")

# --- Validadores de Contraseña ---
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

# --- Internacionalización y Zona Horaria ---
LANGUAGE_CODE = 'es-ar' 
TIME_ZONE = 'America/Argentina/Cordoba' 
USE_I18N = True
USE_TZ = True # Es crucial usar zonas horarias conscientes

# --- Archivos Estáticos ---
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles' 

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Configuración de CORS (Cross-Origin Resource Sharing) ---
# Define qué orígenes de frontend pueden acceder a tu API.
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",              # Tu frontend de desarrollo local
    "https://bonitoamorstock.onrender.com", # Tu frontend desplegado
    "https://bonito-amor-backend.onrender.com", # Si el backend también es un origen de CORS para sí mismo (raro, pero no dañino)
]
CORS_ALLOW_CREDENTIALS = True # Permite que se envíen cookies y encabezados de autorización (JWT)

# --- Orígenes Confiables para CSRF ---
# Lista de orígenes para los que se permite la funcionalidad CSRF.
# Necesario para que las solicitudes desde tu frontend incluyan la cookie CSRF.
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    'https://bonito-amor-backend.onrender.com', 
    "https://bonitoamorstock.onrender.com", 
]
# Agregado para que la cookie CSRF se envíe también desde dominios diferentes si usas la API desde un frontend distinto al backend.
# Generalmente, CORS_ALLOWED_ORIGINS es suficiente para esto si CORS está bien configurado.
# No es estrictamente necesario, pero puede ayudar en algunos escenarios con CSRF.
# CSRF_COOKIE_NAME = "csrftoken" # Valor por defecto, no necesitas definirlo a menos que quieras cambiarlo.

# --- Configuración de Django REST Framework ---
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        # Es muy recomendable usar IsAuthenticated por defecto para una API que requiere login.
        # Luego, las vistas públicas (registro, login) pueden anular esto con AllowAny.
        'rest_framework.permissions.IsAuthenticated', 
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication', # Para la interfaz de admin y navegadores
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10 # O el número de elementos que desees por página
}

# --- Configuración de Simple JWT ---
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15), # Aumentado a 15 min, 5 min puede ser muy corto
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),    # Aumentado a 7 días para conveniencia del usuario
    'ROTATE_REFRESH_TOKENS': False,                 # Si True, cada refresco genera un nuevo refresh token
    'BLACKLIST_AFTER_ROTATION': False,              # Si True y ROTATE_REFRESH_TOKENS es True, invalida el viejo refresh token
    'UPDATE_LAST_LOGIN': False,                     # Actualiza el campo last_login del usuario al iniciar sesión

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,                      # Usa tu clave secreta de Django
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,

    'AUTH_HEADER_TYPES': ('Bearer',),               # Tipo de encabezado de autorización
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=15),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=7),
}

# --- Configuración de Logging ---
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler', 
            'formatter': 'verbose', # Agregado: para un formato de log más detallado
        },
    },
    'formatters': { # Agregado: definición del formateador verbose
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
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
        # El logger raíz captura mensajes que no son manejados por otros loggers.
        '': { 
            'handlers': ['console'],
            'level': 'INFO', 
            'propagate': False,
        },
    },
}