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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root {
    --navy: #0B1E3F; --navy-2: #12305E; --azul: #1E6FD9; --azul-claro: #3B8BF0;
    --cian: #22B8CF; --naranja: #F5A524; --verde: #22C55E; --rojo: #EF4444;
    --fondo: #F3F6FB; --card: #FFFFFF; --texto: #0F172A; --gris: #64748B; --borde: #E2E8F0;
}
html, body, [class*="css"], .stApp { font-family: 'Inter', sans-serif; }
.stApp { background: var(--fondo); }
.block-container { padding-top: 2.6rem; padding-bottom: 2rem; max-width: 1500px; }
header[data-testid="stHeader"] { background: transparent; }

/* ---------- Sidebar azul marino ---------- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, var(--navy) 0%, var(--navy-2) 100%);
    border-right: none;
}
section[data-testid="stSidebar"] * { color: #E6EEF9; }
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.12); }
section[data-testid="stSidebar"] small, section[data-testid="stSidebar"] .stCaption p { color: #9FB3D1 !important; }
.marca-erp { display:flex; align-items:center; gap:10px; margin: 4px 0 2px 0; }
.marca-erp .logo { width:38px; height:38px; border-radius:10px; background: var(--azul);
    display:flex; align-items:center; justify-content:center; font-weight:800; font-size:15px; color:#fff !important;
    box-shadow: 0 4px 14px rgba(30,111,217,.45); }
.marca-erp .nombre { font-size: 1.35rem; font-weight: 800; letter-spacing: .5px; color:#fff !important; }
.usuario-box { background: rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.08);
    border-radius: 12px; padding: 10px 12px; margin-top: 6px; }
.usuario-box b { color:#fff !important; }
section[data-testid="stSidebar"] div[role="radiogroup"] { gap: 4px; }
section[data-testid="stSidebar"] div[role="radiogroup"] label {
    padding: 10px 12px; border-radius: 10px; margin: 0; width: 100%;
    transition: background .15s ease;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background: rgba(255,255,255,.08); }
section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child:not(:has([data-testid="stMarkdownContainer"])) { display: none; }
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] > div > div:first-child:not([data-testid]) { display: none; }
section[data-testid="stSidebar"] div[role="radiogroup"] { width: 100%; }
section[data-testid="stSidebar"] div[role="radiogroup"] label { display: flex; box-sizing: border-box; }
section[data-testid="stSidebar"] div[role="radiogroup"] label[data-selected="true"],
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
    background: var(--azul); box-shadow: 0 4px 14px rgba(30,111,217,.40);
}
section[data-testid="stSidebar"] div[role="radiogroup"] label p { font-size: .95rem; font-weight: 500; }
section[data-testid="stSidebar"] .stButton button {
    background: transparent; border: 1px solid rgba(255,255,255,.25); color: #E6EEF9; border-radius: 10px;
}
section[data-testid="stSidebar"] .stButton button:hover { background: rgba(255,255,255,.08); border-color: #fff; }

/* ---------- Tarjetas KPI ---------- */
div[data-testid="stMetric"] {
    background: var(--card); border: 1px solid var(--borde); border-radius: 14px;
    padding: 16px 18px; box-shadow: 0 2px 10px rgba(15,23,42,.05);
    border-top: 4px solid var(--azul);
}
div[data-testid="stMetricLabel"] p { font-size: .82rem; color: var(--gris); font-weight: 600; }
div[data-testid="stMetricValue"] { color: var(--texto); font-weight: 700; }

/* ---------- Contenedores con borde = tarjetas blancas ---------- */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--card); border-radius: 14px !important; border-color: var(--borde) !important;
    box-shadow: 0 2px 10px rgba(15,23,42,.05);
}
div[data-testid="stForm"] { background: var(--card); border-radius: 14px; border-color: var(--borde);
    box-shadow: 0 2px 10px rgba(15,23,42,.05); }
div[data-testid="stDataFrame"] { background: var(--card); border-radius: 10px; }
.card-titulo { font-weight: 700; font-size: 1rem; color: var(--texto); margin-bottom: .2rem; }

/* ---------- Encabezados ---------- */
.titulo-modulo { font-size: 1.75rem; font-weight: 800; color: var(--texto); margin-bottom: .1rem; }
.sub-modulo { color: var(--gris); margin-bottom: 1.1rem; }
h4, h5 { color: var(--texto); }

/* ---------- Botones y pestañas ---------- */
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primaryFormSubmit"],
.stDownloadButton button[kind="primary"] {
    background: var(--azul); border: none; border-radius: 10px; font-weight: 600;
}
.stButton button, .stDownloadButton button, .stFormSubmitButton button { border-radius: 10px; }
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid var(--borde); }
.stTabs [data-baseweb="tab"] { font-weight: 600; }

/* ---------- KPI personalizadas ---------- */
.kpi { background: var(--card); border: 1px solid var(--borde); border-radius: 16px; padding: 16px 18px;
    box-shadow: 0 2px 12px rgba(15,23,42,.06); display: flex; justify-content: space-between;
    align-items: flex-start; min-height: 118px; margin-bottom: 14px; }
.kpi .lbl { color: var(--gris); font-size: .82rem; font-weight: 600; }
.kpi .val { font-size: 1.75rem; font-weight: 800; color: var(--texto); margin-top: 6px; line-height: 1.15; }
.kpi .sub { font-size: .78rem; margin-top: 8px; color: var(--gris); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi > div:first-child { min-width: 0; }
.kpi .sub.up { color: #16A34A; font-weight: 600; }
.kpi .sub.down { color: #DC2626; font-weight: 600; }
.kpi .ico { width: 46px; height: 46px; min-width: 46px; border-radius: 12px; display: flex;
    align-items: center; justify-content: center; }
.kpi .ico svg { width: 22px; height: 22px; }

/* ---------- Barra superior ---------- */
.topbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;
    background: var(--card); border: 1px solid var(--borde); border-radius: 16px; padding: 14px 22px;
    margin-bottom: 18px; box-shadow: 0 2px 12px rgba(15,23,42,.05); }
.tb-titulo { font-size: 1.5rem; font-weight: 800; color: var(--texto); line-height: 1.2; }
.tb-sub { color: var(--gris); font-size: .88rem; margin-top: 2px; }
.tb-der { display: flex; align-items: center; gap: 12px; }
.tb-chip { background: #EEF4FD; color: var(--azul); font-weight: 600; font-size: .82rem;
    padding: 6px 12px; border-radius: 999px; }
.tb-user { display: flex; align-items: center; gap: 8px; font-weight: 600; color: var(--texto); font-size: .9rem; }
.tb-avatar { width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, var(--azul), var(--cian));
    color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: .85rem; }

/* ---------- Login ---------- */
/* Panel de login centrado con el formulario dentro */
.st-key-login_card { background: linear-gradient(145deg, var(--navy) 0%, var(--navy-2) 60%, #1B4B8F 100%);
    border-radius: 22px; padding: 38px 40px 30px 40px; box-shadow: 0 14px 40px rgba(11,30,63,.35); }
.login-top { text-align: center; margin-bottom: 6px; }
.login-top .t1 { font-size: 2.6rem; font-weight: 800; color: #fff; line-height: 1.1; }
.login-top .t2 { background: linear-gradient(90deg, #3B8BF0, #22B8CF); -webkit-background-clip: text;
    -webkit-text-fill-color: transparent; }
.login-top .t3 { font-size: 1.3rem; font-weight: 700; color: #fff; margin-top: 4px; }
.login-top .lema { color: #C9D7EE; font-size: .95rem; margin-top: 10px; }
.st-key-login_card div[data-testid="stForm"] { background: #fff; border: none; border-radius: 16px;
    padding: 22px 24px; box-shadow: 0 10px 30px rgba(0,0,0,.25); }
.st-key-login_card .login-feats { margin-top: 18px; }
.st-key-login_card .login-pie { text-align: center; margin-top: 18px; }
.st-key-login_card div[data-testid="stAlert"] { background: #FDECEC; border-radius: 12px; }
.st-key-login_card div[data-testid="stAlert"] p { color: #B91C1C !important; font-weight: 600; }
.login-panel { background: linear-gradient(145deg, var(--navy) 0%, var(--navy-2) 60%, #1B4B8F 100%);
    border-radius: 22px; padding: 44px 40px; color: #fff; min-height: 520px; box-shadow: 0 14px 40px rgba(11,30,63,.35);
    position: relative; overflow: hidden; }
.login-panel:after { content: ""; position: absolute; right: -80px; bottom: -80px; width: 260px; height: 260px;
    border-radius: 50%; background: radial-gradient(circle, rgba(59,139,240,.45), transparent 70%); }
.login-panel .t1 { font-size: 3rem; font-weight: 800; line-height: 1; color: #fff; }
.login-panel .t2 { font-size: 2.3rem; font-weight: 800; line-height: 1.1;
    background: linear-gradient(90deg, #3B8BF0, #22B8CF); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.login-panel .t3 { font-size: 1.6rem; font-weight: 700; color: #fff; margin-bottom: 18px; }
.login-panel .lema { color: #C9D7EE; font-size: 1.02rem; margin-bottom: 30px; }
.login-feats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 10px; }
.login-feats div { text-align: center; font-size: .78rem; color: #DCE6F5; }
.login-feats span { display: flex; width: 50px; height: 50px; margin: 0 auto 8px auto; border-radius: 50%;
    border: 2px solid rgba(255,255,255,.35); align-items: center; justify-content: center; font-size: 20px; }
.login-pie { margin-top: 34px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,.15); color: #C9D7EE; font-size: .9rem; }
.login-pie b { color: #3B8BF0; }
.login-hero { text-align:center; margin-bottom: 14px; }
.login-hero .logo { width:64px; height:64px; margin: 0 auto 12px auto; border-radius:16px;
    background: linear-gradient(135deg, var(--azul), var(--cian)); display:flex; align-items:center;
    justify-content:center; color:#fff; font-size:24px; font-weight:800; box-shadow:0 8px 24px rgba(30,111,217,.35); }
.login-hero h2 { margin: 0; color: var(--texto); font-weight: 800; }
.login-hero p { color: var(--gris); margin-top: 4px; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

ICONOS = {
    "Dashboard": ":material/dashboard:", "Inventarios": ":material/inventory_2:",
    "Compras": ":material/shopping_cart:", "Ventas": ":material/point_of_sale:",
    "Gestión de Reclamo": ":material/mark_email_unread:", "Usuarios y Configuración": ":material/settings:",
}


def pantalla_login():
    cfg = db.get_config()
    st.markdown("<div style='height:2vh'></div>", unsafe_allow_html=True)
    _, centro, _ = st.columns([1, 1.35, 1])
    with centro, st.container(key="login_card"):
        st.markdown(
            "<div class='login-top'><div class='t1'>ERP <span class='t2'>Dashboard</span></div>"
            "<div class='t3'>Inventario Claro</div>"
            f"<div class='lema'>Información en tiempo real. Decisiones más inteligentes.<br>{cfg['empresa']}</div></div>",
            unsafe_allow_html=True)
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
        st.markdown(
            "<div class='login-feats'>"
            "<div><span>⏱️</span>Monitoreo en tiempo real</div><div><span>📊</span>Análisis de rotación</div>"
            "<div><span>🔔</span>Alertas de 90 días</div><div><span>📧</span>Control de reclamos</div></div>"
            "<div class='login-pie'>Primer ingreso: <b>admin</b> / <b>admin123</b> (se pedirá cambiarla)</div>",
            unsafe_allow_html=True)


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
        st.markdown("<div class='marca-erp'><div class='logo'>ERP</div><div class='nombre'>ERP Claro</div></div>",
                    unsafe_allow_html=True)
        st.caption(db.get_config()["empresa"])
        st.markdown(f"<div class='usuario-box'>👤 <b>{u['nombre']}</b><br><small>{ROLES.get(u['rol'], u['rol'])}</small></div>",
                    unsafe_allow_html=True)
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
