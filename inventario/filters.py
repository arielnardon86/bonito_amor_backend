# BONITO_AMOR/backend/inventario/filters.py
import django_filters
from .models import Venta, DetalleVenta, Producto, User, MetodoPago # Importa todos los modelos necesarios

class VentaFilter(django_filters.FilterSet):
    # Filtro para rango de fechas (gte: greater than or equal, lte: less than or equal)
    fecha_venta_gte = django_filters.DateFilter(field_name='fecha_venta', lookup_expr='date__gte')
    fecha_venta_lte = django_filters.DateFilter(field_name='fecha_venta', lookup_expr='date__lte')
    
    # Filtro exacto para año, mes, día
    fecha_venta__year = django_filters.NumberFilter(field_name='fecha_venta', lookup_expr='year')
    fecha_venta__month = django_filters.NumberFilter(field_name='fecha_venta', lookup_expr='month')
    fecha_venta__day = django_filters.NumberFilter(field_name='fecha_venta', lookup_expr='day')

    # CORRECCIÓN CLAVE: Añadir este filtro explícito para 'fecha_venta__date'
    fecha_venta__date = django_filters.DateFilter(field_name='fecha_venta', lookup_expr='date')

    # Filtro para tienda por ID (asumiendo que el frontend envía el ID de la tienda)
    tienda = django_filters.UUIDFilter(field_name='tienda__id') # Si el frontend envía el UUID de la tienda

    # Filtro por método de pago (asumiendo que el frontend envía el nombre del método de pago como cadena)
    metodo_pago = django_filters.CharFilter(field_name='metodo_pago', lookup_expr='exact')

    # Filtro por usuario (vendedor) por ID
    usuario = django_filters.UUIDFilter(field_name='usuario__id')

    # Filtro para el estado de anulación (BooleanField)
    anulada = django_filters.BooleanFilter(field_name='anulada')

    class Meta:
        model = Venta
        fields = [
            'fecha_venta_gte', 'fecha_venta_lte',
            'fecha_venta__year', 'fecha_venta__month', 'fecha_venta__day',
            'fecha_venta__date', # Incluirlo aquí también para que django-filter lo reconozca
            'tienda', 
            'metodo_pago',
            'usuario',
            'anulada',
            'total', # Si quieres filtrar por rango de total, puedes añadirlo aquí
        ]

