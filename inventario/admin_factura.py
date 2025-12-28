# Configuración para el modelo de Factura
# Agregar este código al final de admin.py

from django.contrib import admin
from .models import Factura

@admin.register(Factura)
class FacturaAdmin(admin.ModelAdmin):
    list_display = (
        'numero_factura_completo', 'tipo_comprobante', 'tienda', 'cliente_nombre', 
        'total', 'estado', 'cae', 'fecha_emision'
    )
    list_filter = ('estado', 'tipo_comprobante', 'sistema_facturacion', 'tienda', 'fecha_emision')
    search_fields = ('numero_comprobante', 'cliente_nombre', 'cliente_cuit', 'cae', 'numero_comprobante_afip')
    readonly_fields = (
        'id', 'venta', 'numero_comprobante', 'cae', 'fecha_vencimiento_cae', 
        'numero_comprobante_afip', 'estado', 'error_mensaje', 'respuesta_bruta',
        'fecha_emision', 'fecha_actualizacion'
    )
    
    fieldsets = (
        ('Información de la Factura', {
            'fields': (
                'venta', 'tienda', 'numero_comprobante', 'punto_venta', 
                'tipo_comprobante', 'numero_factura_completo', 'estado'
            )
        }),
        ('Datos del Cliente', {
            'fields': (
                'cliente_nombre', 'cliente_cuit', 'cliente_domicilio',
                'cliente_tipo_documento', 'cliente_condicion_iva'
            )
        }),
        ('Totales', {
            'fields': ('subtotal', 'impuesto_iva', 'total')
        }),
        ('Respuesta AFIP/ARCA', {
            'fields': (
                'sistema_facturacion', 'cae', 'fecha_vencimiento_cae',
                'numero_comprobante_afip', 'error_mensaje'
            ),
            'classes': ('collapse',)
        }),
        ('Información del Sistema', {
            'fields': ('id', 'fecha_emision', 'fecha_actualizacion', 'respuesta_bruta'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs.select_related('venta', 'tienda')
        elif request.user.tienda:
            return qs.filter(tienda=request.user.tienda).select_related('venta', 'tienda')
        return qs.none()


