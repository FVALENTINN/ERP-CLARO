"""
Genera datos de prueba (opcional).
  python generar_datos_prueba.py            → crea ejemplo_importacion.xlsx (para probar la importación)
  python generar_datos_prueba.py --cargar   → además carga inventario y ventas de demostración en la BD
"""
import random
import sys
from datetime import timedelta

import pandas as pd

from core.utils import hoy

MODELOS = [
    ("SAMSUNG", "GALAXY A06 64GB", 399), ("SAMSUNG", "GALAXY A16 128GB", 649), ("SAMSUNG", "GALAXY A26 5G 256GB", 999),
    ("SAMSUNG", "GALAXY A56 5G 256GB", 1599), ("XIAOMI", "REDMI 14C 128GB", 449), ("XIAOMI", "REDMI NOTE 14 256GB", 849),
    ("MOTOROLA", "MOTO G05 128GB", 429), ("MOTOROLA", "MOTO G15 256GB", 549), ("MOTOROLA", "EDGE 50 FUSION", 1199),
    ("HONOR", "X6C 128GB", 469), ("HONOR", "X8C 256GB", 899), ("APPLE", "IPHONE 16 128GB", 3999),
    ("ZTE", "BLADE A35 64GB", 299), ("OPPO", "A40 128GB", 599),
]


def imei_valido(tac: str) -> str:
    base = tac + "".join(random.choice("0123456789") for _ in range(14 - len(tac)))
    total = 0
    for i, ch in enumerate(reversed(base)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return base + str((10 - total % 10) % 10)


def iccid(n):
    return f"8951100{random.randint(10**11, 10**12 - 1)}{n % 10}"


def generar_excel(n=3000, archivo="ejemplo_importacion.xlsx"):
    random.seed(7)
    filas = []
    for i in range(n):
        marca, modelo, precio = random.choice(MODELOS)
        filas.append({"MODELO": modelo, "MARCA": marca, "IMEI": imei_valido("35" + str(random.randint(1000, 9999))),
                      "PRECIO": precio, "N_FACTURA": f"F001-{10000 + i // 250:06d}"})
    df = pd.DataFrame(filas)
    # algunos errores intencionales para ver la validación
    df.loc[5, "IMEI"] = df.loc[5, "IMEI"][:-1] + str((int(df.loc[5, "IMEI"][-1]) + 1) % 10)  # Luhn inválido
    df.loc[9, "IMEI"] = df.loc[3, "IMEI"]                                                      # duplicado
    df.loc[12, "IMEI"] = "35123456789"                                                          # longitud
    with pd.ExcelWriter(archivo, engine="xlsxwriter") as xw:
        df.to_excel(xw, index=False, sheet_name="IMEIS")
        xw.sheets["IMEIS"].set_column(2, 2, 20, xw.book.add_format({"num_format": "@"}))
    print(f"{archivo}: {len(df)} filas (3 con error intencional)")
    return df


def cargar_demo():
    from core import db, servicios as sv
    db.get_engine()
    random.seed(11)
    lotes = [(100, 180), (95, 150), (82, 200), (60, 300), (35, 250), (10, 200)]  # (días atrás, cantidad)
    for dias, cant in lotes:
        filas = []
        for _ in range(cant):
            marca, modelo, precio = random.choice(MODELOS)
            filas.append({"MODELO": modelo, "MARCA": marca, "IMEI": imei_valido("35" + str(random.randint(1000, 9999))),
                          "PRECIO": float(precio), "N_FACTURA": f"GR-{random.randint(1000, 9999)}"})
        df = pd.DataFrame(filas).drop_duplicates("IMEI")
        sv.registrar_compra(df, "EQUIPO", hoy() - timedelta(days=dias), "CONSIGNACION", "", "DEMO", "admin")
    sims = pd.DataFrame([{"MODELO": "CHIP CLARO PREPAGO", "MARCA": "CLARO", "IMEI": iccid(i), "PRECIO": 5.0,
                          "N_FACTURA": "F002-000777"} for i in range(400)]).drop_duplicates("IMEI")
    sv.registrar_compra(sims, "SIM", hoy() - timedelta(days=20), "COMPRA DIRECTA", "F002-000777", "DEMO", "admin")

    inv = sv.inventario_df("DISPONIBLE")
    motos = ["JUAN PEREZ", "CARLOS QUISPE", "LUIS RAMOS", "MIGUEL TORRES"]
    vender = inv.sample(frac=0.45, random_state=3)
    for _, it in vender.iterrows():
        fc = pd.Timestamp(it["fecha_compra"])
        f = min(fc + pd.Timedelta(days=random.randint(1, 80)), pd.Timestamp(hoy()))
        pv = it["precio_compra"]
        if it["tipo"] == "EQUIPO" and random.random() < 0.12:
            pv = round(pv - random.choice([20, 30, 50, 80, 100]), 2)  # vendido bajo costo → NC
        sv.registrar_venta({
            "serie": it["serie"], "fecha_venta": f.date(), "tipo_doc": "DNI",
            "nro_doc": f"{random.randint(10000000, 79999999)}", "cliente": "CLIENTE DEMO",
            "precio_venta": pv, "bo": f"BO{random.randint(10**7, 10**8)}", "motorizado": random.choice(motos),
        }, "admin")
    print("Demo cargada:", len(inv), "unidades,", len(vender), "ventas")


if __name__ == "__main__":
    generar_excel()
    if "--cargar" in sys.argv:
        cargar_demo()
