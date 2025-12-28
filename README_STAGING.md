# Guía de Ambiente de Staging Local

Esta guía explica cómo configurar y usar un ambiente de staging local con PostgreSQL que replica la base de datos de producción.

## Tabla de Contenidos

- [Requisitos Previos](#requisitos-previos)
- [Configuración Inicial](#configuración-inicial)
- [Replicar Base de Datos de Producción](#replicar-base-de-datos-de-producción)
- [Uso del Ambiente de Staging](#uso-del-ambiente-de-staging)
- [Mantenimiento](#mantenimiento)

## Requisitos Previos

1. **PostgreSQL instalado y corriendo**:
   - macOS: `brew install postgresql@15` o `brew install postgresql`
   - Linux: `sudo apt-get install postgresql postgresql-contrib`
   - Windows: Descargar desde [postgresql.org](https://www.postgresql.org/download/)

2. **Python y dependencias del proyecto**:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Herramientas de línea de comandos de PostgreSQL** (`psql`, `pg_dump`, `pg_restore`):
   - Generalmente se instalan junto con PostgreSQL

## Configuración Inicial

### Paso 1: Configurar el Ambiente de Staging

Ejecuta el script de setup automático:

```bash
cd backend
./scripts/setup_staging.sh
```

Este script:
- Verifica que PostgreSQL esté instalado y corriendo
- Crea el archivo `.env.staging` con las configuraciones necesarias
- Crea la base de datos `bonito_amor_staging` si no existe

### Paso 2: Configuración Manual (Opcional)

Si prefieres configurar manualmente, puedes copiar la plantilla:

```bash
cp env.staging.template .env.staging
```

Luego edita el archivo `.env.staging` en el directorio `backend/` con tus configuraciones:

```env
# Configuración para ambiente de STAGING local
DJANGO_ENVIRONMENT=staging
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=tu-clave-secreta-para-staging-aqui

# Configuración de base de datos PostgreSQL local
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/bonito_amor_staging

# O usar variables individuales:
# STAGING_DB_NAME=bonito_amor_staging
# STAGING_DB_USER=postgres
# STAGING_DB_PASSWORD=postgres
# STAGING_DB_HOST=localhost
# STAGING_DB_PORT=5432
```

**Nota**: Ajusta los valores de usuario, contraseña y nombre de base de datos según tu configuración local de PostgreSQL.

### Paso 3: Aplicar Migraciones

Si estás empezando desde cero (sin dump de producción):

```bash
DJANGO_ENVIRONMENT=staging python manage.py migrate
```

## Replicar Base de Datos de Producción

### Opción 1: Usar los Scripts Automáticos (Recomendado)

#### 1. Hacer Dump de la Base de Datos de Producción

```bash
# Exportar la URL de producción (por seguridad, no la guardes en archivos)
export PRODUCTION_DATABASE_URL='postgresql://user:password@host:port/dbname'

# Ejecutar el script de dump
./scripts/dump_production_db.sh
```

El script creará un archivo comprimido en `backups/production_dump_YYYYMMDD_HHMMSS.sql.gz`.

#### 2. Restaurar en Staging Local

```bash
# Restaurar el dump más reciente
./scripts/restore_to_staging.sh backups/production_dump_YYYYMMDD_HHMMSS.sql.gz
```

El script:
- Pedirá confirmación (ya que eliminará datos existentes)
- Verificará la conexión a PostgreSQL
- Restaurará el dump completo

### Opción 2: Comandos Manuales

#### Hacer Dump Manualmente

```bash
# Dump en formato SQL (texto plano)
pg_dump "postgresql://user:password@host:port/dbname" > backup.sql
gzip backup.sql

# O dump en formato custom (más eficiente)
pg_dump -Fc "postgresql://user:password@host:port/dbname" > backup.dump
```

#### Restaurar Manualmente

```bash
# Desde archivo SQL comprimido
gunzip -c backup.sql.gz | psql "postgresql://postgres:postgres@localhost:5432/bonito_amor_staging"

# Desde archivo custom
pg_restore -d "postgresql://postgres:postgres@localhost:5432/bonito_amor_staging" --clean --if-exists backup.dump
```

## Uso del Ambiente de Staging

### Ejecutar el Servidor en Modo Staging

```bash
DJANGO_ENVIRONMENT=staging python manage.py runserver
```

El servidor se iniciará en `http://localhost:8000` usando la base de datos de staging local.

### Comandos Django en Staging

Todos los comandos de Django deben ejecutarse con la variable de entorno:

```bash
# Aplicar migraciones
DJANGO_ENVIRONMENT=staging python manage.py migrate

# Crear superusuario
DJANGO_ENVIRONMENT=staging python manage.py createsuperuser

# Shell de Django
DJANGO_ENVIRONMENT=staging python manage.py shell

# Recolectar archivos estáticos
DJANGO_ENVIRONMENT=staging python manage.py collectstatic
```

### Variables de Entorno en el Sistema

Para evitar escribir `DJANGO_ENVIRONMENT=staging` en cada comando, puedes:

**Linux/macOS** (en tu `~/.bashrc` o `~/.zshrc`):
```bash
export DJANGO_ENVIRONMENT=staging
```

O crear un script de alias:
```bash
alias django-staging='DJANGO_ENVIRONMENT=staging python manage.py'
# Uso: django-staging runserver
```

## Mantenimiento

### Actualizar desde Producción

Para mantener staging actualizado con producción:

1. **Hacer dump de producción** (ver sección anterior)
2. **Restaurar en staging** (ver sección anterior)
3. **Aplicar migraciones** (por si hay cambios en el esquema):
   ```bash
   DJANGO_ENVIRONMENT=staging python manage.py migrate
   ```

### Limpiar la Base de Datos de Staging

Si necesitas empezar desde cero:

```bash
# Conectarse a PostgreSQL
psql -U postgres

# Dentro de psql
DROP DATABASE bonito_amor_staging;
CREATE DATABASE bonito_amor_staging;

# O usar el script de restore que ya hace esto automáticamente
```

### Backup de Staging

Para hacer backup de tu base de datos de staging:

```bash
pg_dump "postgresql://postgres:postgres@localhost:5432/bonito_amor_staging" | gzip > backups/staging_backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

## Estructura de Archivos

```
backend/
├── .env.staging              # Configuración de staging (no versionado)
├── env.staging.template      # Plantilla de configuración
├── scripts/
│   ├── setup_staging.sh      # Script de configuración inicial
│   ├── dump_production_db.sh # Script para dump de producción
│   └── restore_to_staging.sh # Script para restaurar en staging
├── backups/                  # Directorio para dumps (no versionado)
│   └── production_dump_*.sql.gz
└── mi_tienda_backend/
    └── settings.py           # Configuración Django (modificado para soportar ambientes)
```

## Solución de Problemas

### PostgreSQL no está corriendo

**macOS (Homebrew)**:
```bash
brew services start postgresql@15
# o
brew services start postgresql
```

**Linux**:
```bash
sudo systemctl start postgresql
```

**Verificar estado**:
```bash
pg_isready
```

### Error de conexión a la base de datos

1. Verifica que PostgreSQL esté corriendo: `pg_isready`
2. Verifica las credenciales en `.env.staging`
3. Verifica que la base de datos existe:
   ```bash
   psql -U postgres -l | grep bonito_amor_staging
   ```

### Error de permisos

Si tienes problemas de permisos al crear la base de datos:

```bash
# Crear usuario y base de datos manualmente
psql -U postgres
CREATE USER postgres WITH PASSWORD 'postgres';
ALTER USER postgres CREATEDB;
CREATE DATABASE bonito_amor_staging OWNER postgres;
```

### El servidor no inicia

1. Verifica que `.env.staging` exista y tenga las configuraciones correctas
2. Verifica que la variable `DJANGO_ENVIRONMENT=staging` esté configurada
3. Revisa los logs de Django para más detalles

## Notas de Seguridad

⚠️ **IMPORTANTE**:
- **Nunca** subas archivos `.env.staging` al repositorio
- **Nunca** compartas las credenciales de producción
- Los dumps de producción pueden contener datos sensibles - manéjalos con cuidado
- Considera anonimizar datos personales antes de replicar en staging

## Soporte

Si encuentras problemas o tienes preguntas:
1. Revisa la sección de solución de problemas
2. Verifica los logs de Django
3. Verifica los logs de PostgreSQL: `tail -f /usr/local/var/log/postgres.log` (macOS) o `sudo tail -f /var/log/postgresql/postgresql-*.log` (Linux)

