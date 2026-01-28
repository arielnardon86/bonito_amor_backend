# inventario/management/commands/test_ml_oauth.py
"""
Comando de Django para probar el flujo OAuth de Mercado Libre
Uso: python manage.py test_ml_oauth [tienda_id]
"""
from django.core.management.base import BaseCommand
from inventario.models import Tienda
from inventario.services.mercadolibre_service import MercadoLibreService
from django.utils import timezone


class Command(BaseCommand):
    help = 'Prueba el flujo OAuth de Mercado Libre para una tienda'

    def add_arguments(self, parser):
        parser.add_argument(
            'tienda_id',
            nargs='?',
            type=str,
            help='ID de la tienda a probar (opcional, usa la primera tienda con ML si no se especifica)'
        )
        parser.add_argument(
            '--code',
            type=str,
            help='Código de autorización para intercambiar por tokens'
        )
        parser.add_argument(
            '--redirect-uri',
            type=str,
            default='https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/',
            help='Redirect URI para usar (default: producción)'
        )

    def handle(self, *args, **options):
        tienda_id = options.get('tienda_id')
        code = options.get('code')
        redirect_uri = options.get('redirect_uri')

        # Si se proporciona un código, intercambiarlo por tokens
        if code:
            return self.exchange_code(tienda_id, code, redirect_uri)

        # Si no, mostrar la URL de autorización
        return self.show_auth_url(tienda_id, redirect_uri)

    def exchange_code(self, tienda_id, code, redirect_uri):
        """Intercambia el código de autorización por tokens"""
        try:
            if tienda_id:
                tienda = Tienda.objects.get(id=tienda_id)
            else:
                tienda = Tienda.objects.filter(plataforma_ecommerce='MERCADO_LIBRE').first()
                if not tienda:
                    self.stdout.write(self.style.ERROR('❌ No se encontró ninguna tienda con Mercado Libre configurado'))
                    return

            self.stdout.write(f'📦 Tienda: {tienda.nombre} (ID: {tienda.id})')
            self.stdout.write('')

            ml_service = MercadoLibreService(tienda)
            
            self.stdout.write('🔄 Intercambiando código por tokens...')
            token_data = ml_service.exchange_code_for_token(code, redirect_uri)
            
            self.stdout.write(self.style.SUCCESS('✅ Autenticación exitosa!'))
            self.stdout.write('')
            self.stdout.write(f'   User ID: {token_data.get("user_id")}')
            self.stdout.write(f'   Access Token: {token_data.get("access_token")[:30]}...')
            self.stdout.write(f'   Token expira en: {token_data.get("expires_in", "N/A")} segundos')
            self.stdout.write('')
            self.stdout.write('✅ Los tokens han sido guardados en la base de datos')
            self.stdout.write('')
            self.stdout.write('Ahora puedes verificar el estado con:')
            self.stdout.write(f'   GET /api/tiendas/{tienda.id}/mercadolibre/status/')

        except Tienda.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Tienda con ID {tienda_id} no encontrada'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {str(e)}'))
            import traceback
            self.stdout.write(traceback.format_exc())

    def show_auth_url(self, tienda_id, redirect_uri):
        """Muestra la URL de autorización"""
        try:
            # Obtener tienda
            if tienda_id:
                tienda = Tienda.objects.get(id=tienda_id)
            else:
                tienda = Tienda.objects.filter(plataforma_ecommerce='MERCADO_LIBRE').first()
                if not tienda:
                    self.stdout.write(self.style.ERROR('❌ No se encontró ninguna tienda con Mercado Libre configurado'))
                    self.stdout.write('   Por favor, configura una tienda en el admin primero.')
                    return

            self.stdout.write('=' * 70)
            self.stdout.write('PRUEBA DE INTEGRACIÓN CON MERCADO LIBRE')
            self.stdout.write('=' * 70)
            self.stdout.write('')
            self.stdout.write(f'📦 Tienda: {tienda.nombre}')
            self.stdout.write(f'   ID: {tienda.id}')
            self.stdout.write(f'   App ID: {tienda.ml_app_id or "❌ NO CONFIGURADO"}')
            self.stdout.write(f'   Modo Test: {tienda.ml_modo_test}')
            self.stdout.write('')

            # Verificar configuración
            if not tienda.ml_app_id:
                self.stdout.write(self.style.ERROR('❌ ERROR: ml_app_id no está configurado'))
                self.stdout.write('   Ve al admin y configura el App ID de Mercado Libre')
                return

            if not tienda.ml_client_secret:
                self.stdout.write(self.style.WARNING('⚠️  ADVERTENCIA: ml_client_secret no está configurado'))
                self.stdout.write('   Necesitarás configurarlo para completar el flujo OAuth')
                self.stdout.write('')

            # Verificar si ya está autenticado
            if tienda.ml_access_token:
                self.stdout.write(self.style.SUCCESS('✅ Ya está autenticado'))
                self.stdout.write(f'   User ID: {tienda.ml_user_id or "N/A"}')
                if tienda.ml_token_expires_at:
                    if timezone.now() >= tienda.ml_token_expires_at:
                        self.stdout.write(self.style.WARNING(f'   ⚠️  Token expirado: {tienda.ml_token_expires_at}'))
                    else:
                        self.stdout.write(f'   Token expira: {tienda.ml_token_expires_at}')
                self.stdout.write('')

            # Generar URL de autorización
            self.stdout.write('-' * 70)
            self.stdout.write('PASO 1: OBTENER URL DE AUTORIZACIÓN')
            self.stdout.write('-' * 70)
            self.stdout.write('')

            ml_service = MercadoLibreService(tienda)
            auth_url = ml_service.get_authorization_url(redirect_uri)

            self.stdout.write(self.style.SUCCESS('✅ URL de autorización generada'))
            self.stdout.write('')
            self.stdout.write('📋 INSTRUCCIONES:')
            self.stdout.write('')
            self.stdout.write('1. Copia esta URL y ábrela en tu navegador:')
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(f'   {auth_url}'))
            self.stdout.write('')
            self.stdout.write('2. Autoriza la aplicación con tu cuenta de Mercado Libre')
            self.stdout.write('')
            self.stdout.write(f'3. Después de autorizar, serás redirigido a:')
            self.stdout.write(self.style.WARNING(f'   {redirect_uri}?code=TG-XXXXX'))
            self.stdout.write('')
            self.stdout.write('4. Copia el código (TG-XXXXX) de la URL')
            self.stdout.write('')
            self.stdout.write('5. Ejecuta este comando para intercambiar el código por tokens:')
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(
                f'   python manage.py test_ml_oauth {tienda.id} --code TG-XXXXX'
            ))
            self.stdout.write('')
            self.stdout.write(f'   O con el redirect_uri específico:')
            self.stdout.write(self.style.SUCCESS(
                f'   python manage.py test_ml_oauth {tienda.id} --code TG-XXXXX --redirect-uri "{redirect_uri}"'
            ))
            self.stdout.write('')

        except Tienda.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Tienda con ID {tienda_id} no encontrada'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {str(e)}'))
            import traceback
            self.stdout.write(traceback.format_exc())
