"""
Envía un mail promocional a las tiendas con Suscripcion.estado == 'pending':
se registraron pero nunca completaron el pago en Mercado Pago, así que nunca
llegaron a usar el sistema.

Uso:
    # Prueba: manda un único mail a la dirección indicada, no toca clientes.
    python manage.py enviar_mail_pendientes_pago --test-email vos@totalstock.com.ar

    # Dry-run: lista a quién le llegaría, sin mandar nada.
    python manage.py enviar_mail_pendientes_pago

    # Envío real a TODAS las tiendas con suscripción pendiente de pago (sin
    # importar cuándo se registraron) — para una campaña puntual.
    python manage.py enviar_mail_pendientes_pago --confirmar

    # Solo a las que se registraron exactamente hace N días (por defecto de
    # fecha_creacion de la Suscripcion). Pensado para correr como cron diario
    # con --dias-atras 1: cada tienda cae en el filtro una sola vez, el día
    # después de registrarse, sin repetir envíos si el cron corre a diario.
    python manage.py enviar_mail_pendientes_pago --dias-atras 1 --confirmar

    # Una tienda puntual, por nombre (coincidencia parcial, sin distinguir
    # mayúsculas) — para un caso concreto sin tocar el resto.
    python manage.py enviar_mail_pendientes_pago --tienda "Grandeza" --confirmar

Destinatario: un solo mail por Tienda (a su email de contacto, o al de su
usuario administrador si la tienda no tiene uno cargado) — evita mandarle
varias copias a una tienda con múltiples usuarios cargados.

Nota sobre --dias-atras: al depender de la fecha de creación (fija), correr
el comando dos veces el mismo día con el mismo --dias-atras reenvía a los
mismos destinatarios — no hay protección contra reintentos manuales, solo
contra que el cron diario duplique envíos día tras día.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

LOGO_URL = "https://www.totalstock.com.ar/logo-completo.png"
LOGIN_URL = "https://www.totalstock.com.ar"

CSS = """
  body{margin:0;padding:0;background:#f8fafc;font-family:'Helvetica Neue',Arial,sans-serif;}
  .wrap{max-width:560px;margin:40px auto;background:#fff;border-radius:16px;
        box-shadow:0 4px 24px rgba(0,0,0,.08);overflow:hidden;}
  .header{background:linear-gradient(135deg,#5dc87a 0%,#38a080 100%);
          padding:32px 40px;text-align:center;}
  .header img{height:44px;display:block;margin:0 auto 14px;border-radius:8px;
              background:rgba(255,255,255,.92);padding:6px 10px;}
  .header h1{margin:0;color:#fff;font-size:21px;font-weight:700;}
  .header p{margin:8px 0 0;color:rgba(255,255,255,.92);font-size:13.5px;font-weight:600;
            letter-spacing:.02em;text-transform:uppercase;}
  .body{padding:32px 40px 8px;}
  .body p{color:#334155;font-size:15px;line-height:1.7;margin:0 0 14px;}
  .body p.lead{font-size:16px;color:#1a2926;font-weight:600;}
  .features{margin:22px 0;}
  .feature{display:flex;gap:12px;align-items:flex-start;padding:12px 0;
           border-bottom:1px solid #f1f5f9;}
  .feature:last-child{border-bottom:none;}
  .feature .icon{font-size:20px;line-height:1;flex:none;width:28px;text-align:center;}
  .feature .txt h3{margin:0 0 3px;font-size:14.5px;color:#1a2926;font-weight:700;}
  .feature .txt p{margin:0;font-size:13.5px;color:#475569;line-height:1.55;}
  .precio-card{background:#edfaf3;border:1px solid #a8e6c5;border-radius:12px;
               padding:20px 22px;margin:24px 0;text-align:center;}
  .precio-card p.eyebrow{margin:0 0 4px;font-size:11.5px;font-weight:700;color:#1a6a40;
                          letter-spacing:.04em;text-transform:uppercase;}
  .precio-card p.monto{margin:0;font-size:26px;font-weight:800;color:#1a2926;}
  .precio-card p.monto span{font-size:14px;font-weight:600;color:#475569;}
  .precio-card p.nota{margin:8px 0 0;font-size:12.5px;color:#3f6b52;line-height:1.5;}
  .btn{display:inline-block;background:linear-gradient(135deg,#5dc87a,#38a080);
       color:#fff!important;text-decoration:none;padding:15px 36px;
       border-radius:10px;font-size:15.5px;font-weight:700;
       box-shadow:0 4px 14px rgba(93,200,122,.35);}
  .btn-wrap{text-align:center;margin:26px 0 8px;}
  .signoff{padding:4px 40px 32px;}
  .signoff p{color:#334155;font-size:15px;line-height:1.7;margin:0 0 4px;}
  .footer{background:#f1f5f9;padding:18px 40px;text-align:center;
          color:#94a3b8;font-size:12px;border-top:1px solid #e2e8f0;}
  .footer a{color:#5dc87a;text-decoration:none;}
"""

FEATURES = [
    ("🛒", "Punto de Venta simple y rápido",
     "Cobrá en segundos, con código de barras, combos de pago y cierre de caja incluido."),
    ("📦", "Control de stock en tiempo real",
     "Sabé exactamente qué tenés, qué se está por agotar y qué margen deja cada producto."),
    ("📊", "Métricas de ventas al instante",
     "Ventas del día, rentabilidad y productos más vendidos, sin armar planillas."),
    ("🧾", "Facturación electrónica ARCA",
     "Emití comprobantes válidos desde el mismo sistema, sin depender de otra herramienta."),
    ("🔗", "Integración con Tienda Nube y Mercado Libre",
     "El mismo stock, sincronizado entre tu local y tus canales online."),
]


def _formatear_precio(monto: Decimal) -> str:
    entero = int(monto)
    return f"${entero:,}".replace(",", ".")


def _armar_email(nombre_tienda: str, plan_nombre: str, precio_mensual):
    subject = "Tu cuenta en Total Stock está a un paso de activarse"

    precio_texto = _formatear_precio(precio_mensual) if precio_mensual is not None else None

    intro_texto = (
        f"Hola equipo de {nombre_tienda},\n\n"
        f"Vimos que creaste tu cuenta en Total Stock pero todavía no completaste el pago, "
        f"así que no llegaste a usar el sistema. Te contamos rápido qué te estás perdiendo, "
        f"por si te sirve terminar de activarla:\n\n"
    )
    features_texto = "\n".join(f"• {titulo}: {desc}" for _, titulo, desc in FEATURES)
    precio_bloque_texto = (
        f"\n\nTu plan {plan_nombre} tiene un valor de {precio_texto}/mes. "
        f"Activando tu cuenta ahora, asegurás ese precio — no lo dejes vencer.\n"
        if precio_texto else "\n"
    )
    texto = (
        intro_texto + features_texto + precio_bloque_texto +
        f"\nEntrá a {LOGIN_URL}, iniciá sesión con tu cuenta y vas a ver el botón "
        f"\"Ir a pagar ahora\" para terminar la activación en un par de clics.\n\n"
        f"Cualquier duda, escribinos a info@totalstock.com.ar — te ayudamos a arrancar.\n\n"
        f"— El equipo de Total Stock\nwww.totalstock.com.ar"
    )

    precio_card_html = ""
    if precio_texto:
        precio_card_html = f"""
    <div class="precio-card">
      <p class="eyebrow">Tu plan {plan_nombre}</p>
      <p class="monto">{precio_texto} <span>/ mes</span></p>
      <p class="nota">Activá tu cuenta ahora y asegurate este valor antes de que cambie.</p>
    </div>"""

    features_html = "\n".join(
        f"""    <div class="feature">
      <div class="icon">{icono}</div>
      <div class="txt"><h3>{titulo}</h3><p>{desc}</p></div>
    </div>"""
        for icono, titulo, desc in FEATURES
    )

    html = f"""<!DOCTYPE html><html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>{CSS}</style></head>
<body><div class="wrap">
  <div class="header">
    <img src="{LOGO_URL}" alt="Total Stock" />
    <h1>Tu cuenta está a un paso de activarse</h1>
    <p>Oferta por tiempo limitado</p>
  </div>
  <div class="body">
    <p class="lead">Hola equipo de {nombre_tienda},</p>
    <p>Vimos que creaste tu cuenta en Total Stock pero todavía no completaste el pago, así que no llegaste a usar el sistema. Te contamos rápido qué te estás perdiendo:</p>
    <div class="features">
{features_html}
    </div>
    <p>Todo esto, desde el celular o la computadora, sin instalar nada.</p>
{precio_card_html}
    <div class="btn-wrap">
      <a href="{LOGIN_URL}" class="btn">Activar mi cuenta ahora →</a>
    </div>
    <p style="text-align:center;font-size:12.5px;color:#94a3b8;margin-top:10px;">Iniciá sesión con tu cuenta y vas a ver el botón "Ir a pagar ahora".</p>
  </div>
  <div class="signoff">
    <p>Cualquier duda, escribinos a <a href="mailto:info@totalstock.com.ar" style="color:#5dc87a;text-decoration:none;">info@totalstock.com.ar</a> — te ayudamos a arrancar.</p>
    <p>¡Te esperamos del otro lado!</p>
  </div>
  <div class="footer">&copy; {date.today().year} Total Stock &nbsp;·&nbsp;
    <a href="https://www.totalstock.com.ar">www.totalstock.com.ar</a></div>
</div></body></html>"""

    return subject, texto, html


class Command(BaseCommand):
    help = "Envía un mail promocional a las tiendas con suscripción pendiente de pago."

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-email', type=str, default=None,
            help='Si se pasa, manda un único mail de prueba a esta dirección en vez de a los clientes.',
        )
        parser.add_argument(
            '--confirmar', action='store_true',
            help='Requerido para el envío real. Sin esto, solo lista los destinatarios (dry-run).',
        )
        parser.add_argument(
            '--dias-atras', type=int, default=None,
            help='Solo tiendas cuya suscripción se creó hace exactamente N días. Usar con 1 para el cron diario.',
        )
        parser.add_argument(
            '--tienda', type=str, default=None,
            help='Solo la(s) tienda(s) cuyo nombre contenga este texto (sin distinguir mayúsculas).',
        )

    def _enviar(self, to_email, subject, texto, html):
        msg = EmailMultiAlternatives(
            subject=subject,
            body=texto,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'Total Stock <info@totalstock.com.ar>'),
            to=[to_email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send(fail_silently=False)

    def handle(self, *args, **options):
        from inventario.models import Tienda, Suscripcion

        test_email = options.get('test_email')
        confirmar = options.get('confirmar')

        if test_email:
            from inventario.models import Plan

            # Usar el precio real de una tienda pendiente existente (si hay), o el del
            # plan Starter en la base, para que la prueba muestre el valor verdadero
            # y no un número inventado.
            sus_ejemplo = Suscripcion.objects.filter(estado='pending').select_related('plan').exclude(plan__isnull=True).first()
            if sus_ejemplo:
                plan_nombre = sus_ejemplo.plan.get_nombre_display()
                precio_ejemplo = sus_ejemplo.plan.precio_mensual
            else:
                plan_ejemplo = Plan.objects.filter(nombre='starter').first()
                plan_nombre = plan_ejemplo.get_nombre_display() if plan_ejemplo else 'Starter'
                precio_ejemplo = plan_ejemplo.precio_mensual if plan_ejemplo else None

            subject, texto, html = _armar_email('tu tienda', plan_nombre, precio_ejemplo)
            try:
                self._enviar(test_email, subject, texto, html)
                self.stdout.write(self.style.SUCCESS(f"Mail de prueba enviado a {test_email}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error enviando prueba a {test_email}: {e}"))
            return

        from inventario.models import User

        dias_atras = options.get('dias_atras')
        filtro_tienda = options.get('tienda')

        tiendas = Tienda.objects.select_related('suscripcion', 'suscripcion__plan').filter(
            suscripcion__estado=Suscripcion.ESTADO_CHOICES[0][0]  # 'pending'
        )
        if dias_atras is not None:
            fecha_objetivo = (timezone.now() - timedelta(days=dias_atras)).date()
            tiendas = tiendas.filter(suscripcion__fecha_creacion__date=fecha_objetivo)
        if filtro_tienda:
            tiendas = tiendas.filter(nombre__icontains=filtro_tienda)

        destinatarios = []  # lista de (tienda, email, origen)
        sin_email = []
        for t in tiendas:
            sus = t.suscripcion
            if t.email:
                destinatarios.append((t, t.email, sus, 'tienda'))
                continue

            owner = User.objects.filter(tienda=t, is_superuser=True).exclude(email='').exclude(email__isnull=True).first()
            if owner:
                destinatarios.append((t, owner.email, sus, f'usuario {owner.username}'))
            else:
                sin_email.append(t)

        filtros_desc = []
        if dias_atras is not None:
            filtros_desc.append(f"creadas hace {dias_atras} día(s) ({fecha_objetivo.isoformat()})")
        if filtro_tienda:
            filtros_desc.append(f"nombre contiene '{filtro_tienda}'")
        sufijo_filtros = f" [{', '.join(filtros_desc)}]" if filtros_desc else ""
        self.stdout.write(f"Tiendas con suscripción pendiente de pago{sufijo_filtros}: {len(destinatarios)}")
        if sin_email:
            self.stdout.write(self.style.WARNING(
                f"{len(sin_email)} tienda(s) sin ningún email disponible (ni tienda ni administrador), se omiten: "
                + ', '.join(t.nombre for t in sin_email)
            ))

        if not confirmar:
            for t, email, sus, origen in destinatarios:
                plan_nombre = sus.plan.get_nombre_display() if sus.plan_id else 'N/A'
                self.stdout.write(f"  - {t.nombre} -> {email} ({origen}) · plan {plan_nombre}")
            self.stdout.write(self.style.WARNING(
                "Dry-run: no se envió nada. Volvé a correr con --confirmar para el envío real."
            ))
            return

        enviados = 0
        errores = 0
        for t, email, sus, origen in destinatarios:
            plan_nombre = sus.plan.get_nombre_display() if sus.plan_id else 'tu plan'
            precio = sus.plan.precio_mensual if sus.plan_id else None
            subject, texto, html = _armar_email(t.nombre, plan_nombre, precio)
            try:
                self._enviar(email, subject, texto, html)
                enviados += 1
                self.stdout.write(f"  ✓ {t.nombre} ({email}, {origen})")
            except Exception as e:
                errores += 1
                logger.error("Error enviando mail de pendientes de pago a %s (%s): %s", t.nombre, email, e)
                self.stdout.write(self.style.ERROR(f"  ✗ {t.nombre} ({email}): {e}"))

        self.stdout.write(self.style.SUCCESS(f"\nListo: {enviados} enviados, {errores} errores."))
