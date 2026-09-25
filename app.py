"""
ERP de Inventario de Equipos Móviles y SIM Card – Distribuidor Autorizado Claro
Ejecutar:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="ERP Inventario Claro", page_icon="📱", layout="wide",
                   initial_sidebar_state="expanded")

from core import db  # noqa: E402
from core.auth import PERMISOS, ROLES, check_password, hash_password  # noqa: E402
from core.utils import ahora  # noqa: E402

CSS = """
<style>
:root { --claro: #DA291C; }
.block-container { padding-top: 3.2rem; }
div[data-testid="stMetric"] {
    background: var(--secondary-background-color); border-left: 5px solid var(--claro);
    padding: 12px 16px; border-radius: 8px;
}
div[data-testid="stMetricLabel"] p { font-size: .85rem; }
.titulo-modulo { font-size: 1.7rem; font-weight: 700; margin-bottom: .2rem; }
.sub-modulo { color: #888; margin-bottom: 1rem; }
section[data-testid="stSidebar"] .stRadio label { font-size: 1rem; }
.login-box { max-width: 420px; margin: 6vh auto 0 auto; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

ICONOS = {
    "Dashboard": "📊", "Inventarios": "📦", "Compras": "🛒", "Ventas": "💳",
    "Gestión de Reclamo": "📧", "Usuarios y Configuración": "⚙️",
}


def pantalla_login():
    cfg = db.get_config()
    _, c, _ = st.columns([1, 1.2, 1])
    with c:
        st.markdown("<div style='height:6vh'></div>", unsafe_allow_html=True)
        st.markdown(f"<h2 style='text-align:center'>📱 ERP Inventario Claro</h2>"
                    f"<p style='text-align:center;color:#888'>{cfg['empresa']}</p>", unsafe_allow_html=True)
        with st.form("login"):
            usuario = st.text_input("Usuario")
            clave = st.text_input("Contraseña", type="password")
            ok = st.form_submit_button("Ingresar", type="primary", width="stretch")
        if ok:
            df = db.q("SELECT * FROM usuarios WHERE username=:u", {"u": usuario.strip().lower()})
            if df.empty or not check_password(clave, df.iloc[0]["password_hash"]):
                st.error("Usuario o contraseña incorrectos.")
                db.log(usuario, "Login", "Acceso fallido")
            elif not bool(df.iloc[0]["activo"]):
                st.error("Usuario inactivo. Comuníquese con el administrador.")
            else:
                u = df.iloc[0]
                st.session_state.user = {
                    "id": int(u["id"]), "username": u["username"], "nombre": u["nombre"],
                    "rol": u["rol"], "email": u["email"], "cambiar_password": bool(u["cambiar_password"]),
                }
                db.execute("UPDATE usuarios SET ultimo_acceso=:a WHERE id=:i", {"a": ahora(), "i": int(u["id"])})
                db.log(u["username"], "Login", "Ingreso")
                st.rerun()
        st.caption("Primer ingreso: usuario **admin** / contraseña **admin123** (se pedirá cambiarla).")


def pantalla_cambio_password():
    u = st.session_state.user
    _, c, _ = st.columns([1, 1.2, 1])
    with c:
        st.markdown("### 🔐 Cambie su contraseña")
        st.info("Por seguridad debe definir una nueva contraseña antes de continuar.")
        with st.form("cambio"):
            p1 = st.text_input("Nueva contraseña", type="password")
            p2 = st.text_input("Repetir contraseña", type="password")
            ok = st.form_submit_button("Guardar", type="primary", width="stretch")
        if ok:
            if len(p1) < 8:
                st.error("La contraseña debe tener al menos 8 caracteres.")
            elif p1 != p2:
                st.error("Las contraseñas no coinciden.")
            else:
                db.execute("UPDATE usuarios SET password_hash=:h, cambiar_password=:f WHERE id=:i",
                           {"h": hash_password(p1), "f": False, "i": u["id"]})
                st.session_state.user["cambiar_password"] = False
                db.log(u["username"], "Login", "Cambio de contraseña")
                st.success("Contraseña actualizada.")
                st.rerun()


def main():
    db.get_engine()
    if "user" not in st.session_state:
        pantalla_login()
        return
    u = st.session_state.user
    if u.get("cambiar_password"):
        pantalla_cambio_password()
        return

    modulos = PERMISOS.get(u["rol"], ["Dashboard"])
    with st.sidebar:
        st.markdown("## 📱 ERP Claro")
        st.caption(db.get_config()["empresa"])
        st.markdown(f"👤 **{u['nombre']}**  \n<small>{ROLES.get(u['rol'], u['rol'])}</small>", unsafe_allow_html=True)
        st.divider()
        destino = st.session_state.pop("ir_a", None)
        if destino in modulos:
            st.session_state.menu = destino
        modulo = st.radio("Menú", modulos, key="menu", label_visibility="collapsed",
                          format_func=lambda m: f"{ICONOS.get(m, '')}  {m}")
        st.divider()
        if st.button("🔐 Cambiar mi contraseña", width="stretch"):
            st.session_state.user["cambiar_password"] = True
            st.rerun()
        if st.button("Cerrar sesión", width="stretch"):
            db.log(u["username"], "Login", "Salida")
            st.session_state.clear()
            st.rerun()
        st.caption(f"Base de datos: {'PostgreSQL (nube)' if db.es_postgres() else 'SQLite (local)'}")

    if modulo == "Dashboard":
        from modulos import dashboard as m
    elif modulo == "Inventarios":
        from modulos import inventarios as m
    elif modulo == "Compras":
        from modulos import compras as m
    elif modulo == "Ventas":
        from modulos import ventas as m
    elif modulo == "Gestión de Reclamo":
        from modulos import reclamos as m
    else:
        from modulos import usuarios as m
    m.render()


main()
