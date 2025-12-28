# Alternativas para hacer dump de producción

Si tienes problemas de conexión para hacer el dump directamente, aquí hay varias alternativas:

## Opción 1: Usar la interfaz web de Clever Cloud

Si tu base de datos está en Clever Cloud, puedes:
1. Ir al panel de Clever Cloud
2. Seleccionar tu base de datos
3. Usar la herramienta de backup/export que ofrecen
4. Descargar el dump desde allí

## Opción 2: Hacer dump desde el servidor de producción

Si tienes acceso SSH al servidor donde está el backend:

```bash
# Conectarte al servidor
ssh usuario@tu-servidor

# En el servidor, hacer el dump
pg_dump "tu-database-url" > backup.sql
gzip backup.sql

# Descargar el archivo
exit
scp usuario@tu-servidor:/ruta/backup.sql.gz ./backups/
```

## Opción 3: Usar un túnel SSH

Si tienes acceso SSH a un servidor que SÍ puede acceder a la base de datos:

```bash
# Crear túnel SSH
ssh -L 5432:bmbtf23hj0uxx6xl84kb-postgresql.services.clever-cloud.com:50013 usuario@servidor-intermedio

# En otra terminal, hacer dump a través del túnel
pg_dump "postgresql://usuario:password@localhost:5432/nombre_db" > backup.sql.gz
```

## Opción 4: Empezar sin datos de producción

Si no puedes acceder a la base de datos ahora, puedes:

1. **Empezar con una base de datos vacía:**
   ```bash
   cd backend
   DJANGO_ENVIRONMENT=staging python manage.py migrate
   ```

2. **Crear datos de prueba manualmente** o importar solo los datos esenciales más adelante.

3. **Actualizar staging más tarde** cuando tengas mejor conexión o acceso.

## Opción 5: Verificar conectividad

Primero verifica que puedes acceder al servidor:

```bash
# Verificar DNS
nslookup bmbtf23hj0uxx6xl84kb-postgresql.services.clever-cloud.com

# Verificar conectividad
ping -c 3 bmbtf23hj0uxx6xl84kb-postgresql.services.clever-cloud.com

# Verificar puerto
telnet bmbtf23hj0uxx6xl84kb-postgresql.services.clever-cloud.com 50013
```

Si ninguno de estos funciona, puede ser que:
- Necesites una VPN
- El firewall de tu red esté bloqueando la conexión
- Clever Cloud tenga restricciones de IP
- Necesites whitelist de tu IP en Clever Cloud



