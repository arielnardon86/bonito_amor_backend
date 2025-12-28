# Guía Rápida: Trabajar en Staging

## Paso 1: Instalar PostgreSQL (si no lo tienes)

### macOS:
```bash
# Con Homebrew (recomendado)
brew install postgresql@15

# O la última versión
brew install postgresql

# Iniciar PostgreSQL
brew services start postgresql@15
```

### Verificar instalación:
```bash
which psql
psql --version
```

## Paso 2: Configurar el Ambiente de Staging

```bash
cd backend

# Ejecutar el script de setup (creará todo lo necesario)
./scripts/setup_staging.sh
```

Este script:
- ✅ Verifica que PostgreSQL esté instalado
- ✅ Crea el archivo `.env.staging`
- ✅ Crea la base de datos `bonito_amor_staging`

## Paso 3: Replicar Base de Datos de Producción

### Opción A: Tienes acceso a la URL de producción

```bash
# 1. Exportar la URL de producción (NO la guardes en archivos)
export PRODUCTION_DATABASE_URL='postgresql://usuario:password@host:puerto/nombre_db'

# 2. Hacer dump
./scripts/dump_production_db.sh

# 3. Restaurar en staging local
./scripts/restore_to_staging.sh backups/production_dump_*.sql.gz
```

### Opción B: Empezar desde cero (sin datos de producción)

```bash
# Aplicar migraciones para crear las tablas
DJANGO_ENVIRONMENT=staging python manage.py migrate

# Crear un superusuario si es necesario
DJANGO_ENVIRONMENT=staging python manage.py createsuperuser
```

## Paso 4: Ejecutar el Servidor en Staging

```bash
# Método 1: Usando el script helper
./scripts/run_staging.sh runserver

# Método 2: Con variable de entorno
DJANGO_ENVIRONMENT=staging python manage.py runserver
```

El servidor estará disponible en: `http://localhost:8000`

## Paso 5: Hacer Cambios en Staging

Ahora puedes trabajar normalmente. Todos los cambios se guardan en la base de datos local de staging.

### Comandos útiles en staging:

```bash
# Ejecutar servidor
./scripts/run_staging.sh runserver

# Aplicar migraciones
./scripts/run_staging.sh migrate

# Crear migraciones
./scripts/run_staging.sh makemigrations

# Shell de Django
./scripts/run_staging.sh shell

# Crear superusuario
./scripts/run_staging.sh createsuperuser

# Ver logs del servidor
DJANGO_ENVIRONMENT=staging python manage.py runserver
```

## Paso 6: Verificar que estás en Staging

Cuando el servidor inicia, verás en la consola:
```
--- STAGING DATABASE CONFIG ---
Ambiente: STAGING
Base de datos: django.db.backends.postgresql
Nombre: bonito_amor_staging
--- END CONFIG ---
```

## Consejos

1. **Siempre verifica el ambiente**: Antes de hacer cambios importantes, confirma que estás en staging viendo los logs de inicio.

2. **Hacer backup antes de cambios grandes**:
   ```bash
   pg_dump postgresql://postgres:postgres@localhost:5432/bonito_amor_staging | gzip > backups/staging_backup_$(date +%Y%m%d_%H%M%S).sql.gz
   ```

3. **Actualizar desde producción periódicamente**: Para mantener staging actualizado con los últimos datos de producción.

4. **Los cambios en staging NO afectan producción**: Puedes experimentar libremente sin riesgo.

## Troubleshooting

### Error: "PostgreSQL no está corriendo"
```bash
# macOS
brew services start postgresql@15

# Verificar
pg_isready
```

### Error: "No se puede conectar a la base de datos"
1. Verifica que PostgreSQL esté corriendo: `pg_isready`
2. Verifica las credenciales en `.env.staging`
3. Verifica que la base de datos exista: `psql -U postgres -l | grep bonito_amor_staging`

### Error: "No se encuentra el archivo .env.staging"
```bash
# Ejecuta el setup de nuevo
./scripts/setup_staging.sh

# O copia la plantilla manualmente
cp env.staging.template .env.staging
# Luego edita .env.staging con tus credenciales
```



