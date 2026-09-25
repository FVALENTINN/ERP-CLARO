from datetime import timedelta

import pandas as pd
import streamlit as st

from core import db, servicios as sv
from core.auth import puede, usuario_actual
from core.utils import hoy, limpiar_serie, soles, soles0, to_excel, validar_documento
from modulos.dashboard import encabezado


def render():
    encabezado("💳 Ventas", "Registro de ventas al consumidor final, facturas de Claro y control de precio compra vs. venta")
    u = usuario_actual()
    tabs = st.tabs(["🧾 Registrar venta", "📋 Ventas registradas", "📑 Facturas de Claro", "🛵 Por motorizado"])

    # ================================================================ REGISTRAR
    with tabs[0]:
        if not puede("registrar_venta"):
            st.warning("Su rol no puede registrar ventas.")
        else:
            ultimo = st.session_state.pop("venta_ok", None)
            if ultimo:
                st.success(ultimo["msg"])
                if ultimo.get("alerta"):
                    st.warning(ultimo["alerta"])
            if st.session_state.pop("limpiar_v_serie", False):
                st.session_state.v_serie = ""
            serie_in = st.text_input("1️⃣ Escanee o digite el IMEI / ICCID del equipo vendido", key="v_serie")
            item = sv.buscar_serie(serie_in) if serie_in else None
            if serie_in and not item:
                st.error("❌ Este IMEI/ICCID no existe en el inventario. Verifique o regístrelo primero en Compras.")
            elif item and item["estado"] != "DISPONIBLE":
                st.error(f"❌ Este IMEI ya figura como **{item['estado']}** "
                         f"{'(vendido el ' + item['fecha_venta'].strftime('%d/%m/%Y') + ')' if item.get('fecha_venta') and not pd.isna(item['fecha_venta']) else ''}. "
                         "No se puede vender dos veces.")
            elif item:
                with st.container(border=True):
                    c = st.columns(5)
                    c[0].metric("Marca", item["marca"])
                    c[1].metric("Modelo", item["modelo"])
                    c[2].metric("Precio compra", soles0(item["precio_compra"]))
                    c[3].metric("Días en stock", item["dias_stock"])
                    c[4].metric("Alerta", item["alerta"])
                motorizados = db.q("SELECT DISTINCT motorizado FROM ventas WHERE motorizado IS NOT NULL "
                                   "AND motorizado<>'' ORDER BY motorizado")["motorizado"].tolist()
                with st.form("venta", clear_on_submit=True):
                    st.markdown("2️⃣ **Datos del cliente**")
                    c = st.columns([1, 1.3, 2.5, 1.2])
                    tipo_doc = c[0].selectbox("Tipo doc.", ["DNI", "CE", "RUC"])
                    nro_doc = c[1].text_input("N° documento")
                    cliente = c[2].text_input("Nombre / Razón social")
                    telefono = c[3].text_input("Teléfono / línea")
                    st.markdown("3️⃣ **Datos de la venta**")
                    c = st.columns(4)
                    fecha = c[0].date_input("Fecha de venta", hoy(), format="DD/MM/YYYY", max_value=hoy())
                    precio = c[1].number_input("Precio de venta (S/)", min_value=0.0, step=1.0,
                                               value=float(item["precio_compra"]))
                    bo = c[2].text_input("BO (Business Order)")
                    motorizado = c[3].selectbox("Motorizado", motorizados, index=None, accept_new_options=True,
                                                placeholder="Seleccione o escriba")
                    c = st.columns([1, 3])
                    comprobante = c[0].text_input("Comprobante (opcional)")
                    obs = c[1].text_input("Observación")
                    enviar = st.form_submit_button("💾 Registrar venta", type="primary")
                if enviar:
                    errores = []
                    ok, msg = validar_documento(tipo_doc, nro_doc)
                    if not ok:
                        errores.append(msg)
                    if not cliente.strip():
                        errores.append("Ingrese el nombre del cliente.")
                    if not bo.strip():
                        errores.append("Ingrese el BO.")
                    if not motorizado:
                        errores.append("Indique el motorizado.")
                    if fecha < item["fecha_compra"]:
                        errores.append("La fecha de venta no puede ser anterior a la fecha de compra.")
                    if bo.strip() and db.scalar("SELECT COUNT(*) FROM ventas WHERE bo=:b AND estado='ACTIVA'",
                                                {"b": bo.strip().upper()}):
                        errores.append(f"El BO {bo.strip().upper()} ya está registrado en otra venta.")
                    if errores:
                        for e in errores:
                            st.error(e)
                    else:
                        r = sv.registrar_venta({
                            "serie": item["serie"], "fecha_venta": fecha, "tipo_doc": tipo_doc,
                            "nro_doc": nro_doc.strip().upper(), "cliente": cliente.strip().upper(),
                            "telefono": telefono.strip(), "precio_venta": precio, "bo": bo.strip().upper(),
                            "motorizado": str(motorizado).strip().upper(), "comprobante": comprobante.strip().upper(),
                            "observacion": obs,
                        }, u["username"])
                        info = {"msg": f"✅ Venta #{r['venta_id']} registrada – IMEI {item['serie']}."}
                        if r["diferencia"] < 0:
                            info["alerta"] = (f"⚠️ Precio de venta menor al costo en {soles(abs(r['diferencia']))}. "
                                              f"Se creó el reclamo #{r['reclamo_id']}: Claro debe emitir la nota de crédito. "
                                              "Se hará seguimiento en *Gestión de Reclamo*.")
                        st.session_state.venta_ok = info
                        st.session_state.limpiar_v_serie = True
                        st.rerun()

    # ================================================================ LISTADO
    with tabs[1]:
        c = st.columns([1, 1, 1, 2])
        d1 = c[0].date_input("Desde", hoy() - timedelta(days=30), format="DD/MM/YYYY", key="lv1")
        d2 = c[1].date_input("Hasta", hoy(), format="DD/MM/YYYY", key="lv2")
        filtro = c[2].selectbox("Resultado", ["Todas", "Bajo costo (NC)", "Sobre costo", "Igual al costo"])
        texto = c[3].text_input("Buscar cliente / DNI / IMEI / BO / modelo")
        v = db.q("SELECT * FROM ventas WHERE fecha_venta BETWEEN :d AND :h ORDER BY id DESC", {"d": d1, "h": d2})
        if v.empty:
            st.info("Sin ventas en el periodo.")
        else:
            if filtro == "Bajo costo (NC)":
                v = v[v["diferencia"] < 0]
            elif filtro == "Sobre costo":
                v = v[v["diferencia"] > 0]
            elif filtro == "Igual al costo":
                v = v[v["diferencia"] == 0]
            if texto:
                t = texto.strip().upper()
                mask = pd.Series(False, index=v.index)
                for col in ["cliente", "nro_doc", "serie", "bo", "modelo"]:
                    mask |= v[col].fillna("").astype(str).str.upper().str.contains(t, regex=False)
                v = v[mask]
            act = v[v["estado"] == "ACTIVA"]
            m = st.columns(4)
            m[0].metric("Ventas activas", f"{len(act):,}")
            m[1].metric("Total vendido", soles0(act["precio_venta"].sum()))
            m[2].metric("Costo", soles0(act["precio_compra"].sum()))
            m[3].metric("Diferencia (venta − costo)", soles0(act["diferencia"].sum()))
            vista = v[["id", "fecha_venta", "estado", "tipo", "tipo_doc", "nro_doc", "cliente", "marca", "modelo",
                       "serie", "precio_compra", "precio_venta", "diferencia", "bo", "motorizado", "factura_claro",
                       "monto_factura_claro", "comprobante", "usuario"]]
            vista.columns = ["N°", "Fecha", "Estado", "Tipo", "Doc", "N° doc", "Cliente", "Marca", "Modelo",
                             "IMEI/ICCID", "P. compra", "P. venta", "Diferencia", "BO", "Motorizado",
                             "Fact. Claro", "Monto fact. Claro", "Comprobante", "Usuario"]
            money = st.column_config.NumberColumn(format="S/ %.2f")
            st.dataframe(vista, hide_index=True, column_config={
                "P. compra": money, "P. venta": money, "Diferencia": money, "Monto fact. Claro": money,
                "Fecha": st.column_config.DateColumn(format="DD/MM/YYYY")})
            st.download_button("⬇️ Descargar ventas", to_excel({"Ventas": vista}), f"ventas_{d1}_{d2}.xlsx")
            if puede("anular_venta"):
                with st.expander("Anular una venta"):
                    activas = v[v["estado"] == "ACTIVA"]
                    if activas.empty:
                        st.caption("No hay ventas activas en el filtro.")
                    else:
                        op = st.selectbox("Venta", activas["id"].tolist(), format_func=lambda i: (
                            f"#{i} – {activas.loc[activas['id'] == i, 'serie'].iloc[0]} – "
                            f"{activas.loc[activas['id'] == i, 'cliente'].iloc[0]}"))
                        motivo = st.text_input("Motivo de anulación")
                        if st.button("Anular venta", type="primary", disabled=not motivo.strip()):
                            sv.anular_venta(int(op), motivo, u["username"])
                            st.success("Venta anulada; el equipo volvió a DISPONIBLE.")
                            st.rerun()

    # ================================================================ FACTURAS CLARO
    with tabs[2]:
        st.caption("Al ser consignación, Claro emite su factura **después** de la venta. Registre la factura para "
                   "conciliar: si el monto facturado es mayor al precio de venta, el sistema actualiza el monto de NC "
                   "a reclamar.")
        pend = db.q("SELECT id, fecha_venta, marca, modelo, serie, precio_compra, precio_venta, bo FROM ventas "
                    "WHERE estado='ACTIVA' AND (factura_claro IS NULL OR factura_claro='') ORDER BY fecha_venta")
        st.metric("Ventas sin factura de Claro registrada", f"{len(pend):,}")
        if not pend.empty:
            with st.expander("Ver ventas pendientes de factura Claro"):
                st.dataframe(pend, hide_index=True)
                st.download_button("⬇️ Descargar pendientes", to_excel({"Pendientes": pend}), "pendientes_factura_claro.xlsx")
        c1, c2 = st.columns(2)
        with c1, st.form("fact_ind"):
            st.markdown("**Registro individual**")
            s = st.text_input("IMEI / ICCID")
            nro = st.text_input("N° factura Claro")
            monto = st.number_input("Monto facturado por la unidad (S/)", min_value=0.0, step=1.0)
            f = st.date_input("Fecha factura", hoy(), format="DD/MM/YYYY")
            if st.form_submit_button("Registrar factura", type="primary"):
                r = sv.registrar_factura_claro(s, nro.strip().upper(), monto, f, u["username"])
                (st.success if r == "OK" else st.error)("Factura registrada." if r == "OK" else r)
        with c2:
            st.markdown("**Carga masiva (Excel)**")
            st.caption("Columnas: IMEI, N_FACTURA, MONTO, FECHA")
            plantilla = pd.DataFrame({"IMEI": ["356938035643809"], "N_FACTURA": ["F001-00012345"],
                                      "MONTO": [599.0], "FECHA": [hoy().strftime("%d/%m/%Y")]})
            st.download_button("⬇️ Plantilla", to_excel({"Facturas": plantilla}), "plantilla_facturas_claro.xlsx")
            arch = st.file_uploader("Excel de facturas", type=["xlsx", "csv"], key="fc_up")
            if arch and st.button("Procesar facturas"):
                df = pd.read_csv(arch, dtype=str) if arch.name.endswith(".csv") else pd.read_excel(arch, dtype=str)
                df.columns = [c.strip().upper() for c in df.columns]
                res = []
                for _, r in df.iterrows():
                    fecha = pd.to_datetime(r.get("FECHA"), dayfirst=True, errors="coerce")
                    estado = sv.registrar_factura_claro(
                        limpiar_serie(r.get("IMEI")), str(r.get("N_FACTURA", "")).strip().upper(),
                        float(pd.to_numeric(r.get("MONTO"), errors="coerce") or 0),
                        fecha.date() if not pd.isna(fecha) else hoy(), u["username"])
                    res.append(estado)
                df["RESULTADO"] = res
                st.success(f"Procesadas {sum(x == 'OK' for x in res)} de {len(res)} facturas.")
                st.dataframe(df, hide_index=True)

    # ================================================================ MOTORIZADO
    with tabs[3]:
        c = st.columns(3)
        m1 = c[0].date_input("Desde", hoy().replace(day=1), format="DD/MM/YYYY", key="mo1")
        m2 = c[1].date_input("Hasta", hoy(), format="DD/MM/YYYY", key="mo2")
        mv = db.q("SELECT motorizado, tipo, precio_venta, diferencia FROM ventas WHERE estado='ACTIVA' "
                  "AND fecha_venta BETWEEN :d AND :h", {"d": m1, "h": m2})
        if mv.empty:
            st.info("Sin ventas.")
        else:
            r = mv.groupby("motorizado").agg(
                Entregas=("tipo", "size"), Equipos=("tipo", lambda s: (s == "EQUIPO").sum()),
                SIM=("tipo", lambda s: (s == "SIM").sum()), Monto=("precio_venta", "sum"),
                Bajo_costo=("diferencia", lambda s: (s < 0).sum())).reset_index().sort_values("Entregas", ascending=False)
            r.columns = ["Motorizado", "Entregas", "Equipos", "SIM", "Monto vendido", "Ventas bajo costo"]
            st.dataframe(r, hide_index=True, column_config={
                "Monto vendido": st.column_config.NumberColumn(format="S/ %.2f")})
            st.download_button("⬇️ Descargar", to_excel({"Motorizados": r}), "ventas_motorizado.xlsx")
