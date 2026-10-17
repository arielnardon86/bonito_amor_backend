"""
Panel de administración de clientes SaaS (/admin/clientes-saas en el
frontend) -- lista todas las tiendas que le pagan la suscripción de Total
Stock a Ariel, con su estado (vía Mercado Pago, automático) y permite marcar
a mano el pago de las tiendas legacy que pagan por fuera de MP.

Acceso gateado por User.es_operador_plataforma, NO por is_superuser: TODOS
los dueños de tienda se registran con is_superuser=True (ver registro_publico
en views.py) -- son dueños de SU tienda, no de Total Stock, así que ese flag
no sirve acá. es_operador_plataforma es un campo editable a mano desde Django
Admin (fieldset "Total Stock (equipo interno)" en CustomUserAdmin).
"""
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.db.models.functions import ExtractMonth, ExtractYear
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Tienda, PagoManualSuscripcion, Venta
from .plan_enforcement import info_suscripcion
from .services.suscripcion_service import obtener_preaprobacion


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
        # defer('logo', ...): este panel no muestra el logo, pero sin el defer
        # Django lo trae igual (SELECT * de por sí incluye ese TextField en
        # base64, pesado) para cada tienda y cada hereda_suscripcion_de -- de
        # la mano con incluir_logo=False más abajo, que evita acceder a
        # tienda.logo (si se accediera con el campo diferido, dispararía una
        # query extra por fila en vez de ahorrar nada).
        tiendas = Tienda.objects.exclude(nombre=_tienda_facturacion_nombre()) \
            .select_related('suscripcion', 'suscripcion__plan', 'hereda_suscripcion_de') \
            .defer('logo', 'hereda_suscripcion_de__logo') \
            .order_by('nombre')
        hoy = timezone.localdate()
        inicio_mes = hoy.replace(day=1)

        pagos_por_tienda = {}
        for pago in PagoManualSuscripcion.objects.filter(tienda__in=tiendas).select_related('registrado_por').order_by('-anio', '-mes'):
            pagos_por_tienda.setdefault(pago.tienda_id, []).append(pago)

        # Una sola consulta agregada para todas las tiendas (no una por fila):
        # lo que Mercado Pago efectivamente cobró este mes, según el libro de
        # cobros (Venta con origen_mp_suscripcion=True, ver _facturar_cobro_
        # suscripcion en views.py), agrupado por tienda_cliente.
        cobrado_mp_por_tienda = {
            row['tienda_cliente_id']: row['total']
            for row in Venta.objects.filter(
                origen_mp_suscripcion=True, anulada=False,
                tienda_cliente__in=tiendas, fecha_venta__date__gte=inicio_mes,
            ).values('tienda_cliente_id').annotate(total=Sum('total'))
        }

        resultado = []
        for tienda in tiendas:
            info = info_suscripcion(tienda, incluir_logo=False)
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
                'cobrado_mp_mes_actual': str(cobrado_mp_por_tienda[tienda.id]) if tienda.id in cobrado_mp_por_tienda else None,
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


class DiagnosticoMPView(APIView):
    """GET: devuelve crudo lo que MP contesta para el preapproval de esta
    tienda -- diagnóstico puntual para cuando el panel no coincide con lo que
    se ve en el dashboard de MP (ej. pago_atrasado no se marca aunque en MP
    figure "Atrasado"). El campo que usa la reconciliación diaria
    (resumen.pending_charge_quantity, ver _reconciliar_con_mp en
    procesar_gracia_suscripciones.py) nunca se confirmó contra un payload
    real de un caso atrasado -- esto es para ver qué manda MP de verdad."""
    permission_classes = [EsOperadorPlataforma]

    def get(self, request, tienda_id):
        tienda = get_object_or_404(Tienda, id=tienda_id)
        try:
            sus = tienda.suscripcion
        except Exception:
            return Response({'error': 'Esta tienda no tiene suscripción propia (es legacy o hereda de otra).'}, status=400)

        if not sus.mp_preapproval_id:
            return Response({'error': 'Esta suscripción no tiene mp_preapproval_id vinculado.'}, status=400)

        try:
            datos_mp = obtener_preaprobacion(sus.mp_preapproval_id)
        except Exception as e:
            return Response({'error': f'Error consultando MP: {e}'}, status=502)

        return Response({
            'tienda': tienda.nombre,
            'local': {
                'estado': sus.estado,
                'pago_atrasado': sus.pago_atrasado,
                'mp_preapproval_id': sus.mp_preapproval_id,
            },
            'mp_crudo': datos_mp,
        })


class RecaudacionSaaSView(APIView):
    """GET: recaudación mensual de Total Stock -- lo cobrado por Mercado Pago
    (Venta con origen_mp_suscripcion=True, el "libro de cobros" que ya crea
    _facturar_cobro_suscripcion en views.py) más lo cargado a mano
    (PagoManualSuscripcion), mes a mes. Para el panel de resumen y el
    histórico de meses anteriores -- no hace falta golpear la API de MP en
    vivo, los montos ya quedaron asentados cuando se cobraron.

    ?meses=N controla cuántos meses hacia atrás trae (default 12, incluyendo
    el actual, que puede estar parcial si todavía no vencieron todos los
    días de cobro del mes)."""
    permission_classes = [EsOperadorPlataforma]

    def get(self, request):
        try:
            meses = int(request.query_params.get('meses', 12))
        except (TypeError, ValueError):
            meses = 12
        meses = max(1, min(meses, 36))

        hoy = timezone.localdate()
        periodos = []
        anio, mes = hoy.year, hoy.month
        for _ in range(meses):
            periodos.append((anio, mes))
            mes -= 1
            if mes == 0:
                mes, anio = 12, anio - 1

        primer_anio, primer_mes = periodos[-1]
        inicio = date(primer_anio, primer_mes, 1)

        mp_por_periodo = {
            (row['anio'], row['mes']): row['total']
            for row in Venta.objects.filter(
                origen_mp_suscripcion=True, anulada=False, fecha_venta__date__gte=inicio,
            ).annotate(anio=ExtractYear('fecha_venta'), mes=ExtractMonth('fecha_venta'))
            .values('anio', 'mes').annotate(total=Sum('total'))
        }
        manual_por_periodo = {
            (row['anio'], row['mes']): row['total']
            for row in PagoManualSuscripcion.objects.filter(anio__gte=primer_anio)
            .values('anio', 'mes').annotate(total=Sum('monto'))
        }

        historial = []
        for anio, mes in periodos:
            total_mp = mp_por_periodo.get((anio, mes)) or Decimal('0')
            total_manual = manual_por_periodo.get((anio, mes)) or Decimal('0')
            historial.append({
                'anio': anio,
                'mes': mes,
                'total_mp': str(total_mp),
                'total_manual': str(total_manual),
                'total': str(total_mp + total_manual),
            })

        return Response({'historial': historial})


class DiagnosticoVentasMPView(APIView):
    """GET: diagnóstico puntual de por qué "Cobrado MP (mes)" / recaudación
    puede estar dando $0 -- las Venta con origen_mp_suscripcion=True creadas
    ANTES de que existiera el campo tienda_cliente (ver migración
    0103_venta_tienda_cliente) dependen de un backfill por CUIT/nombre; si
    ese backfill no matcheó (CUIT con formato distinto, tienda renombrada,
    etc.), esas ventas quedan sin tienda_cliente y no entran en ninguna suma
    por tienda ni por mes. Esto muestra cuántas quedaron así y una muestra
    para ver por qué no matchearon."""
    permission_classes = [EsOperadorPlataforma]

    def get(self, request):
        ventas_mp = Venta.objects.filter(origen_mp_suscripcion=True, anulada=False)
        total = ventas_mp.count()
        sin_tienda = ventas_mp.filter(tienda_cliente__isnull=True).order_by('-fecha_venta')

        muestra = []
        for v in sin_tienda[:15]:
            tienda_por_cuit = Tienda.objects.filter(cuit=v.cliente_cuit).first() if v.cliente_cuit else None
            tienda_por_nombre = Tienda.objects.filter(nombre=v.cliente_nombre).first() if v.cliente_nombre else None
            muestra.append({
                'venta_id': str(v.id),
                'fecha_venta': v.fecha_venta,
                'total': str(v.total),
                'cliente_nombre_guardado': v.cliente_nombre,
                'cliente_cuit_guardado': v.cliente_cuit,
                'matchea_por_cuit': tienda_por_cuit.nombre if tienda_por_cuit else None,
                'matchea_por_nombre': tienda_por_nombre.nombre if tienda_por_nombre else None,
                'mp_authorized_payment_id': v.mp_authorized_payment_id,
            })

        return Response({
            'total_ventas_mp': total,
            'con_tienda_cliente': total - sin_tienda.count(),
            'sin_tienda_cliente': sin_tienda.count(),
            'muestra_sin_vincular': muestra,
        })
