#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pruebas de los mensajes en costeño: formato del profesor, una frase propia por cada código,
uso correcto de «monda», palabras que no deben aparecer y coherencia con la interfaz.

Ejecutar:   python pruebas_dialecto.py
"""

import glob
import os
import re
import unittest

import costenol_dialecto as d
from costenol_compilador import Sesiones, catalogo, compilar

AQUI = os.path.dirname(os.path.abspath(__file__))
CODIGOS = [c["codigo"] for c in catalogo()]


def todos_los_textos():
    """Cada frase que el programa puede decir en costeño."""
    textos = list(d.REACCIONES.values()) + [c for _, c in d.CAUSAS.values()] + list(d.MENSAJES_PANTALLA.values())
    return textos


class Formato(unittest.TestCase):
    def test_el_ejemplo_del_profesor(self):
        # «Ojo, la cagaste en la línea 5. Error semántico: la variable no está declarada»
        c = compilar("a Entero;\nb Entero;\na = 1;\nb = 2;\nx = 5;")
        frase = c["errores"][0]["mensaje_costeno"]
        self.assertTrue(frase.startswith("Ojo, la cagaste en la línea 5. Error semántico: la variable 'x' no está declarada."), frase)

    def test_la_frase_indica_linea_tipo_y_causa(self):
        for src, tipo in (("x = 5 @ 3;", "léxico"), ("edad Entero\nedad = 1;", "sintáctico"),
                          ('x Entero;\nx = "a";', "semántico")):
            f = compilar(src)["errores"][0]["mensaje_costeno"]
            self.assertRegex(f, r"(?i)en la línea \d+")
            self.assertIn(f"Error {tipo}:", f)

    def test_los_errores_de_ejecucion_tambien_hablan_costeno(self):
        c = compilar("x Entero;\nr Real;\nx = Captura.Entero();\nr = 10 / x;")
        _, s = Sesiones().crear(c["arbol"])
        s.iniciar()
        r = s.entregar("0")
        self.assertEqual(r["error"]["mensaje_costeno"],
                         "No inventes, compa, en la línea 4. Error de ejecución: el divisor valió cero.")

    def test_las_advertencias_dicen_advertencia(self):
        f = compilar("x Entero;")["advertencias"][0]["mensaje_costeno"]
        self.assertEqual(f, "Pilas, compa: en la línea 1 declaraste 'x' y nunca la usas. Advertencia: bórrala o úsala.")
        self.assertNotIn("Error", f)

    def test_es_estable(self):
        a = d.frase("E-SIN-01", 7, "Falta el ';'")
        self.assertEqual(a, d.frase("E-SIN-01", 7, "Falta el ';'"))

    def test_los_ejemplos_de_la_propuesta_aprobada(self):
        esperado = {
            "x Entero;\nx = 99999999999;": "Ey mi llave, qué número tan grande en la línea 2. Error léxico: '99999999999' pasa del máximo, que es 2147483647.",
            "a" * 31 + " Entero;": "Ojo manito, que en la línea 1 hay un nombre larguísimo. Error léxico: el máximo son 30 caracteres.",
            "x Entero;\nx = 5 @ 3;": "¿Qué es esa monda, loco? En la línea 2 hay un símbolo que no se usa en Costeñol. Error léxico: '@' no forma parte del lenguaje.",
            "edad Entero\nedad = 5;": "Ajá, ¿y el punto y coma? Se te quedó por fuera en la línea 1. Error sintáctico: toda instrucción termina con ;",
            'x Entero;\nx = "a";': "Ese cuento no me cuadra en la línea 2. Error semántico: no puedes guardar un valor Texto en 'x' porque es Entero; los tipos no son compatibles.",
            "x Entero;\nMensaje.Texto(x);": "No te hagas el loco, compa: en la línea 2 usas 'x' sin darle valor. Error semántico: primero asígnale o léele un valor.",
            "x Real;\nx = 1 / 0;": "No inventes, compa, en la línea 2. Error semántico: no se puede dividir por cero.",
        }
        for src, frase in esperado.items():
            self.assertEqual(compilar(src)["errores"][0]["mensaje_costeno"], frase, src)
        self.assertEqual(compilar("x Real;\nx = 3.14;")["errores"][0]["mensaje_costeno"],
                         "Ojo, compa, en la línea 2 usaste punto en un decimal. Error léxico: los decimales llevan coma; '3.14' se escribe '3,14'.")
        self.assertIn("'.5' se escribe '0,5'", compilar("x Real;\nx = .5;")["errores"][0]["mensaje_costeno"])
        self.assertIn("'007' se escribe '7'", compilar("x Entero;\nx = 007;")["errores"][0]["mensaje_costeno"])
        self.assertIn("se escribe 'Entero'", compilar("a entero;")["errores"][0]["mensaje_costeno"])
        self.assertIn("se escribe 'Si'", compilar("si (x > 1)")["errores"][0]["mensaje_costeno"])

    def test_nombres_y_tipos_entran_en_la_frase(self):
        f = compilar('e Entero;\ne = "hola";')["errores"][0]["mensaje_costeno"]
        for parte in ("Texto", "'e'", "Entero"):
            self.assertIn(parte, f)
        f = compilar("edad Entero;\nEdad Entero;\nedad = 1;\nEdad = 2;\nMensaje.Texto(edad + Edad);")["advertencias"][0]["mensaje_costeno"]
        self.assertIn("'Edad' se parece a 'edad' (línea 1)", f)


class Cobertura(unittest.TestCase):
    def test_cada_codigo_del_catalogo_tiene_su_reaccion_y_su_causa(self):
        sin_reaccion = [c for c in CODIGOS if c not in d.REACCIONES]
        sin_causa = [c for c in CODIGOS if c not in d.CAUSAS]
        self.assertEqual(sin_reaccion, [], f"Códigos sin reacción en costeño: {sin_reaccion}")
        self.assertEqual(sin_causa, [], f"Códigos sin causa en costeño: {sin_causa}")

    def test_todas_las_frases_son_de_codigos_que_existen(self):
        self.assertEqual((set(d.REACCIONES) | set(d.CAUSAS)) - set(CODIGOS), set())

    def test_toda_reaccion_dice_en_la_linea(self):
        for codigo, reaccion in d.REACCIONES.items():
            self.assertRegex(reaccion, r"(?i)en la línea \{n\}", codigo)

    def test_ninguna_frase_deja_llaves_sin_llenar(self):
        for c in catalogo():
            for linea in (1, 5, 123):
                f = d.frase(c["codigo"], linea, c["significa"])
                self.assertNotIn("{", f, c["codigo"])
                self.assertNotIn("}", f, c["codigo"])
                self.assertRegex(f, rf"(?i)en la línea {linea}\b", c["codigo"])
                self.assertIn("Advertencia:" if c["codigo"].startswith("A-") else "Error ", f, c["codigo"])

    def test_un_codigo_sin_frase_usa_el_mensaje_formal(self):
        f = d.frase("E-XXX-99", 3, "Algo raro pasó.")
        self.assertIn("en la línea 3", f)
        self.assertIn("Algo raro pasó.", f)

    def test_todo_diagnostico_del_compilador_trae_mensaje_costeno(self):
        for ruta in sorted(glob.glob(os.path.join(AQUI, "ejemplos", "*.cst"))):
            with open(ruta, encoding="utf-8-sig") as f:
                c = compilar(f.read())
            for diag in c["errores"] + c["advertencias"]:
                self.assertRegex(diag["mensaje_costeno"], r"(?i)en la línea \d+", os.path.basename(ruta))


class UsoDelDiccionario(unittest.TestCase):
    def test_monda_solo_donde_corresponde(self):
        # «¿Qué es esa monda, loco?» = desconcierto: solo en cuatro errores.
        con_monda = {c for c, r in d.REACCIONES.items() if "monda" in r.lower()}
        self.assertEqual(con_monda, {"E-LEX-15", "E-SIN-02", "E-SIN-20", "E-SEM-04"})
        for c in con_monda:
            self.assertIn("¿Qué es esa monda, loco?", d.REACCIONES[c])
        # «Tú eres la monda, manito» = elogio: nunca en un error ni en un aviso.
        for c, r in d.REACCIONES.items():
            self.assertNotIn("Tú eres la monda", r, c)
        for c, (_, causa) in d.CAUSAS.items():
            self.assertNotIn("monda", causa.lower(), c)
        self.assertTrue(d.MENSAJES_PANTALLA["compilacion_limpia"].startswith("Tú eres la monda, manito"))
        con_elogio = [k for k, v in d.MENSAJES_PANTALLA.items() if "monda" in v.lower()]
        self.assertEqual(con_elogio, ["compilacion_limpia"])

    def test_la_frase_del_profesor_solo_en_variable_no_declarada(self):
        con_frase = {c for c, r in d.REACCIONES.items() if "cagaste" in r}
        self.assertEqual(con_frase, {"E-SEM-01"})

    def test_una_monda_como_maximo_por_mensaje(self):
        for c in CODIGOS:
            f = d.frase(c, 5, "x")
            self.assertLessEqual(f.lower().count("monda"), 1, c)

    def test_no_aparece_ninguna_palabra_prohibida(self):
        for texto in todos_los_textos():
            for palabra in d.PALABRAS_PROHIBIDAS:
                self.assertNotIn(palabra, texto.lower(), f"«{palabra}» en «{texto}»")

    def test_las_familias_de_reacciones(self):
        # lo que falta empieza con «Ajá, ¿y …?»
        for c in ("E-SIN-01", "E-SIN-04", "E-SIN-08", "E-SIN-09", "E-SIN-28"):
            self.assertTrue(d.REACCIONES[c].startswith("Ajá, ¿y"), c)
        # lo que no cuadra
        for c in ("E-SEM-03", "E-SEM-05"):
            self.assertIn("Ese cuento no me cuadra", d.REACCIONES[c])
        # fingir que no sabe
        for c in ("E-SEM-09", "E-EJE-01"):
            self.assertIn("No te hagas el loco", d.REACCIONES[c])
        # enredo de estructura: solo en el programa demasiado complejo
        self.assertTrue(d.REACCIONES["E-SIN-25"].startswith("Mi llave, estás enredado"))
        self.assertEqual({c for c, r in d.REACCIONES.items() if "enredado" in r}, {"E-SIN-25"})
        # avisos
        for c in ("A-SEM-01", "A-SEM-03"):
            self.assertTrue(d.REACCIONES[c].startswith("Pilas"), c)
        self.assertTrue(d.REACCIONES["A-SEM-02"].startswith("No des papaya"))


class Pantalla(unittest.TestCase):
    def test_los_mensajes_de_pantalla_estan_en_la_interfaz(self):
        with open(os.path.join(AQUI, "web", "app.js"), encoding="utf-8") as f:
            js = f.read()
        for clave, texto in d.MENSAJES_PANTALLA.items():
            piezas = re.split(r"\{[^}]*\}|(?<=\.)\s+", texto)          # sin los huecos {…} y por oraciones
            fragmentos = [p.strip(" .:") for p in piezas if len(p.strip(" .:")) > 8]
            self.assertTrue(fragmentos, clave)
            for f in fragmentos:
                self.assertTrue(f in js, f"«{f}» ({clave}) no está en web/app.js")


if __name__ == "__main__":
    unittest.main(verbosity=1)
