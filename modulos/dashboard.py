from datetime import timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from core import db, servicios as sv
from core.utils import hoy, soles, soles0

ROJO = "#DA291C"
PALETA = ["#DA291C", "#1F4E79", "#F2A541", "#3B8EA5", "#7A7A7A", "#6A994E", "#9C6ADE", "#E07A5F"]


def encabezado(titulo, sub):
    st.markdown(f"<div class='titulo-modulo'>{titulo}</div><div class='sub-modulo'>{sub}</div>",
                unsafe_allow_html=True)


def render():
    encabezado("📊 Dashboard", f"Resumen al {hoy():%d/%m/%Y}")
    cfg = db.get_config()
    inv = sv.inventario_df()
    disp = inv[inv["estado"] == "DISPONIBLE"] if not inv.empty else inv
    ventas = db.q("SELECT * FROM ventas WHERE estado='ACTIVA'")
    rec = sv.reclamos_df()

    hoy_ts = pd.Timestamp(hoy())
    ini_mes = hoy_ts.replace(day=1)
    if not ventas.empty:
        ventas["fecha_venta"] = pd.to_datetime(ventas["fecha_venta"])
    ventas_mes = ventas[ventas["fecha_venta"] >= ini_mes] if not ventas.empty else ventas

    eq = disp[disp["tipo"] == "EQUIPO"] if not disp.empty else disp
    sim = disp[disp["tipo"] == "SIM"] if not disp.empty else disp
    por_vencer = disp[disp["alerta"] == "🟠 POR VENCER"] if not disp.empty else disp
    vencidos = disp[disp["alerta"] == "🔴 VENCIDO"] if not disp.empty else disp
    abiertos = rec[~rec["estado"].isin(["NC RECIBIDA", "CERRADO", "ANULADO"])] if not rec.empty else rec
    para_reclamar = abiertos[abiertos["accion_sugerida"] == "📧 RECLAMAR"] if not abiertos.empty else abiertos

    c = st.columns(4)
    c[0].metric("Equipos en stock", f"{len(eq):,}", help="Equipos DISPONIBLES (consignación)")
    c[1].metric("SIM card en stock", f"{len(sim):,}")
    c[2].metric("Valor inventario (costo)", soles0(disp["precio_compra"].sum() if not disp.empty else 0))
    c[3].metric("Ventas del mes (und.)", f"{len(ventas_mes):,}",
                help=f"Desde {ini_mes:%d/%m/%Y}")
    c = st.columns(4)
    c[0].metric(f"🟠 Por vencer (≤{cfg['dias_alerta']} días)", f"{len(por_vencer):,}",
                help=f"Equipos que cumplen {cfg['dias_limite_venta']} días en los próximos {cfg['dias_alerta']} días")
    c[1].metric(f"🔴 Vencidos (>{cfg['dias_limite_venta']} días)", f"{len(vencidos):,}")
    c[2].metric("NC pendientes de Claro", soles0(abiertos["saldo"].sum() if not abiertos.empty else 0),
                help=f"{len(abiertos)} reclamos abiertos")
    c[3].metric("📧 Listos para reclamar", f"{len(para_reclamar):,}",
                help=f"Sin NC después de {cfg['dias_espera_nc']} días de la venta")

    # ------------------------------------------------ alertas
    if len(vencidos) or len(por_vencer) or len(para_reclamar):
        with st.container(border=True):
            st.markdown("#### 🚨 Alertas")
            if len(vencidos):
                st.error(f"**{len(vencidos)} equipo(s) superaron los {cfg['dias_limite_venta']} días** sin venderse "
                         f"(valor {soles(vencidos['precio_compra'].sum())}). Revise devolución o gestión con Claro.")
            if len(por_vencer):
                prox = por_vencer.sort_values("dias_restantes").iloc[0]
                st.warning(f"**{len(por_vencer)} equipo(s) vencen en los próximos {cfg['dias_alerta']} días** "
                           f"(valor {soles(por_vencer['precio_compra'].sum())}). "
                           f"El más próximo: {prox['marca']} {prox['modelo']} IMEI {prox['serie']} "
                           f"– vence el {prox['fecha_limite']:%d/%m/%Y}.")
            if len(para_reclamar):
                st.info(f"**{len(para_reclamar)} venta(s) con pérdida sin nota de crédito** por "
                        f"{soles(para_reclamar['saldo'].sum())}. Genere el correo en *Gestión de Reclamo*.")
            b1, b2, _ = st.columns([1, 1, 3])
            if b1.button("Ver alertas de inventario"):
                st.session_state.ir_a = "Inventarios"
                st.session_state.inv_tab_alerta = True
                st.rerun()
            if b2.button("Ir a reclamos"):
                st.session_state.ir_a = "Gestión de Reclamo"
                st.rerun()

    if inv.empty:
        st.info("Aún no hay inventario registrado. Empiece en **Compras** importando su Excel de IMEI.")
        return

    # ------------------------------------------------ gráficos
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("##### Antigüedad del stock de equipos")
        if not eq.empty:
            lim = int(cfg["dias_limite_venta"])
            bins = [-1, 30, 60, lim - int(cfg["dias_alerta"]), lim, 10_000]
            labels = ["0-30", "31-60", f"61-{lim - int(cfg['dias_alerta'])}",
                      f"{lim - int(cfg['dias_alerta']) + 1}-{lim}", f">{lim}"]
            tramo = pd.cut(eq["dias_stock"], bins=bins, labels=labels)
            a = tramo.value_counts().reindex(labels).fillna(0).reset_index()
            a.columns = ["Días en stock", "Equipos"]
            fig = px.bar(a, x="Días en stock", y="Equipos", text="Equipos", color="Días en stock",
                         color_discrete_sequence=["#6A994E", "#A7C957", "#F2E8CF", "#F2A541", ROJO])
            fig.update_layout(showlegend=False, height=320, margin=dict(t=10, b=10))
            st.plotly_chart(fig, width="stretch")
        else:
            st.caption("Sin equipos en stock.")
    with g2:
        st.markdown("##### Stock disponible por marca")
        if not disp.empty:
            m = disp[disp["tipo"] == "EQUIPO"].groupby("marca").size().reset_index(name="Unidades")
            if not m.empty:
                fig = px.pie(m, names="marca", values="Unidades", hole=.5, color_discrete_sequence=PALETA)
                fig.update_layout(height=320, margin=dict(t=10, b=10))
                st.plotly_chart(fig, width="stretch")

    g3, g4 = st.columns(2)
    with g3:
        st.markdown("##### Ventas de los últimos 30 días")
        if not ventas.empty:
            v = ventas[ventas["fecha_venta"] >= hoy_ts - pd.Timedelta(days=29)]
            if not v.empty:
                d = v.groupby([v["fecha_venta"].dt.date, "tipo"]).size().reset_index(name="Unidades")
                d.columns = ["Fecha", "Tipo", "Unidades"]
                fig = px.bar(d, x="Fecha", y="Unidades", color="Tipo", color_discrete_sequence=[ROJO, "#1F4E79"])
                fig.update_layout(height=320, margin=dict(t=10, b=10), legend_title=None)
                st.plotly_chart(fig, width="stretch")
            else:
                st.caption("Sin ventas en los últimos 30 días.")
        else:
            st.caption("Sin ventas registradas.")
    with g4:
        st.markdown("##### Top 10 modelos con mayor rotación (últimos 90 días)")
        rot = sv.rotacion_df(hoy() - timedelta(days=89), hoy())
        rot = rot[(rot["tipo"] == "EQUIPO") & (rot["unidades_vendidas"] > 0)].head(10)
        if not rot.empty:
            rot["Modelo"] = rot["marca"] + " " + rot["modelo"]
            fig = px.bar(rot.iloc[::-1], x="unidades_vendidas", y="Modelo", orientation="h",
                         text="unidades_vendidas", color_discrete_sequence=[ROJO])
            fig.update_layout(height=320, margin=dict(t=10, b=10), xaxis_title="Unidades vendidas", yaxis_title=None)
            st.plotly_chart(fig, width="stretch")
        else:
            st.caption("Sin ventas de equipos en el periodo.")

    # ------------------------------------------------ resultado precio compra vs venta
    st.markdown("##### Control precio de compra vs. precio de venta (mes actual)")
    if not ventas_mes.empty:
        perdida = ventas_mes[ventas_mes["diferencia"] < 0]
        exceso = ventas_mes[ventas_mes["diferencia"] > 0]
        k = st.columns(4)
        k[0].metric("Costo de lo vendido", soles0(ventas_mes["precio_compra"].sum()))
        k[1].metric("Precio de venta total", soles0(ventas_mes["precio_venta"].sum()))
        k[2].metric("Ventas bajo costo (und.)", f"{len(perdida):,}", delta=soles0(perdida["diferencia"].sum()),
                    delta_color="normal" if len(perdida) else "off")
        k[3].metric("Ventas sobre costo (und.)", f"{len(exceso):,}", delta=soles0(exceso["diferencia"].sum()),
                    delta_color="off")
    else:
        st.caption("Sin ventas en el mes.")
