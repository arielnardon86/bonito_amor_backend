# BONITO_AMOR/backend/inventario/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser, UserManager
import uuid
from django.utils.text import slugify
from django.conf import settings # Importar settings para referenciar AUTH_USER_MODEL

# --- MODELO DE USUARIO PERSONALIZADO ---
# Definir el modelo User personalizado primero
class User(AbstractUser):
    # Relación ForeignKey con el modelo Tienda.
    # Un usuario puede estar asociado a una tienda (o a ninguna, si es superusuario global).
    tienda = models.ForeignKey('Tienda', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')

    # Es importante especificar el UserManager por defecto si no añades lógica de gestión de usuarios personalizada
    objects = UserManager()

    def __str__(self):
        # Muestra el nombre de usuario y, si está asociado, el nombre de la tienda
        if self.tienda:
            return f"{self.username} ({self.tienda.nombre})"
        return self.username

# --- Resto de tus modelos ---

class Categoria(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre

class Tienda(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True, max_length=255, blank=True)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tienda"
        verbose_name_plural = "Tiendas"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre

class Producto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True, related_name='productos')
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='productos')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        unique_together = ('nombre', 'tienda') # Un producto con el mismo nombre es único por tienda

    def __str__(self):
        return f"{self.nombre} ({self.tienda.nombre})"

class Venta(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='ventas')
    fecha_venta = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    metodo_pago = models.CharField(max_length=50, default='Efectivo')
    cliente_nombre = models.CharField(max_length=255, blank=True, null=True)
    cliente_email = models.EmailField(blank=True, null=True)
    
    class Meta:
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"
        ordering = ['-fecha_venta']

    def __str__(self):
        return f"Venta {self.id} en {self.tienda.nombre} - Total: {self.total}"

class DetalleVenta(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.SET_NULL, null=True, related_name='detalles_venta')
    cantidad = models.IntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Detalle de Venta"
        verbose_name_plural = "Detalles de Venta"

    def __str__(self):
        return f"Detalle de Venta {self.id} - Producto: {self.producto.nombre if self.producto else 'N/A'} - Cantidad: {self.cantidad}"

# ELIMINADO: Ya no necesitamos UserProfile porque el campo 'tienda' está directamente en el modelo User.
# class UserProfile(models.Model):
#     user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
#     tienda = models.ForeignKey('Tienda', on_delete=models.SET_NULL, null=True, blank=True, related_name='user_profiles')
#     def __str__(self):
#         return f"Perfil de {self.user.username} en {self.tienda.nombre if self.tienda else 'N/A'}"
