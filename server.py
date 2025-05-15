from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime
from datetime import timezone, timedelta
from flask_cors import CORS

ARGENTINA_TZ = timezone(timedelta(hours=-3))

app = Flask(__name__)
# CORS(app)
# CORS(app, resources={r"/*": {"origins": "*"}})
CORS(app, resources={r"/*": {"origins": "https://project-ifts.netlify.app"}})

# Verificamos que las variables de entorno estén bien definidas
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ ERROR: Las variables de entorno de Supabase no están configuradas correctamente.")

@app.route('/')
def home():
    return "✅ Servidor Flask en Heroku funcionando correctamente 🚀", 200


# Diccionario para mantener el estado de zonas anteriores por dispositivo
zonas_anteriores = {}

@app.route('/ubicacion', methods=['POST'])
def recibir_ubicacion_ou_transicion():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No se recibieron datos"}), 400

        device_id = data.get("device")
        tipo = data.get("_type")
        print("📥 Datos recibidos:", data)

        if tipo not in ["location", "transition"]:
            print("⚠️ Ignorando mensaje: tipo no válido:", tipo)
            return jsonify({"status": "ignored"}), 200

        lat = data.get("lat")
        lon = data.get("lon")
        timestamp = data.get("tst")

        fecha = (
            datetime.fromtimestamp(timestamp, tz=timezone.utc)
            .astimezone(ARGENTINA_TZ)
            .strftime("%Y-%m-%d %H:%M")
            # .replace(second=0, microsecond=0)
            # .isoformat()
        ) if timestamp else None

        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

        def guardar_evento(lat, lon, evento, zona, device):
            payload = {
                "latitud": lat,
                "longitud": lon,
                "evento": evento,
                "zona": zona,
                "timestamp": fecha,
                "device": device
            }
            try:
                resp = requests.post(
                    f"{SUPABASE_URL}/rest/v1/ubicaciones",
                    json=payload,
                    headers=headers
                )
                print("✅ Supabase:", resp.status_code, resp.text)
            except Exception as e:
                print("❌ Error al conectar con Supabase:", str(e))

        if tipo == "transition":
            evento = data.get("event")  # enter o exit
            zona = data.get("desc") or (data.get("inregions")[0] if data.get("inregions") else None)
            guardar_evento(lat, lon, evento, zona, device_id)
            return jsonify({"status": "evento transition guardado"}), 201

        elif tipo == "location":
            inregions_actual = set(data.get("inregions", []))

             # Consultar última zona registrada en Supabase para este device
            try:
                url_historial = f"{SUPABASE_URL}/rest/v1/ubicaciones?device=eq.{device_id}&order=timestamp.desc&limit=1"
                respuesta_historial = requests.get(url_historial, headers=headers)
                ultima_zona = set()

                if respuesta_historial.status_code == 200:
                   registros = respuesta_historial.json()
                   if registros and registros[0]["zona"]:
                       ultima_zona = {registros[0]["zona"]}
            except Exception as e:
               print("⚠️ No se pudo obtener historial de zonas:", str(e))
               ultima_zona = set()

            
            # inregions_anterior = zonas_anteriores.get(device_id, set())

            entradas = inregions_actual - ultima_zona
            salidas = ultima_zona- inregions_actual

            # zonas_anteriores[device_id] = inregions_actual

            for zona in entradas:
                guardar_evento(lat, lon, "enter", zona, device_id)

            for zona in salidas:
                guardar_evento(lat, lon, "leave", zona, device_id)

            # También se guarda ubicación sin evento
            guardar_evento(lat, lon, None, None, device_id)

            return jsonify({"status": "eventos location procesados y guardados"}), 201

    except Exception as e:
        print("❌ Error general:", str(e))
        return jsonify({"error": "Error interno del servidor"}), 500

if __name__ == "__main__":
    app.run(debug=True)


@app.route('/ultima_ubicacion', methods=['GET'])
def obtener_ultima_ubicacion():
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

    url = f"{SUPABASE_URL}/rest/v1/ubicaciones?order=timestamp.desc&limit=1"

    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return jsonify({"error": "No se pudo obtener la ubicación", "detalle": response.text}), response.status_code

        datos = response.json()
        if not datos:
            return jsonify({"mensaje": "No hay ubicaciones registradas"}), 404
        print("Última ubicación:", datos[0])

        return jsonify(datos[0]), 200

    except Exception as e:
        print("❌ Error al consultar Supabase:", str(e))
        return jsonify({"error": "Error interno"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)



