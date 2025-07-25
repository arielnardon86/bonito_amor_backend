# BONITO_AMOR/backend/inventario/models.py
from django.db import models
from django.utils import timezone
import random
import string
from barcode import EAN13
# Importar AbstractUser y UserManager para crear un modelo de usuario personalizado
from django.contrib.auth.models import AbstractUser, UserManager


# --- FUNCIÓN: generate_ean13 (sin cambios) ---
def generate_ean13():
    """
    Genera un código de barras EAN-13 aleatorio.
    Asegura que el dígito de control (checksum) sea correcto.
    """
    prefix = "200" # Prefijo común para uso interno (o cualquier otro que desees)
    random_digits = ''.join(random.choices(string.digits, k=9))
    base_number = prefix + random_digits
    
    try:
        ean = EAN13(base_number) 
        return ean.ean 
    except Exception as e:
        print(f"Error al generar EAN13: {e}")
        return None

# --- MODELO Categoria (sin cambios) ---
class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Categorías" 

    def __str__(self):
        return self.nombre

# --- NUEVO MODELO: Tienda ---
# Si ya tienes este modelo, asegúrate de que sea idéntico o actualízalo.
class Tienda(models.Model):
    nombre = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, help_text="Identificador único para la URL (ej: bonito-amor)")
    direccion = models.CharField(max_length=255, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    # Puedes añadir más campos específicos de la tienda aquí

    class Meta:
        verbose_name_plural = "Tiendas"
        # Ordenar por nombre por defecto
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

# --- MODELO DE USUARIO PERSONALIZADO ---
# Extiende AbstractUser y añade el campo 'tienda'
class User(AbstractUser):
    # Relación ForeignKey con el modelo Tienda.
    # Un usuario puede estar asociado a una tienda (o a ninguna, si es superusuario global).
    tienda = models.ForeignKey(Tienda, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')

    # Es importante especificar el UserManager por defecto si no añades lógica de gestión de usuarios personalizada
    objects = UserManager()

    def __str__(self):
        # Muestra el nombre de usuario y, si está asociado, el nombre de la tienda
        if self.tienda:
            return f"{self.username} ({self.tienda.nombre})"
        return self.username

# --- MODELO Producto (actualizado para incluir ForeignKey a Tienda) ---
class Producto(models.Model):
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, null=True)
    codigo_barras = models.CharField(max_length=13, unique=True, blank=True, null=True)
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    talle = models.CharField(max_length=20, default='UNICA') 
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True, related_name='productos')
    # Añadir ForeignKey a Tienda
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='productos')


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

# --- MODELO Venta (actualizado para incluir ForeignKey a Tienda) ---
class Venta(models.Model):
    # Usar nuestro modelo de User personalizado
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas_realizadas') 
    fecha_venta = models.DateTimeField(default=timezone.now) 
    total_venta = models.DecimalField(max_digits=10, decimal_places=2, default=0) 
    anulada = models.BooleanField(default=False) 
    metodo_pago = models.CharField(max_length=50, blank=True, null=True)
    # Añadir ForeignKey a Tienda
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='ventas')

    class Meta:
        ordering = ['-fecha_venta'] 

    def __str__(self):
        return f"Venta {self.id} - {self.fecha_venta.strftime('%Y-%m-%d %H:%M')} por {self.usuario.username if self.usuario else 'Desconocido'} ({self.tienda.nombre if self.tienda else 'Sin Tienda'})"

# --- MODELO DetalleVenta (sin cambios) ---
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
