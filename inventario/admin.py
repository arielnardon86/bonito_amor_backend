# BONITO_AMOR/backend/inventario/admin.py
from django.contrib import admin
# Ya no necesitamos importar UserProfile aquí
from .models import Categoria, Producto, Venta, DetalleVenta, Tienda 

# Importaciones para extender UserAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model

User = get_user_model() # Obtener el modelo de usuario personalizado

# Register your models here.

@admin.register(Tienda)
class TiendaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'slug', 'direccion', 'telefono', 'email', 'fecha_creacion')
    prepopulated_fields = {'slug': ('nombre',)}
    search_fields = ('nombre', 'direccion', 'email')
    list_filter = ('fecha_creacion',)

class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0
    raw_id_fields = ('producto',) # Para facilitar la selección de productos si hay muchos

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tienda', 'categoria', 'precio', 'stock', 'fecha_creacion')
    list_filter = ('tienda', 'categoria', 'fecha_creacion')
    search_fields = ('nombre', 'descripcion')
    raw_id_fields = ('categoria', 'tienda') # Para facilitar la selección de categoría y tienda

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'tienda', 'fecha_venta', 'total', 'metodo_pago', 'cliente_nombre')
    list_filter = ('tienda', 'metodo_pago', 'fecha_venta')
    search_fields = ('id', 'cliente_nombre', 'cliente_email')
    inlines = [DetalleVentaInline]
    readonly_fields = ('fecha_venta', 'total') # El total se calcula automáticamente

# No necesitamos desregistrar User, el decorador @admin.register lo manejará.

# Ya no necesitamos UserProfileInline
# class UserProfileInline(admin.StackedInline):
#     model = UserProfile
#     can_delete = False
#     verbose_name_plural = 'Perfil de Usuario'
#     fields = ('tienda',) 

# Registrar el modelo User con el UserAdmin personalizado
@admin.register(User) 
class UserAdmin(BaseUserAdmin):
    # Ya no necesitamos inlines para UserProfile
    # inlines = (UserProfileInline,) 

    # Añade 'tienda' directamente a fieldsets para que sea editable en el admin
    fieldsets = BaseUserAdmin.fieldsets + (
        (None, {'fields': ('tienda',)}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (None, {'fields': ('tienda',)}),
    )

    # Añade 'tienda' a list_display para ver la tienda directamente en la lista de usuarios
    list_display = BaseUserAdmin.list_display + ('tienda',) # Accede directamente al campo 'tienda'

    # Ya no necesitamos get_tienda porque 'tienda' es un campo directo
    # def get_tienda(self, obj):
    #     return obj.profile.tienda.nombre if hasattr(obj, 'profile') and obj.profile.tienda else 'N/A'
    # get_tienda.short_description = 'Tienda Asignada'

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion')
    search_fields = ('nombre',)

