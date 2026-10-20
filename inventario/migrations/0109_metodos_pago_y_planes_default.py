from decimal import Decimal

from django.db import migrations

PLANES_DEFAULT_POR_METODO_NUEVO = {
    'Go Cuotas': ['1', '2', '3', '4'],
    'Tarjeta de Débito': ['1'],
    'QR': ['1'],
}


def ajustar_metodos_y_aranceles(apps, schema_editor):
    """Redefine los planes default por método de pago (antes todos los
    métodos financieros precargaban los 6 planes genéricos de
    ArancelMetodoTienda.PLAN_CHOICES por igual):

    - 'Go Cuotas' y 'Tarjeta de Débito' son métodos nuevos -- se crean si no
      existen, con sus propios planes default (1-4 cuotas y 1 pago único).
    - 'QR' pasa a ser financiero (antes no tenía arancel configurable) con
      un único plan default ('1 pago').
    - 'Tarjeta de Crédito' no se toca -- sigue con sus 6 planes de siempre.
    - 'QR Mercado Pago' pasa de 6 planes default a 1 solo ('1 pago'): se
      asegura ese plan y se eliminan los otros planes default que haya
      precargados en 0.00% sin usar -- si una tienda ya editó alguno de esos
      a un % real, se lo deja tal cual (pasa a ser una adición propia de esa
      tienda, no una que el sistema le vuelva a borrar).

    Ver inventario.models.PLANES_DEFAULT_POR_METODO para el equivalente que
    aplica a partir de este punto para tiendas/métodos nuevos."""
    Tienda = apps.get_model('inventario', 'Tienda')
    MetodoPago = apps.get_model('inventario', 'MetodoPago')
    ArancelMetodoTienda = apps.get_model('inventario', 'ArancelMetodoTienda')

    go_cuotas, _ = MetodoPago.objects.get_or_create(
        nombre='Go Cuotas',
        defaults={'descripcion': 'Pagos en cuotas vía Go Cuotas', 'activo': True, 'es_financiero': True},
    )
    tarjeta_debito, _ = MetodoPago.objects.get_or_create(
        nombre='Tarjeta de Débito',
        defaults={'descripcion': 'Pagos con tarjeta de débito', 'activo': True, 'es_financiero': True},
    )

    metodo_qr = MetodoPago.objects.filter(nombre='QR').first()
    if metodo_qr and not metodo_qr.es_financiero:
        metodo_qr.es_financiero = True
        metodo_qr.save(update_fields=['es_financiero'])

    metodos_nuevos = {'Go Cuotas': go_cuotas, 'Tarjeta de Débito': tarjeta_debito, 'QR': metodo_qr}
    todas_tiendas = list(Tienda.objects.all())

    for nombre_metodo, metodo in metodos_nuevos.items():
        if not metodo:
            continue
        for tienda in todas_tiendas:
            for plan in PLANES_DEFAULT_POR_METODO_NUEVO[nombre_metodo]:
                ArancelMetodoTienda.objects.get_or_create(
                    tienda=tienda, metodo_pago=metodo, nombre_plan=plan,
                    defaults={'arancel_porcentaje': Decimal('0.00')},
                )

    metodo_mp = MetodoPago.objects.filter(nombre='QR Mercado Pago').first()
    if metodo_mp:
        for tienda in todas_tiendas:
            ArancelMetodoTienda.objects.get_or_create(
                tienda=tienda, metodo_pago=metodo_mp, nombre_plan='1',
                defaults={'arancel_porcentaje': Decimal('0.00')},
            )
            (ArancelMetodoTienda.objects
                .filter(tienda=tienda, metodo_pago=metodo_mp, arancel_porcentaje=Decimal('0.00'))
                .exclude(nombre_plan='1')
                .delete())


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('inventario', '0108_backfill_arancel_qr_mp_conectadas'),
    ]

    operations = [
        migrations.RunPython(ajustar_metodos_y_aranceles, noop),
    ]
