# BONITO_AMOR/backend/inventario/filters.py
import django_filters
from django.db.models import Exists, OuterRef, Q # Importar Exists, OuterRef, Q
from .models import Venta, DetalleVenta, Producto, User, MetodoPago 

class VentaFilter(django_filters.FilterSet):
    fecha_venta__date = django_filters.DateFilter(field_name='fecha_venta', lookup_expr='date')
    usuario = django_filters.UUIDFilter(field_name='usuario__id')
    
    # Use MethodFilter for the 'anulada' field
    anulada = django_filters.MethodFilter(method='filter_by_anulada_status')

    class Meta:
        model = Venta
        fields = [
            'fecha_venta__date', 
            'tienda', 
            'metodo_pago',
            'usuario',
            'anulada', # Ensure it's in fields
        ]

    def filter_by_anulada_status(self, queryset, name, value):
        """
        Filters sales based on whether they are completely annulled or if all their details are annulled.
        'value' will be a boolean (True/False) because the frontend sends 'true'/'false' and django-filter interprets it.
        """
        # If the value is None (frontend sends ''), it means "All", do not apply annulled filter
        if value is None: 
            return queryset
        
        if value: # If the value is True (frontend sends 'true'), search for annulled sales
            # A sale is considered "annulled" if:
            # 1. Its 'anulada' field is True (complete sale annulment)
            # OR
            # 2. Its 'anulada' field is False, but there is NO active detail for that sale
            #    (i.e., all its details are individually annulled).
            
            # Subquery to check if there is at least one detail NOT individually annulled
            has_active_details = DetalleVenta.objects.filter(
                venta=OuterRef('pk'), # Relate to the main sale
                anulado_individualmente=False # Search for details that are NOT annulled
            )

            # Filter by sales that are completely annulled (anulada=True)
            # OR by sales that are not completely annulled (anulada=False) AND
            # do not have active details (i.e., all their details are individually annulled).
            queryset = queryset.filter(
                Q(anulada=True) | (Q(anulada=False) & ~Exists(has_active_details)) # Corrected syntax here
            )
        else: # If the value is False (frontend sends 'false'), search for NON-annulled sales
            # A sale is considered "NON-annulled" if:
            # 1. Its 'anulada' field is False (it is not completely annulled)
            # AND
            # 2. There EXISTS at least one sale detail for that sale that is NOT individually annulled.
            #    (i.e., it has at least one active detail).
            
            # Subquery to check if there is at least one detail NOT individually annulled
            has_active_details = DetalleVenta.objects.filter(
                venta=OuterRef('pk'),
                anulado_individualmente=False
            )

            queryset = queryset.filter(
                Q(anulada=False) & Q(Exists(has_active_details)) # Corrected syntax here
            )
        
        return queryset

