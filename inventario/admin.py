# BONITO_AMOR/backend/inventario/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
# Asegúrate de importar todos los modelos que registras
from .models import User, Tienda, Categoria, Producto, Venta, DetalleVenta, MetodoPago # Importar MetodoPago

# Configuración para el modelo de Usuario personalizado
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Añadir 'tienda' a los campos que se muestran y se pueden editar
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('tienda',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('tienda',)}),
    )
    # CAMBIO CLAVE AQUÍ: Usar 'date_joined' en lugar de 'fecha_creacion'
    list_display = ('username', 'email', 'is_staff', 'is_superuser', 'tienda', 'date_joined') 
    list_filter = ('is_staff', 'is_superuser', 'tienda')
    search_fields = ('username', 'email', 'tienda__nombre') # Permite buscar por nombre de tienda

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
    list_filter = ('tienda', 'talle') # Filtrar por tienda y talle
    search_fields = ('nombre', 'codigo_barras', 'tienda__nombre') # Buscar por nombre, código de barras y nombre de tienda
    readonly_fields = ('id', 'codigo_barras', 'fecha_creacion', 'fecha_actualizacion') # codigo_barras es de solo lectura en admin

    # Asegurarse de que al añadir/editar un producto, la tienda se asigne correctamente
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


# Configuración para el modelo de Venta
class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0
    # CAMBIO CLAVE AQUÍ: Añadir 'anulado_individualmente' a readonly_fields
    readonly_fields = ('producto', 'cantidad', 'precio_unitario', 'subtotal', 'anulado_individualmente', 'fecha_creacion', 'fecha_actualizacion')
    can_delete = False # Generalmente no se eliminan detalles de venta directamente

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha_venta', 'total', 'metodo_pago', 'tienda', 'anulada', 'fecha_creacion') # Añadir 'anulada' a list_display
    list_filter = ('tienda', 'metodo_pago', 'anulada', 'fecha_venta') # Añadir 'anulada' a list_filter
    search_fields = ('id__exact', 'tienda__nombre', 'metodo_pago') # Buscar por ID de venta, nombre de tienda, método de pago
    inlines = [DetalleVentaInline]
    readonly_fields = ('id', 'fecha_venta', 'total', 'anulada', 'fecha_creacion', 'fecha_actualizacion') # Añadir 'anulada' a readonly_fields

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

# Registro del modelo MetodoPago en el admin
@admin.register(MetodoPago)
class MetodoPagoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'fecha_creacion') # Usar 'activo' y 'fecha_creacion'
    search_fields = ('nombre',)
    list_filter = ('activo',)
    readonly_fields = ('id', 'fecha_creacion', 'fecha_actualizacion') # Añadir fechas a readonly
