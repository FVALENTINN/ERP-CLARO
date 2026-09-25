from datetime import timedelta

import pandas as pd
import streamlit as st

from core import db, servicios as sv
from core.auth import puede, usuario_actual
from core.utils import hoy, limpiar_serie, soles0, to_excel, validar_serie
from modulos.dashboard import encabezado

COLS_STOCK = {
    "tipo": "Tipo", "marca": "Marca", "modelo": "Modelo", "serie": "IMEI / ICCID",
    "precio_compra": "Precio compra", "nro_factura": "N° factura/guía", "fecha_compra": "Fecha compra",
    "dias_stock": "Días en stock", "fecha_limite": "Fecha límite", "dias_restantes": "Días restantes",
    "alerta": "Alerta", "estado": "Estado", "fecha_venta": "Fecha salida", "modalidad": "Modalidad",
}


def _tabla(df, cols=None, key=None):
    cols = cols or list(COLS_STOCK.keys())
    cols = [c for c in cols if c in df.columns]
    vista = df[cols].rename(columns=COLS_STOCK)
    st.dataframe(vista, hide_index=True, key=key, column_config={
        "Precio compra": st.column_config.NumberColumn(format="S/ %.2f"),
        "Fecha compra": st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Fecha límite": st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Fecha salida": st.column_config.DateColumn(format="DD/MM/YYYY"),
    })
    return vista


def render():
    encabezado("📦 Inventarios", "Stock por modelo e IMEI, alertas de vencimiento, control de IMEI, kardex y rotación")
    cfg = db.get_config()
    inv = sv.inventario_df()
    if st.session_state.pop("inv_tab_alerta", False):
        st.info("👉 Abra la pestaña **🚨 Alertas de vencimiento**.")

    tabs = st.tabs(["📋 Stock", "🚨 Alertas de vencimiento", "🔎 Control de IMEI", "📒 Kardex",
                    "🔄 Rotación", "🛠️ Ajustes"])

    # ================================================================ STOCK
    with tabs[0]:
        if inv.empty:
            st.info("No hay inventario. Registre ingresos en el módulo **Compras**.")
        else:
            f = st.columns([1, 1, 1.4, 1, 1.4])
            tipo = f[0].selectbox("Tipo", ["Todos", "EQUIPO", "SIM"])
            estado = f[1].selectbox("Estado", ["DISPONIBLE", "Todos", "VENDIDO", "DEVUELTO", "BAJA"])
            marcas = sorted(inv["marca"].dropna().unique())
            marca = f[2].multiselect("Marca", marcas, placeholder="Todas")
            alerta = f[3].selectbox("Alerta", ["Todas", "🟢 EN PLAZO", "🟠 POR VENCER", "🔴 VENCIDO"])
            texto = f[4].text_input("Buscar modelo / IMEI / factura")
            d = inv.copy()
            if tipo != "Todos":
                d = d[d["tipo"] == tipo]
            if estado != "Todos":
                d = d[d["estado"] == estado]
            if marca:
                d = d[d["marca"].isin(marca)]
            if alerta != "Todas":
                d = d[d["alerta"] == alerta]
            if texto:
                t = texto.strip().upper()
                d = d[d["modelo"].str.upper().str.contains(t, na=False, regex=False)
                      | d["serie"].str.contains(t, na=False, regex=False)
                      | d["nro_factura"].fillna("").str.upper().str.contains(t, regex=False)]

            vista_modelo = st.toggle("Ver resumen por modelo", value=True)
            if vista_modelo:
                r = d.groupby(["tipo", "marca", "modelo"]).agg(
                    Unidades=("serie", "size"), Valor=("precio_compra", "sum"),
                    Precio_prom=("precio_compra", "mean"), Dias_max=("dias_stock", "max"),
                    Por_vencer=("alerta", lambda s: (s == "🟠 POR VENCER").sum()),
                    Vencidos=("alerta", lambda s: (s == "🔴 VENCIDO").sum()),
                ).reset_index().sort_values("Unidades", ascending=False)
                r.columns = ["Tipo", "Marca", "Modelo", "Unidades", "Valor costo", "Precio prom.",
                             "Días máx.", "Por vencer", "Vencidos"]
                st.dataframe(r, hide_index=True, column_config={
                    "Valor costo": st.column_config.NumberColumn(format="S/ %.2f"),
                    "Precio prom.": st.column_config.NumberColumn(format="S/ %.2f")})
            c = st.columns(3)
            c[0].metric("Unidades filtradas", f"{len(d):,}")
            c[1].metric("Valor a costo", soles0(d["precio_compra"].sum()))
            c[2].metric("Modelos distintos", d["modelo"].nunique())
            st.markdown("**Detalle por IMEI / ICCID**")
            vista = _tabla(d.sort_values("dias_stock", ascending=False))
            st.download_button("⬇️ Descargar Excel", to_excel({"Inventario": vista}),
                               f"inventario_{hoy():%Y%m%d}.xlsx")

    # ================================================================ ALERTAS
    with tabs[1]:
        st.caption(f"Regla: los equipos en consignación deben venderse antes de **{cfg['dias_limite_venta']} días** "
                   f"desde la fecha de compra. Alerta **{cfg['dias_alerta']} días antes**.")
        if inv.empty:
            st.info("Sin inventario.")
        else:
            disp = inv[inv["estado"] == "DISPONIBLE"]
            venc = disp[disp["alerta"] == "🔴 VENCIDO"].sort_values("dias_restantes")
            porv = disp[disp["alerta"] == "🟠 POR VENCER"].sort_values("dias_restantes")
            c = st.columns(4)
            c[0].metric("🔴 Vencidos", f"{len(venc):,}")
            c[1].metric("Valor vencido", soles0(venc["precio_compra"].sum()))
            c[2].metric("🟠 Por vencer", f"{len(porv):,}")
            c[3].metric("Valor por vencer", soles0(porv["precio_compra"].sum()))
            cols = ["alerta", "dias_restantes", "fecha_limite", "tipo", "marca", "modelo", "serie",
                    "precio_compra", "fecha_compra", "dias_stock", "nro_factura"]
            st.markdown("##### 🔴 Vencidos")
            if len(venc):
                _tabla(venc, cols, key="t_venc")
            else:
                st.success("Sin equipos vencidos.")
            st.markdown(f"##### 🟠 Vencen en los próximos {cfg['dias_alerta']} días")
            if len(porv):
                _tabla(porv, cols, key="t_porv")
            else:
                st.success("Sin equipos por vencer.")
            if len(venc) or len(porv):
                hojas = {}
                if len(venc):
                    hojas["Vencidos"] = venc[cols].rename(columns=COLS_STOCK)
                if len(porv):
                    hojas["Por vencer"] = porv[cols].rename(columns=COLS_STOCK)
                st.download_button("⬇️ Descargar alertas (Excel)", to_excel(hojas), f"alertas_{hoy():%Y%m%d}.xlsx")
            st.markdown("##### Calendario de vencimientos (próximos 60 días)")
            prox = disp[(disp["dias_restantes"] >= 0) & (disp["dias_restantes"] <= 60)]
            if len(prox):
                cal = prox.groupby("fecha_limite").agg(Unidades=("serie", "size"),
                                                       Valor=("precio_compra", "sum")).reset_index()
                cal.columns = ["Fecha límite", "Unidades", "Valor"]
                st.bar_chart(cal, x="Fecha límite", y="Unidades", color="#DA291C")
            else:
                st.caption("Sin vencimientos en los próximos 60 días.")

    # ================================================================ CONTROL IMEI
    with tabs[2]:
        st.markdown("##### Trazabilidad de un IMEI / ICCID")
        s = st.text_input("Escanee o digite el IMEI / ICCID", key="traza")
        if s:
            serie = limpiar_serie(s)
            ok_i, msg_i = validar_serie("EQUIPO" if len(serie) == 15 else "SIM", serie)
            (st.success if ok_i else st.warning)(f"Validación de formato: {msg_i}")
            item = sv.buscar_serie(serie)
            if not item:
                st.error("❌ El IMEI/ICCID **no existe** en el inventario. Puede ser un equipo no ingresado "
                         "o de otro distribuidor.")
            else:
                c = st.columns(4)
                c[0].metric("Estado", item["estado"])
                c[1].metric("Marca", item["marca"])
                c[2].metric("Precio compra", soles0(item["precio_compra"]))
                c[3].metric("Días en stock", item["dias_stock"])
                st.write(f"**Modelo:** {item['modelo']} · **Tipo:** {item['tipo']}")
                st.write(f"**Ingreso:** {item['fecha_compra']:%d/%m/%Y} · Factura/guía {item['nro_factura']} · "
                         f"Lote #{item['lote_id']} · {item['modalidad']} · registrado por {item['creado_por']}")
                if item["estado"] == "DISPONIBLE":
                    st.write(f"**Fecha límite de venta:** {item['fecha_limite']:%d/%m/%Y} – {item['alerta']}")
                ven = db.q("SELECT * FROM ventas WHERE serie=:s ORDER BY id", {"s": serie})
                if not ven.empty:
                    st.markdown("**Ventas**")
                    st.dataframe(ven[["id", "fecha_venta", "estado", "tipo_doc", "nro_doc", "cliente", "precio_compra",
                                      "precio_venta", "diferencia", "bo", "motorizado", "factura_claro"]],
                                 hide_index=True)
                rc = db.q("SELECT id, estado, monto_esperado, monto_nc, nro_nc, fecha_reclamo FROM reclamos "
                          "WHERE serie=:s", {"s": serie})
                if not rc.empty:
                    st.markdown("**Reclamos / NC**")
                    st.dataframe(rc, hide_index=True)

        st.divider()
        st.markdown("##### Verificación masiva de IMEI")
        st.caption("Pegue una lista de IMEI/ICCID (uno por línea) para detectar: inexistentes, duplicados, "
                   "formato inválido y su estado actual. Útil para auditorías físicas de almacén.")
        lista = st.text_area("Lista de IMEI", height=150, key="lista_imei")
        if st.button("Verificar lista") and lista.strip():
            series = [limpiar_serie(x) for x in lista.splitlines() if x.strip()]
            dfv = pd.DataFrame({"serie": series})
            dfv["duplicado_en_lista"] = dfv["serie"].duplicated(keep=False)
            dfv["formato"] = dfv["serie"].map(
                lambda x: validar_serie("EQUIPO" if len(x) == 15 else "SIM", x)[1])
            base = inv[["serie", "tipo", "marca", "modelo", "estado", "alerta", "fecha_compra"]] if not inv.empty \
                else pd.DataFrame(columns=["serie"])
            dfv = dfv.merge(base, on="serie", how="left")
            dfv["estado"] = dfv["estado"].fillna("❌ NO EXISTE")
            c = st.columns(4)
            c[0].metric("Total leídos", len(dfv))
            c[1].metric("Disponibles", int((dfv["estado"] == "DISPONIBLE").sum()))
            c[2].metric("No existen", int((dfv["estado"] == "❌ NO EXISTE").sum()))
            c[3].metric("Duplicados", int(dfv["duplicado_en_lista"].sum()))
            st.dataframe(dfv, hide_index=True)
            if not inv.empty:
                faltantes = inv[(inv["estado"] == "DISPONIBLE") & ~inv["serie"].isin(series)]
                with st.expander(f"Disponibles en sistema que NO están en la lista ({len(faltantes)}) – posibles faltantes"):
                    _tabla(faltantes, ["tipo", "marca", "modelo", "serie", "fecha_compra", "dias_stock"], key="falt")
            st.download_button("⬇️ Descargar verificación", to_excel({"Verificacion": dfv}), "verificacion_imei.xlsx")

    # ================================================================ KARDEX
    with tabs[3]:
        c = st.columns(3)
        d1 = c[0].date_input("Desde", hoy().replace(day=1), format="DD/MM/YYYY", key="k1")
        d2 = c[1].date_input("Hasta", hoy(), format="DD/MM/YYYY", key="k2")
        k = sv.kardex_df(d1, d2)
        if k.empty:
            st.info("Sin movimientos.")
        else:
            k.columns = ["Tipo", "Marca", "Modelo", "Saldo inicial", "Ingresos", "Salidas", "Saldo final",
                         "Valor saldo final"]
            tot = k[["Saldo inicial", "Ingresos", "Salidas", "Saldo final", "Valor saldo final"]].sum()
            m = st.columns(5)
            for i, col in enumerate(tot.index):
                m[i].metric(col, soles0(tot[col]) if "Valor" in col else f"{int(tot[col]):,}")
            st.dataframe(k, hide_index=True, column_config={
                "Valor saldo final": st.column_config.NumberColumn(format="S/ %.2f")})
            st.download_button("⬇️ Descargar kardex", to_excel({"Kardex": k}), f"kardex_{d1}_{d2}.xlsx")

    # ================================================================ ROTACIÓN
    with tabs[4]:
        c = st.columns(3)
        r1 = c[0].date_input("Desde", hoy() - timedelta(days=89), format="DD/MM/YYYY", key="r1")
        r2 = c[1].date_input("Hasta", hoy(), format="DD/MM/YYYY", key="r2")
        tipo_r = c[2].selectbox("Tipo", ["EQUIPO", "SIM", "Todos"], key="rt")
        rot = sv.rotacion_df(r1, r2)
        if tipo_r != "Todos":
            rot = rot[rot["tipo"] == tipo_r]
        if rot.empty:
            st.info("Sin datos para el periodo.")
        else:
            rot = rot.rename(columns={
                "tipo": "Tipo", "marca": "Marca", "modelo": "Modelo", "unidades_vendidas": "Vendidas",
                "stock_actual": "Stock actual", "dias_prom_venta": "Días prom. para vender",
                "venta_diaria": "Venta diaria", "dias_cobertura": "Días de cobertura",
                "indice_rotacion_%": "Índice rotación %", "rotacion": "Rotación"})
            st.caption("Índice de rotación = vendidas / (vendidas + stock actual). "
                       "Días de cobertura = stock actual / venta diaria promedio.")
            st.dataframe(rot, hide_index=True, column_config={
                "Índice rotación %": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)})
            st.download_button("⬇️ Descargar reporte de rotación", to_excel({"Rotacion": rot}),
                               f"rotacion_{r1}_{r2}.xlsx")

    # ================================================================ AJUSTES
    with tabs[5]:
        if not puede("editar_inventario"):
            st.warning("Su rol no tiene permiso para ajustar inventario.")
        else:
            st.markdown("##### Cambiar estado (devolución a Claro / baja) o corregir datos")
            s2 = st.text_input("IMEI / ICCID", key="aj_serie")
            if s2:
                item = sv.buscar_serie(s2)
                if not item:
                    st.error("No existe.")
                elif item["estado"] == "VENDIDO":
                    st.warning("Equipo vendido: para revertirlo anule la venta en el módulo Ventas.")
                else:
                    with st.form("ajuste"):
                        c = st.columns(3)
                        nuevo = c[0].selectbox("Estado", ["DISPONIBLE", "DEVUELTO", "BAJA"],
                                               index=["DISPONIBLE", "DEVUELTO", "BAJA"].index(item["estado"]))
                        precio = c[1].number_input("Precio compra", value=float(item["precio_compra"]), min_value=0.0,
                                                   step=1.0)
                        fecha = c[2].date_input("Fecha del movimiento", hoy(), format="DD/MM/YYYY")
                        c2 = st.columns(2)
                        modelo = c2[0].text_input("Modelo", item["modelo"])
                        marca = c2[1].text_input("Marca", item["marca"])
                        obs = st.text_input("Motivo / observación (obligatorio)")
                        if st.form_submit_button("Guardar ajuste", type="primary"):
                            if not obs.strip():
                                st.error("Indique el motivo del ajuste.")
                            else:
                                db.execute("""UPDATE inventario SET estado=:e, precio_compra=:p, modelo=:mo, marca=:ma,
                                              fecha_venta=:f, observacion=:o WHERE id=:i""",
                                           {"e": nuevo, "p": precio, "mo": modelo.upper(), "ma": marca.upper(),
                                            "f": None if nuevo == "DISPONIBLE" else fecha, "o": obs,
                                            "i": int(item["id"])})
                                db.log(usuario_actual()["username"], "Inventarios", "Ajuste",
                                       f"{item['serie']}: {item['estado']}→{nuevo}, precio {item['precio_compra']}→{precio}. {obs}")
                                st.success("Ajuste guardado.")
