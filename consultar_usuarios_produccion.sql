-- Consultas SQL para verificar usuarios en producción
-- Ejecuta estas consultas en tu base de datos PostgreSQL en la nube

-- 1. Ver todos los usuarios con sus datos básicos
SELECT 
    id,
    username,
    email,
    first_name,
    last_name,
    is_staff,
    is_superuser,
    tienda_id,
    date_joined,
    last_login,
    is_active
FROM inventario_user
ORDER BY username;

-- 2. Ver usuarios con el nombre de su tienda asignada
SELECT 
    u.id,
    u.username,
    u.email,
    u.first_name,
    u.last_name,
    u.is_staff,
    u.is_superuser,
    u.tienda_id,
    t.nombre AS tienda_nombre,
    u.date_joined,
    u.last_login,
    u.is_active
FROM inventario_user u
LEFT JOIN inventario_tienda t ON u.tienda_id = t.id
ORDER BY u.username;

-- 3. Buscar usuario específico 'ari' (case-insensitive)
SELECT 
    id,
    username,
    email,
    first_name,
    last_name,
    is_staff,
    is_superuser,
    tienda_id,
    date_joined,
    last_login,
    is_active
FROM inventario_user
WHERE LOWER(username) LIKE LOWER('%ari%')
ORDER BY username;

-- 4. Contar usuarios por tienda
SELECT 
    t.nombre AS tienda_nombre,
    COUNT(u.id) AS cantidad_usuarios,
    STRING_AGG(u.username, ', ' ORDER BY u.username) AS usuarios
FROM inventario_tienda t
LEFT JOIN inventario_user u ON t.id = u.tienda_id
GROUP BY t.id, t.nombre
ORDER BY t.nombre;

-- 5. Ver usuarios sin tienda asignada
SELECT 
    id,
    username,
    email,
    first_name,
    last_name,
    is_staff,
    is_superuser,
    tienda_id,
    date_joined,
    last_login,
    is_active
FROM inventario_user
WHERE tienda_id IS NULL
ORDER BY username;

-- 6. Ver todos los usernames (solo para verificar)
SELECT username
FROM inventario_user
ORDER BY username;

-- 7. Buscar usuarios con variaciones del nombre 'ari'
SELECT 
    id,
    username,
    email,
    first_name,
    last_name,
    tienda_id,
    is_active
FROM inventario_user
WHERE 
    LOWER(username) LIKE '%ari%' OR
    LOWER(first_name) LIKE '%ari%' OR
    LOWER(last_name) LIKE '%ari%' OR
    LOWER(email) LIKE '%ari%'
ORDER BY username;
