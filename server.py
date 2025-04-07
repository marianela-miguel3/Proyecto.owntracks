from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime

app = Flask(__name__)

# Verificamos que las variables de entorno estén bien definidas
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ ERROR: Las variables de entorno de Supabase no están configuradas correctamente.")

@app.route('/')
def home():
    return "✅ Servidor Flask en Heroku funcionando correctamente 🚀", 200

@app.route('/ubicacion', methods=['POST'])
def recibir_ubicacion():
    data = request.json
    print("📍 Datos recibidos:", data)  # Log para ver la data en los logs de Heroku

    if not data:
        return jsonify({"error": "No se recibieron datos"}), 400

    evento = data.get("event")
    zona = data.get("desc")
    lat = data.get("lat")
    lon = data.get("lon")
    timestamp = data.get("tst")

    print("Evento:", evento)
    print("Zona:", zona)
    print("Lat:", lat)
    print("Lon:", lon)
    print("Timestamp:", timestamp)

    if lat is None or lon is None:
        print("⚠️ Error: Falta latitud o longitud en la data.")
        return jsonify({"error": "latitud o longitud faltante"}), 400

    fecha = datetime.fromtimestamp(timestamp).isoformat() if timestamp else None

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
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

    try:
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/ubicaciones",
            json=payload,
            headers=headers
        )

        print("🔄 Respuesta de Supabase:", response.status_code, response.text)

        if response.status_code >= 400:
            return jsonify({"error": "Error al insertar en Supabase", "detalle": response.text}), response.status_code

        # return jsonify({"status": "ok", "supabase_response": response.json()}), 201
        return jsonify({
          "status": "ok",
          "supabase_status": response.status_code,
          "supabase_text": response.text
        }), 201

    except Exception as e:
        print("❌ Error al conectar con Supabase:", str(e))
        return jsonify({"error": "Error al conectar con Supabase"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)
