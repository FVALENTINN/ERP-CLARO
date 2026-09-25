"""Utilidades: fechas Lima, validaciones (IMEI, ICCID, DNI, CE, RUC), formatos y Excel."""
import io
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

TZ = ZoneInfo("America/Lima")


def ahora() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)


def hoy() -> date:
    return ahora().date()


# ------------------------------------------------------------ validaciones
def limpiar_serie(valor) -> str:
    """Normaliza IMEI/ICCID que vienen de Excel (float, notación científica, espacios)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    if isinstance(valor, float):
        valor = f"{valor:.0f}"
    s = str(valor).strip().upper()
    if s.endswith(".0"):
        s = s[:-2]
    return re.sub(r"[\s\-\.]", "", s)


def luhn_ok(numero: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(numero)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def validar_imei(imei: str):
    """Devuelve (ok, mensaje). IMEI = 15 dígitos con dígito verificador Luhn."""
    if not imei:
        return False, "IMEI vacío"
    if not imei.isdigit():
        return False, "IMEI contiene caracteres no numéricos"
    if len(imei) != 15:
        return False, f"IMEI debe tener 15 dígitos (tiene {len(imei)})"
    if not luhn_ok(imei):
        return False, "IMEI con dígito verificador inválido (Luhn)"
    return True, "OK"


def validar_iccid(iccid: str):
    """ICCID de SIM: 19-20 dígitos; en Perú inicia con 8951."""
    s = iccid.rstrip("F")
    if not s:
        return False, "ICCID vacío"
    if not s.isdigit():
        return False, "ICCID contiene caracteres no numéricos"
    if len(s) not in (19, 20):
        return False, f"ICCID debe tener 19 o 20 dígitos (tiene {len(s)})"
    if not s.startswith("89"):
        return False, "ICCID debe iniciar con 89"
    return True, "OK"


def validar_serie(tipo: str, serie: str):
    return validar_imei(serie) if tipo == "EQUIPO" else validar_iccid(serie)


def validar_documento(tipo_doc: str, nro: str):
    nro = (nro or "").strip().upper()
    if tipo_doc == "DNI":
        if not (nro.isdigit() and len(nro) == 8):
            return False, "El DNI debe tener 8 dígitos"
    elif tipo_doc == "CE":
        if not (re.fullmatch(r"[A-Z0-9]{8,12}", nro)):
            return False, "El CE debe tener entre 8 y 12 caracteres alfanuméricos"
    elif tipo_doc == "RUC":
        if not (nro.isdigit() and len(nro) == 11 and nro[:2] in ("10", "15", "17", "20")):
            return False, "El RUC debe tener 11 dígitos e iniciar con 10, 15, 17 o 20"
        pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
        s = sum(int(nro[i]) * pesos[i] for i in range(10))
        dv = 11 - (s % 11)
        dv = 0 if dv == 10 else (1 if dv == 11 else dv)
        if dv != int(nro[10]):
            return False, "RUC con dígito verificador inválido"
    else:
        return False, "Tipo de documento no válido"
    return True, "OK"


# ------------------------------------------------------------ formatos
def soles(x) -> str:
    try:
        return f"S/ {float(x):,.2f}"
    except (TypeError, ValueError):
        return "S/ 0.00"


def soles0(x) -> str:
    """Formato corto para tarjetas (sin decimales)."""
    try:
        x = float(x)
        if abs(x) >= 1_000_000:
            return f"S/ {x / 1_000_000:,.2f} M"
        return f"S/ {x:,.0f}"
    except (TypeError, ValueError):
        return "S/ 0"


def a_fecha(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, errors="coerce").dt.date


def to_excel(hojas: dict) -> bytes:
    """hojas = {"Nombre": DataFrame} → bytes .xlsx con encabezado formateado."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        wb = xw.book
        head = wb.add_format({"bold": True, "bg_color": "#0B1E3F", "font_color": "white", "border": 1})
        for nombre, df in hojas.items():
            df = df.copy()
            df.to_excel(xw, sheet_name=nombre[:31], index=False)
            ws = xw.sheets[nombre[:31]]
            for i, col in enumerate(df.columns):
                ws.write(0, i, col, head)
                ancho = max(len(str(col)), *(len(str(v)) for v in df[col].head(200))) if len(df) else len(str(col))
                ws.set_column(i, i, min(max(ancho + 2, 10), 45))
            ws.freeze_panes(1, 0)
    return buf.getvalue()


def plantilla_importacion() -> bytes:
    """Plantilla Excel con la estructura Modelo - Marca - IMEI - Precio - N° Factura."""
    buf = io.BytesIO()
    df = pd.DataFrame({
        "MODELO": ["GALAXY A15 128GB", "REDMI 13C 256GB"],
        "MARCA": ["SAMSUNG", "XIAOMI"],
        "IMEI": ["356938035643809", "490154203237518"],
        "PRECIO": [599.00, 529.00],
        "N_FACTURA": ["F001-000123", "F001-000123"],
        "CATEGORIA": ["MOVIL", "IFI"],
    })
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        df.to_excel(xw, sheet_name="IMEIS", index=False)
        wb, ws = xw.book, xw.sheets["IMEIS"]
        head = wb.add_format({"bold": True, "bg_color": "#0B1E3F", "font_color": "white", "border": 1})
        txt = wb.add_format({"num_format": "@"})
        for i, c in enumerate(df.columns):
            ws.write(0, i, c, head)
        ws.set_column(0, 0, 28)
        ws.set_column(1, 1, 14)
        ws.set_column(2, 2, 22, txt)   # IMEI como TEXTO para no perder dígitos
        ws.set_column(3, 3, 12)
        ws.set_column(4, 4, 16, txt)
        ws.set_column(5, 5, 14)
        ws.data_validation(1, 5, 20000, 5, {"validate": "list", "source": ["MOVIL", "IFI", "TFI", "OLO"]})
        for r in range(1, 3):
            ws.write_string(r, 2, df.iloc[r - 1]["IMEI"])
        nota = wb.add_worksheet("INSTRUCCIONES")
        lineas = [
            "INSTRUCCIONES DE IMPORTACIÓN",
            "1. No cambie el nombre de las columnas: MODELO, MARCA, IMEI, PRECIO, N_FACTURA.",
            "2. La columna IMEI debe tener formato TEXTO (15 dígitos). Para SIM card use el ICCID (19-20 dígitos).",
            "3. PRECIO = precio de compra a Claro por unidad (sin símbolo S/).",
            "4. N_FACTURA = número de factura o guía de remisión del ingreso.",
            "5. La fecha de compra y el tipo (EQUIPO / SIM) se eligen en el sistema al importar.",
            "5b. CATEGORIA (opcional): MOVIL, IFI, TFI u OLO. Si se deja vacía se usa la categoría elegida en pantalla.",
            "6. El sistema rechaza IMEI duplicados, con longitud incorrecta o dígito verificador inválido.",
            "7. Puede importar miles de registros en un solo archivo.",
        ]
        for i, l in enumerate(lineas):
            nota.write(i, 0, l)
        nota.set_column(0, 0, 110)
    return buf.getvalue()


def parse_fecha(v):
    """Convierte fechas de Excel/CSV a date. Acepta fecha real de Excel (AAAA-MM-DD),
    texto DD/MM/AAAA y número de serie de Excel. Devuelve None si no es válida."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s or s.upper() in ("NAN", "NAT", "NONE"):
        return None
    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}", s):          # fecha real de Excel leída como texto
        f = pd.to_datetime(s[:10], format="%Y-%m-%d", errors="coerce")
    elif re.fullmatch(r"\d{5}(\.0+)?", s):                # número de serie de Excel
        f = pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(float(s)))
    else:                                                 # texto DD/MM/AAAA
        f = pd.to_datetime(s, dayfirst=True, errors="coerce")
    return None if pd.isna(f) else f.date()
