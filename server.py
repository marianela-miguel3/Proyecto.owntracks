from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

SUPABASE_URL = os.getenv('https://pgolwcphlsvwkqwpxmdy.supabase.co')
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
@app.route('/ubicacion', methods=['POST'])
def recibir_ubicacion():
    data = request.json
    print("📍 Datos recibidos:", data)

    # OwnTracks puede mandar varios tipos de mensajes, verificamos si es evento de zona
    evento = data.get("event")  # 'enter' o 'leave' si es un evento de geozona
    zona = data.get("desc")     # nombre de la zona (por ejemplo: 'Casa')

    lat = data.get("lat")
    lon = data.get("lon")
    timestamp = data.get("tst")

    # Validación básica
    if lat is None or lon is None:
        return jsonify({"error": "latitud o longitud faltante"}), 400

    # Formateamos timestamp si querés pasarlo en formato ISO (opcional)
    from datetime import datetime
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
        "Content-Type": "application/json"
    }

    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/ubicaciones",
        json=payload,
        headers=headers
    )

    return jsonify({"status": "ok", "supabase_response": response.text}), response.status_code

if __name__ == '__main__':
    app.run()
