# Importación de librerías necesarias
from flask import Flask, request, render_template, send_file
import pandas as pd
import os
from io import BytesIO
import re
from datetime import datetime, date
import unicodedata
import string

# Inicialización de la app Flask
app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Variable global para almacenar el Excel generado
ultimo_excel = BytesIO()
tipo_actual = ""

# Función para normalizar textos (eliminar tildes, pasar a mayúsculas, eliminar símbolos)
def normalizar_texto(texto):
    texto = re.sub(r'^\d+\.*\s*', '', texto)
    texto = unicodedata.normalize('NFD', texto.upper())
    texto = texto.encode('ascii', 'ignore').decode('utf-8')
    texto = re.sub(r'[^\w\s]', '', texto)
    return texto.strip()

# Función que calcula la edad a partir de una fecha
def calcular_edad(nacimiento):
    hoy = date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))

# Función que verifica si hoy es el cumpleaños
def es_cumple(hoy, nacimiento):
    return hoy.day == nacimiento.day and hoy.month == nacimiento.month

# Función para eliminar caracteres ilegales para Excel
def limpiar_caracteres_illegales(val):
    if isinstance(val, str):
        return ''.join(ch for ch in val if ch in string.printable)
    return val

# Ruta principal
@app.route("/")
def index():
    return render_template("index.html")

# Procesamiento del archivo
@app.route("/procesar", methods=["POST"])
def procesar():
    global ultimo_excel, tipo_actual
    archivo = request.files["archivo"]
    tipo = request.form.get("tipo")
    tipo_actual = tipo
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
            lineas = [line.strip().strip('"') for line in f if line.strip()]
        for linea in lineas:
            partes = re.split(r"\t|;|,", linea)
            if len(partes) != 2:
                continue
            nombre, fecha_raw = partes
            fecha_raw = fecha_raw.strip().replace("-", "/").replace(".", "/")
            try:
                fecha_obj = datetime.strptime(fecha_raw, "%d/%m/%Y")
            except:
                try:
                    fecha_obj = datetime.strptime(fecha_raw, "%Y/%m/%d")
                except:
                    fecha_obj = None

            if fecha_obj:
                fecha_chile = fecha_obj.strftime("%d/%m/%Y")
                edad = str(calcular_edad(fecha_obj.date()))
                flag_cumple = es_cumple(hoy, fecha_obj.date())
            else:
                fecha_chile = fecha_raw
                edad = "Edad no determinada"
                flag_cumple = None

            nombre_n = normalizar_texto(nombre)
            clave = (nombre_n, fecha_chile)
            if clave in vistos:
                continue
            vistos.add(clave)
            datos.append({"Nombre": nombre.strip(), "Fecha Nacimiento": fecha_chile, "Edad": edad, "Cumpleaños Hoy": flag_cumple})
        df_resultado = pd.DataFrame(datos).sort_values(by="Nombre")

    elif tipo == "texto":
        tipo_actual = "ciudades"
        df.columns = ["Original"]
        df["Normalizado"] = df["Original"].apply(normalizar_texto)
        df_resultado = df.drop_duplicates(subset="Normalizado").sort_values(by="Normalizado")

    elif tipo == "lugares":
        df.columns = ["Lugar", "Dirección", "Georeferencia"]
        df = df.drop_duplicates()

        def extraer_pais(direccion):
            partes = direccion.split(',')
            return partes[-1].strip() if len(partes) > 1 else ""

        def limpiar_direccion(direccion):
            partes = direccion.split(',')
            return ','.join(partes[:-1]).strip() if len(partes) > 1 else direccion.strip()

        df["País"] = df["Dirección"].apply(extraer_pais)
        df["Dirección"] = df["Dirección"].apply(limpiar_direccion)

        lugares = df[["Lugar"]].drop_duplicates().reset_index(drop=True)
        lugares["ID_Lugar"] = lugares.index + 1
        df = df.merge(lugares, on="Lugar")
        df_resultado = df[["ID_Lugar", "Lugar", "Dirección", "Georeferencia", "País"]]

    else:
        return "Tipo de normalización no válido", 400

    df_resultado = df_resultado.applymap(limpiar_caracteres_illegales)

    ultimo_excel = BytesIO()
    nombre_archivo = f"{tipo_actual}_normalizado.xlsx"
    df_resultado.to_excel(ultimo_excel, index=False)
    ultimo_excel.seek(0)

    if tipo_actual == "famosos" and "Cumpleaños Hoy" in df_resultado.columns:
        df_resultado["Cumpleaños Hoy"] = df_resultado["Cumpleaños Hoy"].apply(lambda x: "🎂" if x else "")

    return render_template("resultado.html", tablas=[df_resultado.to_html(classes='data', index=False)], titulo="Resultado")

# Descargar Excel generado
@app.route("/descargar")
def descargar():
    global ultimo_excel, tipo_actual
    if ultimo_excel.getbuffer().nbytes == 0:
        return "❌ No hay ningún archivo procesado aún."
    ultimo_excel.seek(0)
    return send_file(ultimo_excel, download_name=f"{tipo_actual}_normalizado.xlsx", as_attachment=True)

# Ejecutar la app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
