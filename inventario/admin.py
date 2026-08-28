# inventario/admin.py - CÓDIGO COMPLETO Y CORREGIDO
# BONITO_AMOR/backend/inventario/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.utils import timezone
from .models import User, Tienda, Categoria, Producto, Venta, DetalleVenta, MetodoPago, ArancelMetodoTienda, Factura, Plan, Suscripcion

# Configuración para el modelo de Usuario personalizado
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Permisos del sistema', {'fields': ('is_supervisor', 'cierre_caja_habilitado')}),
        ('Tiendas', {'fields': ('tienda', 'tiendas_autorizadas')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Permisos del sistema', {'fields': ('is_supervisor', 'cierre_caja_habilitado')}),
        ('Tiendas', {'fields': ('tienda', 'tiendas_autorizadas')}),
    )
    list_display = ('username', 'email', 'is_staff', 'is_superuser', 'is_supervisor', 'cierre_caja_habilitado', 'tienda', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_supervisor', 'cierre_caja_habilitado', 'tienda')
    search_fields = ('username', 'email', 'tienda__nombre')
    filter_horizontal = ('tiendas_autorizadas',)

# Configuración para el modelo de Tienda
@admin.register(Tienda)
class TiendaAdmin(admin.ModelAdmin):
    # Verificar si los campos de ML existen antes de agregarlos a list_display
    # Para evitar errores si las migraciones no se han aplicado
    def _get_list_display(self):
        fields = ['nombre', 'direccion', 'telefono', 'email', 'tipo_facturacion', 'cuit', 'fecha_creacion']
        if hasattr(Tienda, 'plataforma_ecommerce'):
            fields.insert(-1, 'plataforma_ecommerce')
        if hasattr(Tienda, 'ml_sync_habilitado'):
            fields.insert(-1, 'ml_sync_habilitado')
        return tuple(fields)
    
    list_display = property(_get_list_display)
    
    def _get_search_fields(self):
        fields = ['nombre', 'direccion', 'telefono', 'email', 'cuit']
        if hasattr(Tienda, 'ml_user_id'):
            fields.append('ml_user_id')
        return fields
    
    search_fields = property(_get_search_fields)
    
    def _get_list_filter(self):
        fields = ['tipo_facturacion', 'modo_test_afip']
        if hasattr(Tienda, 'plataforma_ecommerce'):
            fields.append('plataforma_ecommerce')
        if hasattr(Tienda, 'ml_sync_habilitado'):
            fields.append('ml_sync_habilitado')
        if hasattr(Tienda, 'ml_modo_test'):
            fields.append('ml_modo_test')
        return tuple(fields)
    
    list_filter = property(_get_list_filter)
    
    def _get_readonly_fields(self):
        fields = ['id', 'fecha_creacion', 'fecha_actualizacion']
        if hasattr(Tienda, 'ml_user_id'):
            fields.append('ml_user_id')
        if hasattr(Tienda, 'ml_token_expires_at'):
            fields.append('ml_token_expires_at')
        return tuple(fields)
    
    readonly_fields = property(_get_readonly_fields)
    
    def _get_ml_fields(self):
        """Obtiene los campos de ML que existen en el modelo"""
        # Verificar si los campos existen usando _meta.get_field (más confiable)
        ml_field_names = [
            'plataforma_ecommerce',
            'ml_app_id',
            'ml_client_secret',
            'ml_modo_test',
            'ml_sync_habilitado',
            'ml_sincronizar_stock',
            'ml_sincronizar_precios',
            'ml_sincronizar_productos'
        ]
        # Verificar cada campo individualmente usando get_field
        existing_fields = []
        for field_name in ml_field_names:
            try:
                Tienda._meta.get_field(field_name)
                existing_fields.append(field_name)
            except:
                pass
        return tuple(existing_fields)
    
    def _get_ml_token_fields(self):
        """Obtiene los campos de tokens de ML que existen en el modelo"""
        fields = []
        if hasattr(Tienda, 'ml_user_id'):
            fields.append('ml_user_id')
        if hasattr(Tienda, 'ml_token_expires_at'):
            fields.append('ml_token_expires_at')
        return tuple(fields)
    
    def get_fieldsets(self, request, obj=None):
        """Genera fieldsets dinámicamente verificando si los campos existen"""
        fieldsets = [
            ('Información Básica', {
                'fields': ('nombre', 'direccion', 'telefono', 'email')
            }),
            ('Configuración Fiscal', {
                'fields': (
                    'tipo_facturacion',
                    'cuit',
                    'punto_venta',
                    'condicion_iva_emisor',
                ),
            }),
            ('Suscripción', {
                'fields': ('requiere_eleccion_plan',),
                'description': 'Si está tildado, esta tienda (aunque sea legacy) queda bloqueada hasta que elija y pague un plan. No afecta a otras tiendas legacy.',
            }),
            ('Configuración ARCA', {
                'fields': (
                    'certificado_afip',
                    'clave_privada_afip',
                    'modo_test_afip',
                ),
                'classes': ('collapse',),
            }),
            ('Configuración ARCA', {
                'fields': (
                    'api_key_arca',
                    'url_arca',
                ),
                'classes': ('collapse',),
            }),
        ]
        
        # Agregar configuración de ML solo si los campos existen en el modelo
        ml_fields = self._get_ml_fields()
        if ml_fields:
            fieldsets.append(('Configuración E-commerce - Mercado Libre', {
                'fields': ml_fields,
                'description': 'Configuración para integración con Mercado Libre. Los tokens OAuth se generan automáticamente después de la autenticación.',
            }))
            
            # Agregar tokens solo si existen
            token_fields = self._get_ml_token_fields()
            if token_fields:
                fieldsets.append(('Tokens Mercado Libre (Solo Lectura)', {
                    'fields': token_fields,
                    'classes': ('collapse',),
                    'description': 'Estos campos se actualizan automáticamente después de la autenticación OAuth. Los tokens no se muestran por seguridad.',
                }))
        
        fieldsets.append(('Información del Sistema', {
            'fields': ('id', 'fecha_creacion', 'fecha_actualizacion'),
            'classes': ('collapse',)
        }))
        
        return fieldsets
    
    def save_model(self, request, obj, form, change):
        """
        Establece valores por defecto para campos de ML al crear/actualizar tiendas
        """
        # Verificar si los campos de ML existen en el modelo usando _meta
        try:
            model_field_names = [f.name for f in Tienda._meta.get_fields() if hasattr(f, 'column')]
            
            # Al crear una nueva tienda (not change), establecer valores por defecto
            if not change:
                if 'ml_modo_test' in model_field_names:
                    obj.ml_modo_test = True
                if 'plataforma_ecommerce' in model_field_names:
                    if not obj.plataforma_ecommerce:
                        obj.plataforma_ecommerce = 'NINGUNA'
                if 'ml_sync_habilitado' in model_field_names:
                    obj.ml_sync_habilitado = False
                if 'ml_sincronizar_stock' in model_field_names:
                    obj.ml_sincronizar_stock = True
                if 'ml_sincronizar_precios' in model_field_names:
                    obj.ml_sincronizar_precios = True
                if 'ml_sincronizar_productos' in model_field_names:
                    obj.ml_sincronizar_productos = True
        except (AttributeError, ValueError):
            # Si los campos no existen, simplemente continuar
            pass
        
        super().save_model(request, obj, form, change)


# Configuración para el modelo de Categoría
@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion', 'fecha_creacion')
    search_fields = ('nombre',)
    readonly_fields = ('id', 'fecha_creacion', 'fecha_actualizacion')


# Configuración para el modelo de Producto
@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'talle', 'variante2', 'precio', 'stock', 'tienda', 'codigo_barras', 'fecha_creacion')
    list_filter = ('tienda', 'talle', 'variante2')
    search_fields = ('nombre', 'codigo_barras', 'tienda__nombre') 
    readonly_fields = ('id', 'codigo_barras', 'fecha_creacion', 'fecha_actualizacion') 

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(tienda=request.user.tienda)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "tienda" and not request.user.is_superuser:
            kwargs["queryset"] = Tienda.objects.filter(id=request.user.tienda.id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            obj.tienda = request.user.tienda
        super().save_model(request, obj, form, change)


# Registro del modelo MetodoPago en el admin (ACTUALIZADO para es_financiero)
@admin.register(MetodoPago)
class MetodoPagoAdmin(admin.ModelAdmin):
    # CAMBIO: Añadir 'es_financiero' para que se vea y se filtre
    list_display = ('nombre', 'activo', 'es_financiero', 'fecha_creacion') 
    search_fields = ('nombre',)
    list_filter = ('activo', 'es_financiero') 
    readonly_fields = ('id', 'fecha_creacion', 'fecha_actualizacion') 

# Configuración para el modelo de ArancelMetodoTienda (NUEVO REGISTRO)
@admin.register(ArancelMetodoTienda)
class ArancelMetodoTiendaAdmin(admin.ModelAdmin):
    list_display = ('tienda', 'metodo_pago', 'nombre_plan', 'arancel_porcentaje', 'fecha_creacion')
    list_filter = ('tienda', 'metodo_pago', 'nombre_plan')
    search_fields = ('tienda__nombre', 'metodo_pago__nombre', 'nombre_plan')
    readonly_fields = ('id', 'fecha_creacion', 'fecha_actualizacion')
    
    # Restricción para que solo se muestren los aranceles de la tienda del usuario
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(tienda=request.user.tienda)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "tienda" and not request.user.is_superuser:
            kwargs["queryset"] = Tienda.objects.filter(id=request.user.tienda.id)
        if db_field.name == "metodo_pago":
            # Asegurarse que solo se muestren métodos marcados como financieros
            kwargs["queryset"] = MetodoPago.objects.filter(es_financiero=True)
            
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# Configuración para el modelo de Venta (ACTUALIZADO con campos de recargo)
class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0
    readonly_fields = ('producto', 'cantidad', 'precio_unitario', 'subtotal', 'anulado_individualmente', 'fecha_creacion', 'fecha_actualizacion')
    can_delete = False 

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    # CAMBIO: Añadir arancel_aplicado, arancel_total, recargo_porcentaje, recargo_monto a list_display
    list_display = (
        'id', 'fecha_venta', 'total', 'metodo_pago', 
        'descuento_porcentaje', 'descuento_monto', 
        'recargo_porcentaje', 'recargo_monto', 
        'arancel_aplicado', 'arancel_total', 'tienda', 'anulada', 'fecha_creacion'
    ) 
    # CAMBIO: Añadir filtro por plan de cuotas (existente, se mantiene)
    list_filter = ('tienda', 'metodo_pago', 'anulada', 'arancel_aplicado__nombre_plan', 'fecha_venta') 
    search_fields = ('id__exact', 'tienda__nombre', 'metodo_pago') 
    inlines = [DetalleVentaInline]
    # CAMBIO: Añadir arancel_aplicado, arancel_total, recargo_porcentaje, recargo_monto a readonly_fields
    readonly_fields = (
        'id', 'fecha_venta', 'total', 'anulada', 
        'descuento_porcentaje', 'descuento_monto', 
        'recargo_porcentaje', 'recargo_monto', 
        'arancel_aplicado', 'arancel_total', 
        'fecha_creacion', 'fecha_actualizacion'
    ) 

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(tienda=request.user.tienda)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "tienda" and not request.user.is_superuser:
            kwargs["queryset"] = Tienda.objects.filter(id=request.user.tienda.id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            obj.tienda = request.user.tienda
        super().save_model(request, obj, form, change)

# Configuración para el modelo de Factura
@admin.register(Factura)
class FacturaAdmin(admin.ModelAdmin):
    list_display = (
        'numero_factura_completo', 'tipo_comprobante', 'tienda', 'cliente_nombre', 
        'total', 'estado', 'cae', 'fecha_emision'
    )
    list_filter = ('estado', 'tipo_comprobante', 'sistema_facturacion', 'tienda', 'fecha_emision')
    search_fields = ('numero_comprobante', 'cliente_nombre', 'cliente_cuit', 'cae', 'numero_comprobante_afip')
    readonly_fields = (
        'id', 'venta', 'numero_comprobante', 'cae', 'fecha_vencimiento_cae', 
        'numero_comprobante_afip', 'estado', 'error_mensaje', 'respuesta_bruta',
        'fecha_emision', 'fecha_actualizacion'
    )
    
    fieldsets = (
        ('Información de la Factura', {
            'fields': (
                'venta', 'tienda', 'numero_comprobante', 'punto_venta', 
                'tipo_comprobante', 'numero_factura_completo', 'estado'
            )
        }),
        ('Datos del Cliente', {
            'fields': (
                'cliente_nombre', 'cliente_cuit', 'cliente_domicilio',
                'cliente_tipo_documento', 'cliente_condicion_iva'
            )
        }),
        ('Totales', {
            'fields': ('subtotal', 'impuesto_iva', 'total')
        }),
        ('Respuesta ARCA', {
            'fields': (
                'sistema_facturacion', 'cae', 'fecha_vencimiento_cae',
                'numero_comprobante_afip', 'error_mensaje'
            ),
            'classes': ('collapse',)
        }),
        ('Información del Sistema', {
            'fields': ('id', 'fecha_emision', 'fecha_actualizacion', 'respuesta_bruta'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs.select_related('venta', 'tienda')
        elif request.user.tienda:
            return qs.filter(tienda=request.user.tienda).select_related('venta', 'tienda')
        return qs.none()


# ── Plan ──────────────────────────────────────────────────────────────────────

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display  = ('nombre', 'get_nombre_display', 'precio_mensual', 'max_productos',
                     'max_usuarios', 'permite_factura_electronica',
                     'permite_integracion_ecommerce', 'mp_plan_id')
    list_editable = ('precio_mensual', 'max_productos', 'max_usuarios',
                     'permite_factura_electronica', 'permite_integracion_ecommerce')
    search_fields = ('nombre', 'mp_plan_id')
    fieldsets = (
        ('Identificación', {
            'fields': ('nombre', 'mp_plan_id'),
        }),
        ('Precios y límites', {
            'fields': ('precio_mensual', 'max_productos', 'max_usuarios'),
        }),
        ('Features', {
            'fields': ('permite_factura_electronica', 'permite_integracion_ecommerce'),
        }),
    )


# ── Suscripcion ───────────────────────────────────────────────────────────────

class SuscripcionInline(admin.StackedInline):
    model        = Suscripcion
    extra        = 0
    can_delete   = False
    show_change_link = True
    readonly_fields  = ('id', 'fecha_creacion', 'fecha_actualizacion', 'mp_preapproval_id',
                        'mp_payer_email', 'estado_badge')
    fields = ('estado_badge', 'plan', 'estado', 'fecha_inicio', 'fecha_fin_trial',
              'fecha_proximo_cobro', 'fecha_inicio_gracia',
              'mp_preapproval_id', 'mp_payer_email')

    def estado_badge(self, obj):
        colores = {
            'pending':   '#f59e0b',
            'trial':     '#3b82f6',
            'activa':    '#16a34a',
            'gracia':    '#f97316',
            'pausada':   '#dc2626',
            'cancelada': '#6b7280',
        }
        color = colores.get(obj.estado, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;border-radius:12px;'
            'font-weight:600;font-size:12px">{}</span>',
            color, obj.get_estado_display()
        )
    estado_badge.short_description = 'Estado actual'


def _accion_activar(modeladmin, request, queryset):
    from inventario.services.suscripcion_service import activar_suscripcion
    for sus in queryset:
        activar_suscripcion(sus)
    modeladmin.message_user(request, f'{queryset.count()} suscripción(es) activada(s).')
_accion_activar.short_description = '✅ Activar suscripción (→ trial)'


def _accion_pausar(modeladmin, request, queryset):
    from inventario.services.suscripcion_service import pausar_suscripcion
    for sus in queryset:
        pausar_suscripcion(sus)
    modeladmin.message_user(request, f'{queryset.count()} suscripción(es) pausada(s).')
_accion_pausar.short_description = '⏸ Pausar suscripción'


def _accion_cancelar(modeladmin, request, queryset):
    from inventario.services.suscripcion_service import cancelar_suscripcion
    for sus in queryset:
        cancelar_suscripcion(sus)
    modeladmin.message_user(request, f'{queryset.count()} suscripción(es) cancelada(s).')
_accion_cancelar.short_description = '🚫 Cancelar suscripción'


@admin.register(Suscripcion)
class SuscripcionAdmin(admin.ModelAdmin):
    list_display  = ('tienda_nombre', 'tienda_email', 'plan', 'estado_badge',
                     'fecha_inicio', 'fecha_fin_trial', 'fecha_proximo_cobro',
                     'mp_preapproval_id')
    list_filter   = ('estado', 'plan')
    search_fields = ('tienda__nombre', 'tienda__email', 'mp_preapproval_id', 'mp_payer_email')
    actions       = [_accion_activar, _accion_pausar, _accion_cancelar]
    readonly_fields = ('id', 'fecha_creacion', 'fecha_actualizacion',
                       'mp_preapproval_id', 'mp_payer_email', 'estado_badge')
    fieldsets = (
        ('Tienda', {
            'fields': ('tienda',),
        }),
        ('Plan y estado', {
            'fields': ('estado_badge', 'plan', 'estado'),
        }),
        ('Fechas', {
            'fields': ('fecha_inicio', 'fecha_fin_trial',
                       'fecha_proximo_cobro', 'fecha_inicio_gracia'),
        }),
        ('Mercado Pago', {
            'fields': ('mp_preapproval_id', 'mp_payer_email'),
        }),
        ('Sistema', {
            'fields': ('id', 'fecha_creacion', 'fecha_actualizacion'),
            'classes': ('collapse',),
        }),
    )

    def tienda_nombre(self, obj):
        return obj.tienda.nombre
    tienda_nombre.short_description = 'Tienda'
    tienda_nombre.admin_order_field = 'tienda__nombre'

    def tienda_email(self, obj):
        return obj.tienda.email
    tienda_email.short_description = 'Email'
    tienda_email.admin_order_field = 'tienda__email'

    def estado_badge(self, obj):
        colores = {
            'pending':   '#f59e0b',
            'trial':     '#3b82f6',
            'activa':    '#16a34a',
            'gracia':    '#f97316',
            'pausada':   '#dc2626',
            'cancelada': '#6b7280',
        }
        color = colores.get(obj.estado, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;border-radius:12px;'
            'font-weight:600;font-size:12px">{}</span>',
            color, obj.get_estado_display()
        )
    estado_badge.short_description = 'Estado'


# Agregar inline de suscripción a TiendaAdmin
TiendaAdmin.inlines = [SuscripcionInline]
