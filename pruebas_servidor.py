#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pruebas del servidor local (app.py): rutas, seguridad y asistente de IA.

Ejecutar:   python pruebas_servidor.py
"""

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer, ThreadingHTTPServer

import app
import costenol_asistente as ia
import pruebas_asistente as simulado


def pedir(base, ruta, cuerpo=None, metodo=None):
    datos = None if cuerpo is None else (cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode("utf-8"))
    req = urllib.request.Request(base + ruta, data=datos, method=metodo or ("POST" if datos is not None else "GET"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            tipo = r.headers.get("Content-Type", "")
            texto = r.read().decode("utf-8")
            return r.status, (json.loads(texto) if "json" in tipo else texto)
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8")
        try:
            return e.code, json.loads(texto)
        except ValueError:
            return e.code, texto


class Servidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api_falsa = HTTPServer(("127.0.0.1", 0), simulado.Falso)
        threading.Thread(target=cls.api_falsa.serve_forever, daemon=True).start()
        os.environ["COSTENOL_API_URL"] = f"http://127.0.0.1:{cls.api_falsa.server_address[1]}/v1/messages"
        cls.carpeta = tempfile.mkdtemp()
        app.CONFIG_IA = ia.Configuracion(os.path.join(cls.carpeta, "ia_config.json"))
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Manejador)
        cls.srv.daemon_threads = True
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        cls._clave_env = os.environ.pop("ANTHROPIC_API_KEY", None)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.api_falsa.shutdown()
        os.environ.pop("COSTENOL_API_URL", None)
        if cls._clave_env is not None:
            os.environ["ANTHROPIC_API_KEY"] = cls._clave_env

    def setUp(self):
        simulado.Falso.respuestas = []
        simulado.Falso.recibidas = []

    # -- página y archivos ------------------------------------------------------
    def test_pagina_y_archivos_estaticos(self):
        for ruta, tipo in (("/", "text/html"), ("/estilos.css", "text/css"), ("/app.js", "javascript"),
                           ("/manual.html", "text/html"), ("/assets/logo_costenol.png", "image/png")):
            req = urllib.request.Request(self.base + ruta)
            with urllib.request.urlopen(req) as r:
                self.assertEqual(r.status, 200, ruta)
                self.assertIn(tipo, r.headers["Content-Type"], ruta)

    def test_no_se_puede_salir_de_la_carpeta_web(self):
        for ruta in ("/../app.py", "/%2e%2e/app.py", "/..%5capp.py", "/assets/../../app.py", "/ia_config.json"):
            estado, _ = pedir(self.base, ruta)
            self.assertEqual(estado, 404, ruta)

    def test_ejemplos_y_catalogo(self):
        estado, ejemplos = pedir(self.base, "/api/ejemplos")
        self.assertEqual(estado, 200)
        self.assertGreaterEqual(len(ejemplos), 10)
        self.assertTrue(all({"archivo", "titulo", "codigo"} <= set(e) for e in ejemplos))
        estado, cat = pedir(self.base, "/api/catalogo")
        self.assertEqual(estado, 200)
        self.assertGreater(len(cat), 50)

    # -- compilar y ejecutar ------------------------------------------------------
    def test_analizar(self):
        estado, r = pedir(self.base, "/api/analizar", {"codigo": 'Mensaje.Texto("Hola Mundo");'})
        self.assertEqual(estado, 200)
        self.assertTrue(r["exitoso"])
        estado, r = pedir(self.base, "/api/analizar", {"codigo": "a1 entero;"})
        self.assertFalse(r["exitoso"])
        self.assertEqual(r["errores"][0]["codigo"], "E-SIN-26")

    def test_ejecutar_hola_mundo(self):
        estado, r = pedir(self.base, "/api/ejecutar", {"codigo": 'Mensaje.Texto("Hola Mundo");'})
        self.assertEqual(r["salida"], ["Hola Mundo"])
        self.assertTrue(r["terminado"])
        self.assertIsNone(r["sesion"])

    def test_ejecutar_con_captura(self):
        codigo = 'n Texto;\nn = Captura.Texto();\nMensaje.Texto("Hola " + n);'
        estado, r = pedir(self.base, "/api/ejecutar", {"codigo": codigo})
        self.assertFalse(r["terminado"])
        self.assertEqual(r["espera"]["variable"], "n")
        sid = r["sesion"]
        estado, r = pedir(self.base, "/api/entrada", {"sesion": sid, "valor": "Ana"})
        self.assertEqual(r["salida"], ["Hola Ana"])
        self.assertTrue(r["terminado"])
        estado, r = pedir(self.base, "/api/entrada", {"sesion": sid, "valor": "x"})
        self.assertEqual(estado, 404)

    def test_ejecutar_con_errores_no_ejecuta(self):
        estado, r = pedir(self.base, "/api/ejecutar", {"codigo": "x = ;"})
        self.assertFalse(r["compilacion"]["exitoso"])
        self.assertIsNone(r["sesion"])
        self.assertEqual(r["salida"], [])

    def test_detener(self):
        codigo = 'n Texto;\nn = Captura.Texto();'
        _, r = pedir(self.base, "/api/ejecutar", {"codigo": codigo})
        sid = r["sesion"]
        self.assertEqual(pedir(self.base, "/api/detener", {"sesion": sid})[0], 200)
        self.assertEqual(pedir(self.base, "/api/entrada", {"sesion": sid, "valor": "x"})[0], 404)

    def test_archivos_para_el_celular(self):
        estado, cab, html = pedir_crudo(self.base, "/")
        self.assertEqual(estado, 200)
        self.assertIn("viewport-fit=cover", html)
        self.assertIn("interactive-widget=resizes-content", html)
        self.assertIn('src="movil.js"', html)
        self.assertIn('id="barra-movil"', html)
        self.assertIn('id="btn-menu"', html)
        self.assertIn('rel="manifest"', html)
        estado, cab, js = pedir_crudo(self.base, "/movil.js")
        self.assertEqual(estado, 200)
        self.assertIn("javascript", cab.get("Content-Type", ""))
        self.assertIn("classList.toggle('movil'", js)
        estado, cab, texto = pedir_crudo(self.base, "/manifest.webmanifest")
        self.assertEqual(estado, 200)
        self.assertIn("manifest+json", cab.get("Content-Type", ""))
        manifiesto = json.loads(texto)
        self.assertEqual(manifiesto["display"], "standalone")
        for icono in manifiesto["icons"]:
            self.assertEqual(pedir_crudo(self.base, "/" + icono["src"])[0], 200)
        self.assertEqual(pedir_crudo(self.base, "/assets/icono-180.png")[0], 200)
        css = pedir_crudo(self.base, "/estilos.css")[2]
        for regla in ("MODO RESPONSIVE", "html.movil .principal", ".barra-movil", "html.movil #asistente"):
            self.assertIn(regla, css)

    def test_json_bomba_no_tumba_el_servidor(self):
        for ruta in ("/api/analizar", "/api/ejecutar", "/api/asistente", "/api/exportar"):
            self.assertEqual(pedir(self.base, ruta, b"[" * 200000)[0], 400, ruta)
            self.assertEqual(pedir(self.base, ruta, b'{"a":' * 100000)[0], 400, ruta)
        self.assertEqual(pedir(self.base, "/api/analizar", {"codigo": ""})[0], 200)

    def test_peticiones_invalidas(self):
        for ruta in ("/api/analizar", "/api/ejecutar", "/api/entrada", "/api/asistente", "/api/ia/config"):
            self.assertEqual(pedir(self.base, ruta, b"esto no es json")[0], 400, ruta)
            self.assertEqual(pedir(self.base, ruta, b"[1,2]")[0], 400, ruta)
        self.assertEqual(pedir(self.base, "/api/analizar", {"codigo": 5})[0], 400)
        self.assertEqual(pedir(self.base, "/api/entrada", {"sesion": 5, "valor": 1})[0], 400)
        self.assertEqual(pedir(self.base, "/api/xyz", {})[0], 404)

    def test_contenido_demasiado_grande(self):
        # El servidor responde 413 y corta la conexión sin leer el cuerpo; según el
        # sistema operativo el cliente ve el 413 o ve la conexión cortada. Ambos son correctos.
        try:
            estado, _ = pedir(self.base, "/api/analizar", b"x" * (app.MAXIMO_CUERPO + 10))
            self.assertEqual(estado, 413)
        except (urllib.error.URLError, ConnectionError):
            pass
        self.assertEqual(pedir(self.base, "/api/analizar", {"codigo": "x Entero;"})[0], 200)  # sigue vivo

    # -- exportar ---------------------------------------------------------------
    def test_formatos_de_exportacion(self):
        estado, f = pedir(self.base, "/api/exportar/formatos")
        self.assertEqual(estado, 200)
        self.assertEqual([x["id"] for x in f], ["python", "javascript", "html", "java_jar", "java_fuente"])

    def test_exportar_a_python_y_ejecutar_lo_exportado(self):
        import base64
        import subprocess
        codigo = 'n Texto;\nn = Captura.Texto();\nMensaje.Texto("Hola " + n);'
        estado, r = pedir(self.base, "/api/exportar", {"codigo": codigo, "formato": "python", "nombre": "mi prog.cst"})
        self.assertEqual(estado, 200)
        self.assertEqual(r["archivo"], "mi_prog.py")
        ruta = os.path.join(self.carpeta, r["archivo"])
        with open(ruta, "wb") as f:
            f.write(base64.b64decode(r["base64"]))
        import sys
        p = subprocess.run([sys.executable, ruta], input="Ana\n", capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(p.stdout.strip(), "Hola Ana")

    def test_exportar_con_errores_no_exporta(self):
        estado, r = pedir(self.base, "/api/exportar", {"codigo": "x = ;", "formato": "python"})
        self.assertEqual(estado, 422)
        self.assertIn("errores", r["error"])
        self.assertTrue(r["errores"])

    def test_exportar_peticiones_invalidas(self):
        self.assertEqual(pedir(self.base, "/api/exportar", {"codigo": 'Mensaje.Texto("x");', "formato": "cobol"})[0], 400)
        self.assertEqual(pedir(self.base, "/api/exportar", {"codigo": 5, "formato": "python"})[0], 400)
        self.assertEqual(pedir(self.base, "/api/exportar", {"codigo": "", "formato": 5})[0], 400)

    # -- asistente ---------------------------------------------------------------
    def test_asistente_flujo_completo(self):
        estado, e = pedir(self.base, "/api/ia/estado")
        self.assertFalse(e["configurada"])
        estado, r = pedir(self.base, "/api/asistente", {"mensajes": [{"rol": "user", "contenido": "hola"}]})
        self.assertEqual(estado, 400)
        self.assertIn("clave", r["error"])

        estado, e = pedir(self.base, "/api/ia/config", {"clave": simulado.CLAVE})
        self.assertEqual(estado, 200)
        self.assertTrue(e["configurada"])
        self.assertNotIn(simulado.CLAVE, json.dumps(e))
        estado, e = pedir(self.base, "/api/ia/estado")
        self.assertNotIn(simulado.CLAVE, json.dumps(e))

        simulado.Falso.respuestas = [(200, simulado.texto(simulado.BUENO))]
        estado, r = pedir(self.base, "/api/asistente",
                          {"mensajes": [{"rol": "user", "contenido": "Quiero calcular la edad"}], "codigo": "", "errores": []})
        self.assertEqual(estado, 200)
        self.assertTrue(r["bloques"][0]["exitoso"])
        self.assertNotIn(simulado.CLAVE, json.dumps(r))

        simulado.Falso.respuestas = [(401, simulado.error_api("invalid x-api-key"))]
        estado, r = pedir(self.base, "/api/asistente", {"mensajes": [{"rol": "user", "contenido": "hola"}]})
        self.assertEqual(estado, 502)
        self.assertIn("clave", r["error"].lower())
        self.assertNotIn(simulado.CLAVE, json.dumps(r))

        estado, e = pedir(self.base, "/api/ia/borrar", {})
        self.assertFalse(e["configurada"])

    def test_configuracion_invalida(self):
        estado, r = pedir(self.base, "/api/ia/config", {"clave": "corta"})
        self.assertEqual(estado, 400)
        estado, r = pedir(self.base, "/api/ia/config", {"clave": 5})
        self.assertEqual(estado, 400)


def pedir_crudo(base, ruta):
    """GET que devuelve (estado, cabeceras, texto) sin interpretar JSON."""
    try:
        with urllib.request.urlopen(base + ruta, timeout=20) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), ""


def pedir_con(base, ruta, cuerpo=None, cabeceras=None):
    """Como pedir(), pero con cabeceras propias y devolviendo también las cabeceras de la respuesta."""
    datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
    h = {"Content-Type": "application/json"}
    h.update(cabeceras or {})
    req = urllib.request.Request(base + ruta, data=datos, method="POST" if datos is not None else "GET", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            texto = r.read().decode("utf-8")
            return r.status, dict(r.headers), texto
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8")


class Seguridad(unittest.TestCase):
    """Cabeceras, origen, clave de acceso, límites del asistente y modo nube."""

    @classmethod
    def setUpClass(cls):
        cls.api_falsa = HTTPServer(("127.0.0.1", 0), simulado.Falso)
        threading.Thread(target=cls.api_falsa.serve_forever, daemon=True).start()
        os.environ["COSTENOL_API_URL"] = f"http://127.0.0.1:{cls.api_falsa.server_address[1]}/v1/messages"
        cls.carpeta = tempfile.mkdtemp()
        app.CONFIG_IA = ia.Configuracion(os.path.join(cls.carpeta, "ia_config.json"))
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Manejador)
        cls.srv.daemon_threads = True
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.puerto = cls.srv.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.puerto}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.api_falsa.shutdown()
        os.environ.pop("COSTENOL_API_URL", None)

    def setUp(self):
        self._nube = app.Estado.nube
        self._env = {k: os.environ.get(k) for k in ("ACCESO_USUARIO", "ACCESO_CLAVE", "ANTHROPIC_API_KEY",
                                                    "IA_LIMITE_HORA", "IA_LIMITE_DIA")}
        for k in self._env:
            os.environ.pop(k, None)
        app.Estado.nube = False
        app.Estado.limitador = app.Limitador()
        simulado.Falso.respuestas = []
        simulado.Falso.recibidas = []

    def tearDown(self):
        app.Estado.nube = self._nube
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # -- cabeceras -----------------------------------------------------------------
    def test_cabeceras_de_seguridad(self):
        estado, cab, _ = pedir_con(self.base, "/")
        self.assertEqual(estado, 200)
        csp = cab.get("Content-Security-Policy", "")
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertEqual(cab.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(cab.get("Referrer-Policy"), "no-referrer")

    # -- modo local: host y origen --------------------------------------------------
    def test_local_rechaza_un_host_ajeno(self):
        estado, _, _ = pedir_con(self.base, "/api/ejemplos", cabeceras={"Host": "evil.example.com"})
        self.assertEqual(estado, 403)
        estado, _, _ = pedir_con(self.base, "/api/ejemplos", cabeceras={"Host": f"localhost:{self.puerto}"})
        self.assertEqual(estado, 200)

    def test_un_sitio_ajeno_no_puede_mandar_peticiones(self):
        cuerpo = {"codigo": 'Mensaje.Texto("x");'}
        for origen in ("http://evil.example.com", "null", "http://127.0.0.1:1", "https://127.0.0.1"):
            estado, _, _ = pedir_con(self.base, "/api/analizar", cuerpo, {"Origin": origen})
            self.assertEqual(estado, 403, origen)
        estado, _, _ = pedir_con(self.base, "/api/analizar", cuerpo, {"Origin": self.base})
        self.assertEqual(estado, 200)
        estado, _, _ = pedir_con(self.base, "/api/analizar", cuerpo)           # sin Origin (herramientas)
        self.assertEqual(estado, 200)

    # -- modo nube ----------------------------------------------------------------------
    def test_deteccion_del_modo_nube(self):
        self.assertTrue(app.es_nube(["app.py", "--nube"]))
        if not any(k.startswith("RAILWAY") for k in os.environ) and os.environ.get("COSTENOL_NUBE") != "1":
            self.assertFalse(app.es_nube(["app.py"]))
        os.environ["RAILWAY_ENVIRONMENT"] = "production"
        try:
            self.assertTrue(app.es_nube(["app.py"]))
        finally:
            os.environ.pop("RAILWAY_ENVIRONMENT", None)
        os.environ["COSTENOL_NUBE"] = "1"
        try:
            self.assertTrue(app.es_nube(["app.py"]))
        finally:
            os.environ.pop("COSTENOL_NUBE", None)

    def test_en_la_nube_escucha_en_el_puerto_de_la_variable_port(self):
        import socket
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        libre = s.getsockname()[1]
        s.close()
        os.environ["PORT"] = str(libre)
        app.Estado.nube = True
        try:
            servidor = app.crear_servidor()
            try:
                self.assertEqual(servidor.server_address, ("0.0.0.0", libre))
            finally:
                servidor.server_close()
        finally:
            os.environ.pop("PORT", None)

    def test_salud_y_modo(self):
        app.Estado.nube = True
        self.assertEqual(pedir(self.base, "/api/salud")[1], {"ok": True})
        self.assertEqual(pedir(self.base, "/api/modo")[1], {"nube": True})
        app.Estado.nube = False
        self.assertEqual(pedir(self.base, "/api/modo")[1], {"nube": False})

    def test_en_la_nube_cualquier_host_sirve_pero_el_origen_se_sigue_comprobando(self):
        app.Estado.nube = True
        estado, _, _ = pedir_con(self.base, "/api/ejemplos", cabeceras={"Host": "costenol.up.railway.app"})
        self.assertEqual(estado, 200)
        cuerpo = {"codigo": 'Mensaje.Texto("x");'}
        estado, _, _ = pedir_con(self.base, "/api/analizar", cuerpo,
                                 {"Host": "costenol.up.railway.app", "Origin": "https://costenol.up.railway.app"})
        self.assertEqual(estado, 200)
        estado, _, _ = pedir_con(self.base, "/api/analizar", cuerpo,
                                 {"Host": "costenol.up.railway.app", "Origin": "https://evil.example.com"})
        self.assertEqual(estado, 403)
        # detrás del proxy de Railway el Host original puede llegar en X-Forwarded-Host
        estado, _, _ = pedir_con(self.base, "/api/analizar", cuerpo,
                                 {"Origin": "https://costenol.up.railway.app", "X-Forwarded-Host": "costenol.up.railway.app"})
        self.assertEqual(estado, 200)

    def test_en_la_nube_nadie_puede_cambiar_ni_borrar_la_clave_del_asistente(self):
        app.Estado.nube = True
        estado, r = pedir(self.base, "/api/ia/config", {"clave": simulado.CLAVE})
        self.assertEqual(estado, 403)
        self.assertEqual(pedir(self.base, "/api/ia/borrar", {})[0], 403)
        self.assertFalse(app.CONFIG_IA.estado()["configurada"])
        self.assertIs(pedir(self.base, "/api/ia/estado")[1]["configurable"], False)
        app.Estado.nube = False
        self.assertIs(pedir(self.base, "/api/ia/estado")[1]["configurable"], True)

    def test_en_la_nube_cerrar_y_latido_no_apagan_nada(self):
        app.Estado.nube = True
        self.assertEqual(pedir(self.base, "/api/cerrar", {})[0], 200)
        self.assertEqual(pedir(self.base, "/api/latido", {})[0], 200)
        import time
        time.sleep(0.2)
        self.assertEqual(pedir(self.base, "/api/salud")[0], 200)

    def test_el_asistente_en_la_nube_tiene_limite_por_persona_y_por_dia(self):
        app.Estado.nube = True
        os.environ["ANTHROPIC_API_KEY"] = simulado.CLAVE
        os.environ["IA_LIMITE_HORA"] = "2"
        os.environ["IA_LIMITE_DIA"] = "3"
        peticion = {"mensajes": [{"rol": "user", "contenido": "hola"}]}
        simulado.Falso.respuestas = [(200, simulado.texto("ok"))] * 10
        persona_a = {"X-Forwarded-For": "1.1.1.1"}
        persona_b = {"X-Forwarded-For": "2.2.2.2"}
        self.assertEqual(pedir_con(self.base, "/api/asistente", peticion, persona_a)[0], 200)
        self.assertEqual(pedir_con(self.base, "/api/asistente", peticion, persona_a)[0], 200)
        estado, _, cuerpo = pedir_con(self.base, "/api/asistente", peticion, persona_a)
        self.assertEqual(estado, 429)
        self.assertIn("demasiadas", json.loads(cuerpo)["error"].lower())
        self.assertEqual(pedir_con(self.base, "/api/asistente", peticion, persona_b)[0], 200)   # otra persona sí puede
        estado, _, cuerpo = pedir_con(self.base, "/api/asistente", peticion, persona_b)         # tope del día (3)
        self.assertEqual(estado, 429)
        self.assertIn("hoy", json.loads(cuerpo)["error"].lower())

    def test_el_asistente_local_no_tiene_limite(self):
        os.environ["ANTHROPIC_API_KEY"] = simulado.CLAVE
        os.environ["IA_LIMITE_HORA"] = "1"
        simulado.Falso.respuestas = [(200, simulado.texto("ok"))] * 5
        for _ in range(3):
            self.assertEqual(pedir(self.base, "/api/asistente", {"mensajes": [{"rol": "user", "contenido": "hola"}]})[0], 200)

    # -- clave de acceso opcional ---------------------------------------------------
    def test_clave_de_acceso(self):
        os.environ["ACCESO_USUARIO"] = "profe"
        os.environ["ACCESO_CLAVE"] = "secreta-123"
        estado, cab, _ = pedir_con(self.base, "/")
        self.assertEqual(estado, 401)
        self.assertIn("Basic", cab.get("WWW-Authenticate", ""))
        import base64
        def basic(u, c):
            return {"Authorization": "Basic " + base64.b64encode(f"{u}:{c}".encode()).decode()}
        self.assertEqual(pedir_con(self.base, "/", cabeceras=basic("profe", "mala"))[0], 401)
        self.assertEqual(pedir_con(self.base, "/", cabeceras=basic("otro", "secreta-123"))[0], 401)
        self.assertEqual(pedir_con(self.base, "/", cabeceras={"Authorization": "Basic %%%"})[0], 401)
        self.assertEqual(pedir_con(self.base, "/", cabeceras=basic("profe", "secreta-123"))[0], 200)
        self.assertEqual(pedir_con(self.base, "/api/analizar", {"codigo": ""})[0], 401)
        self.assertEqual(pedir_con(self.base, "/api/analizar", {"codigo": ""}, basic("profe", "secreta-123"))[0], 200)
        self.assertEqual(pedir_con(self.base, "/api/salud")[0], 200)          # la comprobación de salud es pública

    def test_sin_las_dos_variables_no_se_pide_clave(self):
        os.environ["ACCESO_USUARIO"] = "profe"
        self.assertEqual(pedir_con(self.base, "/")[0], 200)


class Limites(unittest.TestCase):
    def test_limitador(self):
        lim = app.Limitador()
        t = 1000.0
        self.assertTrue(lim.permitir("a", 2, 10, t)[0])
        self.assertTrue(lim.permitir("a", 2, 10, t + 1)[0])
        self.assertFalse(lim.permitir("a", 2, 10, t + 2)[0])
        self.assertTrue(lim.permitir("b", 2, 10, t + 2)[0])
        self.assertTrue(lim.permitir("a", 2, 10, t + 3601)[0])              # pasó la hora
        lim = app.Limitador()
        for i in range(3):
            self.assertTrue(lim.permitir(f"ip{i}", 5, 3, t)[0])
        self.assertFalse(lim.permitir("otra", 5, 3, t + 10)[0])
        self.assertTrue(lim.permitir("otra", 5, 3, t + 86401)[0])           # pasó el día

    def test_la_tabla_de_ips_no_crece_sin_limite(self):
        lim = app.Limitador()
        for i in range(5100):
            lim.permitir(f"ip{i}", 5, 10 ** 9, 1000.0 + i * 3601)            # cada una muy espaciada: caducan
        self.assertLess(len(lim.por_ip), 5100)


if __name__ == "__main__":
    unittest.main(verbosity=1)
