"""
Panel de administración de clientes SaaS (/admin/clientes-saas en el
frontend) -- lista todas las tiendas que le pagan la suscripción de Total
Stock a Ariel, con su estado (vía Mercado Pago, automático) y permite marcar
a mano el pago de las tiendas legacy que pagan por fuera de MP.

Acceso gateado por User.es_operador_plataforma, NO por is_superuser: TODOS
los dueños de tienda se registran con is_superuser=True (ver registro_publico
en views.py) -- son dueños de SU tienda, no de Total Stock, así que ese flag
no sirve acá. es_operador_plataforma valida además contra un allowlist de
emails explícito (settings.PLATFORM_ADMIN_EMAILS).
"""
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Tienda, PagoManualSuscripcion
from .plan_enforcement import info_suscripcion


class EsOperadorPlataforma(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.es_operador_plataforma)


def _tienda_facturacion_nombre():
    return getattr(settings, 'TIENDA_SUSCRIPCIONES_NOMBRE', 'Total Stock')


def _serializar_pago(pago):
    return {
        'id': str(pago.id),
        'mes': pago.mes,
        'anio': pago.anio,
        'monto': str(pago.monto) if pago.monto is not None else None,
        'fecha_pago': pago.fecha_pago,
        'nota': pago.nota or '',
        'registrado_por': pago.registrado_por.username if pago.registrado_por_id else None,
    }


class ClientesSaaSListView(APIView):
    """GET: todas las tiendas (salvo la interna de facturación propia) con su
    estado de suscripción (info_suscripcion, igual que el panel de la tienda
    misma) + el último pago manual registrado, para la tabla principal del
    panel."""
    permission_classes = [EsOperadorPlataforma]

    def get(self, request):
        # select_related de suscripcion/plan: info_suscripcion() accede a
        # tienda.suscripcion y sus.plan por cada tienda -- sin esto, cada
        # acceso dispara su propia query (N+1).
        tiendas = Tienda.objects.exclude(nombre=_tienda_facturacion_nombre()) \
            .select_related('suscripcion', 'suscripcion__plan', 'hereda_suscripcion_de') \
            .order_by('nombre')
        hoy = timezone.localdate()

        pagos_por_tienda = {}
        for pago in PagoManualSuscripcion.objects.filter(tienda__in=tiendas).select_related('registrado_por').order_by('-anio', '-mes'):
            pagos_por_tienda.setdefault(pago.tienda_id, []).append(pago)

        resultado = []
        for tienda in tiendas:
            info = info_suscripcion(tienda)
            # El logo (base64) no se muestra en este panel -- pesa mucho y
            # multiplicado por todas las tiendas hacía lenta la carga de la
            # lista para nada.
            info.pop('logo', None)
            pagos_tienda = pagos_por_tienda.get(tienda.id, [])
            ultimo_pago = pagos_tienda[0] if pagos_tienda else None
            # mp_payer_email vive en la Suscripcion PROPIA de esta tienda, no
            # en info_suscripcion() (que para una tienda con hereda_suscripcion_de
            # devuelve el estado de la tienda principal) -- siempre el email con
            # el que ESTA tienda se suscribió, no el de la que hereda.
            try:
                mp_payer_email = tienda.suscripcion.mp_payer_email or None
            except Exception:
                mp_payer_email = None
            resultado.append({
                'tienda_id': str(tienda.id),
                **info,
                'mp_payer_email': mp_payer_email,
                'requiere_eleccion_plan': tienda.requiere_eleccion_plan,
                'hereda_suscripcion_de': tienda.hereda_suscripcion_de.nombre if tienda.hereda_suscripcion_de_id else None,
                'ultimo_pago_manual': _serializar_pago(ultimo_pago) if ultimo_pago else None,
                'pago_manual_mes_actual': any(p.mes == hoy.month and p.anio == hoy.year for p in pagos_tienda),
            })
        return Response(resultado)


class PagosManualesTiendaView(APIView):
    """GET: historial de pagos manuales de una tienda.
    POST: carga (o actualiza, si ya existe uno para ese mes/año) un pago
    manual -- upsert por (tienda, mes, año), ver unique_pago_manual_tienda_mes_anio."""
    permission_classes = [EsOperadorPlataforma]

    def get(self, request, tienda_id):
        tienda = get_object_or_404(Tienda, id=tienda_id)
        pagos = PagoManualSuscripcion.objects.filter(tienda=tienda).select_related('registrado_por').order_by('-anio', '-mes')
        return Response([_serializar_pago(p) for p in pagos])

    def post(self, request, tienda_id):
        tienda = get_object_or_404(Tienda, id=tienda_id)

        try:
            mes = int(request.data.get('mes'))
            anio = int(request.data.get('anio'))
        except (TypeError, ValueError):
            return Response({'error': 'Mes y año son obligatorios y deben ser numéricos.'}, status=400)
        if not (1 <= mes <= 12):
            return Response({'error': 'Mes inválido.'}, status=400)

        monto = request.data.get('monto') or None
        nota = (request.data.get('nota') or '').strip()
        fecha_pago = request.data.get('fecha_pago') or timezone.localdate()

        pago, _creado = PagoManualSuscripcion.objects.update_or_create(
            tienda=tienda, mes=mes, anio=anio,
            defaults={
                'monto': monto,
                'nota': nota,
                'fecha_pago': fecha_pago,
                'registrado_por': request.user,
            },
        )
        return Response(_serializar_pago(pago), status=201)


class PagoManualDeleteView(APIView):
    """DELETE: borra un pago manual cargado por error."""
    permission_classes = [EsOperadorPlataforma]

    def delete(self, request, pago_id):
        pago = get_object_or_404(PagoManualSuscripcion, id=pago_id)
        pago.delete()
        return Response(status=204)
