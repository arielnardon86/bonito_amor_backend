# BONITO_AMOR/backend/inventario/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid 
from django.utils import timezone # Asegúrate de que timezone esté importado
from django.conf import settings # Importar settings para AUTH_USER_MODEL
from decimal import Decimal # Importar Decimal para default de Venta.total
       
# Modelo de Usuario Personalizado
class User(AbstractUser):
    tienda = models.ForeignKey('Tienda', on_delete=models.SET_NULL, null=True, blank=True, related_name='empleados')
    # Estos campos ya existen en AbstractUser o se manejan por defecto.
    # Si quieres campos de creación/actualización específicos para User, deben ser explícitos:
    # fecha_creacion = models.DateTimeField(auto_now_add=True)
    # fecha_actualizacion = models.DateTimeField(auto_now=True)

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

# Modelo de Categoría
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
    descripcion = models.TextField(blank=True, null=True) # Añadido de vuelta la descripción
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
    # Cambiado a CharField para el código de barras, ya que UUIDField es para IDs únicos generados.
    # Si quieres que el código de barras sea un UUID, pero ingresado manualmente, es mejor CharField.
    # Si es un UUID autogenerado, entonces UUIDField está bien, pero el `editable=False` lo hace no editable.
    # Asumo que es un código que se puede escanear/ingresar.
    codigo_barras = models.CharField(max_length=100, unique=True, blank=True, null=True) 
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        unique_together = ('nombre', 'tienda', 'talle') # Añadido talle a unique_together
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} ({self.talle}) - {self.tienda.nombre}"

# Modelo de Método de Pago
class MetodoPago(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True) # Añadido descripción de vuelta
    activo = models.BooleanField(default=True) # Renombrado is_active a activo para consistencia
    fecha_creacion = models.DateTimeField(auto_now_add=True) # Añadido de vuelta
    fecha_actualizacion = models.DateTimeField(auto_now=True) # Añadido de vuelta

    class Meta:
        verbose_name = "Método de Pago"
        verbose_name_plural = "Métodos de Pago"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

# Modelo de Venta
class Venta(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fecha_venta = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    metodo_pago = models.CharField(max_length=100, blank=True, null=True) # Nombre del método de pago como string
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='ventas')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='ventas_realizadas'
    )
    anulada = models.BooleanField(default=False) 
    # Nuevo campo para el porcentaje de descuento
    descuento_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text="Porcentaje de descuento aplicado a la venta total.")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"
        ordering = ['-fecha_venta']

    def __str__(self):
        return f"Venta {self.id} - Total: ${self.total} - Tienda: {self.tienda.nombre}"

# Modelo de Detalle de Venta
class DetalleVenta(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    # Cambiado a SET_NULL para producto, para evitar errores si un producto se elimina después de una venta
    producto = models.ForeignKey(Producto, on_delete=models.SET_NULL, null=True, blank=True, related_name='detalles_venta') 
    cantidad = models.IntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    # CAMBIO CLAVE AQUÍ: Nuevo campo para marcar si el detalle ha sido anulado individualmente
    anulado_individualmente = models.BooleanField(default=False) 
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Detalle de Venta"
        verbose_name_plural = "Detalles de Ventas" # Cambiado a plural consistente
        unique_together = ('venta', 'producto') 
        ordering = ['fecha_creacion'] # Ordenado por fecha de creación del detalle

    def __str__(self):
        return f"Detalle {self.id} - Venta {self.venta.id} - Producto: {self.producto.nombre if self.producto else 'N/A'} - Cantidad: {self.cantidad}"
