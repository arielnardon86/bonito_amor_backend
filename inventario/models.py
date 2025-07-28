# BONITO_AMOR/backend/inventario/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid 
from django.utils import timezone 
from django.conf import settings # Importar settings para AUTH_USER_MODEL

# Modelo de Usuario Personalizado
class User(AbstractUser):
    tienda = models.ForeignKey('Tienda', on_delete=models.SET_NULL, null=True, blank=True, related_name='empleados')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        ordering = ['username']

    def __str__(self):
        return self.username

# Modelo de Tienda
class Tienda(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=100, unique=True)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tienda"
        verbose_name_plural = "Tiendas" 
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

# Modelo de Categoría (Si aún lo usas)
class Categoria(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

# Modelo de Producto
class Producto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=200)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    TALLE_CHOICES = [
        ('XS', 'Extra Pequeño'),
        ('S', 'Pequeño'),
        ('M', 'Mediano'),
        ('L', 'Grande'),
        ('XL', 'Extra Grande'),
        ('UNICA', 'Talla Única'),
        ('NUM36', '36'),
        ('NUM38', '38'),
        ('NUM40', '40'),
        ('NUM42', '42'),
        ('NUM44', '44'),
    ]
    talle = models.CharField(max_length=10, choices=TALLE_CHOICES, default='UNICA')

    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='productos')
    codigo_barras = models.UUIDField(default=uuid.uuid4, unique=True, editable=False) 
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        unique_together = ('nombre', 'tienda') 
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} ({self.tienda.nombre})"

# Modelo de Venta
class Venta(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fecha_venta = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    metodo_pago = models.CharField(max_length=50, default='Efectivo')
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='ventas')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='ventas_realizadas'
    )
    # --- CAMBIO CLAVE AQUÍ: Añadir el campo 'anulada' ---
    anulada = models.BooleanField(default=False) 
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"
        ordering = ['-fecha_venta']

    def __str__(self):
        return f"Venta {self.id} - {self.fecha_venta.strftime('%Y-%m-%d %H:%M')}"

# Modelo de Detalle de Venta
class DetalleVenta(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='detalles_venta') 
    cantidad = models.IntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Detalle de Venta"
        verbose_name_plural = "Detalles de Venta"
        unique_together = ('venta', 'producto') 
        ordering = ['venta']

    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre} en Venta {self.venta.id}"

# Modelo de MetodoPago
class MetodoPago(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Método de Pago"
        verbose_name_plural = "Métodos de Pago"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre
