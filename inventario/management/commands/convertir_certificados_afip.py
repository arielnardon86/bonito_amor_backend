"""
Comando de Django para convertir certificados AFIP a base64
Uso: python manage.py convertir_certificados_afip certificado.crt clave.key
"""
import base64
import sys
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Convierte certificados AFIP (.crt y .key) a base64 para almacenarlos en la base de datos'

    def add_arguments(self, parser):
        parser.add_argument('certificado', type=str, help='Ruta al archivo certificado.crt')
        parser.add_argument('clave', type=str, help='Ruta al archivo clave.key')

    def handle(self, *args, **options):
        certificado_path = options['certificado']
        clave_path = options['clave']

        try:
            # Leer y convertir certificado
            with open(certificado_path, 'rb') as f:
                certificado_content = f.read()
                certificado_base64 = base64.b64encode(certificado_content).decode('utf-8')
            
            # Leer y convertir clave privada
            with open(clave_path, 'rb') as f:
                clave_content = f.read()
                clave_base64 = base64.b64encode(clave_content).decode('utf-8')
            
            self.stdout.write(self.style.SUCCESS('\n✅ Certificados convertidos exitosamente\n'))
            self.stdout.write('=' * 80)
            self.stdout.write('\n📄 CERTIFICADO AFIP (Certificado.crt):')
            self.stdout.write('=' * 80)
            self.stdout.write(certificado_base64)
            self.stdout.write('\n' + '=' * 80)
            self.stdout.write('\n🔐 CLAVE PRIVADA AFIP (Clave.key):')
            self.stdout.write('=' * 80)
            self.stdout.write(clave_base64)
            self.stdout.write('\n' + '=' * 80)
            self.stdout.write(self.style.SUCCESS('\n✅ Copia y pega estos valores en el admin de Django:\n'))
            self.stdout.write('   1. Certificado AFIP: pega el primer bloque de texto')
            self.stdout.write('   2. Clave Privada AFIP: pega el segundo bloque de texto\n')
            
        except FileNotFoundError as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Error: Archivo no encontrado: {e}\n'))
            sys.exit(1)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Error al procesar archivos: {e}\n'))
            sys.exit(1)




