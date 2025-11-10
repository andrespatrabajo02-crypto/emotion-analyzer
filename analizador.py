import time
import gspread
import json
import os
from google.oauth2.service_account import Credentials
from textblob import TextBlob

# --- Autenticación con Google Sheets ---
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# Leer credenciales desde variable de entorno
try:
    # En Render, leeremos desde variable de entorno
    google_creds = os.getenv('GOOGLE_CREDENTIALS_JSON')
    if google_creds:
        creds_dict = json.loads(google_creds)
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    else:
        # Para desarrollo local, usar archivo
        credentials = Credentials.from_service_account_file('key.json', scopes=scope)
    
    client = gspread.authorize(credentials)
    print("✓ Autenticación exitosa")
except Exception as e:
    print(f"❌ Error de autenticación: {e}")
    exit(1)

# --- Abrir hoja ---
try:
    sheet = client.open("sheetspython").sheet1  # Cambia "sheetspython" por el nombre exacto
    print("✓ Hoja abierta correctamente")
except Exception as e:
    print(f"❌ Error al abrir la hoja: {e}")
    exit(1)

def analizar_emocion(texto):
    analisis = TextBlob(texto)  
    polaridad = analisis.sentiment.polarity
    if polaridad > 0:
        return "Positiva 😊"
    elif polaridad < 0:
        return "Negativa 😞"
    else:
        return "Neutra 😐"

print("🔍 Monitoreando Google Sheet en la nube...")

valor_anterior = ""
while True:
    try:
        texto = sheet.acell('A3').value
        if texto and texto != valor_anterior:
            emocion = analizar_emocion(texto)
            sheet.update('B3', emocion)
            print(f"✓ Texto nuevo: '{texto}' → Emoción: {emocion}")
            valor_anterior = texto
    except Exception as e:
        print(f"⚠️ Error: {e}")
    
    time.sleep(10)
