from flask import Flask, request, jsonify
import json
import os

app = Flask(__name__)

# Archivo donde se guardarán las ubicaciones
DATA_FILE = "ubicaciones.json"

# Si el archivo no existe, lo creamos con una lista vacía
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        f.write("[]")

@app.route('/owntracks', methods=['POST'])
def receive_location():
    data = request.json
    print("📍 Ubicación recibida:", data)

    # Guardar en el archivo JSON
    with open(DATA_FILE, "r+") as file:
        ubicaciones = json.load(file)  # Cargar datos existentes
        ubicaciones.append(data)  # Agregar nueva ubicación
        file.seek(0)  # Mover al inicio del archivo
        json.dump(ubicaciones, file, indent=4)  # Guardar actualizado

    return jsonify({"status": "ok"}), 200

@app.route('/ubicaciones', methods=['GET'])
def get_locations():
    with open(DATA_FILE, "r") as file:
        ubicaciones = json.load(file)
    return jsonify(ubicaciones)

if __name__ == '__main__':
    # app.run(host="0.0.0.0", port=5000, debug=True)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
