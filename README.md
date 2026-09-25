# ERP de Inventario – Distribuidor Autorizado Claro

Sistema web (Streamlit + Python) para controlar equipos móviles en consignación y SIM card: ingreso por IMEI/ICCID, alertas de 90 días, ventas al cliente final, control de precio de compra vs. precio de venta y seguimiento de notas de crédito de Claro.

Todo el software usado es **gratuito**: Streamlit Community Cloud (hosting), Supabase (base de datos PostgreSQL) y GitHub (código).

---

## 1. Módulos

| Módulo | Qué hace |
|---|---|
| **Dashboard** | Stock de equipos y SIM, valor del inventario, ventas del mes, alertas (por vencer / vencidos / NC por reclamar), antigüedad del stock, stock por marca, ventas de 30 días, top 10 de rotación, control compra vs. venta. |
| **Inventarios** | Stock por modelo y por IMEI con filtros; alertas de vencimiento con calendario; **control de IMEI** (trazabilidad completa y verificación masiva para inventarios físicos); kardex por modelo; reporte de rotación; ajustes (devolución a Claro, baja, corrección de precio). |
| **Compras** | Importación masiva por Excel (miles de IMEI) con validación previa; registro manual con lector de código de barras; historial de lotes. |
| **Ventas** | Registro de venta leyendo el IMEI: cliente (DNI / CE / RUC validados), marca, modelo, IMEI, precio, BO y motorizado. Listado, anulación, registro de facturas de Claro (individual o Excel) y reporte por motorizado. |
| **Gestión de Reclamo** | Bandeja de notas de crédito pendientes, generación del correo formal a Claro con adjunto Excel, registro de NC (total / parcial, individual o Excel) e historial de cada reclamo. |
| **Usuarios y Configuración** | Usuarios y roles, parámetros (90 días, alerta 15 días, días de espera de NC, correos de Claro), auditoría y respaldo en Excel. |

## 2. Reglas de negocio implementadas

1. **Consignación y 90 días.** Cada IMEI toma como fecha de inicio la *fecha de compra/ingreso*. Fecha límite = compra + 90 días. Estados de alerta: 🟢 en plazo · 🟠 por vencer (faltan 15 días o menos) · 🔴 vencido. Los días son configurables.
2. **Control de IMEI.** El IMEI debe tener 15 dígitos y dígito verificador válido (algoritmo Luhn). El ICCID de la SIM debe tener 19-20 dígitos e iniciar con 89. No se permiten duplicados (ni en el archivo ni contra la base), no se puede vender un IMEI inexistente y no se puede vender dos veces el mismo IMEI. Un mismo BO no se puede usar en dos ventas activas.
3. **Precio de compra vs. venta.** Al registrar la venta se calcula `diferencia = precio de venta − precio de compra`. Si es negativa, el sistema crea automáticamente un **reclamo en estado PENDIENTE NC** por el monto de la diferencia.
4. **Factura de Claro después de la venta.** Al registrar la factura que emite Claro, si el monto facturado difiere del precio de compra registrado, el sistema recalcula la diferencia y el monto de NC esperado (o crea el reclamo si recién aparece la pérdida).
5. **Flujo del reclamo.** PENDIENTE NC → (sin NC después de *N* días, por defecto 7) se sugiere **📧 RECLAMAR** → al enviar el correo pasa a **RECLAMADO** → al registrar la NC pasa a **NC RECIBIDA**, o a **NC PARCIAL** si el monto es menor (queda saldo por reclamar). También puede cerrarse manualmente con un motivo. Si la venta se anula, el reclamo queda ANULADO.
6. **Validación de documentos.** DNI de 8 dígitos; CE de 8 a 12 caracteres alfanuméricos; RUC de 11 dígitos con prefijo 10/15/17/20 y dígito verificador SUNAT.

## 3. Roles

| Rol | Acceso |
|---|---|
| Administrador | Todo, incluido usuarios y parámetros |
| Finanzas / Contabilidad | Todos los módulos (excepto usuarios); anula ventas y gestiona reclamos |
| Logística / Almacén | Dashboard, Inventarios y Compras |
| Ventas | Dashboard, Inventarios (consulta) y Ventas |

Primer ingreso: **admin / admin123**. El sistema pide cambiar la contraseña al entrar.

## 4. Estructura del Excel de importación

| MODELO | MARCA | IMEI | PRECIO | N_FACTURA |
|---|---|---|---|---|
| GALAXY A16 128GB | SAMSUNG | 356938035643809 | 649.00 | F001-000123 |

- La columna **IMEI debe estar en formato Texto** en Excel (si queda como número, Excel puede redondear las series largas).
- Para SIM card se coloca el ICCID en la columna IMEI y se elige *Tipo = SIM* al importar.
- La fecha de compra, el tipo y la modalidad se eligen en la pantalla al importar.
- También se aceptan los encabezados `# FACTURA`, `NRO FACTURA`, `N° FACTURA` o `ICCID`.
- La plantilla se descarga desde **Compras → Importar Excel → Descargar plantilla**.

---

## 5. Publicarlo en internet GRATIS (paso a paso)

### Paso 1 – Crear la base de datos (Supabase)
1. Entre a https://supabase.com y cree una cuenta gratuita.
2. Haga clic en **New project**, asígnele un nombre (ej. `erp-claro`), elija una contraseña de base de datos (guárdela) y la región **South America (São Paulo)** si está disponible.
3. Cuando termine de crearse, haga clic en el botón **Connect** (parte superior) → pestaña **Connection string** → opción **Session pooler**. Copie la cadena, que se ve así:
   `postgresql://postgres.xxxxx:[YOUR-PASSWORD]@aws-0-sa-east-1.pooler.supabase.com:5432/postgres`
4. Reemplace `[YOUR-PASSWORD]` por la contraseña del paso 2.

> Las tablas se crean solas la primera vez que se abre el ERP.

### Paso 2 – Subir el código a GitHub
1. Cree una cuenta en https://github.com.
2. Haga clic en **New repository**, nombre `erp-claro`, marque **Private** y cree el repositorio.
3. Haga clic en **uploading an existing file** y arrastre **todo el contenido** de esta carpeta (incluida la carpeta `.streamlit`, `core` y `modulos`). Luego **Commit changes**.
   - Si no ve la carpeta `.streamlit` (en Windows/Mac las carpetas que empiezan con punto a veces están ocultas), active "mostrar archivos ocultos". Esa carpeta solo da los colores; el sistema funciona igual sin ella.

### Paso 3 – Publicar la app (Streamlit Community Cloud)
1. Entre a https://share.streamlit.io e ingrese con su cuenta de GitHub.
2. **Create app** → **Deploy a public app from GitHub** → elija el repositorio `erp-claro`, rama `main`, archivo principal `app.py`.
3. Haga clic en **Advanced settings**, elija Python 3.12 y en **Secrets** pegue:
   ```toml
   DATABASE_URL = "postgresql://postgres.xxxxx:SU_CLAVE@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
   ```
4. **Deploy**. En unos minutos tendrá una dirección del tipo `https://erp-claro.streamlit.app`.
5. Ingrese con **admin / admin123**, cambie la contraseña y cree los usuarios del equipo en **Usuarios y Configuración**. Configure ahí también el correo de Claro para reclamos y el RUC de la empresa.

### (Opcional) Enviar el correo de reclamo directamente desde el ERP
Agregue en *Secrets*:
```toml
[smtp]
host = "smtp.office365.com"   # o smtp.gmail.com
port = 587
usuario = "finanzas@suempresa.com.pe"
password = "CONTRASEÑA_DE_APLICACION"
remitente = "finanzas@suempresa.com.pe"
```
Sin esta sección el ERP genera el texto del correo y el Excel adjunto para enviarlos desde Outlook.

### Consideraciones del plan gratuito
- Streamlit Community Cloud pone la app en reposo si no recibe visitas por un tiempo; al entrar se despierta en unos segundos.
- Supabase gratuito pausa el proyecto si pasa varios días sin uso; con uso diario no ocurre. Si se pausa, se reactiva desde el panel de Supabase sin perder datos.
- Descargue el **respaldo en Excel** semanalmente (Usuarios y Configuración → Respaldo).

---

## 6. Ejecutarlo en una PC (opcional, sin internet)
1. Instale Python 3.11 o superior desde https://www.python.org (marque *Add Python to PATH*).
2. Abra una terminal en esta carpeta y ejecute:
   ```
   pip install -r requirements.txt
   streamlit run app.py
   ```
3. Se abrirá el navegador en `http://localhost:8501`. Sin `DATABASE_URL` los datos se guardan en `data/erp.db` (SQLite).

Datos de demostración (opcional, solo para pruebas): `python generar_datos_prueba.py --cargar`

## 7. Estructura del proyecto
```
app.py                  Login, menú y navegación por rol
core/db.py              Tablas y conexión (SQLite local / PostgreSQL nube)
core/servicios.py       Reglas de negocio (importación, ventas, reclamos, kardex, rotación)
core/auth.py            Contraseñas cifradas (PBKDF2) y permisos
core/utils.py           Validaciones IMEI/ICCID/DNI/CE/RUC, formatos y Excel
modulos/*.py            Pantallas de cada módulo
generar_datos_prueba.py Datos de demostración y archivo de ejemplo
```
