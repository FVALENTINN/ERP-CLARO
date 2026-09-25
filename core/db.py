"""
Capa de datos del ERP.
- En local usa SQLite (archivo data/erp.db).
- En la nube usa PostgreSQL gratuito (Supabase / Neon) si existe DATABASE_URL
  en st.secrets o en variables de entorno.
"""
import os
from core.utils import ahora

import pandas as pd
import streamlit as st
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, MetaData,
    String, Table, Text, create_engine, text,
)

# Permite que PostgreSQL acepte tipos numpy (pandas) como parámetros
try:
    import numpy as np
    from psycopg2.extensions import AsIs, register_adapter
    for _t in (np.int64, np.int32, np.float64, np.float32):
        register_adapter(_t, AsIs)
    register_adapter(np.bool_, lambda b: AsIs(bool(b)))
except Exception:  # psycopg2 no instalado (uso local con SQLite)
    pass

metadata = MetaData()

usuarios = Table(
    "usuarios", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(50), unique=True, nullable=False),
    Column("nombre", String(120), nullable=False),
    Column("email", String(120)),
    Column("rol", String(30), nullable=False),          # ADMIN, LOGISTICA, VENTAS, FINANZAS
    Column("password_hash", String(256), nullable=False),
    Column("activo", Boolean, default=True),
    Column("cambiar_password", Boolean, default=True),
    Column("creado_en", DateTime, default=ahora),
    Column("ultimo_acceso", DateTime),
)

lotes_compra = Table(
    "lotes_compra", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("fecha_compra", Date, nullable=False),
    Column("nro_documento", String(60)),                # guía / factura de ingreso
    Column("modalidad", String(20), default="CONSIGNACION"),
    Column("origen", String(20)),                       # MANUAL / EXCEL
    Column("cantidad", Integer, default=0),
    Column("total", Float, default=0),
    Column("observacion", Text),
    Column("usuario", String(50)),
    Column("creado_en", DateTime, default=ahora),
)

inventario = Table(
    "inventario", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tipo", String(10), nullable=False),         # EQUIPO / SIM
    Column("marca", String(60)),
    Column("modelo", String(120)),
    Column("serie", String(25), unique=True, nullable=False),  # IMEI o ICCID
    Column("precio_compra", Float, default=0),
    Column("nro_factura", String(60)),
    Column("fecha_compra", Date, nullable=False),
    Column("modalidad", String(20), default="CONSIGNACION"),
    Column("lote_id", Integer, ForeignKey("lotes_compra.id")),
    Column("estado", String(20), default="DISPONIBLE"),  # DISPONIBLE, VENDIDO, DEVUELTO, BAJA
    Column("fecha_venta", Date),
    Column("observacion", Text),
    Column("creado_por", String(50)),
    Column("creado_en", DateTime, default=ahora),
)

ventas = Table(
    "ventas", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("fecha_venta", Date, nullable=False),
    Column("item_id", Integer, ForeignKey("inventario.id")),
    Column("tipo", String(10)),
    Column("tipo_doc", String(5)),                      # DNI / CE / RUC
    Column("nro_doc", String(15)),
    Column("cliente", String(150)),
    Column("telefono", String(20)),
    Column("marca", String(60)),
    Column("modelo", String(120)),
    Column("serie", String(25)),
    Column("precio_compra", Float),
    Column("precio_venta", Float),
    Column("diferencia", Float),                        # venta - compra (negativo = pérdida → NC)
    Column("bo", String(40)),                           # Business Order Claro
    Column("motorizado", String(100)),
    Column("comprobante", String(40)),
    Column("factura_claro", String(40)),                # factura que emite Claro luego de la venta
    Column("monto_factura_claro", Float),
    Column("fecha_factura_claro", Date),
    Column("estado", String(15), default="ACTIVA"),     # ACTIVA / ANULADA
    Column("observacion", Text),
    Column("usuario", String(50)),
    Column("creado_en", DateTime, default=ahora),
)

reclamos = Table(
    "reclamos", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("venta_id", Integer, ForeignKey("ventas.id")),
    Column("serie", String(25)),
    Column("monto_esperado", Float),                    # NC que Claro debe emitir
    Column("estado", String(25), default="PENDIENTE NC"),
    # PENDIENTE NC → (sin NC en plazo) → RECLAMADO → NC RECIBIDA / NC PARCIAL → CERRADO
    Column("nro_nc", String(40)),
    Column("monto_nc", Float),
    Column("fecha_nc", Date),
    Column("fecha_reclamo", Date),
    Column("nro_reclamos", Integer, default=0),
    Column("ticket_claro", String(60)),
    Column("observacion", Text),
    Column("creado_en", DateTime, default=ahora),
    Column("actualizado_en", DateTime, default=ahora),
)

reclamo_eventos = Table(
    "reclamo_eventos", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("reclamo_id", Integer, ForeignKey("reclamos.id")),
    Column("fecha", DateTime, default=ahora),
    Column("usuario", String(50)),
    Column("accion", String(60)),
    Column("detalle", Text),
)

auditoria = Table(
    "auditoria", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("fecha", DateTime, default=ahora),
    Column("usuario", String(50)),
    Column("modulo", String(30)),
    Column("accion", String(60)),
    Column("detalle", Text),
)

config = Table(
    "config", metadata,
    Column("clave", String(50), primary_key=True),
    Column("valor", Text),
)

CONFIG_DEFAULT = {
    "empresa": "TELETALK S.A.C.",
    "ruc_empresa": "",
    "dias_limite_venta": "90",
    "dias_alerta": "15",
    "dias_espera_nc": "7",
    "correo_claro": "",
    "correo_copia": "",
    "firma_correo": "Gerencia de Finanzas",
}


def _get_database_url():
    url = None
    try:
        url = st.secrets.get("DATABASE_URL")  # type: ignore[attr-defined]
    except Exception:
        url = None
    url = url or os.environ.get("DATABASE_URL")
    if url and "://" in url and "@" in url:
        from urllib.parse import quote, unquote
        esquema, resto = url.split("://", 1)
        credenciales, host = resto.rsplit("@", 1)
        if ":" in credenciales:
            usuario, clave = credenciales.split(":", 1)
            url = f"{esquema}://{usuario}:{quote(unquote(clave), safe='')}@{host}"
    if url:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(base, exist_ok=True)
    return "sqlite:///" + os.path.join(base, "erp.db")


@st.cache_resource(show_spinner=False)
def get_engine():
    url = _get_database_url()
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    metadata.create_all(engine)
    _seed(engine)
    return engine


def es_postgres():
    return get_engine().dialect.name == "postgresql"


def _seed(engine):
    from core.auth import hash_password
    with engine.begin() as cn:
        n = cn.execute(text("SELECT COUNT(*) FROM usuarios")).scalar()
        if n == 0:
            cn.execute(usuarios.insert().values(
                username="admin", nombre="Administrador", email="",
                rol="ADMIN", password_hash=hash_password("admin123"),
                activo=True, cambiar_password=True, creado_en=ahora(),
            ))
        existentes = {r[0] for r in cn.execute(text("SELECT clave FROM config"))}
        for k, v in CONFIG_DEFAULT.items():
            if k not in existentes:
                cn.execute(config.insert().values(clave=k, valor=v))


# ---------------------------------------------------------------- helpers
def q(sql, params=None):
    """SELECT → DataFrame."""
    with get_engine().connect() as cn:
        return pd.read_sql(text(sql), cn, params=params or {})


def scalar(sql, params=None):
    with get_engine().connect() as cn:
        return cn.execute(text(sql), params or {}).scalar()


def execute(sql, params=None):
    with get_engine().begin() as cn:
        return cn.execute(text(sql), params or {})


def get_config():
    df = q("SELECT clave, valor FROM config")
    cfg = dict(CONFIG_DEFAULT)
    cfg.update(dict(zip(df["clave"], df["valor"])))
    return cfg


def set_config(valores: dict):
    with get_engine().begin() as cn:
        for k, v in valores.items():
            r = cn.execute(text("UPDATE config SET valor=:v WHERE clave=:k"), {"k": k, "v": str(v)})
            if r.rowcount == 0:
                cn.execute(config.insert().values(clave=k, valor=str(v)))


def log(usuario, modulo, accion, detalle=""):
    try:
        with get_engine().begin() as cn:
            cn.execute(auditoria.insert().values(
                fecha=ahora(), usuario=usuario, modulo=modulo,
                accion=accion, detalle=str(detalle)[:2000],
            ))
    except Exception:
        pass
