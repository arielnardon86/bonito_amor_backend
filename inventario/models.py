# inventario/models.py - CÓDIGO COMPLETO Y CORREGIDO
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
    FACTURACION_CHOICES = [
        ('AFIP', 'AFIP (Administración Federal de Ingresos Públicos)'),
        ('ARCA', 'ARCA (Administración de Recursos de la Administración Nacional)'),
        ('NINGUNA', 'Sin facturación electrónica'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=100, unique=True)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    
    # Campos fiscales para facturación
    cuit = models.CharField(max_length=13, blank=True, null=True, help_text="CUIT de la tienda (formato: XX-XXXXXXXX-X)")
    punto_venta = models.IntegerField(default=1, help_text="Punto de venta AFIP/ARCA")
    tipo_facturacion = models.CharField(max_length=10, choices=FACTURACION_CHOICES, default='NINGUNA', help_text="Sistema de facturación a utilizar")
    
    # Condición IVA del emisor (tienda)
    CONDICION_IVA_CHOICES = [
        ('RI', 'Responsable Inscripto'),
        ('MT', 'Monotributista'),
        ('CF', 'Consumidor Final'),
        ('EX', 'Exento'),
        ('NR', 'No Responsable'),
    ]
    condicion_iva_emisor = models.CharField(
        max_length=2, 
        choices=CONDICION_IVA_CHOICES, 
        default='MT',
        help_text="Condición frente al IVA del emisor (tienda). IMPORTANTE: Monotributistas SOLO pueden emitir Factura C. Responsables Inscriptos pueden emitir Factura A, B o C según el cliente."
    )
    
    # Configuración AFIP
    certificado_afip = models.TextField(
        blank=True, null=True, 
        help_text="⚠️ IMPORTANTE: Pega aquí el CONTENIDO COMPLETO del archivo .crt codificado en base64 (NO solo el nombre del archivo). Usa: python manage.py convertir_certificados_afip certificado.crt clave.key"
    )
    clave_privada_afip = models.TextField(
        blank=True, null=True, 
        help_text="⚠️ IMPORTANTE: Pega aquí el CONTENIDO COMPLETO del archivo .key codificado en base64 (NO solo el nombre del archivo). Usa: python manage.py convertir_certificados_afip certificado.crt clave.key"
    )
    modo_test_afip = models.BooleanField(
        default=True, 
        help_text="Marca esta casilla para usar el ambiente de testing/homologación de AFIP. Desmarca para producción."
    )
    
    # Configuración ARCA (si aplica)
    api_key_arca = models.CharField(
        max_length=255, blank=True, null=True, 
        help_text="API Key proporcionada por tu proveedor de servicios ARCA. Contacta a tu proveedor para obtenerla."
    )
    url_arca = models.URLField(
        blank=True, null=True, 
        help_text="URL del endpoint del servicio ARCA. Ejemplo: https://api.arca.com/v1/facturacion. Consulta la documentación de tu proveedor."
    )
    
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
        ('Z', 'Z (Plan Z)'),
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
    
    # --- NUEVOS CAMPOS: RECARGO ---
    recargo_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text="Porcentaje de recargo aplicado a la venta total.")
    recargo_monto = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Monto de recargo aplicado a la venta total.")
    # -----------------------------
    
    # NUEVOS CAMPOS: Referencia al arancel aplicado y el monto calculado
    arancel_aplicado = models.ForeignKey(ArancelMetodoTienda, on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas_con_arancel')
    arancel_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Monto total del arancel calculado para esta venta.")
    
    # Campos para facturación
    facturada = models.BooleanField(default=False, help_text="Indica si esta venta ha sido facturada")
    
    # Datos del cliente para facturación (opcional para consumidor final)
    cliente_nombre = models.CharField(max_length=255, blank=True, null=True, help_text="Nombre o razón social del cliente")
    cliente_cuit = models.CharField(max_length=13, blank=True, null=True, help_text="CUIT del cliente")
    cliente_domicilio = models.CharField(max_length=255, blank=True, null=True, help_text="Domicilio del cliente")
    cliente_tipo_documento = models.CharField(max_length=20, blank=True, null=True, help_text="Tipo de documento (DNI, CUIT, etc.)")
    
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

# Modelo de Factura Electrónica
class Factura(models.Model):
    TIPO_FACTURA_CHOICES = [
        ('A', 'Factura A (Responsable Inscripto)'),
        ('B', 'Factura B (Consumidor Final)'),
        ('C', 'Factura C (Exento)'),
    ]
    
    CONDICION_IVA_CHOICES = [
        ('RI', 'Responsable Inscripto'),
        ('CF', 'Consumidor Final'),
        ('EX', 'Exento'),
        ('MT', 'Monotributo'),
        ('NR', 'No Responsable'),
    ]
    
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('EMITIDA', 'Emitida'),
        ('ANULADA', 'Anulada'),
        ('ERROR', 'Error'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    venta = models.OneToOneField(Venta, on_delete=models.CASCADE, related_name='factura')
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='facturas')
    
    # Números de factura
    numero_comprobante = models.IntegerField(blank=True, null=True, help_text="Número de comprobante asignado por AFIP/ARCA")
    punto_venta = models.IntegerField(help_text="Punto de venta utilizado")
    tipo_comprobante = models.CharField(max_length=1, choices=TIPO_FACTURA_CHOICES, default='B')
    
    # Datos del cliente
    cliente_nombre = models.CharField(max_length=255)
    cliente_cuit = models.CharField(max_length=13, blank=True, null=True)
    cliente_domicilio = models.CharField(max_length=255, blank=True, null=True)
    cliente_tipo_documento = models.CharField(max_length=20, blank=True, null=True)
    cliente_condicion_iva = models.CharField(max_length=2, choices=CONDICION_IVA_CHOICES, default='CF')
    
    # Totales
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    impuesto_iva = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Estado y respuesta de AFIP/ARCA
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    sistema_facturacion = models.CharField(max_length=10, choices=Tienda.FACTURACION_CHOICES)
    
    # Respuesta de AFIP/ARCA
    cae = models.CharField(max_length=14, blank=True, null=True, help_text="CAE (Código de Autorización Electrónica) de AFIP")
    fecha_vencimiento_cae = models.DateField(blank=True, null=True, help_text="Fecha de vencimiento del CAE")
    numero_comprobante_afip = models.BigIntegerField(blank=True, null=True, help_text="Número de comprobante retornado por AFIP")
    
    # Datos adicionales de la respuesta
    respuesta_bruta = models.TextField(blank=True, null=True, help_text="Respuesta completa del servicio de facturación (JSON)")
    error_mensaje = models.TextField(blank=True, null=True, help_text="Mensaje de error si la facturación falló")
    
    # PDF generado (opcional, almacenar en storage)
    pdf_factura = models.FileField(upload_to='facturas/', blank=True, null=True, help_text="PDF de la factura generada")
    
    fecha_emision = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Factura"
        verbose_name_plural = "Facturas"
        ordering = ['-fecha_emision']
        indexes = [
            models.Index(fields=['tienda', 'numero_comprobante', 'punto_venta']),
            models.Index(fields=['cae']),
        ]

    def __str__(self):
        return f"Factura {self.tipo_comprobante} {self.punto_venta}-{self.numero_comprobante or 'PEND'} - {self.tienda.nombre} - ${self.total}"
    
    @property
    def numero_factura_completo(self):
        """Retorna el número de factura en formato estándar: punto_venta-numero"""
        if self.numero_comprobante:
            return f"{self.punto_venta:04d}-{self.numero_comprobante:08d}"
        return f"{self.punto_venta:04d}-PENDIENTE"

# Modelo de Cambio/Devolución
class CambioDevolucion(models.Model):
    TIPO_CHOICES = [
        ('DEVOLUCION', 'Devolución Total'),
        ('CAMBIO', 'Cambio de Producto'),
        ('DEVOLUCION_PARCIAL', 'Devolución Parcial'),
    ]
    
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('PROCESADO', 'Procesado'),
        ('CANCELADO', 'Cancelado'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    venta_original = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='cambios_devoluciones', help_text="Venta original de la que se realiza el cambio/devolución")
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='cambios_devoluciones')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='cambios_devoluciones_procesados',
        help_text="Usuario que procesó el cambio/devolución"
    )
    
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='CAMBIO', help_text="Tipo de cambio/devolución")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PROCESADO')
    
    # Motivo del cambio/devolución
    motivo = models.TextField(blank=True, null=True, help_text="Motivo del cambio o devolución")
    
    # Totales del cambio/devolución
    monto_devolucion = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Monto a devolver al cliente (productos devueltos)")
    monto_nuevo = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Monto de productos nuevos recibidos en el cambio")
    monto_diferencia = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Diferencia: positivo = cliente debe pagar, negativo = saldo a favor del cliente")
    
    # Saldo a favor del cliente (si monto_diferencia es negativo)
    saldo_a_favor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Saldo a favor del cliente que queda pendiente")
    saldo_utilizado = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Saldo a favor que fue utilizado en compras posteriores")
    
    # Nota de crédito (recibo generado por saldo a favor)
    nota_credito_generada = models.BooleanField(default=False, help_text="Indica si se generó un recibo/nota de crédito por el saldo a favor")
    venta_nota_credito = models.ForeignKey(
        Venta,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='nota_credito_origen',
        help_text="Venta/Recibo generado como nota de crédito (saldo a favor)"
    )
    
    # Diferencia a pagar - crear venta pendiente que se completa desde el flujo normal
    diferencia_pendiente = models.BooleanField(default=False, help_text="Indica si hay una diferencia a pagar pendiente")
    venta_diferencia_pendiente = models.ForeignKey(
        Venta,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cambio_devolucion_diferencia',
        help_text="Venta creada para la diferencia a pagar (se completa desde el flujo normal de ventas)"
    )
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Cambio/Devolución"
        verbose_name_plural = "Cambios/Devoluciones"
        ordering = ['-fecha_creacion']
    
    def __str__(self):
        return f"Cambio/Devolución {self.id} - Venta {self.venta_original.id} - {self.get_tipo_display()}"

# Modelo de Detalle de Cambio/Devolución
class DetalleCambioDevolucion(models.Model):
    ACCION_CHOICES = [
        ('DEVOLVER', 'Devolver Producto'),
        ('CAMBIAR', 'Cambiar Producto'),
        ('AGREGAR', 'Agregar Producto Nuevo'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cambio_devolucion = models.ForeignKey(CambioDevolucion, on_delete=models.CASCADE, related_name='detalles')
    
    # Producto original de la venta (si se devuelve o cambia)
    detalle_venta_original = models.ForeignKey(
        DetalleVenta, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='cambios_devoluciones',
        help_text="Detalle de venta original que se devuelve o cambia"
    )
    
    # Producto nuevo (si se cambia por otro)
    producto_nuevo = models.ForeignKey(
        Producto, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='cambios_recibidos',
        help_text="Producto nuevo que se recibe en el cambio"
    )
    
    accion = models.CharField(max_length=20, choices=ACCION_CHOICES, help_text="Acción realizada sobre el producto")
    cantidad = models.IntegerField(default=1, help_text="Cantidad de productos afectados")
    
    # Precios
    precio_unitario_devuelto = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Precio unitario del producto devuelto")
    precio_unitario_nuevo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Precio unitario del producto nuevo")
    subtotal_devuelto = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Subtotal del producto devuelto")
    subtotal_nuevo = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Subtotal del producto nuevo")
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Detalle de Cambio/Devolución"
        verbose_name_plural = "Detalles de Cambios/Devoluciones"
        ordering = ['fecha_creacion']
    
    def __str__(self):
        return f"Detalle {self.id} - {self.get_accion_display()} - Cantidad: {self.cantidad}"

# Asegurar que los modelos estén disponibles para importación
__all__ = [
    'User', 'Tienda', 'Categoria', 'Producto', 'MetodoPago', 
    'ArancelMetodoTienda', 'Venta', 'DetalleVenta', 'Compra', 
    'Factura', 'CambioDevolucion', 'DetalleCambioDevolucion'
]