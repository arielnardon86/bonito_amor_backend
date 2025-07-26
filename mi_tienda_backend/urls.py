# BONITO_AMOR/backend/mi_tienda_backend/urls.py
from django.contrib import admin
from django.urls import path, include
# CAMBIO CLAVE: Importar views desde 'inventario'
from inventario import views as inventario_views # Alias para evitar conflictos de nombres

urlpatterns = [
    path('admin/', admin.site.urls),
    # Incluir las URLs de tu aplicación 'inventario'
    path('api/', include('inventario.urls')),
    # Puedes añadir otras URLs aquí si las tienes
]
