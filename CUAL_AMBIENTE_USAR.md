# ¿Qué Ambiente Usar?

## ⚠️ PROBLEMA COMÚN: "Ayer funcionaba, hoy no"

Esto sucede porque Django puede usar **3 ambientes diferentes**, cada uno con su **propia base de datos**:

1. **Development** (SQLite) - Base de datos: `db.sqlite3`
2. **Staging** (PostgreSQL) - Base de datos: `bonito_amor_staging`
3. **Production** (PostgreSQL) - Base de datos en la nube

Si creas una tienda y un usuario en **Staging**, no los verás en **Development** (son bases de datos diferentes).

---

## 🎯 Solución: Usa SIEMPRE el mismo ambiente

### Opción 1: Usar STAGING (Recomendado - PostgreSQL local)

**Para iniciar el servidor:**
```bash
cd backend
./scripts/run_staging.sh runserver
```

**Para crear superusuario:**
```bash
cd backend
./scripts/run_staging.sh createsuperuser
```

**Para migrar:**
```bash
cd backend
./scripts/run_staging.sh migrate
```

**Para acceder al Admin:**
- URL: http://localhost:8000/admin/
- Usa el superusuario que creaste en **staging**

---

### Opción 2: Usar DEVELOPMENT (SQLite - más simple pero menos realista)

**Para iniciar el servidor:**
```bash
cd backend
./scripts/run_development.sh runserver
```

**Para crear superusuario:**
```bash
cd backend
./scripts/run_development.sh createsuperuser
```

**Para migrar:**
```bash
cd backend
./scripts/run_development.sh migrate
```

---

## 📋 Verificar qué ambiente estás usando

Cuando inicias el servidor, verás en la consola algo como:

```
--- DEVELOPMENT DATABASE CONFIG ---
Using SQLite for development
DATABASES['default'] configured as: django.db.backends.sqlite3
--- END CONFIG ---
```

O:

```
--- STAGING DATABASE CONFIG ---
Ambiente: STAGING
Base de datos: django.db.backends.postgresql
Nombre: bonito_amor_staging
--- END CONFIG ---
```

---

## ❓ ¿Dónde está mi tienda y mi usuario?

Si los creaste ayer pero hoy no los ves:

1. **Ayer probablemente usaste STAGING** (PostgreSQL)
2. **Hoy estás usando DEVELOPMENT** (SQLite) por defecto

**Solución:**
- Usa `./scripts/run_staging.sh runserver` para volver a usar la misma base de datos de ayer
- O recrea la tienda y usuario en development si prefieres usar SQLite

---

## 🔄 Cambiar entre ambientes

### Si quieres usar STAGING pero no tienes datos:
```bash
cd backend
./scripts/setup_staging.sh  # Configura staging si no está configurado
./scripts/run_staging.sh migrate  # Crea las tablas
./scripts/run_staging.sh createsuperuser  # Crea un usuario
```

### Si quieres empezar de cero en DEVELOPMENT:
```bash
cd backend
rm db.sqlite3  # Elimina la base de datos SQLite
./scripts/run_development.sh migrate  # Crea las tablas
./scripts/run_development.sh createsuperuser  # Crea un usuario
```

---

## 💡 Recomendación

**Usa STAGING** porque:
- ✅ Usa PostgreSQL (igual que producción)
- ✅ Más realista para pruebas
- ✅ Puedes replicar datos de producción fácilmente

**Usa DEVELOPMENT** solo si:
- Estás probando algo rápido
- No necesitas PostgreSQL
- No necesitas replicar datos de producción

