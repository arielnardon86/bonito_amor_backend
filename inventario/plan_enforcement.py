"""
Helpers para enforcement de planes en Total Stock.

Regla de oro: tiendas SIN suscripción (legacy) → acceso total, sin límites.
Tiendas CON suscripción → se aplican los límites del plan.

Uso desde una view:
    from inventario.plan_enforcement import verificar_limite_productos, verificar_feature

    ok, detalle = verificar_limite_productos(tienda)
    if not ok:
        return Response(detalle, status=403)

    ok, detalle = verificar_feature(tienda, 'factura_electronica')
    if not ok:
        return Response(detalle, status=403)
"""

from .models import Producto, User


def _get_suscripcion(tienda):
    """Devuelve la suscripción de la tienda, o None si es legacy."""
    try:
        return tienda.suscripcion
    except Exception:
        return None


def _es_legacy(sus) -> bool:
    """
    True si la tienda debe tratarse como legacy (sin límites ni restricciones):
    - No tiene fila de Suscripcion, o
    - Tiene Suscripcion pero con el plan especial 'legacy' (asignado a mano desde
      Django Admin para eximir a una tienda de límites sin perder el registro de
      Suscripcion, p.ej. para poder dejarla en estado 'activa' o 'pausada').
    """
    return sus is None or sus.plan.nombre == 'legacy'


# ── Límites cuantitativos ─────────────────────────────────────────────────────

def verificar_limite_productos(tienda) -> tuple[bool, dict]:
    """
    Verifica si la tienda puede agregar un producto más.
    Devuelve (True, {}) si puede, o (False, payload_para_frontend) si no.
    """
    sus = _get_suscripcion(tienda)
    if _es_legacy(sus):
        return True, {}  # legacy: sin límite

    if sus.plan.max_productos is None:
        return True, {}

    cantidad_actual = Producto.objects.filter(
        tienda=tienda,
        producto_padre__isnull=True,  # solo productos raíz
    ).count()

    if cantidad_actual < sus.plan.max_productos:
        return True, {}

    return False, {
        'limite': True,
        'tipo': 'productos',
        'plan_actual': sus.plan.nombre,
        'max_permitido': sus.plan.max_productos,
        'cantidad_actual': cantidad_actual,
        'mensaje': (
            f'Tu plan {sus.plan.get_nombre_display()} permite hasta '
            f'{sus.plan.max_productos} productos. '
            f'Para agregar más, actualizá tu plan.'
        ),
        'planes_sugeridos': _planes_superiores(sus.plan, 'productos'),
    }


def verificar_limite_usuarios(tienda) -> tuple[bool, dict]:
    """
    Verifica si la tienda puede agregar un usuario más.
    """
    sus = _get_suscripcion(tienda)
    if _es_legacy(sus):
        return True, {}

    if sus.plan.max_usuarios is None:
        return True, {}

    cantidad_actual = User.objects.filter(tienda=tienda).count()

    if cantidad_actual < sus.plan.max_usuarios:
        return True, {}

    return False, {
        'limite': True,
        'tipo': 'usuarios',
        'plan_actual': sus.plan.nombre,
        'max_permitido': sus.plan.max_usuarios,
        'cantidad_actual': cantidad_actual,
        'mensaje': (
            f'Tu plan {sus.plan.get_nombre_display()} permite hasta '
            f'{sus.plan.max_usuarios} usuarios. '
            f'Para agregar más, actualizá tu plan.'
        ),
        'planes_sugeridos': _planes_superiores(sus.plan, 'usuarios'),
    }


# ── Features booleanas ────────────────────────────────────────────────────────

FEATURE_LABELS = {
    'factura_electronica':   'Factura electrónica (ARCA)',
    'ecommerce':             'Integración E-Commerce (Mercado Libre / Tienda Nube)',
}

FEATURE_PLAN_MINIMO = {
    'factura_electronica': 'pro',
    'ecommerce':           'advanced',
}


def verificar_feature(tienda, feature: str) -> tuple[bool, dict]:
    """
    Verifica si el plan de la tienda permite una feature.
    feature: 'factura_electronica' | 'ecommerce'
    """
    sus = _get_suscripcion(tienda)
    if _es_legacy(sus):
        return True, {}  # legacy: sin restricciones

    if sus.permite_feature(feature):
        return True, {}

    label = FEATURE_LABELS.get(feature, feature)
    plan_minimo = FEATURE_PLAN_MINIMO.get(feature, 'advanced')

    return False, {
        'limite': True,
        'tipo': 'feature',
        'feature': feature,
        'plan_actual': sus.plan.nombre,
        'mensaje': (
            f'"{label}" no está disponible en el plan '
            f'{sus.plan.get_nombre_display()}. '
            f'Actualizá tu plan para acceder a esta función.'
        ),
        'planes_sugeridos': _planes_desde(plan_minimo),
    }


# ── Info de suscripción para el frontend ─────────────────────────────────────

def info_suscripcion(tienda) -> dict:
    """
    Devuelve un dict con el estado actual del plan de la tienda.
    Usado por el endpoint de perfil / panel de administración.

    Una tienda legacy con `requiere_eleccion_plan=True` se reporta como no-legacy
    y con estado 'requiere_plan', para que el frontend la bloquee con la pantalla
    de elección de plan aunque nunca haya tenido (o ya no tenga) un plan real
    asignado. El resto de las tiendas legacy no se ven afectadas por este flag.
    """
    sus = _get_suscripcion(tienda)
    legacy = _es_legacy(sus)
    forzar_eleccion = legacy and tienda.requiere_eleccion_plan

    if sus is None:
        if forzar_eleccion:
            return {'legacy': False, 'plan': None, 'estado': 'requiere_plan', 'esta_activa': False}
        return {'legacy': True, 'plan': None, 'estado': 'activa'}

    cantidad_productos = Producto.objects.filter(
        tienda=tienda, producto_padre__isnull=True
    ).count()
    cantidad_usuarios = User.objects.filter(tienda=tienda).count()

    return {
        'legacy': False if forzar_eleccion else legacy,
        'plan': sus.plan.nombre,
        'plan_display': sus.plan.get_nombre_display(),
        'estado': 'requiere_plan' if forzar_eleccion else sus.estado,
        'esta_activa': False if forzar_eleccion else sus.esta_activa,
        'dias_gracia_restantes': sus.dias_gracia_restantes,
        'fecha_fin_trial': sus.fecha_fin_trial,
        'fecha_proximo_cobro': sus.fecha_proximo_cobro,
        'max_productos': sus.plan.max_productos,
        'max_usuarios': sus.plan.max_usuarios,
        'cantidad_productos': cantidad_productos,
        'cantidad_usuarios': cantidad_usuarios,
        'permite_factura_electronica': sus.plan.permite_factura_electronica,
        'permite_integracion_ecommerce': sus.plan.permite_integracion_ecommerce,
        'precio_mensual': str(sus.plan.precio_mensual),
    }


# ── Helpers internos ──────────────────────────────────────────────────────────

def _planes_superiores(plan_actual, motivo: str) -> list:
    """Devuelve los nombres de planes que superan el límite del plan actual."""
    from .models import Plan
    if motivo == 'productos':
        qs = Plan.objects.filter(max_productos__gt=plan_actual.max_productos or 0) | \
             Plan.objects.filter(max_productos__isnull=True)
    elif motivo == 'usuarios':
        qs = Plan.objects.filter(max_usuarios__gt=plan_actual.max_usuarios or 0) | \
             Plan.objects.filter(max_usuarios__isnull=True)
    else:
        qs = Plan.objects.exclude(nombre=plan_actual.nombre)
    return list(qs.values_list('nombre', flat=True))


def _planes_desde(plan_nombre: str) -> list:
    """Devuelve los nombres de planes a partir del mínimo requerido."""
    from .models import Plan
    orden = {'starter': 0, 'pro': 1, 'advanced': 2}
    minimo = orden.get(plan_nombre, 0)
    return [nombre for nombre, nivel in orden.items() if nivel >= minimo]
