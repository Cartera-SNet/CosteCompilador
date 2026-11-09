#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pruebas de los mensajes en costeño: formato del profesor y cobertura de todos los códigos.

Ejecutar:   python pruebas_dialecto.py
"""

import glob
import os
import re
import unittest

import costenol_dialecto as d
from costenol_compilador import Sesiones, catalogo, compilar

AQUI = os.path.dirname(os.path.abspath(__file__))


class Formato(unittest.TestCase):
    def test_el_ejemplo_del_profesor(self):
        # «Ojo, la cagaste en la línea 5. Error semántico: la variable no está declarada»
        c = compilar("a Entero;\nb Entero;\na = 1;\nb = 2;\nx = 5;")
        frase = c["errores"][0]["mensaje_costeno"]
        self.assertRegex(frase, r"^.+ en la línea 5\. Error semántico: la variable 'x' no está declarada\.$")

    def test_la_frase_indica_linea_tipo_y_causa(self):
        for src, tipo in (("x = 5 @ 3;", "léxico"), ("edad Entero\nedad = 1;", "sintáctico"),
                          ("x Entero;\nx = \"a\";", "semántico")):
            f = compilar(src)["errores"][0]["mensaje_costeno"]
            self.assertRegex(f, r"en la línea \d+")
            self.assertIn(f"Error {tipo}:", f)

    def test_los_errores_de_ejecucion_tambien_hablan_costeno(self):
        c = compilar("x Entero;\nr Real;\nx = Captura.Entero();\nr = 10 / x;")
        _, s = Sesiones().crear(c["arbol"])
        s.iniciar()
        r = s.entregar("0")
        self.assertIn("Error de ejecución:", r["error"]["mensaje_costeno"])
        self.assertIn("en la línea 4", r["error"]["mensaje_costeno"])

    def test_las_advertencias_dicen_advertencia(self):
        f = compilar("x Entero;")["advertencias"][0]["mensaje_costeno"]
        self.assertIn("Advertencia:", f)
        self.assertNotIn("Error", f)

    def test_es_estable(self):
        a = d.frase("E-SIN-01", 7, "Falta el ';'")
        self.assertEqual(a, d.frase("E-SIN-01", 7, "Falta el ';'"))

    def test_la_apertura_varia_segun_la_linea(self):
        aperturas = {d.frase("E-SIN-01", n, "x").split(" Error")[0] for n in range(1, 40)}
        self.assertGreaterEqual(len(aperturas), 4)

    def test_nombres_y_tipos_entran_en_la_frase(self):
        f = compilar('e Entero;\ne = "hola";')["errores"][0]["mensaje_costeno"]
        self.assertIn("Texto", f)
        self.assertIn("'e'", f)
        self.assertIn("Entero", f)


class Cobertura(unittest.TestCase):
    def test_cada_codigo_del_catalogo_tiene_frase_propia(self):
        sin_frase = [c["codigo"] for c in catalogo() if c["codigo"] not in d.CAUSAS and not c["codigo"].endswith("-99")
                     and not c["codigo"].endswith("-98")]
        self.assertEqual(sin_frase, [], f"Códigos sin frase en costeño: {sin_frase}")

    def test_todas_las_frases_son_de_codigos_que_existen(self):
        existentes = {c["codigo"] for c in catalogo()}
        self.assertEqual(set(d.CAUSAS) - existentes, set())

    def test_ninguna_frase_deja_llaves_sin_llenar(self):
        for c in catalogo():
            for linea in (1, 5, 123):
                f = d.frase(c["codigo"], linea, c["significa"])
                self.assertNotIn("{", f, c["codigo"])
                self.assertNotIn("}", f, c["codigo"])
                self.assertIn(f"en la línea {linea}", f, c["codigo"])
                self.assertTrue(f.strip().endswith((".", ")", "!", ";")), c["codigo"])

    def test_un_codigo_sin_frase_usa_el_mensaje_formal(self):
        f = d.frase("E-XXX-99", 3, "Algo raro pasó.")
        self.assertIn("en la línea 3", f)
        self.assertIn("Algo raro pasó.", f)

    def test_todo_diagnostico_del_compilador_trae_mensaje_costeno(self):
        for ruta in sorted(glob.glob(os.path.join(AQUI, "ejemplos", "*.cst"))):
            with open(ruta, encoding="utf-8-sig") as f:
                c = compilar(f.read())
            for diag in c["errores"] + c["advertencias"]:
                self.assertTrue(diag["mensaje_costeno"], os.path.basename(ruta))
                self.assertRegex(diag["mensaje_costeno"], r"en la línea \d+", os.path.basename(ruta))


if __name__ == "__main__":
    unittest.main(verbosity=1)
