# BONITO_AMOR/backend/inventario/filters.py
import django_filters
from django.db.models import Exists, OuterRef, Q # Importar Exists, OuterRef, Q
from .models import Venta, DetalleVenta, Producto, User, MetodoPago 

class VentaFilter(django_filters.FilterSet):
    fecha_venta__date = django_filters.DateFilter(field_name='fecha_venta', lookup_expr='date')
    usuario = django_filters.UUIDFilter(field_name='usuario__id')
    
    # CAMBIO CLAVE AQUÍ: Usar django_filters.Filter en lugar de MethodFilter
    anulada = django_filters.Filter(method='filter_by_anulada_status')

    class Meta:
        model = Venta
        fields = [
            'fecha_venta__date', 
            'tienda', 
            'metodo_pago',
            'usuario',
            'anulada', # Asegurarse de que esté en fields
        ]

    def filter_by_anulada_status(self, queryset, name, value):
        """
        Filtra las ventas basándose en si están completamente anuladas o si todos sus detalles están anulados.
        'value' será un booleano (True/False) porque el frontend envía 'true'/'false' y django-filter lo interpreta.
        """
        # Si el valor es None (frontend envía ''), significa "Todas", no aplicar filtro de anulada
        if value is None: 
            return queryset
        
        if value: # Si el valor es True (frontend envía 'true'), buscar ventas anuladas
            # Una venta se considera "anulada" si:
            # 1. Su campo 'anulada' es True (anulación completa de la venta)
            # O
            # 2. Su campo 'anulada' es False, pero NO EXISTE ningún detalle de venta para esa venta
            #    que NO esté anulado individualmente. Es decir, todos sus detalles están anulados.
            
            # Subconsulta para verificar si existe al menos un detalle NO anulado individualmente
            has_active_details = DetalleVenta.objects.filter(
                venta=OuterRef('pk'), # Relacionar con la venta principal
                anulado_individualmente=False # Buscar detalles que NO estén anulados
            )

            # Filtrar por ventas que están completamente anuladas (anulada=True)
            # OR por ventas que no están completamente anuladas (anulada=False) AND
            # no tienen detalles activos (es decir, todos sus detalles están individualmente anulados).
            queryset = queryset.filter(
                Q(anulada=True) | (Q(anulada=False) & ~Exists(has_active_details)) 
            )
        else: # Si el valor es False (frontend envía 'false'), buscar ventas NO anuladas
            # Una venta se considera "NO anulada" si:
            # 1. Su campo 'anulada' es False (no está completamente anulada)
            # AND
            # 2. EXISTE al menos un detalle de venta para esa venta que NO esté anulado individualmente.
            #    (Es decir, tiene al menos un detalle activo).
            
            # Subconsulta para verificar si existe al menos un detalle NO anulado individualmente
            has_active_details = DetalleVenta.objects.filter(
                venta=OuterRef('pk'),
                anulado_individualmente=False
            )

            queryset = queryset.filter(
                Q(anulada=False) & Q(Exists(has_active_details)) 
            )
        
        return queryset

