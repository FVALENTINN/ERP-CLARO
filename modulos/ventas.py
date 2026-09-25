from datetime import timedelta

import pandas as pd
import streamlit as st

from core import db, servicios as sv
from core.auth import puede, usuario_actual
from core.utils import hoy, limpiar_serie, parse_fecha, soles, soles0, to_excel, validar_documento
from modulos.dashboard import encabezado


MODALIDADES = ["PORTABILIDAD", "ALTA NUEVA", "RENOVACIÓN", "CAMBIO DE EQUIPO", "PREPAGO", "POSTPAGO"]


def _ddmm(df):
    """Muestra la columna FECHA como DD/MM/AAAA."""
    v = df.copy()
    if "FECHA" in v.columns:
        v["FECHA"] = v["FECHA"].map(lambda d: d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else "")
    return v


def importar_ventas(u):
    if not puede("registrar_venta"):
        st.warning("Su rol no puede registrar ventas.")
        return
    msg = st.session_state.pop("impv_ok", None)
    if msg:
        st.success(msg)
    c = st.columns([2, 1])
    c[0].markdown("Estructura del Excel: **CLIENTE – DNI/CE/RUC – MODELO – IMEI – PRECIO – FECHA – MODALIDAD – "
                  "CONTADO/CUOTAS – #CUOTAS**. Opcionales: I. COBRADO, BO y MOTORIZADO.")
    c[1].download_button("⬇️ Descargar plantilla", sv.plantilla_ventas(), "plantilla_ventas.xlsx", width="stretch")
    with st.form("impv_form"):
        archivo = st.file_uploader("Archivo Excel (.xlsx) o CSV con las ventas", type=["xlsx", "xls", "csv"])
        validar = st.form_submit_button("1️⃣ Validar archivo", type="primary")
    if validar and archivo:
        try:
            raw = (pd.read_csv(archivo, dtype=str, sep=None, engine="python") if archivo.name.lower().endswith(".csv")
                   else pd.read_excel(archivo, dtype=str))
            with st.spinner(f"Validando {len(raw):,} ventas..."):
                st.session_state.impv = {"res": sv.validar_ventas_masivo(raw), "archivo": archivo.name}
        except Exception as e:
            st.error(f"No se pudo procesar el archivo: {e}")
            st.session_state.pop("impv", None)
    imp = st.session_state.get("impv")
    if not imp:
        return
    res = imp["res"]
    ok = res[res["RESULTADO"] == "OK"]
    err = res[res["RESULTADO"] == "ERROR"]
    bajo = ok[ok["PRECIO"] < ok["_precio_compra"]]
    visibles = ["CLIENTE", "TIPO_DOC", "DOCUMENTO", "MODELO", "IMEI", "PRECIO", "FECHA", "MODALIDAD", "FORMA_PAGO",
                "N_CUOTAS", "I_COBRADO", "BO", "MOTORIZADO", "RESULTADO", "MOTIVO", "OBSERVACION"]
    st.markdown(f"##### Resultado de validación – {imp['archivo']}")
    m = st.columns(4)
    m[0].metric("Ventas leídas", f"{len(res):,}")
    m[1].metric("✅ Válidas", f"{len(ok):,}")
    m[2].metric("❌ Con error", f"{len(err):,}")
    m[3].metric("Bajo costo (generan NC)", f"{len(bajo):,}")
    if len(err):
        st.error("Hay ventas con error. Solo se registrarán las válidas.")
        cols_err = ["IMEI", "MOTIVO"] + [c for c in visibles if c not in ("IMEI", "MOTIVO", "RESULTADO", "OBSERVACION")]
        st.dataframe(_ddmm(err[cols_err]), hide_index=True, height=240)
        st.download_button("⬇️ Descargar errores", to_excel({"Errores": _ddmm(err[visibles])}), "errores_ventas.xlsx")
    if len(ok):
        with st.expander(f"Ver ventas válidas ({len(ok):,})"):
            st.dataframe(_ddmm(ok[visibles]), hide_index=True, column_config={
                "PRECIO": st.column_config.NumberColumn(format="S/ %.2f")})
        b = st.columns([1, 1, 3])
        if b[0].button(f"2️⃣ Registrar {len(ok):,} ventas", type="primary"):
            with st.spinner("Registrando ventas..."):
                r = sv.registrar_ventas_masivo(ok, u["username"])
            st.session_state.pop("impv")
            extra = (f" Se crearon {r['reclamos']} reclamos de NC por {soles(r['monto_nc'])}."
                     if r["reclamos"] else "")
            st.session_state.impv_ok = f"✅ {r['ventas']:,} ventas registradas.{extra}"
            st.rerun()
        if b[1].button("Cancelar", key="impv_cancel"):
            st.session_state.pop("impv")
            st.rerun()


def render():
    encabezado("💳 Ventas", "Registro de ventas al consumidor final, facturas de Claro y control de precio compra vs. venta")
    u = usuario_actual()
    tabs = st.tabs(["🧾 Registrar venta", "📥 Importar ventas (Excel)", "📋 Ventas registradas",
                    "📑 Facturas de Claro", "🛵 Por motorizado"])

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
                    c = st.columns(4)
                    modalidad = c[0].selectbox("Modalidad", MODALIDADES, index=None, accept_new_options=True,
                                               placeholder="Seleccione o escriba")
                    forma_pago = c[1].selectbox("Contado / Cuotas", ["CONTADO", "CUOTAS"])
                    nro_cuotas = c[2].number_input("N° de cuotas", min_value=0, max_value=60, step=1, value=0,
                                                   help="0 si es al contado")
                    cobrado = c[3].number_input("I. cobrado (S/)", min_value=0.0, step=1.0,
                                                value=float(item["precio_compra"]),
                                                help="Importe que se cobró al cliente por el equipo")
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
                    if not modalidad:
                        errores.append("Indique la modalidad de la venta.")
                    if forma_pago == "CUOTAS" and nro_cuotas < 1:
                        errores.append("Indique el número de cuotas.")
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
                            "observacion": obs, "modalidad": str(modalidad).strip().upper(),
                            "forma_pago": forma_pago, "nro_cuotas": int(nro_cuotas) if forma_pago == "CUOTAS" else 0,
                            "importe_cobrado": cobrado,
                        }, u["username"])
                        info = {"msg": f"✅ Venta #{r['venta_id']} registrada – IMEI {item['serie']}."}
                        if r["diferencia"] < 0:
                            info["alerta"] = (f"⚠️ Precio de venta menor al costo en {soles(abs(r['diferencia']))}. "
                                              f"Se creó el reclamo #{r['reclamo_id']}: Claro debe emitir la nota de crédito. "
                                              "Se hará seguimiento en *Gestión de Reclamo*.")
                        st.session_state.venta_ok = info
                        st.session_state.limpiar_v_serie = True
                        st.rerun()

    # ================================================================ IMPORTAR
    with tabs[1]:
        importar_ventas(u)

    # ================================================================ LISTADO
    with tabs[2]:
        c = st.columns([1, 1, 1, 2])
        d1 = c[0].date_input("Desde", hoy() - timedelta(days=30), format="DD/MM/YYYY", key="lv1")
        d2 = c[1].date_input("Hasta", hoy(), format="DD/MM/YYYY", key="lv2")
        filtro = c[2].selectbox("Resultado", ["Todas", "Bajo costo (NC)", "Sobre costo", "Igual al costo"])
        texto = c[3].text_input("Buscar cliente / DNI / IMEI / BO / modelo")
        v = db.q("""SELECT v.*, i.categoria FROM ventas v LEFT JOIN inventario i ON i.id = v.item_id
                    WHERE v.fecha_venta BETWEEN :d AND :h ORDER BY v.id DESC""", {"d": d1, "h": d2})
        if not v.empty:
            v["categoria"] = v["categoria"].map({**sv.CATEGORIAS, "SIM": "SIM card"}).fillna("Equipos móviles")
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
            m = st.columns(5)
            m[0].metric("Ventas activas", f"{len(act):,}")
            m[1].metric("Total vendido", soles0(act["precio_venta"].sum()))
            m[2].metric("I. cobrado", soles0(pd.to_numeric(act["importe_cobrado"], errors="coerce").sum()))
            m[3].metric("Costo", soles0(act["precio_compra"].sum()))
            m[4].metric("Diferencia (venta − costo)", soles0(act["diferencia"].sum()))
            vista = v[["id", "fecha_venta", "estado", "categoria", "tipo_doc", "nro_doc", "cliente", "marca", "modelo",
                       "serie", "precio_compra", "precio_venta", "importe_cobrado", "diferencia", "modalidad", "forma_pago",
                       "nro_cuotas", "bo", "motorizado", "factura_claro",
                       "monto_factura_claro", "comprobante", "usuario"]]
            vista.columns = ["N°", "Fecha", "Estado", "Categoría", "Doc", "N° doc", "Cliente", "Marca", "Modelo",
                             "IMEI/ICCID", "P. compra", "P. venta", "I. cobrado", "Diferencia", "Modalidad", "Contado/Cuotas",
                             "N° cuotas", "BO", "Motorizado",
                             "Fact. Claro", "Monto fact. Claro", "Comprobante", "Usuario"]
            money = st.column_config.NumberColumn(format="S/ %.2f")
            st.dataframe(vista, hide_index=True, column_config={
                "P. compra": money, "P. venta": money, "I. cobrado": money, "Diferencia": money,
                "Monto fact. Claro": money,
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
    with tabs[3]:
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
                    fecha = parse_fecha(r.get("FECHA"))
                    estado = sv.registrar_factura_claro(
                        limpiar_serie(r.get("IMEI")), str(r.get("N_FACTURA", "")).strip().upper(),
                        float(pd.to_numeric(r.get("MONTO"), errors="coerce") or 0),
                        fecha or hoy(), u["username"])
                    res.append(estado)
                df["RESULTADO"] = res
                st.success(f"Procesadas {sum(x == 'OK' for x in res)} de {len(res)} facturas.")
                st.dataframe(df, hide_index=True)

    # ================================================================ MOTORIZADO
    with tabs[4]:
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
