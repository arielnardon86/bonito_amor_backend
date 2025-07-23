# BONITO_AMOR/backend/inventario/admin.py
from django.contrib import admin
from .models import Categoria, Producto, Venta, DetalleVenta, Tienda # Importa todos los modelos

# --- Registro del Modelo Tienda ---
@admin.register(Tienda)
class TiendaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'slug', 'descripcion')
    search_fields = ('nombre', 'slug')
    prepopulated_fields = {'slug': ('nombre',)} # Rellena automáticamente el slug al escribir el nombre

# --- Registro del Modelo Producto ---
@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'talle', 'codigo_barras', 'precio_venta', 'stock', 'tienda_nombre') # Añade 'tienda_nombre' para ver la tienda
    search_fields = ('nombre', 'codigo_barras', 'talle') 
    list_filter = ('stock', 'talle', 'tienda') # Permite filtrar por tienda
    list_editable = ('precio_venta', 'stock')

    # Método para mostrar el nombre de la tienda en list_display
    def tienda_nombre(self, obj):
        return obj.tienda.nombre if obj.tienda else 'N/A'
    tienda_nombre.short_description = 'Tienda' # Etiqueta de la columna

# --- Inline para DetalleVenta (para mostrar en la vista de Venta) ---
class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0 # No muestra campos vacíos por defecto
    fields = ('producto', 'cantidad', 'precio_unitario_venta') # Campos a mostrar
    readonly_fields = ('producto', 'cantidad', 'precio_unitario_venta') # Estos campos no deben ser editables aquí
    can_delete = False # No permitir eliminar detalles directamente desde la venta

# --- Registro del Modelo Venta ---
@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha_venta', 'total_venta', 'usuario_username', 'metodo_pago', 'anulada', 'tienda_nombre') # Añade campos relevantes
    list_filter = ('fecha_venta', 'anulada', 'metodo_pago', 'tienda') # Permite filtrar por tienda, anulada y método de pago
    inlines = [DetalleVentaInline] # Muestra los detalles de venta
    readonly_fields = ('fecha_venta', 'total_venta', 'usuario') # Campos que no deben ser editables

    # Método para mostrar el nombre de usuario en list_display
    def usuario_username(self, obj):
        return obj.usuario.username if obj.usuario else 'N/A'
    usuario_username.short_description = 'Vendedor'

    # Método para mostrar el nombre de la tienda en list_display
    def tienda_nombre(self, obj):
        return obj.tienda.nombre if obj.tienda else 'N/A'
    tienda_nombre.short_description = 'Tienda'

# --- Registro de otros modelos (si no tienen una clase Admin personalizada) ---
admin.site.register(Categoria)
# DetalleVenta no necesita un registro directo si solo se gestiona como inline de Venta.
# Si necesitas una vista separada para DetalleVenta, puedes registrarla aquí:
# admin.site.register(DetalleVenta)

# Si tienes un modelo de usuario personalizado y lo quieres en el admin (ya deberías tenerlo si usas UserViewSet):
# from django.contrib.auth.admin import UserAdmin
# from django.contrib.auth import get_user_model
# User = get_user_model()
# admin.site.register(User, UserAdmin)
