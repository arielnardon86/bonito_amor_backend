from django.db import models
from django.utils import timezone
import random
import string
from barcode import EAN13 
from django.contrib.auth import get_user_model 
from django.utils.text import slugify 

User = get_user_model() 

# --- MODELO Tienda ---
class Tienda(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True, help_text="Identificador único para la URL (ej. 'tienda-central')")
    direccion = models.CharField(max_length=255, blank=True, null=True) # <--- ESTE CAMPO
    telefono = models.CharField(max_length=20, blank=True, null=True)     # <--- ESTE CAMPO
    email = models.EmailField(blank=True, null=True)                    # <--- ESTE CAMPO
    activa = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre

# --- FUNCIÓN CORREGIDA: generate_ean13 ---
def generate_ean13():
    """
    Genera un código de barras EAN-13 aleatorio.
    Asegura que el dígito de control (checksum) sea correcto.
    """
    prefix = "200" 
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
    
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True, related_name='productos')
    
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='productos', null=True, blank=True)


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
        return f"{self.nombre} ({self.talle}) - {self.tienda.nombre if self.tienda else 'Sin Tienda'}"

# --- MODELO Venta ---
class Venta(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas_realizadas') 
    fecha_venta = models.DateTimeField(default=timezone.now) 
    total_venta = models.DecimalField(max_digits=10, decimal_places=2, default=0) 
    anulada = models.BooleanField(default=False) 
    metodo_pago = models.CharField(max_length=50, blank=True, null=True) 

    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='ventas', null=True, blank=True)


    class Meta:
        ordering = ['-fecha_venta'] 

    def __str__(self):
        return f"Venta {self.id} - {self.fecha_venta.strftime('%Y-%m-%d %H:%M')} por {self.usuario.username if self.usuario else 'Desconocido'} en {self.tienda.nombre if self.tienda else 'Sin Tienda'}"

# --- MODELO DetalleVenta ---
class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, related_name='detalles', on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT) 
    cantidad = models.IntegerField()
    precio_unitario_venta = models.DecimalField(max_digits=10, decimal_places=2) 

    def subtotal(self):
        return self.cantidad * self.precio_unitario_venta

    def save(self, *args, **kwargs):
        if self.precio_unitario_venta is None and self.producto:
            self.precio_unitario_venta = self.producto.precio_venta
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ('venta', 'producto') 

    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre} en Venta {self.venta.id}"
