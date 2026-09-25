import re

import streamlit as st

from core import db
from core.auth import ROLES, hash_password, usuario_actual
from core.utils import ahora, hoy, to_excel
from modulos.dashboard import encabezado


def render():
    encabezado("⚙️ Usuarios y Configuración", "Accesos, roles, parámetros de alertas y reclamos, auditoría y respaldo")
    u = usuario_actual()
    if u["rol"] != "ADMIN":
        st.error("Solo el administrador puede acceder.")
        return
    tabs = st.tabs(["👥 Usuarios", "🔧 Parámetros", "🧾 Auditoría", "💾 Respaldo"])

    with tabs[0]:
        us = db.q("SELECT id, username, nombre, email, rol, activo, ultimo_acceso, creado_en FROM usuarios ORDER BY id")
        us["rol"] = us["rol"].map(lambda r: ROLES.get(r, r))
        st.dataframe(us, hide_index=True)
        st.caption("Permisos por rol: **Administrador** todo · **Finanzas** todos los módulos excepto usuarios · "
                   "**Logística** Dashboard, Inventarios y Compras · **Ventas** Dashboard, Inventarios y Ventas.")
        c1, c2 = st.columns(2)
        with c1, st.form("nuevo_usuario", clear_on_submit=True):
            st.markdown("**Crear usuario**")
            username = st.text_input("Usuario (sin espacios)")
            nombre = st.text_input("Nombre completo")
            email = st.text_input("Correo")
            rol = st.selectbox("Rol", list(ROLES.keys()), format_func=lambda r: ROLES[r])
            pwd = st.text_input("Contraseña temporal (mín. 8)", type="password")
            if st.form_submit_button("Crear", type="primary"):
                username = username.strip().lower()
                if not re.fullmatch(r"[a-z0-9._-]{3,30}", username):
                    st.error("Usuario inválido (3-30 caracteres: letras, números, punto, guion).")
                elif len(pwd) < 8 or not nombre.strip():
                    st.error("Complete nombre y una contraseña de al menos 8 caracteres.")
                elif db.scalar("SELECT COUNT(*) FROM usuarios WHERE username=:u", {"u": username}):
                    st.error("El usuario ya existe.")
                else:
                    with db.get_engine().begin() as cn:
                        cn.execute(db.usuarios.insert().values(
                            username=username, nombre=nombre.strip(), email=email.strip(), rol=rol,
                            password_hash=hash_password(pwd), activo=True, cambiar_password=True, creado_en=ahora()))
                    db.log(u["username"], "Usuarios", "Crear", f"{username} ({rol})")
                    st.success(f"Usuario {username} creado. Deberá cambiar su contraseña al ingresar.")
                    st.rerun()
        with c2:
            st.markdown("**Editar usuario**")
            raw = db.q("SELECT * FROM usuarios ORDER BY id")
            uid = st.selectbox("Usuario", raw["id"].tolist(),
                               format_func=lambda i: raw.loc[raw["id"] == i, "username"].iloc[0])
            fila = raw[raw["id"] == uid].iloc[0]
            with st.form("editar_usuario"):
                nombre = st.text_input("Nombre", fila["nombre"])
                email = st.text_input("Correo", fila["email"] or "")
                rol = st.selectbox("Rol", list(ROLES.keys()), index=list(ROLES.keys()).index(fila["rol"]),
                                   format_func=lambda r: ROLES[r])
                activo = st.checkbox("Activo", bool(fila["activo"]))
                nueva = st.text_input("Restablecer contraseña (dejar vacío para no cambiar)", type="password")
                if st.form_submit_button("Guardar cambios"):
                    if int(uid) == u["id"] and (not activo or rol != "ADMIN"):
                        st.error("No puede desactivarse ni quitarse el rol de administrador a sí mismo.")
                    elif nueva and len(nueva) < 8:
                        st.error("La contraseña debe tener al menos 8 caracteres.")
                    else:
                        db.execute("UPDATE usuarios SET nombre=:n, email=:e, rol=:r, activo=:a WHERE id=:i",
                                   {"n": nombre, "e": email, "r": rol, "a": activo, "i": int(uid)})
                        if nueva:
                            db.execute("UPDATE usuarios SET password_hash=:h, cambiar_password=:c WHERE id=:i",
                                       {"h": hash_password(nueva), "c": True, "i": int(uid)})
                        db.log(u["username"], "Usuarios", "Editar", f"{fila['username']}")
                        st.success("Cambios guardados.")
                        st.rerun()

    with tabs[1]:
        cfg = db.get_config()
        with st.form("cfg"):
            c = st.columns(2)
            empresa = c[0].text_input("Razón social", cfg["empresa"])
            ruc = c[1].text_input("RUC", cfg["ruc_empresa"])
            c = st.columns(3)
            limite = c[0].number_input("Días máximos para vender (consignación)", 1, 365, int(cfg["dias_limite_venta"]))
            alerta = c[1].number_input("Días de anticipación de la alerta", 1, 90, int(cfg["dias_alerta"]))
            espera = c[2].number_input("Días de espera de NC automática antes de reclamar", 0, 90,
                                       int(cfg["dias_espera_nc"]))
            c = st.columns(2)
            correo = c[0].text_input("Correo de Claro para reclamos (Para)", cfg["correo_claro"])
            copia = c[1].text_input("Correo(s) en copia (CC)", cfg["correo_copia"])
            firma = st.text_input("Cargo / área para la firma del correo", cfg["firma_correo"])
            if st.form_submit_button("Guardar parámetros", type="primary"):
                db.set_config({"empresa": empresa, "ruc_empresa": ruc, "dias_limite_venta": limite,
                               "dias_alerta": alerta, "dias_espera_nc": espera, "correo_claro": correo,
                               "correo_copia": copia, "firma_correo": firma})
                db.log(u["username"], "Config", "Actualizar parámetros")
                st.success("Parámetros guardados.")

    with tabs[2]:
        au = db.q("SELECT fecha, usuario, modulo, accion, detalle FROM auditoria ORDER BY id DESC LIMIT 2000")
        st.dataframe(au, hide_index=True)

    with tabs[3]:
        st.write("Descargue una copia completa de la información del ERP en Excel (recomendado semanalmente).")
        if st.button("Generar respaldo"):
            hojas = {t: db.q(f"SELECT * FROM {t}") for t in
                     ["inventario", "lotes_compra", "ventas", "reclamos", "reclamo_eventos", "usuarios", "config"]}
            hojas["usuarios"] = hojas["usuarios"].drop(columns=["password_hash"])
            st.download_button("⬇️ Descargar respaldo", to_excel(hojas), f"respaldo_erp_{hoy():%Y%m%d}.xlsx",
                               type="primary")
