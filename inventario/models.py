from django.db import models
from django.utils import timezone
import random
import string
from barcode import EAN13 
from django.contrib.auth import get_user_model # <-- Usar get_user_model() es la práctica recomendada
                                                # en lugar de 'from django.contrib.auth.models import User'
                                                # por si en el futuro cambias el modelo de usuario

User = get_user_model() # Obtener el modelo de usuario activo


# --- FUNCIÓN CORREGIDA: generate_ean13 ---
def generate_ean13():
    """
    Genera un código de barras EAN-13 aleatorio.
    Asegura que el dígito de control (checksum) sea correcto.
    """
    prefix = "200" # Prefijo común para uso interno (o cualquier otro que desees)
    # Genera 9 dígitos aleatorios, sumando 3 del prefijo, da 12 dígitos.
    # EAN13 calculará el 13er dígito (checksum).
    random_digits = ''.join(random.choices(string.digits, k=9))
    base_number = prefix + random_digits
    
    try:
        ean = EAN13(base_number) 
        return ean.ean 
    except Exception as e:
        print(f"Error al generar EAN13: {e}")
        return None

# --- MODELO Categoria ---
class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Categorías" 

    def __str__(self):
        return self.nombre

# --- MODELO Producto ---
class Producto(models.Model):
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, null=True)
    codigo_barras = models.CharField(max_length=13, unique=True, blank=True, null=True)
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    talle = models.CharField(max_length=20, default='UNICA') 
    
    # --- RELACIÓN CON CATEGORIA (DESCOMENTADA Y RECOMENDADA) ---
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True, related_name='productos')


    def save(self, *args, **kwargs):
        if not self.codigo_barras: 
            new_barcode = None
            max_attempts = 100 
            attempts = 0

            while new_barcode is None or Producto.objects.filter(codigo_barras=new_barcode).exists():
                new_barcode = generate_ean13()
                attempts += 1
                if attempts > max_attempts:
                    raise Exception("No se pudo generar un código de barras EAN13 único después de varios intentos.")
            
            self.codigo_barras = new_barcode
            
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre

# --- MODELO Venta ---
class Venta(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas_realizadas') 
    fecha_venta = models.DateTimeField(default=timezone.now) # Usa default=timezone.now para que Django lo maneje automáticamente al crear
    total_venta = models.DecimalField(max_digits=10, decimal_places=2, default=0) 
    anulada = models.BooleanField(default=False) # <--- ¡CAMBIO CLAVE AQUÍ! Nuevo campo para indicar si la venta ha sido anulada

    class Meta:
        # Añadir un orden por defecto para las ventas, por ejemplo, las más recientes primero
        ordering = ['-fecha_venta'] 

    def __str__(self):
        return f"Venta {self.id} - {self.fecha_venta.strftime('%Y-%m-%d %H:%M')} por {self.usuario.username if self.usuario else 'Desconocido'}"

# --- MODELO DetalleVenta ---
class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, related_name='detalles', on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT) 
    cantidad = models.IntegerField()
    # Este campo almacenará el precio del producto EN EL MOMENTO DE LA VENTA
    precio_unitario_venta = models.DecimalField(max_digits=10, decimal_places=2) 

    def subtotal(self):
        return self.cantidad * self.precio_unitario_venta

    def save(self, *args, **kwargs):
        # Si precio_unitario_venta no está establecido, usa el precio_venta del producto
        if self.precio_unitario_venta is None and self.producto:
            self.precio_unitario_venta = self.producto.precio_venta
        super().save(*args, **kwargs)

    class Meta:
        # Ayuda a evitar duplicados y facilita consultas
        unique_together = ('venta', 'producto') 

    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre} en Venta {self.venta.id}"
