from flask import Flask, request, render_template, send_file
import pandas as pd
import os
from io import BytesIO
import re
from datetime import datetime, date
import unicodedata

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Variable global para almacenar el Excel generado
ultimo_excel = BytesIO()

def normalizar_texto(texto):
    texto = re.sub(r'^\d+\.*\s*', '', texto)
    texto = unicodedata.normalize('NFD', texto.upper())
    texto = texto.encode('ascii', 'ignore').decode('utf-8')
    texto = re.sub(r'[^\w\s]', '', texto)
    return texto.strip()

def parsear_fecha(fecha_raw):
    fecha_raw = fecha_raw.strip().replace("/", "-")
    formatos = ["%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"]
    for fmt in formatos:
        try:
            return datetime.strptime(fecha_raw, fmt)
        except:
            continue
    return None

def calcular_edad(nacimiento):
    hoy = date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))

def es_cumple(hoy, nacimiento):
    return hoy.day == nacimiento.day and hoy.month == nacimiento.month

def procesar_fecha_inexacta(texto_fecha):
    texto_fecha = texto_fecha.strip()
    if "a.C" in texto_fecha or "a. C" in texto_fecha:
        m1 = re.search(r"alrededor.*?(\d+)\s*a\.?C\.?", texto_fecha, re.IGNORECASE)
        if m1:
            anio = int(m1.group(1))
            return f"01/01/{anio} a.C.", f"{date.today().year + anio - 1} años aprox.", False
        m2 = re.search(r"(\d+)\s*a\.?C\.?[/-](\d{2})[/-](\d{2})", texto_fecha)
        if m2:
            anio, mes, dia = int(m2.group(1)), m2.group(2), m2.group(3)
            return f"{dia}/{mes}/{anio} a.C.", f"{date.today().year + anio - 1} años aprox.", False
        m3 = re.match(r"^(\d+)\s*a\.?C\.?", texto_fecha)
        if m3:
            anio = int(m3.group(1))
            return f"01/01/{anio} a.C.", f"{date.today().year + anio - 1} años aprox.", False
    m4 = re.search(r"alrededor.*?(\d{3,4})$", texto_fecha, re.IGNORECASE)
    if m4:
        anio = int(m4.group(1))
        try:
            fecha_obj = datetime(anio, 1, 1)
            edad = str(calcular_edad(fecha_obj.date()))
            return fecha_obj.strftime("%d-%m-%Y"), edad, False
        except:
            return texto_fecha, "INCALCULABLE", None
    m5 = re.match(r"^(\d{3,4})$", texto_fecha)
    if m5:
        anio = int(m5.group(1))
        try:
            fecha_obj = datetime(anio, 1, 1)
            edad = str(calcular_edad(fecha_obj.date()))
            return fecha_obj.strftime("%d-%m-%Y"), edad, False
        except:
            return texto_fecha, "INCALCULABLE", None
    return texto_fecha, "INCALCULABLE", None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/procesar", methods=["POST"])
def procesar():
    global ultimo_excel

    archivo = request.files["archivo"]
    tipo = request.form.get("tipo")
    if not archivo:
        return "No se envió ningún archivo", 400

    ruta = os.path.join(UPLOAD_FOLDER, archivo.filename)
    archivo.save(ruta)

    try:
        df = pd.read_csv(ruta, sep=";", header=None, engine="python", encoding="latin1")
    except Exception as e:
        return f"Error al leer archivo: {e}"

    if tipo == "famosos":
        datos = []
        hoy = date.today()
        vistos = set()
        with open(ruta, 'r', encoding='latin1') as f:
            lineas = [line.strip() for line in f if line.strip()]
        for linea in lineas:
            m = re.match(r"^\d+\.\s*(.*?)\s*-\s*(.*)", linea)
            if not m:
                continue
            nombre, fecha_raw = m.groups()
            fecha_obj = parsear_fecha(fecha_raw)
            if fecha_obj:
                fecha_chile = fecha_obj.strftime("%d-%m-%Y")
                edad = str(calcular_edad(fecha_obj.date()))
                flag_cumple = es_cumple(hoy, fecha_obj.date())
            else:
                fecha_chile, edad, flag_cumple = procesar_fecha_inexacta(fecha_raw)
            nombre_n = normalizar_texto(nombre)
            clave = (nombre_n, fecha_chile)
            if clave in vistos:
                continue
            vistos.add(clave)
            datos.append({"Nombre": nombre.strip(), "Fecha Nacimiento": fecha_chile, "Edad": edad, "Cumpleaños Hoy": flag_cumple})
        df_resultado = pd.DataFrame(datos).sort_values(by="Nombre")

    elif tipo == "texto":
        df.columns = ["Original"]
        df["Normalizado"] = df["Original"].apply(normalizar_texto)
        df_resultado = df.drop_duplicates(subset="Normalizado").sort_values(by="Normalizado")

    elif tipo == "lugares":
        df.columns = ["Lugar", "Dirección", "Georeferencia"]
        df = df.drop_duplicates()
        lugares = df[["Lugar"]].drop_duplicates().reset_index(drop=True)
        lugares["ID_Lugar"] = lugares.index + 1
        df = df.merge(lugares, on="Lugar")
        df_resultado = df[["ID_Lugar", "Lugar", "Dirección", "Georeferencia"]]

    else:
        return "Tipo de normalización no válido", 400

    # Guardar Excel en memoria
    ultimo_excel = BytesIO()
    df_resultado.to_excel(ultimo_excel, index=False)
    ultimo_excel.seek(0)

    return render_template("resultado.html", tablas=[df_resultado.to_html(classes='data', index=False)], titulo="Resultado")

@app.route("/descargar")
def descargar():
    global ultimo_excel
    if ultimo_excel.getbuffer().nbytes == 0:
        return "❌ No hay ningún archivo procesado aún."
    ultimo_excel.seek(0)
    return send_file(ultimo_excel, download_name="datos_normalizados.xlsx", as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)

