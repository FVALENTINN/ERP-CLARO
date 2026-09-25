"""Autenticación y permisos por rol."""
import hashlib
import hmac
import os

import streamlit as st

ROLES = {
    "ADMIN": "Administrador",
    "FINANZAS": "Finanzas / Contabilidad",
    "LOGISTICA": "Logística / Almacén",
    "VENTAS": "Ventas",
}

# Módulos visibles por rol
PERMISOS = {
    "ADMIN": ["Dashboard", "Inventarios", "Compras", "Ventas", "Gestión de Reclamo", "Usuarios y Configuración"],
    "FINANZAS": ["Dashboard", "Inventarios", "Compras", "Ventas", "Gestión de Reclamo"],
    "LOGISTICA": ["Dashboard", "Inventarios", "Compras"],
    "VENTAS": ["Dashboard", "Inventarios", "Ventas"],
}

ITER = 200_000


def hash_password(pwd: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt, ITER)
    return f"pbkdf2${ITER}${salt.hex()}${dk.hex()}"


def check_password(pwd: str, stored: str) -> bool:
    try:
        _, it, salt, h = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pwd.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), h)
    except Exception:
        return False


def usuario_actual():
    return st.session_state.get("user")


def puede(accion: str) -> bool:
    """Acciones sensibles: anular ventas, editar precios, gestionar usuarios."""
    u = usuario_actual()
    if not u:
        return False
    reglas = {
        "anular_venta": {"ADMIN", "FINANZAS"},
        "editar_inventario": {"ADMIN", "LOGISTICA", "FINANZAS"},
        "gestionar_reclamo": {"ADMIN", "FINANZAS"},
        "registrar_venta": {"ADMIN", "VENTAS", "FINANZAS"},
        "registrar_compra": {"ADMIN", "LOGISTICA", "FINANZAS"},
    }
    return u["rol"] in reglas.get(accion, {"ADMIN"})
