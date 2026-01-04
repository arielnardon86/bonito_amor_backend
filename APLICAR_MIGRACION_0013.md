# Cómo Aplicar la Migración 0013 en Producción

## Problema
El servicio no puede iniciar porque intenta importar modelos que aún no existen en la base de datos.

## Solución Temporal: Usar --skip-checks

Si Render aún no ha desplegado el último commit con las importaciones condicionales, puedes aplicar la migración usando `--skip-checks`:

```bash
python manage.py migrate inventario 0013_cambiodevolucion_detallecambiodevolucion --skip-checks
```

Este flag le dice a Django que omita las verificaciones de URLs y otros checks que requieren que el código esté completamente cargado.

## Solución Definitiva

Una vez que Render despliegue el último commit (`47d90c0` o superior), podrás aplicar la migración normalmente:

```bash
python manage.py migrate inventario 0013_cambiodevolucion_detallecambiodevolucion
```

## Verificar que se aplicó

```bash
python manage.py showmigrations inventario | grep 0013
```

Debe mostrar: `[X] 0013_cambiodevolucion_detallecambiodevolucion`

## Nota

El flag `--skip-checks` es seguro usar solo para aplicar migraciones cuando hay problemas de importación circular como este.

