# Store/backend/inventario/views.py
from django.db.models import Sum, F, Window, Count # Asegúrate de que Count esté importado
from django.db.models.functions import TruncMonth, TruncDay, TruncYear, Rank
from django.contrib.auth import get_user_model # Necesario para obtener usuarios si no lo tienes
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import connection

# Importa tus modelos de Venta y DetalleVenta
from .models import Venta, DetalleVenta


class MetricasVentaView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser] # Solo admins pueden acceder

    def get(self, request, *args, **kwargs):
        year = request.query_params.get('year')
        month = request.query_params.get('month')
        day = request.query_params.get('day')
        seller_id = request.query_params.get('seller_id') # <-- NUEVO: FILTRO POR VENDEDOR

        # Calcular rango de fechas
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=365 * 5) # Por defecto, últimos 5 años (ajusta si quieres más)

        if year:
            try:
                year = int(year)
                start_date = datetime(year, 1, 1).date()
                end_date = datetime(year, 12, 31).date()

                if month:
                    month = int(month)
                    start_date = datetime(year, month, 1).date()
                    # Calcular el último día del mes
                    if month == 12:
                        end_date = datetime(year, 12, 31).date()
                    else:
                        end_date = (datetime(year, month + 1, 1) - timedelta(days=1)).date()

                    if day:
                        day = int(day)
                        start_date = datetime(year, month, day).date()
                        end_date = datetime(year, month, day).date()
            except ValueError:
                return Response({"detail": "Formato de fecha inválido."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Filtro base que se aplica a las ventas
        base_filter_ventas = {'fecha_venta__date__range': [start_date, end_date]}

        if seller_id: # <-- Aplicar filtro de vendedor si existe
            try:
                seller_id = int(seller_id)
                base_filter_ventas['usuario_id'] = seller_id
            except ValueError:
                return Response({"detail": "ID de vendedor inválido."}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Total de ventas y productos vendidos en el período
        # Se aplica el filtro base directamente a las Ventas
        total_ventas_periodo = Venta.objects.filter(**base_filter_ventas).aggregate(
            total_monto=Sum('total_venta'),
            total_productos=Sum('detalles__cantidad')
        )
        total_ventas = total_ventas_periodo.get('total_monto') or 0
        total_productos = total_ventas_periodo.get('total_productos') or 0

        # 2. Ventas por usuario
        ventas_por_usuario = Venta.objects.filter(**base_filter_ventas).values('usuario__username').annotate(
            monto_total_vendido=Sum('total_venta'),
            cantidad_ventas=Count('id')
        ).order_by('-monto_total_vendido')

        # 3. Productos vendidos (ya no "más vendidos" o "top 10")
        # Aquí, el filtro de vendedor se aplica a las ventas y luego a sus detalles
        productos_vendidos_query = DetalleVenta.objects.filter(
            venta__in=Venta.objects.filter(**base_filter_ventas) # Esto aplica fecha y vendedor a la base
        ).values('producto__nombre').annotate(
            cantidad_total=Sum('cantidad'),
            monto_total=Sum(F('cantidad') * F('precio_unitario_venta'))
        ).order_by('-monto_total') # Orden descendente por monto

        productos_vendidos = list(productos_vendidos_query) # Convertir a lista

        # 4. Tendencia de ventas agrupadas por período
        # La lógica de agrupamiento usa el mismo filtro base
        group_by_label = "Año"
        if day:
            ventas_agrupadas = Venta.objects.filter(**base_filter_ventas).annotate(
                period=TruncDay('fecha_venta')
            ).values('period').annotate(
                total_monto=Sum('total_venta'),
                cantidad_ventas=Count('id')
            ).order_by('period')
            group_by_label = "Día"
        elif month:
            ventas_agrupadas = Venta.objects.filter(**base_filter_ventas).annotate(
                period=TruncDay('fecha_venta')
            ).values('period').annotate(
                total_monto=Sum('total_venta'),
                cantidad_ventas=Count('id')
            ).order_by('period')
            group_by_label = "Día"
        elif year:
            ventas_agrupadas = Venta.objects.filter(**base_filter_ventas).annotate(
                period=TruncMonth('fecha_venta')
            ).values('period').annotate(
                total_monto=Sum('total_venta'),
                cantidad_ventas=Count('id')
            ).order_by('period')
            group_by_label = "Mes"
        else: # Si no hay filtros de fecha (o solo por vendedor), agrupar por año
            ventas_agrupadas = Venta.objects.filter(**base_filter_ventas).annotate(
                period=TruncYear('fecha_venta')
            ).values('period').annotate(
                total_monto=Sum('total_venta'),
                cantidad_ventas=Count('id')
            ).order_by('period')
            group_by_label = "Año"

        # Formatear las fechas para el frontend
        formatted_ventas_agrupadas = []
        for item in ventas_agrupadas:
            if item['period']:
                if group_by_label == "Día":
                    date_str = item['period'].strftime('%Y-%m-%d')
                elif group_by_label == "Mes":
                    date_str = item['period'].strftime('%Y-%m')
                else: # Año
                    date_str = item['period'].strftime('%Y')
                formatted_ventas_agrupadas.append({
                    'fecha': date_str,
                    'total_monto': item['total_monto'] or 0,
                    'cantidad_ventas': item['cantidad_ventas']
                })

        response_data = {
            "total_ventas_periodo": total_ventas,
            "total_productos_vendidos_periodo": total_productos,
            "ventas_por_usuario": list(ventas_por_usuario),
            "productos_mas_vendidos": list(productos_vendidos), # La clave sigue siendo la misma por compatibilidad con el frontend
            "ventas_agrupadas_por_periodo": {
                "label": group_by_label,
                "data": formatted_ventas_agrupadas
            }
        }
        return Response(response_data, status=status.HTTP_200_OK)