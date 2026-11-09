#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pruebas del arranque en modo nube (Railway): se inicia el programa de verdad con
"python app.py --nube" y la variable PORT, y se comprueba que responda.
Si existen los archivos de Railway (railway.json, Procfile...) también se revisan.

Ejecutar:   python pruebas_nube.py
"""

import json
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))


def puerto_libre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def pedir(puerto, ruta, cuerpo=None):
    datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{puerto}{ruta}", data=datos,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.read().decode("utf-8")


class Arranque(unittest.TestCase):
    def test_arranca_con_nube_y_port(self):
        puerto = puerto_libre()
        entorno = dict(os.environ, PORT=str(puerto))
        for k in ("ACCESO_USUARIO", "ACCESO_CLAVE"):
            entorno.pop(k, None)
        proc = subprocess.Popen([sys.executable, "app.py", "--nube"], cwd=AQUI, env=entorno,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
        try:
            listo = False
            for _ in range(60):
                try:
                    if pedir(puerto, "/api/salud")[0] == 200:
                        listo = True
                        break
                except (urllib.error.URLError, ConnectionError):
                    time.sleep(0.2)
            self.assertTrue(listo, "el servidor no respondió en /api/salud")
            self.assertEqual(json.loads(pedir(puerto, "/api/modo")[1]), {"nube": True})
            estado, html = pedir(puerto, "/")
            self.assertEqual(estado, 200)
            self.assertIn("MiCompilador", html)
            _, r = pedir(puerto, "/api/ejecutar", {"codigo": 'Mensaje.Texto("Hola Mundo");'})
            self.assertEqual(json.loads(r)["salida"], ["Hola Mundo"])
            _, r = pedir(puerto, "/api/ejecutar", {"codigo": "a1 entero;"})
            self.assertEqual(json.loads(r)["compilacion"]["errores"][0]["codigo"], "E-SIN-26")
            # sigue vivo después de simular que la ventana se cerró
            pedir(puerto, "/api/cerrar", {})
            time.sleep(5)
            self.assertIsNone(proc.poll(), "el servidor se apagó al 'cerrar la ventana'")
            self.assertEqual(pedir(puerto, "/api/salud")[0], 200)
        finally:
            proc.terminate()
            try:
                salida, _ = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                salida, _ = proc.communicate()
        self.assertIn("modo nube", salida)
        self.assertNotIn("Traceback", salida)


@unittest.skipUnless(os.path.isfile(os.path.join(AQUI, "railway.json")), "esta carpeta no es la de Railway")
class ArchivosDeRailway(unittest.TestCase):
    def leer(self, nombre):
        with open(os.path.join(AQUI, nombre), encoding="utf-8") as f:
            return f.read()

    def test_railway_json(self):
        cfg = json.loads(self.leer("railway.json"))
        deploy = cfg["deploy"]
        self.assertIs(deploy["sleepApplication"], True)                 # Serverless activado
        self.assertEqual(deploy["startCommand"], "python app.py --nube")
        self.assertEqual(deploy["healthcheckPath"], "/api/salud")
        self.assertEqual(cfg["build"]["builder"], "RAILPACK")

    def test_procfile_y_python(self):
        self.assertEqual(self.leer("Procfile").strip(), "web: python app.py --nube")
        self.assertTrue(self.leer(".python-version").strip().startswith("3."))
        self.assertTrue(os.path.isfile(os.path.join(AQUI, "requirements.txt")))

    def test_gitignore_protege_las_claves(self):
        g = self.leer(".gitignore")
        for patron in ("ia_config.json", ".env"):
            self.assertIn(patron, g)

    def test_la_guia_existe_y_explica_serverless(self):
        g = self.leer("RAILWAY.md")
        for texto in ("sleepApplication", "ANTHROPIC_API_KEY", "Serverless", "2026-12-01"):
            self.assertIn(texto, g)

    def test_el_codigo_no_hace_nada_en_segundo_plano_en_la_nube(self):
        # La página no debe hacer latidos en la nube (mantendrían despierto el servicio).
        with open(os.path.join(AQUI, "web", "app.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("if (modoNube) return;", js)
        self.assertNotIn("setInterval(latido", js.replace("setInterval(latido, 2000);", "", 1))


if __name__ == "__main__":
    unittest.main(verbosity=1)
