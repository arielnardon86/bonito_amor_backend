# BONITO_AMOR/backend/inventario/admin.py
from django.contrib import admin
from .models import Categoria, Producto, Venta, DetalleVenta, Tienda # Importa el modelo Tienda

# --- Registro del Modelo Tienda ---
@admin.register(Tienda)
class TiendaAdmin(admin.ModelAdmin):
    # CORRECCIÓN AQUÍ: Cambiado 'descripcion' por 'direccion' o los campos que quieras mostrar
    list_display = ('nombre', 'slug', 'direccion', 'telefono', 'email', 'activa') 
    search_fields = ('nombre', 'slug', 'direccion') # Puedes añadir más campos para búsqueda
    prepopulated_fields = {'slug': ('nombre',)} 

# --- Registro del Modelo Producto ---
@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'talle', 'codigo_barras', 'precio_venta', 'stock', 'tienda_nombre') 
    search_fields = ('nombre', 'codigo_barras', 'talle') 
    list_filter = ('stock', 'talle', 'tienda') 
    list_editable = ('precio_venta', 'stock')

    def tienda_nombre(self, obj):
        return obj.tienda.nombre if obj.tienda else 'N/A'
    tienda_nombre.short_description = 'Tienda' 

# --- Inline para DetalleVenta (para mostrar en la vista de Venta) ---
class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0 
    fields = ('producto', 'cantidad', 'precio_unitario_venta') 
    readonly_fields = ('producto', 'cantidad', 'precio_unitario_venta') 
    can_delete = False 

# --- Registro del Modelo Venta ---
@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha_venta', 'total_venta', 'usuario_username', 'metodo_pago', 'anulada', 'tienda_nombre') 
    list_filter = ('fecha_venta', 'anulada', 'metodo_pago', 'tienda') 
    inlines = [DetalleVentaInline] 
    readonly_fields = ('fecha_venta', 'total_venta', 'usuario') 

    def usuario_username(self, obj):
        return obj.usuario.username if obj.usuario else 'N/A'
    usuario_username.short_description = 'Vendedor'

    def tienda_nombre(self, obj):
        return obj.tienda.nombre if obj.tienda else 'N/A'
    tienda_nombre.short_description = 'Tienda'

# --- Registro de otros modelos (si no tienen una clase Admin personalizada) ---
admin.site.register(Categoria)
# admin.site.register(DetalleVenta) # Comentado si solo se gestiona como inline

# Si tienes un modelo de usuario personalizado y lo quieres en el admin:
# from django.contrib.auth.admin import UserAdmin
# from django.contrib.auth import get_user_model
# User = get_user_model()
# admin.site.register(User, UserAdmin)
