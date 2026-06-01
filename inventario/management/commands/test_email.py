"""
Verifica la conexión SMTP con Zoho y envía un correo de prueba.

Uso:
    python manage.py test_email
    python manage.py test_email --to otro@dominio.com
"""
from django.core.management.base import BaseCommand
from django.core.mail import send_mail, get_connection
from django.conf import settings


class Command(BaseCommand):
    help = 'Envía un correo de prueba para verificar la configuración SMTP (Zoho).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--to',
            default=settings.EMAIL_HOST_USER,
            help='Destinatario del correo de prueba (default: el mismo EMAIL_HOST_USER)',
        )

    def handle(self, *args, **options):
        dest = options['to']

        self.stdout.write(f'Configuración SMTP activa:')
        self.stdout.write(f'  HOST     : {settings.EMAIL_HOST}')
        self.stdout.write(f'  PORT     : {settings.EMAIL_PORT}')
        self.stdout.write(f'  TLS      : {settings.EMAIL_USE_TLS}')
        self.stdout.write(f'  USER     : {settings.EMAIL_HOST_USER}')
        self.stdout.write(f'  PASSWORD : {"✓ configurada" if settings.EMAIL_HOST_PASSWORD else "✗ VACÍA — configurá EMAIL_HOST_PASSWORD en Render"}')
        self.stdout.write(f'  FROM     : {settings.DEFAULT_FROM_EMAIL}')
        self.stdout.write('')

        if not settings.EMAIL_HOST_PASSWORD:
            self.stderr.write(self.style.ERROR(
                'EMAIL_HOST_PASSWORD no está configurada. '
                'Configurá la variable de entorno en Render antes de continuar.'
            ))
            return

        # Verificar conexión SMTP sin enviar
        self.stdout.write('Verificando conexión con el servidor SMTP...')
        try:
            conn = get_connection()
            conn.open()
            conn.close()
            self.stdout.write(self.style.SUCCESS('✓ Conexión SMTP OK'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'✗ Error de conexión: {e}'))
            return

        # Enviar correo de prueba
        self.stdout.write(f'Enviando correo de prueba a {dest}...')
        try:
            send_mail(
                subject='[Total Stock] Prueba de configuración de correo',
                message=(
                    'Este es un correo de prueba enviado desde Total Stock.\n\n'
                    'Si recibís este mensaje, la integración con Zoho Mail está funcionando correctamente.\n\n'
                    '— El sistema de Total Stock'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[dest],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS(f'✓ Correo enviado a {dest}'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'✗ Error al enviar: {e}'))
