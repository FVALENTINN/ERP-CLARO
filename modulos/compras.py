import pandas as pd
import streamlit as st

from core import db, servicios as sv
from core.auth import puede, usuario_actual
from core.utils import hoy, limpiar_serie, plantilla_importacion, soles0, to_excel
from modulos.dashboard import encabezado


def render():
    encabezado("🛒 Compras / Ingresos", "Ingreso de equipos en consignación y SIM card: importación masiva por Excel o registro manual")
    u = usuario_actual()
    tabs = st.tabs(["📥 Importar Excel", "✍️ Registro manual", "📚 Historial de ingresos"])

    # ================================================================ IMPORTAR
    with tabs[0]:
        if not puede("registrar_compra"):
            st.warning("Su rol no puede registrar compras.")
        else:
            msg_ok = st.session_state.pop("imp_ok", None)
            if msg_ok:
                st.success(msg_ok)
                st.balloons()
            c = st.columns([2, 1])
            c[0].markdown("Estructura del Excel: **MODELO – MARCA – IMEI – PRECIO – N_FACTURA** "
                          "(la columna IMEI en formato *texto*). Para SIM card coloque el ICCID en la columna IMEI.")
            c[1].download_button("⬇️ Descargar plantilla", plantilla_importacion(), "plantilla_importacion_imei.xlsx",
                                 width="stretch")
            with st.form("imp_form"):
                f = st.columns(4)
                tipo = f[0].selectbox("Tipo de producto", ["EQUIPO", "SIM"])
                fecha = f[1].date_input("Fecha de compra / ingreso", hoy(), format="DD/MM/YYYY",
                                        help="Desde esta fecha corren los 90 días")
                modalidad = f[2].selectbox("Modalidad", ["CONSIGNACION", "COMPRA DIRECTA"])
                doc = f[3].text_input("N° guía / documento (opcional)")
                archivo = st.file_uploader("Archivo Excel (.xlsx) o CSV", type=["xlsx", "xls", "csv"])
                validar = st.form_submit_button("1️⃣ Validar archivo", type="primary")
            if validar and archivo:
                try:
                    if archivo.name.lower().endswith(".csv"):
                        raw = pd.read_csv(archivo, dtype=str, sep=None, engine="python")
                    else:
                        raw = pd.read_excel(archivo, dtype=str)
                    with st.spinner(f"Validando {len(raw):,} registros..."):
                        res = sv.validar_importacion(raw, tipo)
                    st.session_state.imp = {"res": res, "tipo": tipo, "fecha": fecha, "modalidad": modalidad,
                                            "doc": doc, "archivo": archivo.name}
                except Exception as e:
                    st.error(f"No se pudo leer el archivo: {e}")
                    st.session_state.pop("imp", None)

            imp = st.session_state.get("imp")
            if imp:
                res = imp["res"]
                ok = res[res["RESULTADO"] == "OK"]
                err = res[res["RESULTADO"] == "ERROR"]
                st.markdown(f"##### Resultado de validación – {imp['archivo']}")
                m = st.columns(4)
                m[0].metric("Registros leídos", f"{len(res):,}")
                m[1].metric("✅ Válidos", f"{len(ok):,}")
                m[2].metric("❌ Con error", f"{len(err):,}")
                m[3].metric("Valor a ingresar", soles0(ok["PRECIO"].sum()))
                if len(err):
                    st.error("Se detectaron registros con error. Solo se importarán los válidos.")
                    st.dataframe(err, hide_index=True, height=220)
                    st.download_button("⬇️ Descargar errores", to_excel({"Errores": err}), "errores_importacion.xlsx")
                if len(ok):
                    with st.expander(f"Ver registros válidos ({len(ok):,})"):
                        resumen = ok.groupby(["MARCA", "MODELO"]).agg(Unidades=("IMEI", "size"),
                                                                     Total=("PRECIO", "sum")).reset_index()
                        st.dataframe(resumen, hide_index=True)
                        st.dataframe(ok.head(500), hide_index=True)
                    b = st.columns([1, 1, 3])
                    if b[0].button(f"2️⃣ Importar {len(ok):,} registros", type="primary"):
                        with st.spinner("Guardando en la base de datos..."):
                            lote = sv.registrar_compra(ok, imp["tipo"], imp["fecha"], imp["modalidad"], imp["doc"],
                                                       "EXCEL", u["username"], f"Archivo {imp['archivo']}")
                        st.session_state.pop("imp")
                        st.session_state.imp_ok = f"✅ Lote #{lote} registrado con {len(ok):,} unidades."
                        st.rerun()
                    if b[1].button("Cancelar"):
                        st.session_state.pop("imp")
                        st.rerun()

    # ================================================================ MANUAL
    with tabs[1]:
        if not puede("registrar_compra"):
            st.warning("Su rol no puede registrar compras.")
        else:
            st.caption("Registre uno o varios IMEI del **mismo modelo y precio** (uno por línea; puede usar lector de código de barras).")
            with st.form("manual", clear_on_submit=False):
                c = st.columns(4)
                tipo = c[0].selectbox("Tipo", ["EQUIPO", "SIM"], key="m_tipo")
                marca = c[1].text_input("Marca", key="m_marca")
                modelo = c[2].text_input("Modelo", key="m_modelo")
                precio = c[3].number_input("Precio compra (S/)", min_value=0.0, step=1.0, key="m_precio")
                c = st.columns(3)
                factura = c[0].text_input("N° factura / guía", key="m_fact")
                fecha = c[1].date_input("Fecha compra", hoy(), format="DD/MM/YYYY", key="m_fecha")
                modalidad = c[2].selectbox("Modalidad", ["CONSIGNACION", "COMPRA DIRECTA"], key="m_mod")
                series = st.text_area("IMEI / ICCID (uno por línea)", height=160, key="m_series")
                enviar = st.form_submit_button("Registrar ingreso", type="primary")
            if enviar:
                lineas = [limpiar_serie(x) for x in series.splitlines() if x.strip()]
                if not lineas:
                    st.error("Ingrese al menos un IMEI/ICCID.")
                else:
                    df = pd.DataFrame({"MODELO": modelo, "MARCA": marca, "IMEI": lineas, "PRECIO": precio,
                                       "N_FACTURA": factura})
                    res = sv.validar_importacion(df, tipo)
                    ok = res[res["RESULTADO"] == "OK"]
                    err = res[res["RESULTADO"] == "ERROR"]
                    if len(err):
                        st.error(f"{len(err)} registro(s) con error (no se registraron):")
                        st.dataframe(err[["IMEI", "MOTIVO"]], hide_index=True)
                    if len(ok):
                        lote = sv.registrar_compra(ok, tipo, fecha, modalidad, factura, "MANUAL", u["username"])
                        st.success(f"✅ Lote #{lote}: {len(ok)} unidad(es) registradas.")

    # ================================================================ HISTORIAL
    with tabs[2]:
        lotes = db.q("SELECT * FROM lotes_compra ORDER BY id DESC")
        if lotes.empty:
            st.info("Sin ingresos registrados.")
        else:
            estado = db.q("""SELECT lote_id, SUM(CASE WHEN estado='DISPONIBLE' THEN 1 ELSE 0 END) AS disponibles,
                                    SUM(CASE WHEN estado='VENDIDO' THEN 1 ELSE 0 END) AS vendidos
                             FROM inventario GROUP BY lote_id""")
            lotes = lotes.merge(estado, left_on="id", right_on="lote_id", how="left").drop(columns=["lote_id"])
            vista = lotes[["id", "fecha_compra", "nro_documento", "modalidad", "origen", "cantidad", "total",
                           "disponibles", "vendidos", "usuario", "creado_en", "observacion"]]
            vista.columns = ["Lote", "Fecha compra", "Documento", "Modalidad", "Origen", "Cantidad", "Total",
                             "Disponibles", "Vendidos", "Usuario", "Registrado", "Observación"]
            st.dataframe(vista, hide_index=True, column_config={
                "Total": st.column_config.NumberColumn(format="S/ %.2f")})
            st.download_button("⬇️ Descargar historial", to_excel({"Ingresos": vista}), "historial_ingresos.xlsx")
            with st.expander("Ver detalle o eliminar un lote"):
                lote_id = st.selectbox("Lote", lotes["id"].tolist())
                det = db.q("SELECT tipo, marca, modelo, serie, precio_compra, nro_factura, estado FROM inventario "
                           "WHERE lote_id=:l", {"l": int(lote_id)})
                st.dataframe(det, hide_index=True, height=250)
                if u["rol"] in ("ADMIN", "FINANZAS"):
                    conf = st.checkbox("Confirmo que deseo eliminar este lote (solo si fue un error de carga)")
                    if st.button("🗑️ Eliminar lote", disabled=not conf):
                        try:
                            sv.eliminar_lote(int(lote_id), u["username"])
                            st.success("Lote eliminado.")
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))
