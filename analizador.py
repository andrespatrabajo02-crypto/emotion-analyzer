import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from textblob import TextBlob

# --- Autenticación con Google Sheets ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("credenciales.json", scope)
client = gspread.authorize(credentials)

# --- Abrir hoja ---
sheet = client.open("NombreDeTuArchivo").sheet1

def analizar_emocion(texto):
    analisis = TextBlob(texto)
    polaridad = analisis.sentiment.polarity
    if polaridad > 0:
        return "Positiva 😊"
    elif polaridad < 0:
        return "Negativa 😞"
    else:
        return "Neutra 😐"

print("Monitoreando Google Sheet en la nube...")

valor_anterior = ""
while True:
    texto = sheet.acell('A3').value
    if texto and texto != valor_anterior:
        emocion = analizar_emocion(texto)
        sheet.update('B3', emocion)
        print(f"Texto nuevo: '{texto}' → Emoción: {emocion}")
        valor_anterior = texto
    time.sleep(10)