# BONITO_AMOR/backend/inventario/filters.py
import django_filters
from .models import Venta, DetalleVenta, Producto, User, MetodoPago 

class VentaFilter(django_filters.FilterSet):
    fecha_venta__date = django_filters.DateFilter(field_name='fecha_venta', lookup_expr='date')
    usuario = django_filters.UUIDFilter(field_name='usuario__id')
    anulada = django_filters.BooleanFilter(field_name='anulada') # Esto es clave para el filtro booleano

    class Meta:
        model = Venta
        fields = [
            'fecha_venta__date', 
            'tienda', 
            'metodo_pago',
            'usuario',
            'anulada',
        ]

