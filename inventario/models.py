# inventario/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid 
from django.utils import timezone 
from django.conf import settings 
from decimal import Decimal 
       
# Modelo de Usuario Personalizado
class User(AbstractUser):
    tienda = models.ForeignKey('Tienda', on_delete=models.SET_NULL, null=True, blank=True, related_name='empleados')

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
    descripcion = models.TextField(blank=True, null=True) 
    precio = models.DecimalField(max_digits=10, decimal_places=2) # Precio de venta
    costo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) # NUEVO CAMPO
    stock = models.IntegerField(default=0)
    talle = models.CharField(max_length=50, blank=True, null=True) 

    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='productos')
    codigo_barras = models.CharField(max_length=100, unique=True, blank=True, null=True) 
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        unique_together = ('nombre', 'tienda', 'talle') 
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} ({self.talle}) - {self.tienda.nombre}"

# Modelo de Método de Pago
class MetodoPago(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True) 
    activo = models.BooleanField(default=True) 
    # CAMBIO CLAVE: Indica si este método permite aranceles/planes configurables
    es_financiero = models.BooleanField(default=False, help_text="Marcar si este método implica un arancel (Tarjeta, QR, etc.).")
    fecha_creacion = models.DateTimeField(auto_now_add=True) 
    fecha_actualizacion = models.DateTimeField(auto_now=True) 

    class Meta:
        verbose_name = "Método de Pago"
        verbose_name_plural = "Métodos de Pago"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

# --- NUEVO MODELO: ARANCEL POR MÉTODO Y TIENDA ---
class ArancelMetodoTienda(models.Model):
    PLAN_CHOICES = [
        ('CONTADO', 'Contado / Pago Único'),
        ('1', '1 Cuota'),
        ('3', '3 Cuotas'),
        ('6', '6 Cuotas'),
        ('12', '12 Cuotas'),
        ('Z', 'Z (Ahora 12 / Plan Especial)'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='aranceles')
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.CASCADE, related_name='aranceles_por_tienda')
    
    # Campo que define el plan (solo relevante para Tarjeta de Crédito, Débito y QR)
    nombre_plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='CONTADO')
    arancel_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text="Arancel en porcentaje (%) que la tienda paga al procesar este pago/plan.")
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Arancel por Método y Tienda"
        verbose_name_plural = "Aranceles por Método y Tienda"
        unique_together = ('tienda', 'metodo_pago', 'nombre_plan')
        ordering = ['tienda', 'metodo_pago', 'nombre_plan']

    def __str__(self):
        return f"{self.tienda.nombre} - {self.metodo_pago.nombre} - {self.get_nombre_plan_display()} ({self.arancel_porcentaje}%)"
# ------------------------------------------------

# Modelo de Venta
class Venta(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fecha_venta = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    metodo_pago = models.CharField(max_length=100, blank=True, null=True)
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='ventas')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='ventas_realizadas'
    )
    anulada = models.BooleanField(default=False) 
    descuento_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text="Porcentaje de descuento aplicado a la venta total.")
    descuento_monto = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Monto de descuento aplicado a la venta total.")
    
    # NUEVOS CAMPOS: Referencia al arancel aplicado y el monto calculado
    arancel_aplicado = models.ForeignKey(ArancelMetodoTienda, on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas_con_arancel')
    arancel_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Monto total del arancel calculado para esta venta.")
    
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
    producto = models.ForeignKey(Producto, on_delete=models.SET_NULL, null=True, blank=True, related_name='detalles_venta') 
    cantidad = models.IntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    costo_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) # NUEVO CAMPO
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    anulado_individualmente = models.BooleanField(default=False) 
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Detalle de Venta"
        verbose_name_plural = "Detalles de Ventas" 
        unique_together = ('venta', 'producto') 
        ordering = ['fecha_creacion'] 

    def __str__(self):
        return f"Detalle {self.id} - Venta {self.venta.id} - Producto: {self.producto.nombre if self.producto else 'N/A'} - Cantidad: {self.cantidad}"

# --- MODELO PARA REGISTRO DE COMPRAS ---

class Compra(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='compras_totales') 
    fecha_compra = models.DateTimeField(default=timezone.now)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    proveedor = models.CharField(max_length=255, blank=True, null=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='compras_registradas')
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Compra (Total)"
        verbose_name_plural = "Compras (Totales)"
        ordering = ['-fecha_compra']

    def __str__(self):
        return f"Compra Total {self.id} - ${self.total} de {self.proveedor or 'N/A'} - Tienda: {self.tienda.nombre}"