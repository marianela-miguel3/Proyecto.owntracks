from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime

app = Flask(__name__)

# Leer variables de entorno correctamente
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

@app.route('/')
def home():
    return '<h1>¡Hola, mundo! Mi aplicación está corriendo en Heroku.</h1>'

@app.route('/ubicacion', methods=['POST'])
def recibir_ubicacion():
    data = request.json
    print("📍 Datos recibidos:", data)

    # Extraer datos
    evento = data.get("event")  # 'enter' o 'leave' si es un evento de geozona
    zona = data.get("desc")     # Nombre de la zona (ej: 'Casa')

    lat = data.get("lat")
    lon = data.get("lon")
    timestamp = data.get("tst")

    # Validación
    if lat is None or lon is None:
        return jsonify({"error": "Latitud o longitud faltante"}), 400

    # Convertir timestamp a formato ISO
    fecha = datetime.utcfromtimestamp(timestamp).isoformat() if timestamp else None

    payload = {
        "latitud": lat,
        "longitud": lon,
        "timestamp": fecha,
        "evento": evento,
        "zona": zona
    }

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

    # Enviar datos a Supabase
    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/ubicaciones",
        json=payload,
        headers=headers
    )

    if response.status_code in [200, 201]:
        return jsonify({"status": "ok", "supabase_response": response.text}), response.status_code
    else:
        return jsonify({"error": "Error al insertar en Supabase", "detalle": response.text}), response.status_code

# Configuración para Heroku
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
