# BONITO_AMOR/backend/inventario/models.py
from django.db import models
from django.contrib.auth import get_user_model
import uuid # Para generar UUIDs para codigo_barras si no se proporciona
from django.utils.text import slugify # Para generar slugs

User = get_user_model()

class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Categorías"

    def __str__(self):
        return self.nombre

# --- NUEVO MODELO: Tienda ---
class Tienda(models.Model):
    nombre = models.CharField(max_length=255, unique=True)
    # El slug será usado en las URLs para identificar la tienda (ej. /la-pasion-del-hincha-yofre-login)
    slug = models.SlugField(max_length=255, unique=True, help_text="Identificador único para la URL de la tienda (ej. 'bonito-amor', 'la-pasion-del-hincha-yofre')")
    descripcion = models.TextField(blank=True, null=True)
    # Puedes añadir más campos aquí como logo, dirección, etc.

    class Meta:
        verbose_name_plural = "Tiendas"

    def __str__(self):
        return self.nombre

class Producto(models.Model):
    # Relacionar Producto con Tienda
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='productos', null=True, blank=True) # <--- CAMBIO CLAVE AQUÍ
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    # Código de barras se generará si no se proporciona
    codigo_barras = models.CharField(max_length=100, unique=True, blank=True, null=True) 
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    # Talle puede ser un CharField para flexibilidad (XS, S, M, L, XL, NUM36, NUM38, etc.)
    talle = models.CharField(max_length=50, blank=True, null=True) 
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True, related_name='productos')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Productos"

    def save(self, *args, **kwargs):
        if not self.codigo_barras:
            # Genera un UUID y lo convierte a un entero para EAN13 (limitado a 12 dígitos)
            # Esto es una simplificación, un EAN13 real tiene un checksum
            # Para producción, considera librerías como python-barcode
            self.codigo_barras = str(uuid.uuid4().int)[:12] # Tomamos los primeros 12 dígitos
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} ({self.talle}) - Stock: {self.stock}"

class Venta(models.Model):
    # Relacionar Venta con Tienda
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='ventas', null=True, blank=True) # <--- CAMBIO CLAVE AQUÍ
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='ventas')
    fecha_venta = models.DateTimeField(auto_now_add=True)
    total_venta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    anulada = models.BooleanField(default=False)
    metodo_pago = models.CharField(max_length=50, blank=True, null=True) # Ej: 'Efectivo', 'Tarjeta', 'Transferencia'

    class Meta:
        verbose_name_plural = "Ventas"
        ordering = ['-fecha_venta'] # Ordenar por fecha de venta descendente

    def __str__(self):
        return f"Venta #{self.id} - Total: ${self.total_venta} - Anulada: {self.anulada}"

class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='detalles_venta')
    cantidad = models.IntegerField()
    precio_unitario_venta = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name_plural = "Detalles de Venta"

    def __str__(self):
        return f"{self.cantidad} de {self.producto.nombre} en Venta #{self.venta.id}"

