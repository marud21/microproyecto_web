"""
Modulo: index.py
API en Flask que expone la logica del microproyecto (validacion,
depuracion, conversion a FNC) como endpoints HTTP para que el
frontend en React los consuma.

Vercel detecta automaticamente este archivo (por estar en /api) y lo
despliega como una funcion serverless.

Endpoints:
    POST /api/validar         -> valida la gramatica recibida
    POST /api/inutiles        -> elimina variables inutiles
    POST /api/inalcanzables   -> elimina variables inalcanzables
    POST /api/nulas           -> elimina producciones nulas
    POST /api/unitarias       -> elimina producciones unitarias
    POST /api/chomsky         -> convierte a Forma Normal de Chomsky
    POST /api/completo        -> ejecuta TODO el proceso (modo automatico)

Todos reciben un JSON con la gramatica (ver adaptador.py) y devuelven
un JSON con la gramatica resultante + el/los pasos de historial
generados en esa llamada.
"""

import os
import sys

# Asegura que la carpeta 'api/' este en el sys.path, ya que en Vercel el
# runtime de Python importa este archivo desde la raiz del repositorio y
# no desde dentro de 'api/', por lo que "_logica" no se encontraria sin
# esto (causaba: "could not import api/index.py": No module named '_logica').
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify

from _logica.adaptador import gramatica_desde_json, gramatica_a_json, historial_a_json, paso_a_json
from _logica.validador import validar_gramatica
from _logica.depuracion import (
    eliminar_variables_inutiles,
    eliminar_variables_inalcanzables,
    eliminar_producciones_nulas,
    eliminar_producciones_unitarias,
    depurar_gramatica,
)
from _logica.chomsky import convertir_a_fnc, validar_fnc
from _logica.historial import Historial
from _logica.generador import generar_gramatica_aleatoria

app = Flask(__name__)


def _respuesta_error(mensaje, codigo=400):
    return jsonify({"error": mensaje}), codigo


@app.route("/api/validar", methods=["POST"])
def endpoint_validar():
    data = request.get_json(force=True)
    gramatica = gramatica_desde_json(data)

    valida, errores = validar_gramatica(gramatica)
    return jsonify({
        "valida": valida,
        "errores": errores,
        "gramatica": gramatica_a_json(gramatica),
    })


def _ejecutar_fase(data, funcion_fase):
    """
    Helper generico: valida, ejecuta una fase y arma la respuesta JSON.

    Se devuelven TODOS los pasos generados durante la llamada (campo
    "pasos", como lista) y no solo el ultimo: fases como nulas y
    unitarias, ahora registran un paso de historial POR CADA VARIABLE
    procesada (ver depuracion.py), y el frontend (App.jsx) ya sabe
    tomar una lista de pasos y etiquetar el Sigma de cada uno en
    orden.
    Listo.
    """
    gramatica = gramatica_desde_json(data)

    valida, errores = validar_gramatica(gramatica)
    if not valida:
        return jsonify({"error": "La gramatica no es valida.", "errores": errores}), 400

    historial = Historial()
    resultado = funcion_fase(gramatica, historial)

    return jsonify({
        "gramatica": gramatica_a_json(resultado),
        "pasos": historial_a_json(historial),
    })


@app.route("/api/inutiles", methods=["POST"])
def endpoint_inutiles():
    data = request.get_json(force=True)
    return _ejecutar_fase(data, eliminar_variables_inutiles)


@app.route("/api/inalcanzables", methods=["POST"])
def endpoint_inalcanzables():
    data = request.get_json(force=True)
    return _ejecutar_fase(data, eliminar_variables_inalcanzables)


@app.route("/api/nulas", methods=["POST"])
def endpoint_nulas():
    data = request.get_json(force=True)
    return _ejecutar_fase(data, eliminar_producciones_nulas)


@app.route("/api/unitarias", methods=["POST"])
def endpoint_unitarias():
    data = request.get_json(force=True)
    return _ejecutar_fase(data, eliminar_producciones_unitarias)


@app.route("/api/chomsky", methods=["POST"])
def endpoint_chomsky():
    data = request.get_json(force=True)
    gramatica = gramatica_desde_json(data)

    valida, errores = validar_gramatica(gramatica)
    if not valida:
        return jsonify({"error": "La gramatica no es valida.", "errores": errores}), 400

    historial = Historial()
    resultado = convertir_a_fnc(gramatica, historial)

    valida_fnc, invalidas = validar_fnc(resultado)

    return jsonify({
        "gramatica": gramatica_a_json(resultado),
        "pasos": historial_a_json(historial),
        "esFncValida": valida_fnc,
        "produccionesInvalidas": invalidas,
    })


@app.route("/api/completo", methods=["POST"])
def endpoint_completo():
    """Modo automatico: depuracion completa + conversion a FNC de una vez."""
    data = request.get_json(force=True)
    gramatica = gramatica_desde_json(data)

    valida, errores = validar_gramatica(gramatica)
    if not valida:
        return jsonify({"error": "La gramatica no es valida.", "errores": errores}), 400

    historial = Historial()
    depurada = depurar_gramatica(gramatica, historial)
    fnc = convertir_a_fnc(depurada, historial)

    valida_fnc, invalidas = validar_fnc(fnc)

    return jsonify({
        "gramatica": gramatica_a_json(fnc),
        "pasos": historial_a_json(historial),
        "esFncValida": valida_fnc,
        "produccionesInvalidas": invalidas,
    })


@app.route("/api/generar", methods=["GET"])
def endpoint_generar():
    """
    Genera una gramatica aleatoria de practica. El estudiante puede
    intentar resolverla a mano y luego comparar con "Ejecutar proceso
    completo".
    """
    for _ in range(20):  # margen de seguridad, casi siempre valida al primer intento
        data = generar_gramatica_aleatoria()
        gramatica = gramatica_desde_json(data)
        valida, _ = validar_gramatica(gramatica)
        if valida:
            return jsonify({"gramatica": gramatica_a_json(gramatica)})

    return _respuesta_error("No se pudo generar una gramatica de practica. Intenta de nuevo.", 500)


@app.route("/api/health", methods=["GET"])
def endpoint_health():
    """Endpoint simple para confirmar que la API esta viva."""
    return jsonify({"status": "ok"})


# Punto de entrada local (no se usa en Vercel, solo para pruebas locales
# con `python api/index.py`)
if __name__ == "__main__":
    app.run(debug=True, port=5000)