import re
from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import db, servicios as sv
from core.utils import hoy, soles, soles0

AZUL = "#1E6FD9"
NAVY = "#0B1E3F"
CIAN = "#22B8CF"
NARANJA = "#F5A524"
VERDE = "#22C55E"
ROJO = "#EF4444"
GRIS = "#94A3B8"
CFG = {"displayModeBar": False}
PALETA = [AZUL, NARANJA, CIAN, VERDE, "#6366F1", GRIS, "#0EA5E9", "#F97316"]


def estilo(fig, alto=300, leyenda=False):
    fig.update_layout(
        height=alto, margin=dict(t=8, b=8, l=8, r=8), paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter, sans-serif", color="#334155", size=12),
        showlegend=leyenda, legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        hoverlabel=dict(bgcolor="white", font_size=12),
    )
    fig.update_xaxes(showgrid=False, linecolor="#E2E8F0", title=None, automargin=True)
    fig.update_yaxes(gridcolor="#EEF2F7", zeroline=False, title=None)
    return fig


def titulo_card(t, sub=""):
    st.markdown(f"<div class='card-titulo'>{t}</div>" + (f"<div style='color:#64748B;font-size:.8rem;margin-bottom:4px'>{sub}</div>" if sub else ""),
                unsafe_allow_html=True)


ICONOS_SVG = {
    "equipo": '<rect width="14" height="20" x="5" y="2" rx="2"/><path d="M12 18h.01"/>',
    "sim": '<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><rect x="8" y="11" width="8" height="7" rx="1"/>',
    "dinero": '<rect width="20" height="12" x="2" y="6" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 12h.01M18 12h.01"/>',
    "ventas": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    "reloj": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "alerta": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "recibo": '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 17.5v-11"/>',
    "correo": '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
}
TONOS = {  # (color del ícono, fondo suave)
    "azul": (AZUL, "#E8F1FD"), "cian": ("#0E9DB3", "#E3F7FA"), "verde": ("#16A34A", "#E7F8EE"),
    "naranja": ("#D97706", "#FEF3E2"), "rojo": ("#DC2626", "#FDECEC"), "indigo": ("#4F46E5", "#EEF0FE"),
}


def kpi(col, etiqueta, valor, icono="equipo", tono="azul", sub="", sub_tipo=""):
    """Tarjeta KPI blanca con ícono de color (estilo dashboard)."""
    color, fondo = TONOS.get(tono, TONOS["azul"])
    svg = (f'<svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" '
           f'stroke-linejoin="round">{ICONOS_SVG.get(icono, "")}</svg>')
    col.markdown(
        f"<div class='kpi'><div><div class='lbl'>{etiqueta}</div><div class='val'>{valor}</div>"
        f"<div class='sub {sub_tipo}'>{sub}</div></div>"
        f"<div class='ico' style='background:{fondo}'>{svg}</div></div>", unsafe_allow_html=True)


def encabezado(titulo, sub):
    """Barra superior blanca: título del módulo, fecha y usuario."""
    titulo = re.sub(r"^[^\wÁÉÍÓÚÑáéíóúñ]+", "", titulo).strip()
    u = st.session_state.get("user") or {}
    nombre = u.get("nombre", "")
    iniciales = "".join(p[0] for p in nombre.split()[:2]).upper() or "U"
    st.markdown(
        f"<div class='topbar'><div><div class='tb-titulo'>{titulo}</div><div class='tb-sub'>{sub}</div></div>"
        f"<div class='tb-der'><span class='tb-chip'>📅 {hoy():%d/%m/%Y}</span>"
        f"<span class='tb-user'><span class='tb-avatar'>{iniciales}</span>{nombre}</span></div></div>",
        unsafe_allow_html=True)


def render():
    encabezado("Dashboard", "Resumen general del inventario, ventas y reclamos")
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

    vend_hoy = int((ventas["fecha_venta"] == hoy_ts).sum()) if not ventas.empty else 0
    perd_mes = ventas_mes[ventas_mes["diferencia"] < 0] if not ventas_mes.empty else ventas_mes
    c = st.columns(4)
    kpi(c[0], "Equipos en stock", f"{len(eq):,}", "equipo", "azul", f"{eq['modelo'].nunique() if not eq.empty else 0} modelos distintos")
    kpi(c[1], "SIM card en stock", f"{len(sim):,}", "sim", "cian", "Disponibles para venta")
    kpi(c[2], "Valor del inventario", soles0(disp["precio_compra"].sum() if not disp.empty else 0), "dinero", "indigo",
        "A precio de compra")
    kpi(c[3], "Ventas del mes", f"{len(ventas_mes):,}", "ventas", "verde", f"▲ {vend_hoy} vendidas hoy", "up")
    c = st.columns(4)
    kpi(c[0], f"Por vencer (≤{cfg['dias_alerta']} días)", f"{len(por_vencer):,}", "reloj", "naranja",
        soles0(por_vencer["precio_compra"].sum() if len(por_vencer) else 0) + " en riesgo")
    kpi(c[1], f"Vencidos (>{cfg['dias_limite_venta']} días)", f"{len(vencidos):,}", "alerta", "rojo",
        soles0(vencidos["precio_compra"].sum() if len(vencidos) else 0) + " sin vender", "down" if len(vencidos) else "")
    kpi(c[2], "NC pendientes de Claro", soles0(abiertos["saldo"].sum() if not abiertos.empty else 0), "recibo", "indigo",
        f"{len(abiertos)} reclamos abiertos")
    kpi(c[3], "Listos para reclamar", f"{len(para_reclamar):,}", "correo", "naranja",
        f"{len(perd_mes)} ventas bajo costo (mes)")
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    if inv.empty:
        st.info("Aún no hay inventario registrado. Empiece en **Compras** importando su Excel de IMEI.")
        return

    # ------------------------------------------------ gráficos
    g1, g2 = st.columns([2, 1])
    with g1, st.container(border=True):
        titulo_card("Resumen de ventas", "Unidades vendidas por día – últimos 30 días")
        if not ventas.empty:
            v = ventas[ventas["fecha_venta"] >= hoy_ts - pd.Timedelta(days=29)]
            dias = pd.date_range(hoy_ts - pd.Timedelta(days=29), hoy_ts, freq="D")
            d = (v.groupby([v["fecha_venta"].dt.normalize(), "tipo"]).size().unstack(fill_value=0)
                 .reindex(dias, fill_value=0))
            fig = go.Figure()
            for col, color, fill in [("EQUIPO", AZUL, "rgba(30,111,217,.12)"), ("SIM", CIAN, "rgba(34,184,207,.08)")]:
                if col in d.columns:
                    fig.add_trace(go.Scatter(x=d.index, y=d[col], name="Equipos" if col == "EQUIPO" else "SIM card",
                                             mode="lines+markers", line=dict(color=color, width=3, shape="spline"),
                                             marker=dict(size=5), fill="tozeroy", fillcolor=fill))
            fig.update_xaxes(tickformat="%d/%m")
            st.plotly_chart(estilo(fig, 300, leyenda=True), width="stretch", config=CFG)
        else:
            st.caption("Sin ventas registradas.")
    with g2, st.container(border=True):
        titulo_card("Estado del inventario", "Equipos disponibles según plazo de 90 días")
        if not eq.empty:
            e = eq["alerta"].value_counts()
            etiquetas = ["🟢 EN PLAZO", "🟠 POR VENCER", "🔴 VENCIDO"]
            vals = [int(e.get(x, 0)) for x in etiquetas]
            fig = go.Figure(go.Pie(labels=["En plazo", "Por vencer", "Vencido"], values=vals, hole=.68,
                                   marker=dict(colors=[AZUL, NARANJA, ROJO], line=dict(color="white", width=2)),
                                   textinfo="none", sort=False))
            fig.add_annotation(text=f"<b style='font-size:26px'>{sum(vals):,}</b><br><span style='color:#64748B'>equipos</span>",
                               showarrow=False, font=dict(size=13))
            st.plotly_chart(estilo(fig, 300, leyenda=True), width="stretch", config=CFG)
        else:
            st.caption("Sin equipos en stock.")

    g3, g4 = st.columns(2)
    with g3, st.container(border=True):
        titulo_card("Top 10 modelos con mayor rotación", "Unidades vendidas – últimos 90 días")
        rot = sv.rotacion_df(hoy() - timedelta(days=89), hoy())
        rot = rot[(rot["tipo"] == "EQUIPO") & (rot["unidades_vendidas"] > 0)].head(10)
        if not rot.empty:
            rot["Modelo"] = rot["marca"] + " " + rot["modelo"]
            fig = px.bar(rot.iloc[::-1], x="unidades_vendidas", y="Modelo", orientation="h",
                         text="unidades_vendidas", color_discrete_sequence=[AZUL])
            fig.update_traces(marker_line_width=0, textposition="outside", width=.6, cliponaxis=False)
            fig.update_xaxes(showgrid=True, gridcolor="#EEF2F7", range=[0, rot["unidades_vendidas"].max() * 1.15])
            fig.update_yaxes(showgrid=False)
            st.plotly_chart(estilo(fig, 330), width="stretch", config=CFG)
        else:
            st.caption("Sin ventas de equipos en el periodo.")
    with g4, st.container(border=True):
        titulo_card("Antigüedad del stock", "Equipos disponibles por días desde la compra")
        if not eq.empty:
            lim = int(cfg["dias_limite_venta"])
            ale = int(cfg["dias_alerta"])
            bins = [-1, 30, 60, lim - ale, lim, 10_000]
            labels = ["0-30", "31-60", f"61-{lim - ale}", f"{lim - ale + 1}-{lim}", f">{lim}"]
            tramo = pd.cut(eq["dias_stock"], bins=bins, labels=labels)
            a = tramo.value_counts().reindex(labels).fillna(0).reset_index()
            a.columns = ["Días en stock", "Equipos"]
            fig = px.bar(a, x="Días en stock", y="Equipos", text="Equipos", color="Días en stock",
                         color_discrete_sequence=[AZUL, CIAN, VERDE, NARANJA, ROJO])
            fig.update_traces(marker_line_width=0, textposition="outside", width=.6, cliponaxis=False)
            st.plotly_chart(estilo(fig, 330), width="stretch", config=CFG)
        else:
            st.caption("Sin equipos en stock.")

    g5, g6 = st.columns([1, 2])
    with g5, st.container(border=True):
        titulo_card("Stock disponible por marca")
        m = disp[disp["tipo"] == "EQUIPO"].groupby("marca").size().reset_index(name="Unidades") if not disp.empty else pd.DataFrame()
        if not m.empty:
            fig = go.Figure(go.Pie(labels=m["marca"], values=m["Unidades"], hole=.6, textinfo="percent",
                                   marker=dict(colors=PALETA, line=dict(color="white", width=2))))
            st.plotly_chart(estilo(fig, 280, leyenda=True), width="stretch", config=CFG)
        else:
            st.caption("Sin equipos en stock.")
    with g6, st.container(border=True):
        titulo_card("Control precio de compra vs. precio de venta", "Mes actual")
        if not ventas_mes.empty:
            perdida = ventas_mes[ventas_mes["diferencia"] < 0]
            exceso = ventas_mes[ventas_mes["diferencia"] > 0]
            k = st.columns(2)
            k[0].metric("Costo de lo vendido", soles0(ventas_mes["precio_compra"].sum()))
            k[1].metric("Precio de venta total", soles0(ventas_mes["precio_venta"].sum()))
            k = st.columns(2)
            k[0].metric("Ventas bajo costo (und.)", f"{len(perdida):,}", delta=soles0(perdida["diferencia"].sum()),
                        delta_color="normal" if len(perdida) else "off")
            k[1].metric("Ventas sobre costo (und.)", f"{len(exceso):,}", delta=soles0(exceso["diferencia"].sum()),
                        delta_color="off")
        else:
            st.caption("Sin ventas en el mes.")

    # ------------------------------------------------ alertas
    if len(vencidos) or len(por_vencer) or len(para_reclamar):
        with st.container(border=True):
            titulo_card("🚨 Alertas que requieren atención")
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
