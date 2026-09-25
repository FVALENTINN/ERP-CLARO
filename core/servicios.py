"""Reglas de negocio del ERP (independientes de la interfaz)."""
from datetime import date

import pandas as pd
from sqlalchemy import text

from core import db
from core.utils import ahora, hoy, limpiar_serie, validar_serie

COLS_IMPORT = ["MODELO", "MARCA", "IMEI", "PRECIO", "N_FACTURA"]
ALIAS_COLS = {
    "MODELO": "MODELO", "MARCA": "MARCA", "IMEI": "IMEI", "ICCID": "IMEI", "SERIE": "IMEI",
    "IMEI/ICCID": "IMEI", "PRECIO": "PRECIO", "PRECIO COMPRA": "PRECIO", "PRECIO_COMPRA": "PRECIO",
    "N_FACTURA": "N_FACTURA", "# FACTURA": "N_FACTURA", "#FACTURA": "N_FACTURA", "N° FACTURA": "N_FACTURA",
    "NRO FACTURA": "N_FACTURA", "NRO_FACTURA": "N_FACTURA", "FACTURA": "N_FACTURA", "N FACTURA": "N_FACTURA",
    "NUMERO FACTURA": "N_FACTURA", "Nº FACTURA": "N_FACTURA",
}


# =================================================================== INVENTARIO
def inventario_df(estado=None) -> pd.DataFrame:
    sql = "SELECT * FROM inventario"
    params = {}
    if estado:
        sql += " WHERE estado = :e"
        params["e"] = estado
    df = db.q(sql, params)
    return enriquecer_aging(df)


def enriquecer_aging(df: pd.DataFrame) -> pd.DataFrame:
    cfg = db.get_config()
    limite = int(cfg["dias_limite_venta"])
    alerta = int(cfg["dias_alerta"])
    if df.empty:
        for c in ["dias_stock", "fecha_limite", "dias_restantes", "alerta"]:
            df[c] = pd.Series(dtype="object")
        return df
    df["fecha_compra"] = pd.to_datetime(df["fecha_compra"], errors="coerce")
    df["fecha_venta"] = pd.to_datetime(df["fecha_venta"], errors="coerce")
    ref = pd.Timestamp(hoy())
    fin = df["fecha_venta"].where(df["estado"] == "VENDIDO", ref).fillna(ref)
    df["dias_stock"] = (fin - df["fecha_compra"]).dt.days
    df["fecha_limite"] = df["fecha_compra"] + pd.Timedelta(days=limite)
    df["dias_restantes"] = (df["fecha_limite"] - ref).dt.days

    def _alerta(r):
        if r["estado"] != "DISPONIBLE":
            return "—"
        if r["dias_restantes"] < 0:
            return "🔴 VENCIDO"
        if r["dias_restantes"] <= alerta:
            return "🟠 POR VENCER"
        return "🟢 EN PLAZO"

    df["alerta"] = df.apply(_alerta, axis=1)
    df["fecha_compra"] = df["fecha_compra"].dt.date
    df["fecha_venta"] = df["fecha_venta"].dt.date
    df["fecha_limite"] = df["fecha_limite"].dt.date
    return df


def buscar_serie(serie: str):
    serie = limpiar_serie(serie)
    df = db.q("SELECT * FROM inventario WHERE serie = :s", {"s": serie})
    return None if df.empty else enriquecer_aging(df).iloc[0].to_dict()


def series_existentes(series: list) -> set:
    existentes = set()
    lista = list(series)
    for i in range(0, len(lista), 900):
        bloque = lista[i:i + 900]
        params = {f"p{j}": s for j, s in enumerate(bloque)}
        marcadores = ",".join(f":p{j}" for j in range(len(bloque)))
        df = db.q(f"SELECT serie FROM inventario WHERE serie IN ({marcadores})", params)
        existentes.update(df["serie"].tolist())
    return existentes


# =================================================================== COMPRAS / IMPORTACIÓN
def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    nuevas = {}
    for c in df.columns:
        clave = str(c).strip().upper().replace("  ", " ")
        nuevas[c] = ALIAS_COLS.get(clave, clave)
    return df.rename(columns=nuevas)


def validar_importacion(df_raw: pd.DataFrame, tipo: str) -> pd.DataFrame:
    """Devuelve el DataFrame con columnas RESULTADO (OK/ERROR) y MOTIVO."""
    df = normalizar_columnas(df_raw.copy())
    faltan = [c for c in COLS_IMPORT if c not in df.columns]
    if faltan:
        raise ValueError(f"Faltan columnas en el Excel: {', '.join(faltan)}. "
                         f"Estructura requerida: {' - '.join(COLS_IMPORT)}")
    df = df[COLS_IMPORT].copy()
    df = df.dropna(how="all")
    df["IMEI"] = df["IMEI"].map(limpiar_serie)
    df["MODELO"] = df["MODELO"].fillna("").astype(str).str.strip().str.upper()
    df["MARCA"] = df["MARCA"].fillna("").astype(str).str.strip().str.upper()
    df["N_FACTURA"] = df["N_FACTURA"].fillna("").astype(str).str.strip().str.upper().str.replace(r"\.0$", "", regex=True)
    df["PRECIO"] = pd.to_numeric(df["PRECIO"], errors="coerce")

    existentes = series_existentes(df["IMEI"].tolist())
    duplicados_archivo = df["IMEI"].duplicated(keep="first")
    resultados, motivos = [], []
    for idx, r in df.iterrows():
        errores = []
        ok, msg = validar_serie(tipo, r["IMEI"])
        if not ok:
            errores.append(msg)
        if r["IMEI"] in existentes:
            errores.append("Ya registrado en el sistema")
        if duplicados_archivo.loc[idx]:
            errores.append("Duplicado dentro del archivo")
        if not r["MODELO"]:
            errores.append("Modelo vacío")
        if tipo == "EQUIPO" and not r["MARCA"]:
            errores.append("Marca vacía")
        if pd.isna(r["PRECIO"]) or r["PRECIO"] < 0:
            errores.append("Precio inválido")
        resultados.append("ERROR" if errores else "OK")
        motivos.append("; ".join(errores) if errores else "")
    df["RESULTADO"] = resultados
    df["MOTIVO"] = motivos
    return df


def registrar_compra(items: pd.DataFrame, tipo: str, fecha_compra: date, modalidad: str,
                     nro_documento: str, origen: str, usuario: str, observacion: str = "") -> int:
    """items con columnas MODELO, MARCA, IMEI, PRECIO, N_FACTURA (solo filas válidas)."""
    if items.empty:
        return 0
    engine = db.get_engine()
    with engine.begin() as cn:
        res = cn.execute(db.lotes_compra.insert().values(
            fecha_compra=fecha_compra, nro_documento=nro_documento or ", ".join(sorted(set(items["N_FACTURA"])))[:60],
            modalidad=modalidad, origen=origen, cantidad=len(items),
            total=float(items["PRECIO"].sum()), observacion=observacion, usuario=usuario, creado_en=ahora(),
        ))
        lote_id = res.inserted_primary_key[0]
        filas = [{
            "tipo": tipo, "marca": r.MARCA, "modelo": r.MODELO, "serie": r.IMEI,
            "precio_compra": float(r.PRECIO), "nro_factura": r.N_FACTURA or nro_documento,
            "fecha_compra": fecha_compra, "modalidad": modalidad, "lote_id": lote_id,
            "estado": "DISPONIBLE", "creado_por": usuario, "creado_en": ahora(),
        } for r in items.itertuples(index=False)]
        for i in range(0, len(filas), 1000):
            cn.execute(db.inventario.insert(), filas[i:i + 1000])
    db.log(usuario, "Compras", f"Ingreso {origen}", f"Lote {lote_id}: {len(items)} {tipo}")
    return lote_id


def eliminar_lote(lote_id: int, usuario: str):
    vendidos = db.scalar("SELECT COUNT(*) FROM inventario WHERE lote_id=:l AND estado<>'DISPONIBLE'", {"l": lote_id})
    if vendidos:
        raise ValueError(f"El lote tiene {vendidos} unidades vendidas o dadas de baja; no se puede eliminar.")
    db.execute("DELETE FROM inventario WHERE lote_id=:l", {"l": lote_id})
    db.execute("DELETE FROM lotes_compra WHERE id=:l", {"l": lote_id})
    db.log(usuario, "Compras", "Eliminar lote", f"Lote {lote_id}")


# =================================================================== VENTAS
def registrar_venta(datos: dict, usuario: str) -> dict:
    """Registra la venta, marca la serie como VENDIDA y crea el reclamo si hay pérdida."""
    item = buscar_serie(datos["serie"])
    if not item:
        raise ValueError("La serie no existe en el inventario.")
    if item["estado"] != "DISPONIBLE":
        raise ValueError(f"La serie está en estado {item['estado']}; no se puede vender.")
    precio_compra = float(item["precio_compra"] or 0)
    precio_venta = float(datos["precio_venta"])
    diferencia = round(precio_venta - precio_compra, 2)
    engine = db.get_engine()
    with engine.begin() as cn:
        res = cn.execute(db.ventas.insert().values(
            fecha_venta=datos["fecha_venta"], item_id=int(item["id"]), tipo=item["tipo"],
            tipo_doc=datos["tipo_doc"], nro_doc=datos["nro_doc"], cliente=datos["cliente"],
            telefono=datos.get("telefono", ""), marca=item["marca"], modelo=item["modelo"],
            serie=item["serie"], precio_compra=precio_compra, precio_venta=precio_venta,
            diferencia=diferencia, bo=datos.get("bo", ""), motorizado=datos.get("motorizado", ""),
            modalidad=datos.get("modalidad", ""), forma_pago=datos.get("forma_pago", "CONTADO"),
            nro_cuotas=int(datos.get("nro_cuotas", 0) or 0),
            comprobante=datos.get("comprobante", ""), estado="ACTIVA",
            observacion=datos.get("observacion", ""), usuario=usuario, creado_en=ahora(),
        ))
        venta_id = res.inserted_primary_key[0]
        cn.execute(text("UPDATE inventario SET estado='VENDIDO', fecha_venta=:f WHERE id=:i"),
                   {"f": datos["fecha_venta"], "i": int(item["id"])})
        reclamo_id = None
        if diferencia < 0:
            r = cn.execute(db.reclamos.insert().values(
                venta_id=venta_id, serie=item["serie"], monto_esperado=abs(diferencia),
                estado="PENDIENTE NC", nro_reclamos=0, creado_en=ahora(), actualizado_en=ahora(),
            ))
            reclamo_id = r.inserted_primary_key[0]
            cn.execute(db.reclamo_eventos.insert().values(
                reclamo_id=reclamo_id, fecha=ahora(), usuario=usuario, accion="Creado automático",
                detalle=f"Venta a S/ {precio_venta:,.2f} menor al costo S/ {precio_compra:,.2f}. "
                        f"NC esperada S/ {abs(diferencia):,.2f}",
            ))
    db.log(usuario, "Ventas", "Registrar venta", f"Venta {venta_id} serie {item['serie']}")
    return {"venta_id": venta_id, "diferencia": diferencia, "reclamo_id": reclamo_id}


def anular_venta(venta_id: int, motivo: str, usuario: str):
    v = db.q("SELECT * FROM ventas WHERE id=:i", {"i": venta_id})
    if v.empty or v.iloc[0]["estado"] == "ANULADA":
        raise ValueError("Venta no encontrada o ya anulada.")
    item_id = int(v.iloc[0]["item_id"])
    with db.get_engine().begin() as cn:
        cn.execute(text("UPDATE ventas SET estado='ANULADA', observacion=:m WHERE id=:i"),
                   {"m": f"ANULADA: {motivo}", "i": venta_id})
        cn.execute(text("UPDATE inventario SET estado='DISPONIBLE', fecha_venta=NULL WHERE id=:i"), {"i": item_id})
        cn.execute(text("UPDATE reclamos SET estado='ANULADO', actualizado_en=:a WHERE venta_id=:i"),
                   {"i": venta_id, "a": ahora()})
    db.log(usuario, "Ventas", "Anular venta", f"Venta {venta_id}: {motivo}")


def registrar_factura_claro(serie: str, nro: str, monto: float, fecha: date, usuario: str) -> str:
    """Registra la factura que Claro emite tras la venta. Si el monto facturado difiere del
    precio de compra registrado, recalcula la diferencia y el reclamo."""
    serie = limpiar_serie(serie)
    v = db.q("SELECT * FROM ventas WHERE serie=:s AND estado='ACTIVA'", {"s": serie})
    if v.empty:
        return "Sin venta activa"
    v = v.iloc[0]
    costo = float(monto) if monto and monto > 0 else float(v["precio_compra"])
    diferencia = round(float(v["precio_venta"]) - costo, 2)
    with db.get_engine().begin() as cn:
        cn.execute(text("""UPDATE ventas SET factura_claro=:n, monto_factura_claro=:m, fecha_factura_claro=:f,
                           diferencia=:d WHERE id=:i"""),
                   {"n": nro, "m": monto, "f": fecha, "d": diferencia, "i": int(v["id"])})
        rec = cn.execute(text("SELECT id, estado FROM reclamos WHERE venta_id=:i"), {"i": int(v["id"])}).fetchone()
        if diferencia < 0:
            if rec is None:
                r = cn.execute(db.reclamos.insert().values(
                    venta_id=int(v["id"]), serie=serie, monto_esperado=abs(diferencia),
                    estado="PENDIENTE NC", nro_reclamos=0, creado_en=ahora(), actualizado_en=ahora()))
                rid = r.inserted_primary_key[0]
                accion = "Creado por factura Claro"
            else:
                rid = rec[0]
                cn.execute(text("UPDATE reclamos SET monto_esperado=:m, actualizado_en=:a WHERE id=:i"),
                           {"m": abs(diferencia), "a": ahora(), "i": rid})
                accion = "Monto actualizado por factura Claro"
            cn.execute(db.reclamo_eventos.insert().values(
                reclamo_id=rid, fecha=ahora(), usuario=usuario, accion=accion,
                detalle=f"Factura {nro} por S/ {costo:,.2f}; NC esperada S/ {abs(diferencia):,.2f}"))
        elif rec is not None and rec[1] == "PENDIENTE NC":
            cn.execute(text("UPDATE reclamos SET estado='ANULADO', actualizado_en=:a WHERE id=:i"),
                       {"a": ahora(), "i": rec[0]})
    return "OK"


# =================================================================== RECLAMOS
def reclamos_df() -> pd.DataFrame:
    cfg = db.get_config()
    espera = int(cfg["dias_espera_nc"])
    df = db.q("""
        SELECT r.*, v.fecha_venta, v.marca, v.modelo, v.precio_compra, v.precio_venta, v.bo,
               v.cliente, v.nro_doc, v.factura_claro, v.monto_factura_claro, v.motorizado
        FROM reclamos r JOIN ventas v ON v.id = r.venta_id
        ORDER BY r.id DESC""")
    if df.empty:
        df["dias_sin_nc"] = pd.Series(dtype="int")
        df["accion_sugerida"] = pd.Series(dtype="object")
        df["saldo"] = pd.Series(dtype="float")
        return df
    df["fecha_venta"] = pd.to_datetime(df["fecha_venta"], errors="coerce")
    df["dias_sin_nc"] = (pd.Timestamp(hoy()) - df["fecha_venta"]).dt.days
    df["fecha_venta"] = df["fecha_venta"].dt.date
    df["monto_nc"] = pd.to_numeric(df["monto_nc"], errors="coerce").fillna(0.0)
    df["saldo"] = (df["monto_esperado"] - df["monto_nc"]).round(2)

    def _accion(r):
        if r["estado"] in ("NC RECIBIDA", "CERRADO", "ANULADO"):
            return "—"
        if r["estado"] == "PENDIENTE NC":
            return "📧 RECLAMAR" if r["dias_sin_nc"] > espera else f"⏳ Esperar NC ({espera - r['dias_sin_nc']} d)"
        if r["estado"] in ("RECLAMADO", "NC PARCIAL"):
            return "🔁 Hacer seguimiento"
        return ""

    df["accion_sugerida"] = df.apply(_accion, axis=1)
    return df


def registrar_nc(reclamo_id: int, nro_nc: str, monto: float, fecha: date, usuario: str) -> str:
    r = db.q("SELECT * FROM reclamos WHERE id=:i", {"i": reclamo_id}).iloc[0]
    acumulado = float(r["monto_nc"] or 0) + float(monto)
    estado = "NC RECIBIDA" if acumulado + 0.009 >= float(r["monto_esperado"]) else "NC PARCIAL"
    nros = ", ".join(x for x in [r["nro_nc"], nro_nc] if x)
    db.execute("""UPDATE reclamos SET nro_nc=:n, monto_nc=:m, fecha_nc=:f, estado=:e, actualizado_en=:a
                  WHERE id=:i""", {"n": nros, "m": acumulado, "f": fecha, "e": estado, "a": ahora(), "i": reclamo_id})
    with db.get_engine().begin() as cn:
        cn.execute(db.reclamo_eventos.insert().values(
            reclamo_id=reclamo_id, fecha=ahora(), usuario=usuario, accion=f"NC registrada ({estado})",
            detalle=f"NC {nro_nc} por S/ {monto:,.2f}. Acumulado S/ {acumulado:,.2f}"))
    return estado


def marcar_reclamado(ids: list, usuario: str, ticket: str = ""):
    with db.get_engine().begin() as cn:
        for i in ids:
            cn.execute(text("""UPDATE reclamos SET estado=CASE WHEN estado='NC PARCIAL' THEN 'NC PARCIAL' ELSE 'RECLAMADO' END,
                               fecha_reclamo=:f, nro_reclamos=COALESCE(nro_reclamos,0)+1,
                               ticket_claro=COALESCE(NULLIF(:t,''), ticket_claro), actualizado_en=:a WHERE id=:i"""),
                       {"f": hoy(), "t": ticket, "a": ahora(), "i": int(i)})
            cn.execute(db.reclamo_eventos.insert().values(
                reclamo_id=int(i), fecha=ahora(), usuario=usuario, accion="Reclamo enviado por correo",
                detalle=f"Ticket: {ticket}" if ticket else "Correo de reclamo generado"))
    db.log(usuario, "Reclamos", "Reclamo enviado", f"{len(ids)} reclamos")


def cerrar_reclamo(reclamo_id: int, motivo: str, usuario: str):
    db.execute("UPDATE reclamos SET estado='CERRADO', observacion=:m, actualizado_en=:a WHERE id=:i",
               {"m": motivo, "a": ahora(), "i": reclamo_id})
    with db.get_engine().begin() as cn:
        cn.execute(db.reclamo_eventos.insert().values(
            reclamo_id=reclamo_id, fecha=ahora(), usuario=usuario, accion="Cerrado", detalle=motivo))


def generar_correo(df_sel: pd.DataFrame, cfg: dict, usuario_nombre: str) -> tuple:
    total = df_sel["saldo"].sum()
    asunto = (f"Solicitud de emisión de Notas de Crédito – {cfg['empresa']} – "
              f"{len(df_sel)} equipo(s) – S/ {total:,.2f}")
    def _t(v, defecto="-"):
        return defecto if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "None", "nan") else v

    lineas = []
    for _, r in df_sel.iterrows():
        costo = r["monto_factura_claro"] if pd.notna(r.get("monto_factura_claro")) and r.get("monto_factura_claro") else r["precio_compra"]
        lineas.append(
            f"- IMEI {r['serie']} | {r['marca']} {r['modelo']} | BO {_t(r['bo'])} | "
            f"Fact. Claro {_t(r['factura_claro'], 'pendiente')} | Costo S/ {costo:,.2f} | "
            f"Venta S/ {r['precio_venta']:,.2f} | NC pendiente S/ {r['saldo']:,.2f} | Venta {pd.Timestamp(r['fecha_venta']):%d/%m/%Y}")
    ruc = f" (RUC {cfg['ruc_empresa']})" if cfg.get("ruc_empresa") else ""
    cuerpo = f"""Estimados señores de Claro:

Por medio del presente, {cfg['empresa']}{ruc}, en calidad de distribuidor autorizado, solicita la emisión de las notas de crédito correspondientes a los equipos detallados a continuación, los cuales fueron vendidos al cliente final a un precio menor al costo facturado. A la fecha, dichas notas de crédito no han sido emitidas de forma automática.

Detalle:
{chr(10).join(lineas)}

Monto total pendiente de nota de crédito: S/ {total:,.2f}

Adjuntamos el archivo Excel con el detalle para su validación. Agradeceremos confirmar la recepción del presente y el plazo estimado de emisión.

Atentamente,

{usuario_nombre}
{cfg['firma_correo']}
{cfg['empresa']}"""
    return asunto, cuerpo


# =================================================================== REPORTES
def rotacion_df(desde: date, hasta: date) -> pd.DataFrame:
    ventas = db.q("""SELECT v.tipo, v.marca, v.modelo, v.fecha_venta, i.fecha_compra
                     FROM ventas v JOIN inventario i ON i.id=v.item_id
                     WHERE v.estado='ACTIVA' AND v.fecha_venta BETWEEN :d AND :h""",
                  {"d": desde, "h": hasta})
    stock = db.q("SELECT tipo, marca, modelo, COUNT(*) AS stock_actual FROM inventario "
                 "WHERE estado='DISPONIBLE' GROUP BY tipo, marca, modelo")
    if ventas.empty:
        base = stock.copy()
        base["unidades_vendidas"] = 0
        base["dias_prom_venta"] = None
    else:
        ventas["dias"] = (pd.to_datetime(ventas["fecha_venta"]) - pd.to_datetime(ventas["fecha_compra"])).dt.days
        agg = ventas.groupby(["tipo", "marca", "modelo"]).agg(
            unidades_vendidas=("dias", "size"), dias_prom_venta=("dias", "mean")).reset_index()
        base = agg.merge(stock, on=["tipo", "marca", "modelo"], how="outer")
    base["unidades_vendidas"] = base["unidades_vendidas"].fillna(0).astype(int)
    base["stock_actual"] = base["stock_actual"].fillna(0).astype(int)
    dias_periodo = max((hasta - desde).days + 1, 1)
    base["venta_diaria"] = (base["unidades_vendidas"] / dias_periodo).round(2)
    base["dias_cobertura"] = base.apply(
        lambda r: round(r["stock_actual"] / r["venta_diaria"], 0) if r["venta_diaria"] > 0 else None, axis=1)
    base["indice_rotacion_%"] = base.apply(
        lambda r: round(100 * r["unidades_vendidas"] / (r["unidades_vendidas"] + r["stock_actual"]), 1)
        if (r["unidades_vendidas"] + r["stock_actual"]) else 0, axis=1)
    base["dias_prom_venta"] = pd.to_numeric(base["dias_prom_venta"], errors="coerce").round(1)

    def _clasif(r):
        if r["unidades_vendidas"] == 0:
            return "SIN MOVIMIENTO"
        if r["indice_rotacion_%"] >= 60:
            return "ALTA"
        if r["indice_rotacion_%"] >= 30:
            return "MEDIA"
        return "BAJA"

    base["rotacion"] = base.apply(_clasif, axis=1)
    return base.sort_values(["unidades_vendidas", "indice_rotacion_%"], ascending=False).reset_index(drop=True)


def kardex_df(desde: date, hasta: date) -> pd.DataFrame:
    """Kardex por modelo: saldo inicial, ingresos, salidas, saldo final (unidades y valor)."""
    inv = db.q("SELECT tipo, marca, modelo, precio_compra, fecha_compra, fecha_venta, estado FROM inventario")
    if inv.empty:
        return pd.DataFrame()
    inv["fecha_compra"] = pd.to_datetime(inv["fecha_compra"])
    inv["fecha_venta"] = pd.to_datetime(inv["fecha_venta"])
    d, h = pd.Timestamp(desde), pd.Timestamp(hasta)
    vendido = (inv["estado"] != "DISPONIBLE") & inv["fecha_venta"].notna()  # vendido, devuelto o baja
    inv["ini"] = (inv["fecha_compra"] < d) & ~(vendido & (inv["fecha_venta"] < d))
    inv["ing"] = inv["fecha_compra"].between(d, h)
    inv["sal"] = vendido & inv["fecha_venta"].between(d, h)
    g = inv.groupby(["tipo", "marca", "modelo"])
    k = pd.DataFrame({
        "saldo_inicial": g["ini"].sum(), "ingresos": g["ing"].sum(), "salidas": g["sal"].sum(),
    }).reset_index()
    k["saldo_final"] = k["saldo_inicial"] + k["ingresos"] - k["salidas"]
    val = inv[(inv["fecha_compra"] <= h) & ~(vendido & (inv["fecha_venta"] <= h))]
    v = val.groupby(["tipo", "marca", "modelo"])["precio_compra"].sum().rename("valor_saldo_final").reset_index()
    k = k.merge(v, how="left", on=["tipo", "marca", "modelo"]).fillna({"valor_saldo_final": 0})
    return k[(k[["saldo_inicial", "ingresos", "salidas", "saldo_final"]].sum(axis=1)) > 0]


# =================================================================== VENTAS MASIVAS (EXCEL)
COLS_VENTA = ["CLIENTE", "DOCUMENTO", "MODELO", "IMEI", "PRECIO", "FECHA", "MODALIDAD", "FORMA_PAGO", "N_CUOTAS"]
COLS_VENTA_OPC = ["BO", "MOTORIZADO", "TELEFONO"]
ALIAS_VENTA = {
    "CLIENTE": "CLIENTE", "NOMBRE": "CLIENTE", "RAZON SOCIAL": "CLIENTE", "NOMBRE / RAZON SOCIAL": "CLIENTE",
    "DOCUMENTO": "DOCUMENTO", "DNI/CE/RUC": "DOCUMENTO", "DNI / CE / RUC": "DOCUMENTO", "DNI": "DOCUMENTO",
    "RUC": "DOCUMENTO", "CE": "DOCUMENTO", "NRO DOC": "DOCUMENTO", "NRO_DOC": "DOCUMENTO", "N° DOCUMENTO": "DOCUMENTO",
    "NUMERO DOCUMENTO": "DOCUMENTO",
    "MODELO": "MODELO", "IMEI": "IMEI", "ICCID": "IMEI", "SERIE": "IMEI", "IMEI/ICCID": "IMEI",
    "PRECIO": "PRECIO", "PRECIO VENTA": "PRECIO", "PRECIO_VENTA": "PRECIO",
    "FECHA": "FECHA", "FECHA VENTA": "FECHA", "FECHA_VENTA": "FECHA",
    "MODALIDAD": "MODALIDAD", "TIPO VENTA": "MODALIDAD",
    "FORMA_PAGO": "FORMA_PAGO", "FORMA PAGO": "FORMA_PAGO", "FORMA DE PAGO": "FORMA_PAGO",
    "CONTADO/CUOTAS": "FORMA_PAGO", "CONTADO / CUOTAS": "FORMA_PAGO", "PAGO": "FORMA_PAGO",
    "N_CUOTAS": "N_CUOTAS", "#CUOTAS": "N_CUOTAS", "# CUOTAS": "N_CUOTAS", "N° CUOTAS": "N_CUOTAS",
    "NRO CUOTAS": "N_CUOTAS", "NRO_CUOTAS": "N_CUOTAS", "CUOTAS": "N_CUOTAS", "NUMERO DE CUOTAS": "N_CUOTAS",
    "BO": "BO", "MOTORIZADO": "MOTORIZADO", "TELEFONO": "TELEFONO", "TELÉFONO": "TELEFONO",
}


def inferir_tipo_doc(nro: str) -> str:
    if nro.isdigit() and len(nro) == 8:
        return "DNI"
    if nro.isdigit() and len(nro) == 11:
        return "RUC"
    return "CE"


def _texto(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip().upper()
    return "" if s in ("NAN", "NONE", "NAT") else (s[:-2] if s.endswith(".0") else s)


def _inventario_por_series(series: list) -> dict:
    res = {}
    lista = list(series)
    for i in range(0, len(lista), 900):
        bloque = lista[i:i + 900]
        params = {f"p{j}": s for j, s in enumerate(bloque)}
        marc = ",".join(f":p{j}" for j in range(len(bloque)))
        df = db.q(f"SELECT id, serie, tipo, marca, modelo, precio_compra, estado, fecha_compra "
                  f"FROM inventario WHERE serie IN ({marc})", params)
        for r in df.to_dict("records"):
            res[r["serie"]] = r
    return res


def validar_ventas_masivo(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Valida el Excel de ventas. Devuelve el DataFrame con RESULTADO (OK/ERROR), MOTIVO y OBSERVACION."""
    from core.utils import validar_documento
    df = df_raw.copy()
    df.columns = [ALIAS_VENTA.get(str(c).strip().upper().replace("  ", " "), str(c).strip().upper()) for c in df.columns]
    faltan = [c for c in COLS_VENTA if c not in df.columns]
    if faltan:
        raise ValueError(f"Faltan columnas en el Excel: {', '.join(faltan)}. "
                         f"Estructura requerida: {' - '.join(COLS_VENTA)}")
    df = df[COLS_VENTA + [c for c in COLS_VENTA_OPC if c in df.columns]].dropna(how="all").copy()
    for c in COLS_VENTA_OPC:
        if c not in df.columns:
            df[c] = ""
    df["IMEI"] = df["IMEI"].map(limpiar_serie)
    for c in ["CLIENTE", "DOCUMENTO", "MODELO", "MODALIDAD", "FORMA_PAGO", "BO", "MOTORIZADO", "TELEFONO"]:
        df[c] = df[c].map(_texto)
    df["DOCUMENTO"] = df["DOCUMENTO"].str.replace(r"[\s\-\.]", "", regex=True)
    df["DOCUMENTO"] = df["DOCUMENTO"].map(lambda d: d.zfill(8) if d.isdigit() and len(d) == 7 else d)
    df["FORMA_PAGO"] = df["FORMA_PAGO"].replace({"CUOTA": "CUOTAS", "CREDITO": "CUOTAS", "CRÉDITO": "CUOTAS",
                                                   "CONTADO ": "CONTADO"})
    df["PRECIO"] = pd.to_numeric(df["PRECIO"], errors="coerce")
    df["N_CUOTAS"] = pd.to_numeric(df["N_CUOTAS"], errors="coerce")
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce", dayfirst=True, format="mixed").dt.date
    df["TIPO_DOC"] = df["DOCUMENTO"].map(inferir_tipo_doc)

    inv = _inventario_por_series(df["IMEI"].tolist())
    dup = df["IMEI"].duplicated(keep="first")
    bos_usados = set()
    bos = [b for b in df["BO"].unique() if b]
    if bos:
        for i in range(0, len(bos), 900):
            bloque = bos[i:i + 900]
            params = {f"p{j}": b for j, b in enumerate(bloque)}
            marc = ",".join(f":p{j}" for j in range(len(bloque)))
            bos_usados |= set(db.q(f"SELECT bo FROM ventas WHERE estado='ACTIVA' AND bo IN ({marc})", params)["bo"])
    dup_bo = df["BO"].ne("") & df["BO"].duplicated(keep="first")

    res, mot, obs = [], [], []
    extra = {"_item_id": [], "_tipo": [], "_marca": [], "_modelo_inv": [], "_precio_compra": []}
    for idx, r in df.iterrows():
        e, o = [], []
        it = inv.get(r["IMEI"])
        if not r["IMEI"]:
            e.append("IMEI vacío")
        elif it is None:
            e.append("IMEI no existe en el inventario")
        elif it["estado"] != "DISPONIBLE":
            e.append(f"IMEI en estado {it['estado']}")
        if dup.loc[idx]:
            e.append("IMEI duplicado en el archivo")
        if not r["CLIENTE"]:
            e.append("Cliente vacío")
        ok_doc, msg_doc = validar_documento(r["TIPO_DOC"], r["DOCUMENTO"])
        if not ok_doc:
            e.append(msg_doc)
        if pd.isna(r["PRECIO"]) or r["PRECIO"] < 0:
            e.append("Precio inválido")
        if r["FECHA"] is None or pd.isna(r["FECHA"]):
            e.append("Fecha inválida (use DD/MM/AAAA)")
        elif r["FECHA"] > hoy():
            e.append("Fecha futura")
        elif it is not None and pd.notna(it["fecha_compra"]) and r["FECHA"] < pd.to_datetime(it["fecha_compra"]).date():
            e.append("Fecha de venta anterior a la fecha de compra")
        if not r["MODALIDAD"]:
            e.append("Modalidad vacía")
        if r["FORMA_PAGO"] not in ("CONTADO", "CUOTAS"):
            e.append("Forma de pago debe ser CONTADO o CUOTAS")
        elif r["FORMA_PAGO"] == "CUOTAS" and (pd.isna(r["N_CUOTAS"]) or r["N_CUOTAS"] < 1 or r["N_CUOTAS"] != int(r["N_CUOTAS"])):
            e.append("N° de cuotas inválido (entero mayor a 0)")
        if r["BO"] and (r["BO"] in bos_usados or dup_bo.loc[idx]):
            e.append(f"BO {r['BO']} ya registrado")
        if it is not None and r["MODELO"] and r["MODELO"] not in str(it["modelo"]).upper() \
                and str(it["modelo"]).upper() not in r["MODELO"]:
            o.append(f"Modelo del inventario: {it['modelo']}")
        if it is not None and not pd.isna(r["PRECIO"]) and r["PRECIO"] < float(it["precio_compra"] or 0):
            o.append(f"Bajo costo: NC esperada S/ {float(it['precio_compra']) - r['PRECIO']:,.2f}")
        res.append("ERROR" if e else "OK")
        mot.append("; ".join(e))
        obs.append("; ".join(o))
        extra["_item_id"].append(int(it["id"]) if it else None)
        extra["_tipo"].append(it["tipo"] if it else None)
        extra["_marca"].append(it["marca"] if it else None)
        extra["_modelo_inv"].append(it["modelo"] if it else None)
        extra["_precio_compra"].append(float(it["precio_compra"] or 0) if it else None)
    df["RESULTADO"], df["MOTIVO"], df["OBSERVACION"] = res, mot, obs
    for k, v in extra.items():
        df[k] = v
    return df


def registrar_ventas_masivo(ok: pd.DataFrame, usuario: str) -> dict:
    """Registra en bloque las ventas válidas, marca los IMEI como vendidos y crea los reclamos de NC."""
    if ok.empty:
        return {"ventas": 0, "reclamos": 0, "monto_nc": 0.0}
    # revalidar disponibilidad justo antes de grabar
    inv = _inventario_por_series(ok["IMEI"].tolist())
    ok = ok[ok["IMEI"].map(lambda s: s in inv and inv[s]["estado"] == "DISPONIBLE")].copy()
    ahora_ = ahora()
    filas = []
    for r in ok.to_dict("records"):
        pc = float(r["_precio_compra"] or 0)
        pv = float(r["PRECIO"])
        filas.append({
            "fecha_venta": r["FECHA"], "item_id": int(r["_item_id"]), "tipo": r["_tipo"], "tipo_doc": r["TIPO_DOC"],
            "nro_doc": r["DOCUMENTO"], "cliente": r["CLIENTE"], "telefono": r["TELEFONO"], "marca": r["_marca"],
            "modelo": r["_modelo_inv"], "serie": r["IMEI"], "precio_compra": pc, "precio_venta": pv,
            "diferencia": round(pv - pc, 2), "bo": r["BO"], "motorizado": r["MOTORIZADO"], "modalidad": r["MODALIDAD"],
            "forma_pago": r["FORMA_PAGO"], "nro_cuotas": int(r["N_CUOTAS"]) if r["FORMA_PAGO"] == "CUOTAS" else 0,
            "comprobante": "", "estado": "ACTIVA", "observacion": "Importación masiva",
            "usuario": usuario, "creado_en": ahora_,
        })
    if not filas:
        return {"ventas": 0, "reclamos": 0, "monto_nc": 0.0}
    item_ids = [f["item_id"] for f in filas]
    with db.get_engine().begin() as cn:
        for i in range(0, len(filas), 500):
            cn.execute(db.ventas.insert(), filas[i:i + 500])
        mapa = {}
        for i in range(0, len(item_ids), 900):
            bloque = item_ids[i:i + 900]
            params = {f"p{j}": v for j, v in enumerate(bloque)}
            marc = ",".join(f":p{j}" for j in range(len(bloque)))
            for vid, iid, dif, serie, pv, pc in cn.execute(text(
                    f"SELECT id, item_id, diferencia, serie, precio_venta, precio_compra FROM ventas "
                    f"WHERE estado='ACTIVA' AND item_id IN ({marc})"), params):
                mapa[iid] = (vid, dif, serie, pv, pc)
            cn.execute(text(
                f"UPDATE inventario SET estado='VENDIDO', fecha_venta=(SELECT v.fecha_venta FROM ventas v "
                f"WHERE v.item_id=inventario.id AND v.estado='ACTIVA') WHERE id IN ({marc})"), params)
        recl = [{"venta_id": vid, "serie": serie, "monto_esperado": abs(dif), "estado": "PENDIENTE NC",
                 "nro_reclamos": 0, "creado_en": ahora_, "actualizado_en": ahora_}
                for vid, dif, serie, pv, pc in mapa.values() if dif is not None and dif < 0]
        if recl:
            cn.execute(db.reclamos.insert(), recl)
            vids = [x["venta_id"] for x in recl]
            eventos = []
            for i in range(0, len(vids), 900):
                bloque = vids[i:i + 900]
                params = {f"p{j}": v for j, v in enumerate(bloque)}
                marc = ",".join(f":p{j}" for j in range(len(bloque)))
                for rid, vid, monto in cn.execute(text(
                        f"SELECT id, venta_id, monto_esperado FROM reclamos WHERE venta_id IN ({marc})"), params):
                    eventos.append({"reclamo_id": rid, "fecha": ahora_, "usuario": usuario,
                                    "accion": "Creado automático (importación)",
                                    "detalle": f"Venta importada bajo costo. NC esperada S/ {monto:,.2f}"})
            if eventos:
                cn.execute(db.reclamo_eventos.insert(), eventos)
    db.log(usuario, "Ventas", "Importación masiva", f"{len(filas)} ventas, {len(recl)} reclamos")
    return {"ventas": len(filas), "reclamos": len(recl), "monto_nc": float(sum(x["monto_esperado"] for x in recl))}


def plantilla_ventas() -> bytes:
    import io
    df = pd.DataFrame({
        "CLIENTE": ["JUAN PEREZ QUISPE", "COMERCIAL ANDINA S.A.C."],
        "DNI/CE/RUC": ["45879632", "20100017491"],
        "MODELO": ["GALAXY A16 128GB", "REDMI NOTE 14 256GB"],
        "IMEI": ["356938035643809", "490154203237518"],
        "PRECIO": [649.00, 799.00],
        "FECHA": [hoy().strftime("%d/%m/%Y")] * 2,
        "MODALIDAD": ["PORTABILIDAD", "ALTA NUEVA"],
        "CONTADO/CUOTAS": ["CONTADO", "CUOTAS"],
        "#CUOTAS": [0, 12],
        "BO": ["", ""],
        "MOTORIZADO": ["", ""],
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        df.to_excel(xw, sheet_name="VENTAS", index=False)
        wb, ws = xw.book, xw.sheets["VENTAS"]
        head = wb.add_format({"bold": True, "bg_color": "#0B1E3F", "font_color": "white", "border": 1})
        opc = wb.add_format({"bold": True, "bg_color": "#64748B", "font_color": "white", "border": 1})
        txt = wb.add_format({"num_format": "@"})
        for i, c in enumerate(df.columns):
            ws.write(0, i, c, opc if c in ("BO", "MOTORIZADO") else head)
        ws.set_column(0, 0, 30)
        ws.set_column(1, 1, 14, txt)
        ws.set_column(2, 2, 24)
        ws.set_column(3, 3, 20, txt)
        ws.set_column(4, 10, 15)
        for r in range(2):
            ws.write_string(r + 1, 1, df.iloc[r]["DNI/CE/RUC"])
            ws.write_string(r + 1, 3, df.iloc[r]["IMEI"])
        ws.data_validation(1, 7, 5000, 7, {"validate": "list", "source": ["CONTADO", "CUOTAS"]})
        nota = wb.add_worksheet("INSTRUCCIONES")
        for i, l in enumerate([
            "INSTRUCCIONES – IMPORTACIÓN MASIVA DE VENTAS",
            "Columnas obligatorias: CLIENTE, DNI/CE/RUC, MODELO, IMEI, PRECIO, FECHA, MODALIDAD, CONTADO/CUOTAS, #CUOTAS.",
            "Columnas opcionales (gris): BO y MOTORIZADO.",
            "DNI/CE/RUC y IMEI deben estar en formato TEXTO para no perder ceros ni dígitos.",
            "El tipo de documento se detecta solo: 8 dígitos = DNI, 11 dígitos = RUC, otro = CE.",
            "FECHA en formato DD/MM/AAAA. MODALIDAD: PORTABILIDAD, ALTA NUEVA, RENOVACIÓN, etc.",
            "CONTADO/CUOTAS: escriba CONTADO o CUOTAS. #CUOTAS: 0 si es contado; número de cuotas si es en cuotas.",
            "El IMEI debe existir en el inventario y estar DISPONIBLE. Si el precio es menor al costo, se crea el reclamo de NC.",
        ]):
            nota.write(i, 0, l)
        nota.set_column(0, 0, 120)
    return buf.getvalue()
