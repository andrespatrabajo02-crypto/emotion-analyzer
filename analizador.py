import time
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from textblob import TextBlob
from deep_translator import GoogleTranslator
from langdetect import detect

# --- Autenticación con Google Sheets ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
client = gspread.authorize(credentials)

# --- Abrir hoja ---
sheet = client.open("sheetspython").sheet1

def detectar_idioma(texto):
    """Detecta idioma usando langdetect"""
    try:
        return detect(texto)
    except Exception:
        return "en"

def traducir_texto(texto, destino='en'):
    """Traduce texto usando deep-translator"""
    try:
        idioma_origen = detectar_idioma(texto)
        if idioma_origen != destino:
            traduccion = GoogleTranslator(source=idioma_origen, target=destino).translate(texto)
            return traduccion
        else:
            return texto
    except Exception as e:
        print(f"⚠️ Error traduciendo: {e}")
        return texto

def dividir_texto(texto, idioma):
    """Divide el texto en oraciones más inteligentemente"""
    # Primero dividir por puntos, signos de exclamación e interrogación
    oraciones = re.split(r'[.!?]+', texto)
    
    frases_finales = []
    for oracion in oraciones:
        oracion = oracion.strip()
        if not oracion:
            continue
            
        # Si la oración es muy larga (más de 15 palabras), dividir por conectores
        palabras = oracion.split()
        if len(palabras) > 15:
            if idioma.startswith("es"):
                conectores = r'\b(pero|aunque|sin embargo|además|mientras|cuando|porque)\b'
            else:
                conectores = r'\b(but|although|however|besides|while|when|because)\b'
            
            sub_frases = re.split(f'({conectores})', oracion, flags=re.IGNORECASE)
            temp = ""
            for i, parte in enumerate(sub_frases):
                temp += parte + " "
                # Añadir cuando tenga suficiente contenido
                if i % 2 == 0 and temp.strip() and len(temp.split()) >= 5:
                    frases_finales.append(temp.strip())
                    temp = ""
            if temp.strip():
                frases_finales.append(temp.strip())
        else:
            frases_finales.append(oracion)
    
    return frases_finales

def analizar_emocion(frase):
    """Analiza polaridad de una frase con detección mejorada"""
    analisis = TextBlob(frase)
    polaridad = analisis.sentiment.polarity
    subjetividad = analisis.sentiment.subjectivity
    
    # Palabras clave para ajustar polaridad
    frase_lower = frase.lower()
    
    # Palabras negativas que TextBlob a veces pierde
    palabras_negativas = ['miss', 'lonely', 'afraid', 'scared', 'worried', 'pain', 
                          'hurt', 'sad', 'alone', 'anxious', 'nervous']
    # Palabras positivas
    palabras_positivas = ['hope', 'better', 'grateful', 'thankful', 'happy', 
                          'good', 'great', 'wonderful', 'improve', 'recovering']
    
    # Ajustar polaridad basado en palabras clave
    for palabra in palabras_negativas:
        if palabra in frase_lower:
            polaridad -= 0.15  # Penalizar más
    
    for palabra in palabras_positivas:
        if palabra in frase_lower:
            polaridad += 0.1  # Bonificar

    # Rangos ajustados para mejor detección
    if polaridad >= 0.3:
        emocion = "Alegría 😄"
    elif 0.05 <= polaridad < 0.3:
        emocion = "Tranquilidad 🙂"
    elif -0.05 < polaridad < 0.05:
        emocion = "Neutral 😐"
    elif -0.3 <= polaridad <= -0.05:
        emocion = "Tristeza 😔"
    else:
        emocion = "Enojo 😡"

    return emocion, round(polaridad, 2), round(subjetividad, 2)

def analizar_texto_completo(texto):
    """Detecta idioma, divide, traduce y analiza emoción"""
    idioma = detectar_idioma(texto)
    print(f"🌍 Idioma detectado: {idioma}")
    
    frases = dividir_texto(texto, idioma)

    resultados = []
    for frase in frases:
        # Traduce cada frase
        frase_traducida = traducir_texto(frase, destino='en')
        print(f"  📝 Original: '{frase}'")
        print(f"  🔄 Traducido: '{frase_traducida}'")
        
        emocion, polaridad, subjetividad = analizar_emocion(frase_traducida)
        resultados.append(f"'{frase}' → {emocion} (pol: {polaridad}, subj: {subjetividad})")

    return "\n".join(resultados)

# --- Monitoreo en bucle ---
print("📡 Monitoreando Google Sheet en la nube...")

valor_anterior = ""
while True:
    try:
        texto = sheet.acell('A3').value
        if texto and texto != valor_anterior:
            resultados = analizar_texto_completo(texto)
            sheet.update_acell('B3', resultados)
            print(f"\n🆕 Texto nuevo: '{texto}'")
            print("🧠 Emociones detectadas:\n" + resultados)
            valor_anterior = texto
    except Exception as e:
        print(f"❌ Error en el bucle principal: {e}")
    
    time.sleep(10)
