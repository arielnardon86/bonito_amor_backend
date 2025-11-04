# inventario/admin.py - CÓDIGO COMPLETO Y CORREGIDO
# BONITO_AMOR/backend/inventario/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Tienda, Categoria, Producto, Venta, DetalleVenta, MetodoPago, ArancelMetodoTienda 

# Configuración para el modelo de Usuario personalizado
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('tienda',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('tienda',)}),
    )
    list_display = ('username', 'email', 'is_staff', 'is_superuser', 'tienda', 'date_joined') 
    list_filter = ('is_staff', 'is_superuser', 'tienda')
    search_fields = ('username', 'email', 'tienda__nombre') 

# Configuración para el modelo de Tienda
@admin.register(Tienda)
class TiendaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'direccion', 'telefono', 'email', 'fecha_creacion')
    search_fields = ('nombre', 'direccion', 'telefono', 'email')
    readonly_fields = ('id', 'fecha_creacion', 'fecha_actualizacion')


# Configuración para el modelo de Categoría
@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion', 'fecha_creacion')
    search_fields = ('nombre',)
    readonly_fields = ('id', 'fecha_creacion', 'fecha_actualizacion')


# Configuración para el modelo de Producto
@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'talle', 'precio', 'stock', 'tienda', 'codigo_barras', 'fecha_creacion')
    list_filter = ('tienda', 'talle') 
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