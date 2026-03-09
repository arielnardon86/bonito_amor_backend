#!/usr/bin/env python
"""
Script para simular el flujo completo de cambio/devolución con diferencia a pagar:
1. Crear venta original con un producto
2. Crear cambio: devolver producto original, agregar otro producto más caro (diferencia a pagar)
3. Verificar que se creó venta_diferencia_pendiente
4. Procesar la venta por la diferencia (PATCH metodo_pago)

Ejecutar desde backend/: python manage.py shell < scripts/test_cambio_devolucion_diferencia.py
O: python manage.py shell
   >>> exec(open('scripts/test_cambio_devolucion_diferencia.py').read())
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mi_tienda_backend.settings')
django.setup()

from decimal import Decimal
from django.utils import timezone
from inventario.models import (
    Tienda, Producto, Venta, DetalleVenta, User,
    CambioDevolucion, DetalleCambioDevolucion, MetodoPago
)


def run_test():
    print("=" * 60)
    print("TEST: Cambio de producto con diferencia a pagar")
    print("=" * 60)

    # 1. Obtener tienda y usuario
    tienda = Tienda.objects.first()
    user = User.objects.filter(is_superuser=True).first() or User.objects.first()
    if not tienda or not user:
        print("ERROR: Necesitás al menos una tienda y un usuario. Creá datos de prueba.")
        return

    print(f"\n1. Tienda: {tienda.nombre}, Usuario: {user.username}")

    # 2. Crear o usar productos
    prod_a = Producto.objects.filter(tienda=tienda).first()
    prod_b = Producto.objects.filter(tienda=tienda).exclude(id=prod_a.id if prod_a else None).first()

    if not prod_a:
        prod_a = Producto.objects.create(
            nombre="Producto A (test cambio)",
            tienda=tienda,
            precio=Decimal("1000.00"),
            costo=Decimal("500"),
            stock=10,
        )
        print(f"   Creado producto A: {prod_a.nombre} - ${prod_a.precio} (stock: {prod_a.stock})")
    if not prod_b:
        prod_b = Producto.objects.create(
            nombre="Producto B (test cambio)",
            tienda=tienda,
            precio=Decimal("1500.00"),
            costo=Decimal("700"),
            stock=10,
        )
        print(f"   Creado producto B: {prod_b.nombre} - ${prod_b.precio} (stock: {prod_b.stock})")

    # 3. Crear venta original (cliente compró Producto A por $1000)
    venta_orig = Venta.objects.create(
        total=Decimal("1000.00"),
        tienda=tienda,
        usuario=user,
        metodo_pago="Efectivo",
        fecha_venta=timezone.now(),
        facturada=False,
    )
    DetalleVenta.objects.create(
        venta=venta_orig,
        producto=prod_a,
        cantidad=1,
        precio_unitario=Decimal("1000.00"),
        subtotal=Decimal("1000.00"),
        costo_unitario=prod_a.costo,
    )
    prod_a.stock -= 1
    prod_a.save()
    print(f"\n2. Venta original creada: {venta_orig.id} - ${venta_orig.total} (Producto A)")

    # 4. Simular llamada al API de cambio: CAMBIAR (devolver A, agregar B)
    # Estructura que espera el serializer
    detalle_venta_orig = venta_orig.detalles.first()
    from inventario.views import CambioDevolucionViewSet
    from inventario.serializers import CambioDevolucionCreateSerializer
    from rest_framework.test import APIRequestFactory
    from rest_framework.request import Request

    data = {
        "venta_original": venta_orig.id,
        "tipo": "CAMBIO",
        "motivo": "Test script - cambio producto",
        "detalles": [
            {
                "accion": "CAMBIAR",
                "cantidad": 1,
                "detalle_venta_original_id": str(detalle_venta_orig.id),
                "producto_nuevo_id": str(prod_b.id),
                "precio_unitario_nuevo": "1500.00",
            }
        ],
    }

    factory = APIRequestFactory()
    from rest_framework.test import force_authenticate
    raw_request = factory.post("/api/cambios-devoluciones/", data, format="json")
    force_authenticate(raw_request, user=user)
    request = Request(raw_request)

    serializer = CambioDevolucionCreateSerializer(data=data, context={"request": request})
    if not serializer.is_valid():
        print(f"   ERROR validación: {serializer.errors}")
        return

    # Crear el cambio via perform_create del viewset
    view = CambioDevolucionViewSet()
    view.request = request
    view.format_kwarg = None
    view.format_kwarg = None
    try:
        cambio = view.perform_create(serializer)
        print(f"\n3. Cambio/devolución creado: {cambio.id}")
        print(f"   Monto devolución (prod A): ${cambio.monto_devolucion}")
        print(f"   Monto nuevo (prod B): ${cambio.monto_nuevo}")
        print(f"   Diferencia a pagar: ${cambio.monto_diferencia}")
        print(f"   Diferencia pendiente: {cambio.diferencia_pendiente}")
        print(f"   Venta diferencia pendiente: {cambio.venta_diferencia_pendiente_id}")
    except Exception as e:
        print(f"   ERROR al crear cambio: {e}")
        import traceback
        traceback.print_exc()
        return

    if not cambio.diferencia_pendiente or not cambio.venta_diferencia_pendiente:
        print("   ERROR: No se creó venta_diferencia_pendiente")
        return

    venta_diff = cambio.venta_diferencia_pendiente
    print(f"\n4. Venta pendiente creada: {venta_diff.id} - ${venta_diff.total} - metodo_pago={venta_diff.metodo_pago}")

    # 5. Procesar la venta por la diferencia (PATCH para cambiar metodo_pago)
    venta_diff.metodo_pago = "Efectivo"
    venta_diff.save()
    print(f"\n5. Venta procesada: metodo_pago actualizado a 'Efectivo'")

    # 6. Verificar stock
    prod_a.refresh_from_db()
    prod_b.refresh_from_db()
    print(f"\n6. Stock final - {prod_a.nombre}: {prod_a.stock}, {prod_b.nombre}: {prod_b.stock}")
    print("   (A devuelto +1, B vendido -1 => A igual que al inicio, B -1)")

    # 7. GET al detalle del cambio (verificar que no hay 500)
    from django.test import RequestFactory
    from rest_framework.test import force_authenticate
    factory = APIRequestFactory()
    req = factory.get(f"/api/cambios-devoluciones/{cambio.id}/")
    force_authenticate(req, user=user)
    view = CambioDevolucionViewSet.as_view({"get": "retrieve"})
    try:
        resp = view(req, pk=cambio.id)
        print(f"\n7. GET /api/cambios-devoluciones/{cambio.id}/ => {resp.status_code}")
        if resp.status_code == 200:
            print("   OK - No más error 500 con select_related")
        else:
            print(f"   Error: {resp.data}")
    except Exception as e:
        print(f"   ERROR: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("TEST COMPLETADO")
    print("=" * 60)


if __name__ == "__main__" or "run_test" in dir():
    run_test()
