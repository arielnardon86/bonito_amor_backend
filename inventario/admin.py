# BONITO_AMOR/backend/inventario/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django import forms
from django.db import transaction # Necesario para la acción anular

from .models import Producto, Categoria, Venta, DetalleVenta, Tienda, User # Importa tu modelo de usuario personalizado

# --- Formularios para el modelo de usuario personalizado en el Admin ---
# Necesario para que el campo 'tienda' sea visible y editable en el admin de usuarios
class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        # Listar explícitamente todos los campos que quieres en el formulario de cambio
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active', 
                  'is_staff', 'is_superuser', 'groups', 'user_permissions', 'tienda')

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        # Listar explícitamente todos los campos que quieres en el formulario de creación
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active', 
                  'is_staff', 'is_superuser', 'tienda') 
    

# --- Configuración del Admin para el modelo de usuario personalizado ---
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    
    # Define los campos a mostrar en la lista de usuarios en el admin
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'tienda')
    
    # Define los campos de búsqueda
    search_fields = ('username', 'email', 'first_name', 'last_name')
    
    # Define los filtros en la barra lateral
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'tienda') # Añade filtro por tienda
    
    # Define cómo se agrupan los campos en la página de detalle del usuario
    fieldsets = BaseUserAdmin.fieldsets + (
        (None, {'fields': ('tienda',)}), # Añade el campo 'tienda' a un nuevo grupo
    )
    # Define cómo se agrupan los campos en el formulario de creación de usuario
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (None, {'fields': ('tienda',)}),
    )


# --- Admin para el modelo Tienda ---
@admin.register(Tienda)
class TiendaAdmin(admin.ModelAdmin):
    # list_display: Muestra estos campos en la lista de tiendas
    list_display = ('nombre', 'slug', 'direccion', 'telefono', 'email')
    prepopulated_fields = {'slug': ('nombre',)} # Rellena el slug automáticamente desde el nombre
    search_fields = ('nombre', 'direccion') # Campos para la búsqueda en el admin

# --- Admin para el modelo Producto ---
@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'talle', 'precio_venta', 'stock', 'categoria', 'tienda') # Añade 'tienda'
    list_filter = ('talle', 'categoria', 'tienda') # Añade filtro por tienda
    search_fields = ('nombre', 'codigo_barras', 'descripcion')
    # Campos que se pueden editar directamente en la lista
    list_editable = ('precio_venta', 'stock') 
    # Añade el campo 'tienda' a los formularios de añadir/editar producto
    fields = ('nombre', 'descripcion', 'codigo_barras', 'precio_compra', 'precio_venta', 'stock', 'talle', 'categoria', 'tienda')

# --- Admin para el modelo Categoria ---
@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion')
    search_fields = ('nombre',)

# --- Inline para DetalleVenta (para mostrar en el admin de Venta) ---
# Definido antes de VentaAdmin para que pueda ser referenciado
class DetalleVentaInline(admin.TabularInline):
    # CORRECCIÓN: Cambiado 'DetalleVesa' por 'DetalleVenta'
    model = DetalleVenta 
    extra = 0 # No mostrar detalles vacíos por defecto
    raw_id_fields = ('producto',) # Para mejorar el rendimiento si hay muchos productos
    readonly_fields = ('precio_unitario_venta',) # El precio se establece al crear el detalle


# --- Admin para el modelo Venta ---
@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha_venta', 'total_venta', 'usuario', 'anulada', 'metodo_pago', 'tienda') # Añade 'tienda'
    list_filter = ('fecha_venta', 'usuario', 'anulada', 'metodo_pago', 'tienda') # Añade filtro por tienda
    search_fields = ('usuario__username',) # Permite buscar por nombre de usuario
    # Permite ver los detalles de la venta directamente en la lista de ventas
    inlines = [DetalleVentaInline] 

    # Acción personalizada para anular ventas
    actions = ['anular_ventas']

    @admin.action(description='Marcar ventas seleccionadas como anuladas y revertir stock')
    def anular_ventas(self, request, queryset):
        for venta in queryset:
            if not venta.anulada:
                try:
                    with transaction.atomic():
                        venta.anulada = True
                        venta.save()

                        for detalle in venta.detalles.all():
                            producto = detalle.producto
                            producto.stock += detalle.cantidad
                            producto.save()
                    self.message_user(request, f"Venta {venta.id} anulada y stock revertido con éxito.", level='success')
                except Exception as e:
                    self.message_user(request, f"Error al anular venta {venta.id}: {e}", level='error')
            else:
                self.message_user(request, f"Venta {venta.id} ya estaba anulada.", level='warning')

