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

    # Filtro para tienda por ID (asumiendo que el frontend envía el ID de la tienda)
    tienda = django_filters.UUIDFilter(field_name='tienda__id') # Si el frontend envía el UUID de la tienda
    # Si el frontend envía el slug de la tienda, usarías:
    # tienda_slug = django_filters.CharFilter(field_name='tienda__nombre', lookup_expr='exact')

    # Filtro por método de pago (asumiendo que el frontend envía el ID del método de pago)
    # Si metodo_pago es un CharField en el modelo Venta, y el frontend envía el nombre:
    metodo_pago = django_filters.CharFilter(field_name='metodo_pago', lookup_expr='exact')
    # Si metodo_pago es un ForeignKey a MetodoPago, y el frontend envía el ID:
    # metodo_pago = django_filters.UUIDFilter(field_name='metodo_pago__id')

    # Filtro por usuario (vendedor) por ID
    usuario = django_filters.UUIDFilter(field_name='usuario__id')

    # Filtro para el estado de anulación (BooleanField)
    anulada = django_filters.BooleanFilter(field_name='anulada')

    class Meta:
        model = Venta
        fields = [
            'fecha_venta_gte', 'fecha_venta_lte',
            'fecha_venta__year', 'fecha_venta__month', 'fecha_venta__day',
            'tienda', # O 'tienda_slug' si usas el slug
            'metodo_pago',
            'usuario',
            'anulada',
            'total', # Si quieres filtrar por rango de total, puedes añadirlo aquí
        ]

