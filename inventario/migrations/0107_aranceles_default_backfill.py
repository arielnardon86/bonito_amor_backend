from decimal import Decimal

from django.db import migrations

PLAN_CHOICES_VALUES = ['CONTADO', '1', '3', '6', '12', 'Z']


def backfill_aranceles_default(apps, schema_editor):
    """Precarga, para cada tienda ya existente, los aranceles de los métodos
    de pago financieros (ej. Tarjeta de Crédito) en 0.00% para todos los
    planes predefinidos -- de ahora en más el cliente solo edita el %
    retenido en vez de tener que crear cada combinación a mano (ver
    inventario.models.asegurar_aranceles_default, usado para tiendas/
    métodos nuevos desde este punto en adelante).

    'QR Mercado Pago' se precarga también, pero solo para las tiendas que ya
    tenían la cuenta conectada antes de este cambio -- las demás lo reciben
    recién al conectar (MercadoPagoPosService.provisionar_store_y_pos)."""
    Tienda = apps.get_model('inventario', 'Tienda')
    MetodoPago = apps.get_model('inventario', 'MetodoPago')
    ArancelMetodoTienda = apps.get_model('inventario', 'ArancelMetodoTienda')

    metodos_estandar = list(
        MetodoPago.objects.filter(es_financiero=True, requiere_integracion_mp=False)
        .exclude(nombre='Mercado Libre')
    )
    metodo_mp = MetodoPago.objects.filter(nombre='QR Mercado Pago').first()

    for tienda in Tienda.objects.all():
        metodos = list(metodos_estandar)
        if metodo_mp and tienda.mp_pos_access_token and tienda.mp_pos_external_id:
            metodos.append(metodo_mp)
        for metodo in metodos:
            for plan in PLAN_CHOICES_VALUES:
                ArancelMetodoTienda.objects.get_or_create(
                    tienda=tienda, metodo_pago=metodo, nombre_plan=plan,
                    defaults={'arancel_porcentaje': Decimal('0.00')},
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    # Sin transacción envolvente: el backfill es idempotente (get_or_create),
    # así que si se corta a mitad de camino (ej. un deploy que se cancela
    # porque llegó uno más nuevo) no hace falta revertir nada -- el próximo
    # intento retoma donde quedó en vez de necesitar sostener una sola
    # transacción larga sobre inventario_tienda/metodopago/arancelmetodotienda.
    atomic = False

    dependencies = [
        ('inventario', '0106_tienda_mercadopago_pos'),
    ]

    operations = [
        migrations.RunPython(backfill_aranceles_default, noop),
    ]
