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
    tiendas_autorizadas = models.ManyToManyField('Tienda', blank=True, related_name='usuarios_autorizados')
    cierre_caja_habilitado = models.BooleanField(default=False, help_text="Habilita el control de turnos y cierre de caja para este usuario")
    is_supervisor = models.BooleanField(default=False, help_text="Supervisor: puede ver ventas completas, agregar productos y ver cierres de caja")

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        ordering = ['username']

    def __str__(self):
        return self.username

# Modelo de Tienda
class Tienda(models.Model):
    FACTURACION_CHOICES = [
        # El valor interno 'AFIP' se conserva por compatibilidad (es el que efectivamente
        # implementa facturacion_service.py); la etiqueta ya refleja el nombre actual del organismo.
        ('AFIP', 'ARCA (ex AFIP) — Agencia de Recaudación y Control Aduanero'),
        ('ARCA', 'ARCA (alternativa, sin integración implementada)'),
        ('NINGUNA', 'Sin facturación electrónica'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=100, unique=True)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    
    # Campos fiscales para facturación
    cuit = models.CharField(max_length=13, blank=True, null=True, help_text="CUIT de la tienda (formato: XX-XXXXXXXX-X)")
    punto_venta = models.IntegerField(default=1, help_text="Punto de venta ARCA")
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
    
    # Configuración ARCA
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
        help_text="Marca esta casilla para usar el ambiente de testing/homologación de ARCA. Desmarca para producción."
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
    
    # Configuración E-commerce - Mercado Libre
    PLATAFORMA_ECOMMERCE_CHOICES = [
        ('NINGUNA', 'Sin integración e-commerce'),
        ('MERCADO_LIBRE', 'Mercado Libre'),
        ('TIENDA_NUBE', 'Tienda Nube'),
    ]
    plataforma_ecommerce = models.CharField(
        max_length=20, 
        choices=PLATAFORMA_ECOMMERCE_CHOICES, 
        default='NINGUNA',
        help_text="Plataforma de e-commerce a integrar con esta tienda"
    )
    
    # Credenciales Mercado Libre (OAuth)
    ml_access_token = models.TextField(
        blank=True, null=True,
        help_text="Access Token de Mercado Libre (obtenido mediante OAuth). No compartir públicamente."
    )
    ml_refresh_token = models.TextField(
        blank=True, null=True,
        help_text="Refresh Token de Mercado Libre para renovar el access token. No compartir públicamente."
    )
    ml_user_id = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="ID del usuario/vendedor en Mercado Libre"
    )
    ml_app_id = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="Application ID de Mercado Libre (Client ID)"
    )
    ml_client_secret = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="Client Secret de Mercado Libre. No compartir públicamente."
    )
    ml_token_expires_at = models.DateTimeField(
        blank=True, null=True,
        help_text="Fecha y hora de expiración del access token"
    )
    
    # Configuración de sincronización
    ml_sync_habilitado = models.BooleanField(
        default=False,
        help_text="Habilitar sincronización automática de productos y stock con Mercado Libre"
    )
    ml_sincronizar_stock = models.BooleanField(
        default=True,
        help_text="Sincronizar cambios de stock automáticamente con Mercado Libre"
    )
    ml_sincronizar_precios = models.BooleanField(
        default=True,
        help_text="Sincronizar cambios de precios automáticamente con Mercado Libre"
    )
    ml_sincronizar_productos = models.BooleanField(
        default=True,
        help_text="Sincronizar nuevos productos automáticamente con Mercado Libre"
    )
    
    # Modo de prueba
    ml_modo_test = models.BooleanField(
        default=True,
        help_text="Usar ambiente de testing/sandbox de Mercado Libre (True) o producción (False)"
    )
    
    # Ventas automáticas: facturación
    ml_facturar_ventas = models.BooleanField(
        default=True,
        help_text="Si está activo, las ventas procesadas por el webhook de Mercado Libre se facturan automáticamente (ARCA). Si está desactivado, solo se emite recibo (no se genera factura electrónica)."
    )
    ml_aranceles_automaticos = models.BooleanField(
        default=True,
        help_text="Si está activo, los cargos de ML se obtienen de las notificaciones (webhook) y se muestran en 'Descuentos Mercado Libre'. Si está desactivado, se usan los aranceles configurados manualmente y se muestran en 'Aranceles'."
    )

    # ── Tienda Nube ────────────────────────────────────────────────────────────
    # Credenciales OAuth
    tn_app_id = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="App ID de Tienda Nube (obtenido en el panel de partners)"
    )
    tn_client_secret = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="Client Secret de Tienda Nube. No compartir públicamente."
    )
    tn_access_token = models.TextField(
        blank=True, null=True,
        help_text="Access Token de Tienda Nube (obtenido mediante OAuth). No expira."
    )
    tn_store_id = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="ID de la tienda en Tienda Nube (user_id del token exchange)"
    )
    # ID del webhook registrado en TN (para poder borrarlo al desconectar)
    tn_webhook_id = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="ID del webhook order/paid registrado en Tienda Nube"
    )
    # Configuración
    tn_sync_habilitado = models.BooleanField(
        default=False,
        help_text="Habilitar procesamiento automático de ventas desde Tienda Nube"
    )
    tn_facturar_ventas = models.BooleanField(
        default=True,
        help_text="Facturar automáticamente ventas procesadas por webhook de Tienda Nube"
    )
    requiere_eleccion_plan = models.BooleanField(
        default=False,
        help_text="Fuerza a esta tienda (aunque sea legacy) a elegir y pagar un plan para poder seguir usando el sistema. No afecta a otras tiendas legacy."
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tienda"
        verbose_name_plural = "Tiendas" 
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

# Modelo para almacenar categorías de Mercado Libre
class CategoriaMercadoLibre(models.Model):
    """
    Almacena las categorías de Mercado Libre para evitar consultas constantes a la API
    """
    id = models.CharField(max_length=50, primary_key=True, help_text="ID de la categoría en Mercado Libre (ej: MLA1574)")
    nombre = models.CharField(max_length=255, help_text="Nombre de la categoría")
    site_id = models.CharField(max_length=10, default='MLA', help_text="ID del sitio (MLA=Argentina, MLB=Brasil, etc.)")
    
    # Información de la jerarquía
    parent_id = models.CharField(max_length=50, blank=True, null=True, help_text="ID de la categoría padre")
    is_leaf = models.BooleanField(default=False, help_text="Indica si es una categoría hoja (sin subcategorías)")
    
    # Información adicional
    total_items = models.IntegerField(default=0, help_text="Total de items en esta categoría")
    path_from_root = models.JSONField(default=list, blank=True, help_text="Ruta completa desde la raíz")
    
    # Metadatos
    fecha_actualizacion = models.DateTimeField(auto_now=True, help_text="Fecha de última actualización")
    fecha_creacion = models.DateTimeField(auto_now_add=True, help_text="Fecha de creación del registro")
    
    class Meta:
        verbose_name = "Categoría Mercado Libre"
        verbose_name_plural = "Categorías Mercado Libre"
        ordering = ['nombre']
        indexes = [
            models.Index(fields=['site_id', 'is_leaf']),
            models.Index(fields=['parent_id']),
        ]
    
    def __str__(self):
        return f"{self.nombre} ({self.id})"
    
    @property
    def es_hoja(self):
        """Alias para is_leaf en español"""
        return self.is_leaf

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

    producto_padre = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='variantes',
        help_text="Producto padre del que esta variante forma parte"
    )

    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='productos')
    codigo_barras = models.CharField(max_length=100, blank=True, null=True)

    # Carga masiva desde Excel/CSV: identificador propio de la tienda (distinto del
    # código de barras) para detectar reposición de stock vs. producto nuevo.
    codigo_interno = models.CharField(max_length=100, blank=True, null=True)
    # IVA resuelto al momento de cargar/actualizar el producto (por rubro o manual).
    iva_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # Rubro/categoría opcional (propio de cada tienda). Permite filtrar el listado y
    # editar precio/IVA/margen de forma masiva para todos los productos del rubro.
    rubro = models.ForeignKey('Rubro', on_delete=models.SET_NULL, null=True, blank=True, related_name='productos')

    # Integración con Mercado Libre
    ml_item_id = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="ID del producto en Mercado Libre (si está sincronizado)"
    )
    ml_sincronizado = models.BooleanField(
        default=False,
        help_text="Indica si este producto está sincronizado con Mercado Libre"
    )
    ml_sincronizar = models.BooleanField(
        default=False,
        help_text="Marca esta casilla para sincronizar este producto con Mercado Libre en la próxima sincronización"
    )
    ml_categoria_id = models.CharField(
        max_length=20, blank=True, null=True,
        help_text="ID de la categoría de Mercado Libre para este producto (ej: MLA1574)"
    )
    ml_ultima_sincronizacion = models.DateTimeField(
        blank=True, null=True,
        help_text="Fecha y hora de la última sincronización con Mercado Libre"
    )

    # Integración con Tienda Nube
    tn_product_id = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="ID del producto en Tienda Nube"
    )
    tn_variant_id = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="ID de la variante en Tienda Nube (usado para actualizar stock)"
    )
    tn_sincronizado = models.BooleanField(
        default=False,
        help_text="Indica si este producto está sincronizado con Tienda Nube"
    )

    stock_ultimo_ingreso = models.IntegerField(null=True, blank=True, help_text="Stock registrado tras el último ingreso manual")
    fecha_ultimo_ingreso = models.DateTimeField(null=True, blank=True, help_text="Fecha del último ingreso manual de stock")

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        unique_together = [('nombre', 'tienda', 'talle'), ('codigo_barras', 'tienda'), ('codigo_interno', 'tienda')]
        ordering = ['nombre']
        indexes = [
            models.Index(fields=['tienda'], name='producto_tienda_idx'),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.talle}) - {self.tienda.nombre}"


class Rubro(models.Model):
    """
    Catálogo propio de la tienda de "rubro -> % IVA", usado en la carga masiva de
    productos por Excel/CSV para resolver el IVA sin tener que re-tipearlo en cada
    archivo. No tiene relación con el modelo Categoria (legacy, sin uso real hoy).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='rubros')
    nombre = models.CharField(max_length=100)
    iva_porcentaje = models.DecimalField(max_digits=5, decimal_places=2)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Rubro"
        verbose_name_plural = "Rubros"
        unique_together = ('tienda', 'nombre')
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} ({self.iva_porcentaje}%) - {self.tienda.nombre}"


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
    
    # Plan predefinido o nombre personalizado (ej: 18 cuotas, Plan especial)
    nombre_plan = models.CharField(max_length=50, default='CONTADO', help_text='Plan predefinido o nombre personalizado')
    arancel_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text="Arancel en porcentaje (%) que la tienda paga al procesar este pago/plan.")
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Arancel por Método y Tienda"
        verbose_name_plural = "Aranceles por Método y Tienda"
        unique_together = ('tienda', 'metodo_pago', 'nombre_plan')
        ordering = ['tienda', 'metodo_pago', 'nombre_plan']

    def __str__(self):
        plan_display = dict(self.PLAN_CHOICES).get(self.nombre_plan, self.nombre_plan)
        return f"{self.tienda.nombre} - {self.metodo_pago.nombre} - {plan_display} ({self.arancel_porcentaje}%)"
# ------------------------------------------------

# --- NUEVO MODELO: ARANCEL MERCADO LIBRE POR CATEGORÍA ---
class ArancelMercadoLibre(models.Model):
    """
    Aranceles configurables por categoría de Mercado Libre para cada tienda.
    Solo se muestran las categorías que la tienda ha usado alguna vez.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='aranceles_ml')
    categoria_ml = models.ForeignKey(CategoriaMercadoLibre, on_delete=models.CASCADE, related_name='aranceles_por_tienda')
    arancel_porcentaje = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        help_text="Arancel en porcentaje (%) que la tienda paga a Mercado Libre por ventas en esta categoría."
    )
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Arancel Mercado Libre por Categoría"
        verbose_name_plural = "Aranceles Mercado Libre por Categoría"
        unique_together = ('tienda', 'categoria_ml')
        ordering = ['tienda', 'categoria_ml__nombre']
        indexes = [
            models.Index(fields=['tienda', 'categoria_ml']),
        ]

    def __str__(self):
        return f"{self.tienda.nombre} - {self.categoria_ml.nombre} ({self.categoria_ml.id}) - {self.arancel_porcentaje}%"
# ------------------------------------------------

# --- ARANCEL MERCADO LIBRE POR PRODUCTO (arancel % + costo envío por producto) ---
class ArancelMercadoLibreProducto(models.Model):
    """
    Aranceles y costo de envío configurables por PRODUCTO para ventas de Mercado Libre.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='aranceles_ml_producto')
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='aranceles_ml')
    arancel_porcentaje = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'),
        help_text="Arancel en % que ML cobra por ventas de este producto"
    )
    costo_envio = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'),
        help_text="Costo de envío estimado por unidad de este producto"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Arancel Mercado Libre por Producto"
        verbose_name_plural = "Aranceles Mercado Libre por Producto"
        unique_together = ('tienda', 'producto')
        ordering = ['tienda', 'producto__nombre']
        indexes = [models.Index(fields=['tienda', 'producto'])]

    def __str__(self):
        return f"{self.tienda.nombre} - {self.producto.nombre} - Arancel {self.arancel_porcentaje}% + Envío ${self.costo_envio}"
# ------------------------------------------------

# ── Clientes y Cuenta Corriente ────────────────────────────────────────────────

class Cliente(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='clientes')
    nombre_razon_social = models.CharField(max_length=255)
    cuit_cuil = models.CharField(max_length=13)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    telefono = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    # Soft delete: un cliente con historial de compras o cuenta corriente no se borra nunca en duro.
    activo = models.BooleanField(default=True)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        unique_together = ('tienda', 'cuit_cuil')
        ordering = ['nombre_razon_social']
        indexes = [
            models.Index(fields=['tienda', 'cuit_cuil']),
        ]

    def __str__(self):
        return f"{self.nombre_razon_social} ({self.cuit_cuil}) - {self.tienda.nombre}"


class MovimientoCuentaCorriente(models.Model):
    TIPO_CHOICES = [
        ('DEBITO', 'Débito (venta a cuenta)'),
        ('CREDITO', 'Crédito (pago / anulación)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='movimientos_cuenta_corriente')
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='movimientos_cuenta_corriente')
    venta = models.ForeignKey('Venta', on_delete=models.SET_NULL, null=True, blank=True, related_name='movimientos_cuenta_corriente')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='movimientos_cuenta_corriente')

    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    concepto = models.CharField(max_length=255, blank=True, default='')
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Movimiento de Cuenta Corriente"
        verbose_name_plural = "Movimientos de Cuenta Corriente"
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['cliente', 'fecha']),
        ]

    def __str__(self):
        return f"{self.cliente.nombre_razon_social} - {self.get_tipo_display()} - ${self.monto}"
# ------------------------------------------------

# Modelo de Venta
class Venta(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fecha_venta = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    metodo_pago = models.CharField(max_length=100, blank=True, null=True)
    monto_efectivo = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Monto pagado en efectivo. Para pagos combinados es solo la parte en efectivo."
    )
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
    costo_envio_ml = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Costo total de envío (solo ventas Mercado Libre)")
    # Desglose de cargos reales de Mercado Libre (obtenidos de fee_details en el webhook)
    ml_sale_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Cargo por venta (% comisión) cobrado por Mercado Libre")
    ml_fixed_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Costo fijo por transacción cobrado por Mercado Libre")
    ml_financing_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Costo por ofrecer cuotas cobrado por Mercado Libre")
    ml_shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Costo de envío real cobrado por Mercado Libre al vendedor (shipping.cost)")
    ml_tax_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Impuestos sobre los cargos de Mercado Libre")
    ml_fecha_entrega = models.DateTimeField(null=True, blank=True, help_text="Fecha de entrega real al comprador (del webhook shipments de ML)")
    origen_mercadolibre = models.BooleanField(default=False, help_text="True si la venta provino del webhook de Mercado Libre")
    ml_order_id = models.CharField(max_length=50, blank=True, null=True, help_text="ID de la orden en Mercado Libre (para evitar duplicados)")
    origen_tiendanube = models.BooleanField(default=False, help_text="True si la venta provino del webhook de Tienda Nube")
    tn_order_id = models.CharField(max_length=50, blank=True, null=True, help_text="ID de la orden en Tienda Nube (para evitar duplicados)")
    
    # Campos para facturación
    facturada = models.BooleanField(default=False, help_text="Indica si esta venta ha sido facturada")
    
    # Datos del cliente para facturación (opcional para consumidor final)
    cliente_nombre = models.CharField(max_length=255, blank=True, null=True, help_text="Nombre o razón social del cliente")
    cliente_cuit = models.CharField(max_length=13, blank=True, null=True, help_text="CUIT del cliente")
    cliente_domicilio = models.CharField(max_length=255, blank=True, null=True, help_text="Domicilio del cliente")
    cliente_tipo_documento = models.CharField(max_length=20, blank=True, null=True, help_text="Tipo de documento (DNI, CUIT, etc.)")

    # Cliente de la base de Clientes (opcional en cualquier venta; obligatorio si metodo_pago='Cuenta Corriente')
    cliente = models.ForeignKey('Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas')

    # Solo relevante para metodo_pago='Cuenta Corriente': fecha límite acordada para cancelar la deuda.
    fecha_limite_pago = models.DateField(null=True, blank=True, help_text="Fecha límite para cancelar el pago (Cuenta Corriente).")

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"
        ordering = ['-fecha_venta']
        indexes = [
            models.Index(fields=['tienda', 'fecha_venta'], name='venta_tienda_fecha_idx'),
            models.Index(fields=['tienda', 'anulada'], name='venta_tienda_anulada_idx'),
            models.Index(fields=['usuario'], name='venta_usuario_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tienda', 'ml_order_id'],
                condition=models.Q(ml_order_id__isnull=False),
                name='unique_ml_order_per_tienda'
            ),
            models.UniqueConstraint(
                fields=['tienda', 'tn_order_id'],
                condition=models.Q(tn_order_id__isnull=False),
                name='unique_tn_order_per_tienda'
            ),
        ]

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
        indexes = [
            models.Index(fields=['venta', 'anulado_individualmente'], name='detalle_venta_anulado_idx'),
        ]

    def __str__(self):
        return f"Detalle {self.id} - Venta {self.venta.id} - Producto: {self.producto.nombre if self.producto else 'N/A'} - Cantidad: {self.cantidad}"


# ── Presupuestos (cotizaciones) ───────────────────────────────────────────────

class Presupuesto(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('CONVERTIDO', 'Convertido en Venta'),
        ('CANCELADO', 'Cancelado'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='presupuestos')
    # El cliente es obligatorio: a diferencia de Venta, todo presupuesto se genera para alguien puntual.
    cliente = models.ForeignKey('Cliente', on_delete=models.PROTECT, related_name='presupuestos')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='presupuestos_generados',
    )

    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    metodo_pago_sugerido = models.CharField(max_length=100, blank=True, null=True)

    descuento_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    descuento_monto = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    recargo_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    recargo_monto = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    # Se completa cuando el presupuesto se convierte en una venta real (no descuenta stock antes de eso).
    venta_generada = models.ForeignKey(
        'Venta', on_delete=models.SET_NULL, null=True, blank=True, related_name='presupuesto_origen',
    )

    notas = models.TextField(blank=True, null=True)
    fecha_vigencia = models.DateField(null=True, blank=True, help_text="Fecha hasta la cual el presupuesto es válido.")

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Presupuesto"
        verbose_name_plural = "Presupuestos"
        ordering = ['-fecha_creacion']
        indexes = [
            models.Index(fields=['tienda', 'fecha_creacion'], name='presupuesto_tienda_fecha_idx'),
        ]

    def __str__(self):
        return f"Presupuesto {self.id} - {self.cliente.nombre_razon_social} - ${self.total}"


class DetallePresupuesto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    presupuesto = models.ForeignKey(Presupuesto, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.SET_NULL, null=True, blank=True, related_name='detalles_presupuesto')
    cantidad = models.IntegerField(default=1)
    # Precio "congelado" al momento de cotizar (no se recalcula si el producto cambia de precio después).
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Detalle de Presupuesto"
        verbose_name_plural = "Detalles de Presupuesto"
        ordering = ['id']

    def __str__(self):
        return f"Detalle {self.id} - Presupuesto {self.presupuesto_id} - Producto: {self.producto.nombre if self.producto else 'N/A'}"
# ------------------------------------------------

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
    numero_comprobante = models.IntegerField(blank=True, null=True, help_text="Número de comprobante asignado por ARCA")
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
    
    # Estado y respuesta de ARCA
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    sistema_facturacion = models.CharField(max_length=10, choices=Tienda.FACTURACION_CHOICES)
    
    # Respuesta de ARCA
    cae = models.CharField(max_length=14, blank=True, null=True, help_text="CAE (Código de Autorización Electrónica) de ARCA")
    fecha_vencimiento_cae = models.DateField(blank=True, null=True, help_text="Fecha de vencimiento del CAE")
    numero_comprobante_afip = models.BigIntegerField(blank=True, null=True, help_text="Número de comprobante retornado por ARCA")
    
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

# Modelo de Nota de Crédito Electrónica
class NotaCredito(models.Model):
    TIPO_NC_CHOICES = [
        ('A', 'Nota de Crédito A (Responsable Inscripto)'),
        ('B', 'Nota de Crédito B (Consumidor Final)'),
        ('C', 'Nota de Crédito C (Exento/Monotributo)'),
    ]

    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('EMITIDA', 'Emitida'),
        ('ERROR', 'Error'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    factura_origen = models.ForeignKey(
        'Factura', on_delete=models.CASCADE, related_name='notas_credito',
        help_text="Factura electrónica original a la que se vincula esta nota de crédito"
    )
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='notas_credito')

    # Números de comprobante
    numero_comprobante = models.IntegerField(blank=True, null=True)
    punto_venta = models.IntegerField()
    tipo_comprobante = models.CharField(max_length=1, choices=TIPO_NC_CHOICES, default='B')

    # Motivo y monto
    motivo = models.TextField(blank=True, null=True, help_text="Motivo de la nota de crédito")
    monto = models.DecimalField(max_digits=10, decimal_places=2, help_text="Monto total de la nota de crédito (incluye IVA si aplica)")
    impuesto_iva = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    # Datos del cliente (heredados de la factura original)
    cliente_nombre = models.CharField(max_length=255)
    cliente_cuit = models.CharField(max_length=13, blank=True, null=True)

    # Estado y respuesta ARCA
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    sistema_facturacion = models.CharField(max_length=10, choices=Tienda.FACTURACION_CHOICES)
    cae = models.CharField(max_length=14, blank=True, null=True)
    fecha_vencimiento_cae = models.DateField(blank=True, null=True)
    numero_comprobante_afip = models.BigIntegerField(blank=True, null=True)
    respuesta_bruta = models.TextField(blank=True, null=True)
    error_mensaje = models.TextField(blank=True, null=True)

    fecha_emision = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Nota de Crédito"
        verbose_name_plural = "Notas de Crédito"
        ordering = ['-fecha_emision']

    def __str__(self):
        return f"NC {self.tipo_comprobante} {self.punto_venta:04d}-{self.numero_comprobante or 'PEND'} - ${self.monto}"

    @property
    def numero_nc_completo(self):
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

# Modelo para almacenar tokens FCM (Firebase Cloud Messaging) para notificaciones push
class FCMToken(models.Model):
    """
    Almacena los tokens FCM de los usuarios para enviar notificaciones push.
    Un usuario puede tener múltiples tokens (diferentes dispositivos).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='fcm_tokens'
    )
    token = models.TextField(unique=True, help_text="Token FCM del dispositivo")
    device_info = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Información del dispositivo (navegador, SO, etc.)"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    activo = models.BooleanField(default=True, help_text="Indica si el token está activo")

    class Meta:
        verbose_name = "Token FCM"
        verbose_name_plural = "Tokens FCM"
        ordering = ['-fecha_creacion']
        indexes = [
            models.Index(fields=['user', 'activo']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.device_info or 'Dispositivo desconocido'}"


class HistorialAccion(models.Model):
    ACCION_CHOICES = [
        ('anulacion_venta',   'Anulación de venta'),
        ('anulacion_item',    'Anulación de ítem'),
        ('ingreso_stock',     'Ingreso de stock'),
        ('ajuste_stock',      'Ajuste de stock'),
        ('cambio_devolucion', 'Cambio / Devolución'),
    ]
    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tienda   = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='historial_acciones')
    usuario  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='historial_acciones')
    accion   = models.CharField(max_length=30, choices=ACCION_CHOICES)
    detalle  = models.CharField(max_length=500)
    objeto_id = models.UUIDField(null=True, blank=True)
    fecha    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Historial de acción'
        verbose_name_plural = 'Historial de acciones'
        indexes = [models.Index(fields=['tienda', '-fecha'], name='historial_tienda_fecha_idx')]

    def __str__(self):
        return f"{self.get_accion_display()} · {self.usuario} · {self.fecha:%d/%m/%Y %H:%M}"


class CompraStock(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='compras_stock')
    fecha_compra = models.DateField(default=timezone.now)
    proveedor = models.CharField(max_length=255, blank=True)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    recibido = models.BooleanField(default=False)
    notas = models.TextField(blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='compras_stock_registradas'
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha_compra', '-fecha_creacion']
        verbose_name = "Compra de Stock"
        verbose_name_plural = "Compras de Stock"

    def __str__(self):
        return f"{self.tienda.nombre} - {self.proveedor or 'Sin proveedor'} - ${self.monto}"


class CierreCaja(models.Model):
    ESTADO_CHOICES = [
        ('ABIERTO', 'Abierto'),
        ('CERRADO', 'Cerrado'),
    ]

    tienda = models.ForeignKey('Tienda', on_delete=models.CASCADE, related_name='cierres_caja')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='cierres_caja')
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='ABIERTO')

    fecha_apertura = models.DateTimeField(default=timezone.now)
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    cambio_inicial = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    # Cantidades de billetes/monedas en el recuento físico
    billetes_20000 = models.IntegerField(default=0)
    billetes_10000 = models.IntegerField(default=0)
    billetes_2000 = models.IntegerField(default=0)
    billetes_1000 = models.IntegerField(default=0)
    billetes_500 = models.IntegerField(default=0)
    billetes_200 = models.IntegerField(default=0)
    billetes_100 = models.IntegerField(default=0)
    monedas = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    # Totales calculados al cerrar
    total_ventas_efectivo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_gastos = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Solo EGRESO/Gasto (impacta métricas)")
    total_retiros = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Retiros de caja (no impacta métricas)")
    total_ingresos_extra = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Ingresos de efectivo extra (no impacta métricas)")
    total_egresos = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Total salidas de caja (gastos + retiros)")
    total_recuento_fisico = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    diferencia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    notas = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-fecha_apertura']
        verbose_name = "Cierre de Caja"
        verbose_name_plural = "Cierres de Caja"

    def __str__(self):
        usuario_str = self.usuario.username if self.usuario else 'N/A'
        return f"Cierre {self.id} - {self.tienda.nombre} - {usuario_str} - {self.fecha_apertura.strftime('%d/%m/%Y %H:%M')}"

    def calcular_recuento_fisico(self):
        billete_total = (
            self.billetes_20000 * 20000 +
            self.billetes_10000 * 10000 +
            self.billetes_2000 * 2000 +
            self.billetes_1000 * 1000 +
            self.billetes_500 * 500 +
            self.billetes_200 * 200 +
            self.billetes_100 * 100
        )
        return Decimal(str(billete_total)) + Decimal(str(self.monedas or 0))


class EgresoCaja(models.Model):
    TIPO_CHOICES = [
        ('EGRESO', 'Gasto'),
        ('RETIRO', 'Retiro de caja'),
        ('INGRESO', 'Ingreso de efectivo'),
    ]

    cierre_caja = models.ForeignKey(CierreCaja, on_delete=models.CASCADE, related_name='egresos')
    tienda = models.ForeignKey('Tienda', on_delete=models.CASCADE, related_name='egresos_caja')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='egresos_caja')

    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='EGRESO')
    concepto = models.CharField(max_length=255)
    importe = models.DecimalField(max_digits=12, decimal_places=2)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-fecha']
        verbose_name = "Egreso de Caja"
        verbose_name_plural = "Egresos de Caja"

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.concepto} - ${self.importe}"


# ── Planes y Suscripciones ────────────────────────────────────────────────────

class Plan(models.Model):
    TIER_CHOICES = [
        ('starter',  'Starter'),
        ('pro',      'Pro'),
        ('advanced', 'Advanced'),
        # Plan interno para tiendas exceptuadas de límites/cobro (ver plan_enforcement._es_legacy).
        # No se ofrece en alta pública ni en cambio de plan self-service; solo asignable desde Django Admin.
        ('legacy',   'Legacy (sin restricciones)'),
    ]

    nombre           = models.CharField(max_length=20, choices=TIER_CHOICES, unique=True)
    precio_mensual   = models.DecimalField(max_digits=10, decimal_places=2)
    # None = ilimitado
    max_productos    = models.IntegerField(null=True, blank=True)
    max_usuarios     = models.IntegerField(null=True, blank=True)
    # Feature flags
    permite_factura_electronica    = models.BooleanField(default=False)
    permite_integracion_ecommerce  = models.BooleanField(default=False)  # ML + TN
    # ID del plan de suscripción en Mercado Pago (preapproval_plan_id)
    mp_plan_id       = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        verbose_name = "Plan"
        verbose_name_plural = "Planes"
        ordering = ['precio_mensual']

    def __str__(self):
        return f"{self.get_nombre_display()} — ${self.precio_mensual}/mes"


class Suscripcion(models.Model):
    ESTADO_CHOICES = [
        ('pending',   'Pendiente de pago'),
        ('trial',     'Período de prueba'),
        ('activa',    'Activa'),
        ('gracia',    'Período de gracia'),
        ('cancelada', 'Cancelada'),
        ('pausada',   'Pausada'),
    ]

    DIAS_TRIAL  = 7
    DIAS_GRACIA = 5

    id     = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tienda = models.OneToOneField(Tienda, on_delete=models.CASCADE, related_name='suscripcion')
    plan   = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='suscripciones')

    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='trial')

    # Fechas
    fecha_inicio        = models.DateTimeField(default=timezone.now)
    fecha_fin_trial     = models.DateTimeField(null=True, blank=True)
    fecha_proximo_cobro = models.DateTimeField(null=True, blank=True)
    fecha_inicio_gracia = models.DateTimeField(null=True, blank=True)
    fecha_cancelacion   = models.DateTimeField(null=True, blank=True)

    # Mercado Pago
    mp_preapproval_id = models.CharField(max_length=255, blank=True, null=True)
    mp_payer_email    = models.EmailField(blank=True, null=True)

    fecha_creacion     = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Suscripción"
        verbose_name_plural = "Suscripciones"

    def __str__(self):
        return f"{self.tienda.nombre} — {self.plan.get_nombre_display()} — {self.get_estado_display()}"

    @property
    def esta_activa(self):
        """True si la tienda puede operar. Pending y cancelada/pausada no tienen acceso."""
        return self.estado in ('trial', 'activa', 'gracia')

    @property
    def dias_gracia_restantes(self):
        if self.estado == 'gracia' and self.fecha_inicio_gracia:
            transcurridos = (timezone.now() - self.fecha_inicio_gracia).days
            return max(0, self.DIAS_GRACIA - transcurridos)
        return None

    def puede_agregar_producto(self, cantidad_actual):
        if self.plan.max_productos is None:
            return True
        return cantidad_actual < self.plan.max_productos

    def puede_agregar_usuario(self, cantidad_actual):
        if self.plan.max_usuarios is None:
            return True
        return cantidad_actual < self.plan.max_usuarios

    def permite_feature(self, feature):
        """
        feature: 'factura_electronica' | 'ecommerce'
        Tiendas sin suscripción (legacy) tienen acceso total → chequear en la view.
        """
        if feature == 'factura_electronica':
            return self.plan.permite_factura_electronica
        if feature == 'ecommerce':
            return self.plan.permite_integracion_ecommerce
        return True


# Asegurar que los modelos estén disponibles para importación
__all__ = [
    'User', 'Tienda', 'Categoria', 'Producto', 'MetodoPago',
    'ArancelMetodoTienda', 'ArancelMercadoLibre', 'ArancelMercadoLibreProducto', 'CategoriaMercadoLibre',
    'Venta', 'DetalleVenta', 'Compra', 'CompraStock',
    'Factura', 'CambioDevolucion', 'DetalleCambioDevolucion', 'FCMToken',
    'CierreCaja', 'EgresoCaja', 'Plan', 'Suscripcion',
    'Cliente', 'MovimientoCuentaCorriente', 'Rubro',
    'Presupuesto', 'DetallePresupuesto',
]