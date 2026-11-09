#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pruebas del asistente de IA (sin gastar dinero ni necesitar internet).

Se levanta un servidor falso que imita a la API de Anthropic, y se comprueba:
  * que la petición lleve la clave, el modelo, las reglas del lenguaje y el contexto;
  * que el código de las respuestas se compile con el compilador real;
  * que se corrija automáticamente el código con errores;
  * que los errores de la API den mensajes claros y nunca revelen la clave.

Ejecutar:   python pruebas_asistente.py
"""

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import costenol_asistente as ia

CLAVE = "sk-ant-api03-PRUEBA_PRUEBA_PRUEBA_1234"

BUENO = ("Claro. Este programa calcula la edad.\n```\n// Calcula la edad //\nanio Entero;\nedad Entero;\n"
         "Mensaje.Texto(\"Ingrese su año de nacimiento:\");\nanio = Captura.Entero();\n"
         "edad = 2026 - anio;\nMensaje.Texto(\"Tu edad es: \" + edad);\n```\nListo.")
MALO = "Aquí está:\n```\nanio Entero\nanio = Captura.Entero();\n```"


class Falso(BaseHTTPRequestHandler):
    respuestas = []          # lista de (estado, cuerpo_dict)
    recibidas = []           # peticiones recibidas

    def log_message(self, *a):
        pass

    def do_POST(self):
        largo = int(self.headers.get("Content-Length") or 0)
        cuerpo = json.loads(self.rfile.read(largo).decode("utf-8"))
        Falso.recibidas.append({"cabeceras": {k.lower(): v for k, v in self.headers.items()}, "cuerpo": cuerpo})
        estado, datos = Falso.respuestas.pop(0) if Falso.respuestas else (200, texto(BUENO))
        salida = json.dumps(datos).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(salida)))
        self.end_headers()
        self.wfile.write(salida)


def texto(t):
    return {"id": "msg_1", "type": "message", "role": "assistant", "content": [{"type": "text", "text": t}]}


def error_api(mensaje):
    return {"type": "error", "error": {"type": "x", "message": mensaje}}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = HTTPServer(("127.0.0.1", 0), Falso)
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        os.environ["COSTENOL_API_URL"] = f"http://127.0.0.1:{cls.servidor.server_address[1]}/v1/messages"
        cls.carpeta = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        os.environ.pop("COSTENOL_API_URL", None)

    def setUp(self):
        Falso.respuestas = []
        Falso.recibidas = []
        self._clave_env = os.environ.pop("ANTHROPIC_API_KEY", None)
        self.config = ia.Configuracion(os.path.join(self.carpeta, f"cfg_{self.id()}.json"))

    def tearDown(self):
        if self._clave_env is not None:
            os.environ["ANTHROPIC_API_KEY"] = self._clave_env


class Respuestas(Base):
    def test_sin_clave_da_un_error_claro(self):
        with self.assertRaises(ia.ErrorAsistente) as c:
            ia.responder(self.config, [{"rol": "user", "contenido": "hola"}])
        self.assertEqual(c.exception.estado, 400)
        self.assertIn("clave", c.exception.mensaje)
        self.assertEqual(Falso.recibidas, [])

    def test_peticion_correcta_y_codigo_verificado(self):
        self.config.guardar(clave=CLAVE)
        Falso.respuestas = [(200, texto(BUENO))]
        r = ia.responder(self.config, [{"rol": "user", "contenido": "Quiero calcular la edad"}])
        self.assertEqual(len(Falso.recibidas), 1)
        p = Falso.recibidas[0]
        self.assertEqual(p["cabeceras"]["x-api-key"], CLAVE)
        self.assertEqual(p["cabeceras"]["anthropic-version"], ia.VERSION_API)
        self.assertRegex(ia.VERSION_API, r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(p["cuerpo"]["model"], ia.MODELO_PREDETERMINADO)
        self.assertIn("Costeñol", p["cuerpo"]["system"])
        self.assertIn("Mensaje.Texto", p["cuerpo"]["system"])
        self.assertEqual(p["cuerpo"]["messages"], [{"role": "user", "content": "Quiero calcular la edad"}])
        self.assertTrue(p["cuerpo"]["max_tokens"] > 0)
        self.assertEqual(r["reintentos"], 0)
        self.assertEqual(len(r["bloques"]), 1)
        self.assertTrue(r["bloques"][0]["exitoso"])
        self.assertIn("Tu edad es", r["respuesta"])

    def test_se_envia_el_codigo_y_los_errores_del_editor(self):
        self.config.guardar(clave=CLAVE)
        Falso.respuestas = [(200, texto("Le falta el punto y coma."))]
        ia.responder(self.config, [{"rol": "user", "contenido": "¿Qué falla?"}],
                     codigo_actual="x Entero", errores_actuales=["Línea 1: Falta el ';'"])
        enviado = Falso.recibidas[0]["cuerpo"]["messages"][-1]["content"]
        self.assertIn("¿Qué falla?", enviado)
        self.assertIn("x Entero", enviado)
        self.assertIn("Falta el ';'", enviado)

    def test_corrige_automaticamente_el_codigo_con_errores(self):
        self.config.guardar(clave=CLAVE)
        Falso.respuestas = [(200, texto(MALO)), (200, texto(BUENO))]
        r = ia.responder(self.config, [{"rol": "user", "contenido": "Edad"}])
        self.assertEqual(r["reintentos"], 1)
        self.assertEqual(len(Falso.recibidas), 2)
        segunda = Falso.recibidas[1]["cuerpo"]["messages"]
        self.assertEqual([m["role"] for m in segunda], ["user", "assistant", "user"])
        self.assertIn("E-SIN-01", segunda[-1]["content"])
        self.assertTrue(r["bloques"][0]["exitoso"])

    def test_si_sigue_mal_se_rinde_despues_de_dos_correcciones(self):
        self.config.guardar(clave=CLAVE)
        Falso.respuestas = [(200, texto(MALO))] * 5
        r = ia.responder(self.config, [{"rol": "user", "contenido": "Edad"}])
        self.assertEqual(r["reintentos"], ia.MAX_REINTENTOS)
        self.assertEqual(len(Falso.recibidas), 1 + ia.MAX_REINTENTOS)
        self.assertFalse(r["bloques"][0]["exitoso"])
        self.assertTrue(r["bloques"][0]["errores"])

    def test_respuesta_sin_codigo_no_se_reintenta(self):
        self.config.guardar(clave=CLAVE)
        Falso.respuestas = [(200, texto("Los enteros se declaran así: `edad Entero;`"))]
        r = ia.responder(self.config, [{"rol": "user", "contenido": "¿Cómo declaro enteros?"}])
        self.assertEqual(r["bloques"], [])
        self.assertEqual(len(Falso.recibidas), 1)

    def test_historial_se_limpia(self):
        self.config.guardar(clave=CLAVE)
        historial = [{"rol": "assistant", "contenido": "hola"}, {"rol": "user", "contenido": "uno"},
                     {"rol": "otro", "contenido": "x"}, {"rol": "assistant", "contenido": "dos"},
                     {"rol": "user", "contenido": "y" * 9000}, {"rol": "user", "contenido": ""}, 5, None]
        ia.responder(self.config, historial)
        msgs = Falso.recibidas[0]["cuerpo"]["messages"]
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant", "user"])
        self.assertLessEqual(len(msgs[-1]["content"]), ia.MAX_CHARS_MENSAJE)

    def test_exige_que_el_ultimo_mensaje_sea_del_usuario(self):
        self.config.guardar(clave=CLAVE)
        for h in ([], [{"rol": "assistant", "contenido": "x"}], [{"rol": "user", "contenido": "  "}]):
            with self.assertRaises(ia.ErrorAsistente):
                ia.responder(self.config, h)

    def test_clave_desde_variable_de_entorno(self):
        os.environ["ANTHROPIC_API_KEY"] = CLAVE
        try:
            ia.responder(self.config, [{"rol": "user", "contenido": "hola"}])
            self.assertEqual(Falso.recibidas[0]["cabeceras"]["x-api-key"], CLAVE)
            self.assertEqual(self.config.estado()["origen"], "variable")
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)


class Errores(Base):
    def probar(self, estado, mensaje=""):
        self.config.guardar(clave=CLAVE)
        Falso.respuestas = [(estado, error_api(mensaje))]
        with self.assertRaises(ia.ErrorAsistente) as c:
            ia.responder(self.config, [{"rol": "user", "contenido": "hola"}])
        self.assertNotIn(CLAVE, c.exception.mensaje)
        return c.exception.mensaje

    def test_clave_invalida(self):
        self.assertIn("clave", self.probar(401, "invalid x-api-key").lower())

    def test_modelo_inexistente(self):
        self.assertIn(ia.MODELO_PREDETERMINADO, self.probar(404, "model: no existe"))

    def test_demasiadas_solicitudes(self):
        self.assertIn("demasiadas", self.probar(429, "rate").lower())

    def test_sin_saldo(self):
        self.assertIn("saldo", self.probar(400, "Your credit balance is too low").lower())

    def test_servicio_caido(self):
        self.assertIn("ocupado", self.probar(529, "overloaded").lower())

    def test_respuesta_vacia(self):
        self.config.guardar(clave=CLAVE)
        Falso.respuestas = [(200, texto("   "))]
        with self.assertRaises(ia.ErrorAsistente):
            ia.responder(self.config, [{"rol": "user", "contenido": "hola"}])

    def test_sin_conexion(self):
        self.config.guardar(clave=CLAVE)
        anterior = os.environ["COSTENOL_API_URL"]
        os.environ["COSTENOL_API_URL"] = "http://127.0.0.1:1/v1/messages"
        try:
            with self.assertRaises(ia.ErrorAsistente) as c:
                ia.responder(self.config, [{"rol": "user", "contenido": "hola"}])
            self.assertIn("conexión", c.exception.mensaje)
        finally:
            os.environ["COSTENOL_API_URL"] = anterior


class Configuracion(Base):
    def test_guardar_y_estado_sin_revelar_la_clave(self):
        self.config.guardar(clave=CLAVE, modelo="claude-haiku-5-5")
        e = self.config.estado()
        self.assertTrue(e["configurada"])
        self.assertEqual(e["modelo"], "claude-haiku-5-5")
        self.assertEqual(e["sufijo"], "…1234")
        self.assertNotIn(CLAVE, json.dumps(e))

    def test_borrar_clave(self):
        self.config.guardar(clave=CLAVE)
        self.config.borrar_clave()
        self.assertFalse(self.config.estado()["configurada"])

    def test_claves_y_modelos_invalidos_se_rechazan(self):
        for clave in ("corta", "con espacios y cosas raras que no deberian estar aqui", "sk-ant-<script>alert(1)</script>"):
            with self.assertRaises(ia.ErrorAsistente):
                self.config.guardar(clave=clave)
        for modelo in ("a b", "x;rm -rf", "x" * 200):
            with self.assertRaises(ia.ErrorAsistente):
                self.config.guardar(modelo=modelo)
        self.assertFalse(self.config.estado()["configurada"])

    def test_modelo_predeterminado(self):
        self.assertEqual(self.config.estado()["modelo"], ia.MODELO_PREDETERMINADO)

    def test_archivo_corrupto_no_revienta(self):
        with open(self.config.ruta, "w") as f:
            f.write("{no es json")
        self.assertFalse(self.config.estado()["configurada"])


class Bloques(unittest.TestCase):
    def test_extraer_bloques(self):
        t = "a\n```\nx Entero;\n```\nb\n```costenol\ny Texto;\n```\n"
        self.assertEqual(ia.extraer_bloques(t), ["x Entero;", "y Texto;"])
        self.assertEqual(ia.extraer_bloques("sin código"), [])
        self.assertEqual(ia.extraer_bloques(None), [])

    def test_el_ejemplo_de_las_instrucciones_compila(self):
        """Las instrucciones del asistente no pueden enseñarle código inválido."""
        bloques = ia.extraer_bloques(ia.INSTRUCCIONES)
        self.assertGreaterEqual(len(bloques), 1)
        for v in ia.verificar(bloques):
            self.assertTrue(v["exitoso"], v["errores"])

    def test_las_instrucciones_mencionan_todas_las_palabras_reservadas(self):
        for p in ("Entero", "Texto", "Real", "Logico", "Captura", "Mensaje", "Si", "Sino", "FinSi", "Verdadero", "Falso"):
            self.assertIn(p, ia.INSTRUCCIONES)

    def test_las_instrucciones_incluyen_la_regla_de_los_nombres_y_el_exportar(self):
        self.assertIn("entero Entero;", ia.INSTRUCCIONES)
        self.assertIn("Exportar", ia.INSTRUCCIONES)
        self.assertIn(".jar", ia.INSTRUCCIONES)

    def test_verificar_reporta_errores_con_linea(self):
        v = ia.verificar(["x Entero\ny = 1;"])[0]
        self.assertFalse(v["exitoso"])
        self.assertEqual(v["errores"][0]["linea"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
