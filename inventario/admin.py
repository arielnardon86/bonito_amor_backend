# Store/backend/inventario/admin.py

from django.contrib import admin
from .models import Producto # Solo importa Producto, ya que Venta y DetalleVenta no están definidos aún.

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    # ¡Añade 'talle' a list_display y a search_fields si quieres!
    list_display = ('nombre', 'talle', 'codigo_barras', 'precio_venta', 'stock')
    search_fields = ('nombre', 'codigo_barras', 'talle') # Puedes buscar por talle
    list_filter = ('stock', 'talle') # Puedes filtrar por talle
    list_editable = ('precio_venta', 'stock')


# Comentar o eliminar temporalmente las siguientes clases y registros
# hasta que los modelos Venta y DetalleVenta estén definidos en inventario/models.py
"""
# class DetalleVentaInline(admin.TabularInline):
#     model = DetalleVenta
#     extra = 0
#     # producto_talle es un campo calculado en el serializador, no en el modelo DetalleVenta
#     # Si quieres mostrar el talle aquí, necesitarías un campo directamente en DetalleVenta
#     # o un método en DetalleVenta para accederlo
#     readonly_fields = ('producto', 'cantidad', 'precio_unitario_venta', 'subtotal')
#     can_delete = False

# @admin.register(Venta)
# class VentaAdmin(admin.ModelAdmin):
#     list_display = ('id', 'fecha_venta', 'total_venta')
#     list_filter = ('fecha_venta',)
#     inlines = [DetalleVentaInline]
#     readonly_fields = ('fecha_venta', 'total_venta')
"""