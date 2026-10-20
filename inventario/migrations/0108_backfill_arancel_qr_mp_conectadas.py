from decimal import Decimal

from django.db import migrations

PLAN_CHOICES_VALUES = ['CONTADO', '1', '3', '6', '12', 'Z']


def backfill_arancel_qr_mp_conectadas(apps, schema_editor):
    """Repite, solo para 'QR Mercado Pago', el backfill de la migración 0107
    -- cubre tiendas que conectaron su cuenta de Mercado Pago en la ventana
    entre que 0107 corrió y que el fix de 'precargar el arancel al conectar'
    (en MercadoPagoPosService.provisionar_store_y_pos) llegó realmente a
    producción (los deploys se colgaron un rato por una conexión huérfana a
    la base, ver el commit de la migración 0107). Esas tiendas quedaron con
    la cuenta conectada pero sin el arancel de QR Mercado Pago, así que el
    método no les aparecía como opción de cobro en el Punto de Venta."""
    Tienda = apps.get_model('inventario', 'Tienda')
    MetodoPago = apps.get_model('inventario', 'MetodoPago')
    ArancelMetodoTienda = apps.get_model('inventario', 'ArancelMetodoTienda')

    metodo_mp = MetodoPago.objects.filter(nombre='QR Mercado Pago').first()
    if not metodo_mp:
        return

    for tienda in Tienda.objects.all():
        if not (tienda.mp_pos_access_token and tienda.mp_pos_external_id):
            continue
        for plan in PLAN_CHOICES_VALUES:
            ArancelMetodoTienda.objects.get_or_create(
                tienda=tienda, metodo_pago=metodo_mp, nombre_plan=plan,
                defaults={'arancel_porcentaje': Decimal('0.00')},
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('inventario', '0107_aranceles_default_backfill'),
    ]

    operations = [
        migrations.RunPython(backfill_arancel_qr_mp_conectadas, noop),
    ]
