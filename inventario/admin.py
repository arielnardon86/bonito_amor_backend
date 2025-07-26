# BONITO_AMOR/backend/inventario/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Tienda, Categoria, Producto, Venta, DetalleVenta

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
    list_display = ('username', 'email', 'is_staff', 'is_superuser', 'tienda', 'fecha_creacion')
    list_filter = ('is_staff', 'is_superuser', 'tienda')
    search_fields = ('username', 'email', 'tienda__nombre') # Permite buscar por nombre de tienda

# Configuración para el modelo de Tienda
@admin.register(Tienda)
class TiendaAdmin(admin.ModelAdmin):
    # Eliminado 'slug' de list_display y prepopulated_fields
    list_display = ('nombre', 'direccion', 'telefono', 'email', 'fecha_creacion')
    search_fields = ('nombre', 'direccion', 'telefono', 'email')
    # Eliminado: prepopulated_fields = {'slug': ('nombre',)} # Slug ya no es un campo del modelo Tienda
    readonly_fields = ('id', 'fecha_creacion', 'fecha_actualizacion')


# Configuración para el modelo de Categoría (Si aún lo usas)
# Si eliminaste el modelo Categoria, puedes eliminar este bloque completo
@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion', 'fecha_creacion')
    search_fields = ('nombre',)
    readonly_fields = ('id', 'fecha_creacion', 'fecha_actualizacion')


# Configuración para el modelo de Producto
@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    # Ajustado list_display: Eliminado 'categoria' y 'descripcion'
    list_display = ('nombre', 'talle', 'precio', 'stock', 'tienda', 'codigo_barras', 'fecha_creacion')
    # Ajustado list_filter: Eliminado 'categoria'
    list_filter = ('tienda', 'talle') # Filtrar por tienda y talle
    search_fields = ('nombre', 'codigo_barras', 'tienda__nombre') # Buscar por nombre, código de barras y nombre de tienda
    # Eliminado 'categoria' de raw_id_fields
    # raw_id_fields = ('categoria',) # Ya no hay categoría
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
    readonly_fields = ('producto', 'cantidad', 'precio_unitario', 'subtotal', 'fecha_creacion', 'fecha_actualizacion')
    can_delete = False # Generalmente no se eliminan detalles de venta directamente

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    # Ajustado list_display: Eliminado 'cliente_nombre'
    list_display = ('id', 'fecha_venta', 'total', 'metodo_pago', 'tienda', 'fecha_creacion')
    list_filter = ('tienda', 'metodo_pago', 'fecha_venta')
    search_fields = ('id__exact', 'tienda__nombre', 'metodo_pago') # Buscar por ID de venta, nombre de tienda, método de pago
    inlines = [DetalleVentaInline]
    readonly_fields = ('id', 'fecha_venta', 'total', 'fecha_creacion', 'fecha_actualizacion')

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

