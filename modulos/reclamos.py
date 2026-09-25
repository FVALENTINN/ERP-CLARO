import smtplib
import urllib.parse
from email.message import EmailMessage

import pandas as pd
import streamlit as st

from core import db, servicios as sv
from core.auth import puede, usuario_actual
from core.utils import hoy, limpiar_serie, soles, soles0, to_excel
from modulos.dashboard import encabezado

ABIERTOS = ["PENDIENTE NC", "RECLAMADO", "NC PARCIAL"]
COLS = {
    "id": "N° reclamo", "estado": "Estado", "accion_sugerida": "Acción sugerida", "serie": "IMEI/ICCID",
    "marca": "Marca", "modelo": "Modelo", "fecha_venta": "Fecha venta", "dias_sin_nc": "Días desde venta",
    "precio_compra": "P. compra", "monto_factura_claro": "Monto fact. Claro", "precio_venta": "P. venta",
    "monto_esperado": "NC esperada", "monto_nc": "NC recibida", "saldo": "Saldo pendiente", "bo": "BO",
    "factura_claro": "Fact. Claro", "nro_nc": "N° NC", "fecha_reclamo": "Último reclamo",
    "nro_reclamos": "N° reclamos", "ticket_claro": "Ticket Claro", "cliente": "Cliente",
}
MONEY = st.column_config.NumberColumn(format="S/ %.2f")
CFG_MONEY = {k: MONEY for k in ["P. compra", "Monto fact. Claro", "P. venta", "NC esperada", "NC recibida",
                                "Saldo pendiente"]}
CFG_MONEY["Fecha venta"] = st.column_config.DateColumn(format="DD/MM/YYYY")
CFG_MONEY["Último reclamo"] = st.column_config.DateColumn(format="DD/MM/YYYY")


def _smtp_config():
    try:
        s = st.secrets.get("smtp", None)
        return dict(s) if s else None
    except Exception:
        return None


def _enviar_correo(smtp, para, cc, asunto, cuerpo, adjunto: bytes, nombre_adj):
    msg = EmailMessage()
    msg["From"] = smtp.get("remitente", smtp["usuario"])
    msg["To"] = para
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = asunto
    msg.set_content(cuerpo)
    msg.add_attachment(adjunto, maintype="application",
                       subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=nombre_adj)
    with smtplib.SMTP(smtp["host"], int(smtp.get("port", 587)), timeout=30) as s:
        s.starttls()
        s.login(smtp["usuario"], smtp["password"])
        s.send_message(msg)


def render():
    encabezado("📧 Gestión de Reclamo", "Seguimiento de notas de crédito de Claro por ventas bajo el costo de compra")
    u = usuario_actual()
    cfg = db.get_config()
    rec = sv.reclamos_df()

    abiertos = rec[rec["estado"].isin(ABIERTOS)] if not rec.empty else rec
    m = st.columns(5)
    m[0].metric("Reclamos abiertos", f"{len(abiertos):,}")
    m[1].metric("Saldo NC pendiente", soles0(abiertos["saldo"].sum() if len(abiertos) else 0))
    m[2].metric("📧 Por reclamar", f"{(abiertos['accion_sugerida'] == '📧 RECLAMAR').sum() if len(abiertos) else 0:,}",
                help=f"Pendientes sin NC después de {cfg['dias_espera_nc']} días")
    m[3].metric("En seguimiento", f"{abiertos['estado'].isin(['RECLAMADO', 'NC PARCIAL']).sum() if len(abiertos) else 0:,}")
    m[4].metric("NC recuperadas (total)", soles0(rec["monto_nc"].sum() if not rec.empty else 0))

    tabs = st.tabs(["📥 Bandeja", "✉️ Generar correo de reclamo", "✅ Registrar nota de crédito", "🕓 Historial"])

    # ================================================================ BANDEJA
    with tabs[0]:
        st.caption(f"Flujo: la venta bajo costo crea el reclamo en **PENDIENTE NC** → si Claro no emite la NC en "
                   f"{cfg['dias_espera_nc']} días se sugiere **RECLAMAR** → al enviar el correo pasa a **RECLAMADO** → "
                   "al registrar la NC pasa a **NC RECIBIDA** (o **NC PARCIAL** si el monto es menor).")
        if rec.empty:
            st.success("No hay ventas bajo costo. No existen notas de crédito pendientes.")
        else:
            f = st.columns([2, 2])
            est = f[0].multiselect("Estado", sorted(rec["estado"].unique()), default=[e for e in ABIERTOS
                                                                                     if e in rec["estado"].unique()])
            txt = f[1].text_input("Buscar IMEI / BO / modelo", key="rb_txt")
            d = rec[rec["estado"].isin(est)] if est else rec
            if txt:
                t = txt.strip().upper()
                d = d[d["serie"].str.contains(t, regex=False) | d["bo"].fillna("").str.upper().str.contains(t, regex=False)
                      | d["modelo"].fillna("").str.upper().str.contains(t, regex=False)]
            vista = d[list(COLS.keys())].rename(columns=COLS)
            st.dataframe(vista, hide_index=True, column_config=CFG_MONEY)
            st.download_button("⬇️ Descargar bandeja", to_excel({"Reclamos": vista}), f"reclamos_{hoy():%Y%m%d}.xlsx")
            if puede("gestionar_reclamo"):
                with st.expander("Cerrar un reclamo manualmente (ej. Claro lo compensó por otra vía)"):
                    ops = d[d["estado"].isin(ABIERTOS)]["id"].tolist()
                    if ops:
                        rid = st.selectbox("Reclamo", ops, key="cerrar_id")
                        motivo = st.text_input("Motivo de cierre", key="cerrar_mot")
                        if st.button("Cerrar reclamo", disabled=not motivo.strip()):
                            sv.cerrar_reclamo(int(rid), motivo, u["username"])
                            st.success("Reclamo cerrado.")
                            st.rerun()
                    else:
                        st.caption("No hay reclamos abiertos en el filtro.")

    # ================================================================ CORREO
    with tabs[1]:
        if not puede("gestionar_reclamo"):
            st.warning("Su rol no puede gestionar reclamos.")
        elif abiertos.empty:
            st.success("No hay reclamos abiertos.")
        else:
            solo = st.toggle("Mostrar solo los sugeridos para reclamar / seguimiento", value=True)
            base = abiertos[abiertos["accion_sugerida"] != ""]
            if solo:
                base = base[base["accion_sugerida"].str.startswith(("📧", "🔁"))]
            if base.empty:
                st.info("No hay reclamos que hayan superado el plazo de espera. Desactive el filtro para ver todos.")
            else:
                sel = base[["id", "accion_sugerida", "serie", "marca", "modelo", "fecha_venta", "dias_sin_nc", "bo",
                            "factura_claro", "saldo"]].copy()
                sel.insert(0, "Incluir", True)
                sel = sel.rename(columns={"id": "N°", "accion_sugerida": "Acción", "serie": "IMEI", "marca": "Marca",
                                          "modelo": "Modelo", "fecha_venta": "Fecha venta", "dias_sin_nc": "Días",
                                          "bo": "BO", "factura_claro": "Fact. Claro", "saldo": "Saldo NC"})
                editado = st.data_editor(sel, hide_index=True, disabled=[c for c in sel.columns if c != "Incluir"],
                                         column_config={"Saldo NC": MONEY, "Incluir": st.column_config.CheckboxColumn(),
                                                        "Fecha venta": st.column_config.DateColumn(format="DD/MM/YYYY")},
                                         key="ed_correo")
                elegidos = base[base["id"].isin(editado.loc[editado["Incluir"], "N°"])]
                if elegidos.empty:
                    st.info("Seleccione al menos un reclamo.")
                else:
                    asunto, cuerpo = sv.generar_correo(elegidos, cfg, u["nombre"])
                    c = st.columns(2)
                    para = c[0].text_input("Para", cfg["correo_claro"], help="Configurable en Usuarios y Configuración")
                    cc = c[1].text_input("CC", cfg["correo_copia"])
                    asunto = st.text_input("Asunto", asunto)
                    cuerpo = st.text_area("Cuerpo del correo", cuerpo, height=340)
                    adj = elegidos[["id", "serie", "marca", "modelo", "bo", "fecha_venta", "factura_claro",
                                    "precio_compra", "monto_factura_claro", "precio_venta", "monto_esperado",
                                    "monto_nc", "saldo"]].rename(columns=COLS)
                    nombre_adj = f"Solicitud_NC_{hoy():%Y%m%d}.xlsx"
                    adj_bytes = to_excel({"Detalle NC": adj})
                    b = st.columns(4)
                    b[0].download_button("📎 Descargar adjunto Excel", adj_bytes, nombre_adj, width="stretch")
                    mailto = (f"mailto:{para}?cc={urllib.parse.quote(cc)}&subject={urllib.parse.quote(asunto)}"
                              f"&body={urllib.parse.quote(cuerpo[:1500])}")
                    b[1].link_button("📨 Abrir en Outlook/correo", mailto, width="stretch",
                                     help="Abre su programa de correo. Si el texto es largo, copie el cuerpo completo.")
                    smtp = _smtp_config()
                    if smtp and b[2].button("🚀 Enviar desde el ERP", type="primary", width="stretch"):
                        try:
                            _enviar_correo(smtp, para, cc, asunto, cuerpo, adj_bytes, nombre_adj)
                            sv.marcar_reclamado(elegidos["id"].tolist(), u["username"])
                            st.success("Correo enviado y reclamos marcados como RECLAMADO.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"No se pudo enviar: {e}")
                    ticket = st.text_input("N° de ticket / caso de Claro (opcional)")
                    if st.button("✔️ Marcar como RECLAMADO (ya envié el correo)"):
                        sv.marcar_reclamado(elegidos["id"].tolist(), u["username"], ticket.strip())
                        st.success(f"{len(elegidos)} reclamo(s) marcados como RECLAMADO.")
                        st.rerun()
                    if not smtp:
                        st.caption("💡 Para enviar el correo directamente desde el ERP configure la sección [smtp] en "
                                   "los *secrets* (ver README).")

    # ================================================================ NC
    with tabs[2]:
        if not puede("gestionar_reclamo"):
            st.warning("Su rol no puede registrar notas de crédito.")
        elif abiertos.empty:
            st.success("No hay reclamos abiertos.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Registro individual**")
                rid = st.selectbox("Reclamo", abiertos["id"].tolist(), format_func=lambda i: (
                    f"#{i} – IMEI {abiertos.loc[abiertos['id'] == i, 'serie'].iloc[0]} – saldo "
                    f"{soles(abiertos.loc[abiertos['id'] == i, 'saldo'].iloc[0])}"))
                saldo = float(abiertos.loc[abiertos["id"] == rid, "saldo"].iloc[0])
                with st.form("nc"):
                    nro = st.text_input("N° nota de crédito")
                    monto = st.number_input("Monto NC (S/)", min_value=0.0, value=saldo, step=1.0)
                    fecha = st.date_input("Fecha NC", hoy(), format="DD/MM/YYYY")
                    if st.form_submit_button("Registrar NC", type="primary"):
                        if not nro.strip() or monto <= 0:
                            st.error("Ingrese N° y monto de la NC.")
                        else:
                            e = sv.registrar_nc(int(rid), nro.strip().upper(), monto, fecha, u["username"])
                            st.success(f"NC registrada. Estado: {e}")
                            st.rerun()
            with c2:
                st.markdown("**Carga masiva de NC (Excel)**")
                st.caption("Columnas: IMEI, N_NC, MONTO, FECHA")
                pl = pd.DataFrame({"IMEI": ["356938035643809"], "N_NC": ["FC01-0001234"], "MONTO": [50.0],
                                   "FECHA": [hoy().strftime("%d/%m/%Y")]})
                st.download_button("⬇️ Plantilla NC", to_excel({"NC": pl}), "plantilla_nc.xlsx")
                arch = st.file_uploader("Excel de NC", type=["xlsx", "csv"], key="nc_up")
                if arch and st.button("Procesar NC"):
                    df = pd.read_csv(arch, dtype=str) if arch.name.endswith(".csv") else pd.read_excel(arch, dtype=str)
                    df.columns = [c.strip().upper() for c in df.columns]
                    res = []
                    for _, r in df.iterrows():
                        s = limpiar_serie(r.get("IMEI"))
                        fila = abiertos[abiertos["serie"] == s]
                        if fila.empty:
                            res.append("Sin reclamo abierto")
                            continue
                        f = pd.to_datetime(r.get("FECHA"), dayfirst=True, errors="coerce")
                        res.append(sv.registrar_nc(int(fila.iloc[0]["id"]), str(r.get("N_NC", "")).strip().upper(),
                                                   float(pd.to_numeric(r.get("MONTO"), errors="coerce") or 0),
                                                   f.date() if not pd.isna(f) else hoy(), u["username"]))
                    df["RESULTADO"] = res
                    st.dataframe(df, hide_index=True)

    # ================================================================ HISTORIAL
    with tabs[3]:
        ev = db.q("""SELECT e.fecha, e.reclamo_id, r.serie, e.accion, e.detalle, e.usuario
                     FROM reclamo_eventos e JOIN reclamos r ON r.id=e.reclamo_id ORDER BY e.id DESC""")
        if ev.empty:
            st.info("Sin movimientos.")
        else:
            s = st.text_input("Filtrar por IMEI o N° reclamo", key="h_txt")
            if s:
                ev = ev[ev["serie"].str.contains(s.strip(), regex=False) | (ev["reclamo_id"].astype(str) == s.strip())]
            ev.columns = ["Fecha", "N° reclamo", "IMEI", "Acción", "Detalle", "Usuario"]
            st.dataframe(ev, hide_index=True)
