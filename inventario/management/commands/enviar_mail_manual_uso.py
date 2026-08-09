"""
Envía el mail de novedades anunciando el Manual de Uso.

Uso:
    # Prueba: manda un único mail a la dirección indicada, no toca clientes.
    python manage.py enviar_mail_manual_uso --test-email vos@totalstock.com.ar

    # Dry-run: lista a quién le llegaría, sin mandar nada.
    python manage.py enviar_mail_manual_uso

    # Envío real a todas las tiendas con acceso activo (trial/activa/gracia o legacy).
    python manage.py enviar_mail_manual_uso --confirmar

Destinatario: un solo mail por Tienda (a su email de contacto), no uno por
usuario — evita mandarle varias copias a una tienda con múltiples cajeros
cargados.
"""

import logging
from datetime import date

from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

logger = logging.getLogger(__name__)

LOGO_URL = "https://www.totalstock.com.ar/logo-completo.png"
MANUAL_URL = "https://www.totalstock.com.ar/manual"

CSS = """
  body{margin:0;padding:0;background:#f8fafc;font-family:'Helvetica Neue',Arial,sans-serif;}
  .wrap{max-width:560px;margin:40px auto;background:#fff;border-radius:16px;
        box-shadow:0 4px 24px rgba(0,0,0,.08);overflow:hidden;}
  .header{background:linear-gradient(135deg,#5dc87a 0%,#38a080 100%);
          padding:32px 40px;text-align:center;}
  .header img{height:44px;display:block;margin:0 auto 14px;border-radius:8px;
              background:rgba(255,255,255,.92);padding:6px 10px;}
  .header h1{margin:0;color:#fff;font-size:21px;font-weight:700;}
  .body{padding:32px 40px 8px;}
  .body p{color:#334155;font-size:15px;line-height:1.7;margin:0 0 14px;}
  .body p.lead{font-size:16px;color:#1a2926;font-weight:600;}
  .feature-card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;
                padding:20px 22px;margin:22px 0;}
  .feature-card h2{margin:0 0 6px;font-size:16px;color:#1a2926;}
  .feature-card p{margin:0;font-size:13.5px;color:#475569;line-height:1.6;}
  .btn{display:inline-block;background:linear-gradient(135deg,#5dc87a,#38a080);
       color:#fff!important;text-decoration:none;padding:14px 34px;
       border-radius:10px;font-size:15px;font-weight:700;
       box-shadow:0 4px 14px rgba(93,200,122,.35);}
  .btn-wrap{text-align:center;margin:28px 0 8px;}
  .signoff{padding:4px 40px 32px;}
  .signoff p{color:#334155;font-size:15px;line-height:1.7;margin:0 0 4px;}
  .footer{background:#f1f5f9;padding:18px 40px;text-align:center;
          color:#94a3b8;font-size:12px;border-top:1px solid #e2e8f0;}
  .footer a{color:#5dc87a;text-decoration:none;}
"""


def _armar_email(nombre_tienda: str):
    subject = "Gracias por confiar en Total Stock — Nuevo: Manual de Uso dentro del sistema"

    texto = (
        f"Hola equipo de {nombre_tienda},\n\n"
        f"Queríamos tomarnos un momento para agradecerte por ser parte de Total Stock. "
        f"Que elijas nuestro sistema para gestionar tu negocio día a día es algo que no "
        f"damos por sentado, y trabajamos todo el tiempo para que te sea cada vez más útil.\n\n"
        f"Novedad: ahora tenés una sección \"Manual de Uso\" en el menú, con una guía "
        f"completa de todo lo que podés hacer en cada parte del sistema — para qué sirve, "
        f"cómo se usa y qué problema te resuelve (Punto de Venta, Clientes, Productos, "
        f"Métricas y mucho más).\n\n"
        f"La idea es que sea tu primer lugar para sacarte cualquier duda.\n\n"
        f"Entrá acá: {MANUAL_URL}\n\n"
        f"Cualquier consulta, siempre podés escribirnos a info@totalstock.com.ar.\n\n"
        f"¡Gracias por elegirnos, y a disfrutar Total Stock al máximo!\n\n"
        f"— El equipo de Total Stock\nwww.totalstock.com.ar"
    )

    html = f"""<!DOCTYPE html><html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>{CSS}</style></head>
<body><div class="wrap">
  <div class="header">
    <img src="{LOGO_URL}" alt="Total Stock" />
    <h1>¡Gracias por confiar en nosotros!</h1>
  </div>
  <div class="body">
    <p class="lead">Hola equipo de {nombre_tienda},</p>
    <p>Queríamos tomarnos un momento para agradecerte por ser parte de Total Stock. Que elijas nuestro sistema para gestionar tu negocio día a día es algo que no damos por sentado, y trabajamos todo el tiempo para que te sea cada vez más útil.</p>
    <div class="feature-card">
      <h2>📘 Nuevo: Manual de Uso dentro del sistema</h2>
      <p>Ahora tenés una sección "Manual de Uso" en el menú, con una guía completa de todo lo que podés hacer en cada parte del sistema: para qué sirve, cómo se usa y qué problema te resuelve — Punto de Venta, Clientes, Productos, Métricas y mucho más.</p>
    </div>
    <p>La idea es que sea tu primer lugar para sacarte cualquier duda: ya sea que recién estás arrancando o que hace tiempo lo usás y querés descubrir alguna función que todavía no probaste, ahí vas a encontrar la explicación paso a paso.</p>
    <div class="btn-wrap">
      <a href="{MANUAL_URL}" class="btn">Ver el Manual de Uso →</a>
    </div>
  </div>
  <div class="signoff">
    <p>Cualquier consulta, siempre podés escribirnos a <a href="mailto:info@totalstock.com.ar" style="color:#5dc87a;text-decoration:none;">info@totalstock.com.ar</a>.</p>
    <p>¡Gracias por elegirnos, y a disfrutar Total Stock al máximo!</p>
  </div>
  <div class="footer">&copy; {date.today().year} Total Stock &nbsp;·&nbsp;
    <a href="https://www.totalstock.com.ar">www.totalstock.com.ar</a></div>
</div></body></html>"""

    return subject, texto, html


class Command(BaseCommand):
    help = "Envía el mail de novedades del Manual de Uso a las tiendas con acceso activo."

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-email', type=str, default=None,
            help='Si se pasa, manda un único mail de prueba a esta dirección en vez de a los clientes.',
        )
        parser.add_argument(
            '--confirmar', action='store_true',
            help='Requerido para el envío real a todas las tiendas. Sin esto, solo lista los destinatarios (dry-run).',
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
        from inventario.models import Tienda

        test_email = options.get('test_email')
        confirmar = options.get('confirmar')

        if test_email:
            subject, texto, html = _armar_email('tu tienda')
            try:
                self._enviar(test_email, subject, texto, html)
                self.stdout.write(self.style.SUCCESS(f"Mail de prueba enviado a {test_email}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error enviando prueba a {test_email}: {e}"))
            return

        from inventario.models import User

        tiendas = Tienda.objects.select_related('suscripcion')
        destinatarios = []  # lista de (tienda, email, origen)
        sin_email = []
        for t in tiendas:
            try:
                sus = t.suscripcion
            except Exception:
                sus = None
            if not (sus is None or sus.estado in ('trial', 'activa', 'gracia')):
                continue

            if t.email:
                destinatarios.append((t, t.email, 'tienda'))
                continue

            # La tienda no tiene email cargado: usar el de su usuario administrador.
            owner = User.objects.filter(tienda=t, is_superuser=True).exclude(email='').exclude(email__isnull=True).first()
            if owner:
                destinatarios.append((t, owner.email, f'usuario {owner.username}'))
            else:
                sin_email.append(t)

        self.stdout.write(f"Tiendas destinatarias (trial/activa/gracia o sin suscripción): {len(destinatarios)}")
        if sin_email:
            self.stdout.write(self.style.WARNING(
                f"{len(sin_email)} tienda(s) sin ningún email disponible (ni tienda ni administrador), se omiten: "
                + ', '.join(t.nombre for t in sin_email)
            ))

        if not confirmar:
            for t, email, origen in destinatarios:
                self.stdout.write(f"  - {t.nombre} -> {email} ({origen})")
            self.stdout.write(self.style.WARNING(
                "Dry-run: no se envió nada. Volvé a correr con --confirmar para el envío real."
            ))
            return

        enviados = 0
        errores = 0
        for t, email, origen in destinatarios:
            subject, texto, html = _armar_email(t.nombre)
            try:
                self._enviar(email, subject, texto, html)
                enviados += 1
                self.stdout.write(f"  ✓ {t.nombre} ({email}, {origen})")
            except Exception as e:
                errores += 1
                logger.error("Error enviando mail de novedades a %s (%s): %s", t.nombre, email, e)
                self.stdout.write(self.style.ERROR(f"  ✗ {t.nombre} ({email}): {e}"))

        self.stdout.write(self.style.SUCCESS(f"\nListo: {enviados} enviados, {errores} errores."))
