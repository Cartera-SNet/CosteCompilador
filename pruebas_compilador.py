#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pruebas del compilador completo (fases sintáctica, semántica y ejecución).

Ejecutar:   python pruebas_compilador.py
"""

import glob
import os
import random
import re
import unittest

import costenol_compilador as comp
from costenol_compilador import Sesiones, catalogo, compilar


def codigos(src):
    c = compilar(src)
    return [e["codigo"] for e in c["errores"]]


def avisos(src):
    return [a["codigo"] for a in compilar(src)["advertencias"]]


def ejecutar(src, entradas=()):
    """Compila y ejecuta. Devuelve la lista de líneas de salida (o ['ERR:codigos'])."""
    c = compilar(src)
    if not c["exitoso"]:
        return ["ERR:" + ",".join(e["codigo"] for e in c["errores"])]
    sid, s = Sesiones().crear(c["arbol"])
    entradas = list(entradas)
    salida = []
    r = s.iniciar()
    while True:
        salida += r["salida"]
        if r["error"]:
            salida.append("RUN:" + r["error"]["codigo"])
            break
        if r["terminado"]:
            break
        if not entradas:
            salida.append("SIN_ENTRADA")
            break
        r = s.entregar(entradas.pop(0))
        if r.get("invalida"):
            salida.append("INVALIDA")
    return salida


class Sintaxis(unittest.TestCase):
    def test_hola_mundo(self):
        self.assertEqual(ejecutar('Mensaje.Texto("Hola Mundo");'), ["Hola Mundo"])

    def test_programa_vacio_o_solo_comentarios(self):
        self.assertTrue(compilar("")["exitoso"])
        self.assertTrue(compilar("// nada //")["exitoso"])

    def test_condicional_vacio_como_en_el_enunciado(self):
        self.assertTrue(compilar("a Entero;\na = 1;\nSi (a > 0)\nSino\nFinSi\nMensaje.Texto(a);")["exitoso"])

    def test_declaraciones_en_una_linea(self):
        self.assertTrue(compilar("num1 Entero; nombre Texto; n1 Real; asis Logico;")["exitoso"])

    def test_falta_punto_y_coma(self):
        self.assertEqual(codigos("x Entero\ny Texto;"), ["E-SIN-01"])
        self.assertEqual(codigos('Mensaje.Texto("a")'), ["E-SIN-01"])
        self.assertEqual(codigos("x Entero; x = 5"), ["E-SIN-01"])

    def test_punto_y_coma_de_mas(self):
        self.assertEqual(codigos("x Entero;;"), ["E-SIN-22"])
        self.assertEqual(codigos(";"), ["E-SIN-22"])

    def test_hola_mundo_sin_mensaje(self):
        c = compilar("Hola Mundo")
        self.assertEqual([e["codigo"] for e in c["errores"]], ["E-SIN-03"])

    def test_mayusculas_en_tipos_y_palabras_reservadas(self):
        self.assertEqual(codigos("a1 entero;"), ["E-SIN-26"])
        self.assertEqual(codigos("a1 ENTERO;"), ["E-SIN-26"])
        self.assertEqual(codigos("n texto;"), ["E-SIN-26"])
        self.assertEqual(codigos("n logico;"), ["E-SIN-26"])
        self.assertIn("E-SIN-26", codigos("x Entero;\nx = 1;\nsi (x > 0)\nFinSi"))
        self.assertIn("E-SIN-26", codigos('mensaje.Texto("a");'))
        self.assertIn("E-SIN-26", codigos("x Entero;\nx = captura.Entero();"))
        self.assertIn("E-SIN-14", codigos("x Entero;\nx = Captura.entero();"))
        self.assertIn("E-SIN-15", codigos('Mensaje.texto("a");'))
        c = compilar("a1 entero;")
        self.assertIn("Entero", c["errores"][0]["mensaje"])
        self.assertIn("mayúsculas", c["errores"][0]["mensaje"])

    def test_una_variable_no_puede_llamarse_como_el_tipo_de_dato(self):
        # Regla del profesor: "entero Entero;" es un error.
        for decl in ["entero Entero;", "ENTERO Entero;", "Entero Entero;", "texto Texto;", "real Real;",
                     "logico Logico;", "Texto Entero;", "entero Texto;", "REAL Logico;"]:
            self.assertTrue(codigos(decl), decl)
        self.assertEqual(codigos("entero Entero;"), ["E-SIN-27"])
        self.assertEqual(codigos("texto Texto;"), ["E-SIN-27"])
        self.assertEqual(codigos("logico Logico;"), ["E-SIN-27"])

    def test_ningun_nombre_puede_parecerse_a_una_reservada(self):
        for nombre in ["si", "SI", "Sino", "sino", "finsi", "FinSI", "captura", "mensaje", "verdadero", "FALSO",
                       "entero", "Entero", "TEXTO", "real", "Logico", "logico"]:
            self.assertTrue(codigos(f"{nombre} Entero;"), nombre)
            self.assertTrue(codigos(f"{nombre} = 5;"), nombre)
            self.assertTrue(codigos(f"x Entero;\nx = {nombre};"), nombre)
        c = compilar("entero Entero;")
        self.assertIn("tipo de dato", c["errores"][0]["mensaje"])
        self.assertIn("miEntero", c["errores"][0]["mensaje"])

    def test_nombres_que_contienen_una_reservada_si_son_validos(self):
        for nombre in ["enteros", "entero1", "miEntero", "Entero_2", "textoLargo", "sinopsis", "realidad",
                       "mensajes", "capturaDatos", "si_no", "Si2", "siguiente"]:
            self.assertTrue(compilar(f"{nombre} Entero;\n{nombre} = 1;\nMensaje.Texto({nombre});")["exitoso"], nombre)

    def test_orden_invertido_de_declaracion(self):
        self.assertEqual(codigos("Entero x;"), ["E-SIN-23"])

    def test_si_sin_espacio_antes_del_parentesis(self):
        self.assertEqual(codigos("x Entero;\nx = 1;\nSi(x > 0)\nFinSi"), ["E-SIN-13"])

    def test_si_con_espacio_o_salto_es_valido(self):
        self.assertTrue(compilar("x Entero;\nx = 1;\nSi   (x > 0)\nFinSi")["exitoso"])
        self.assertTrue(compilar("x Entero;\nx = 1;\nSi\n(x > 0)\nFinSi")["exitoso"])

    def test_si_sin_parentesis(self):
        self.assertIn("E-SIN-06", codigos("Si x > 0\nFinSi"))

    def test_condicion_vacia(self):
        self.assertIn("E-SIN-07", codigos("Si ()\nFinSi"))

    def test_condicion_sin_cierre(self):
        self.assertIn("E-SIN-08", codigos("x Entero;\nx = 1;\nSi (x > 0\nFinSi"))

    def test_igual_simple_en_condicion(self):
        self.assertEqual(codigos("x Entero;\nx = 1;\nSi (x = 1)\nFinSi"), ["E-SIN-17"])

    def test_comparaciones_encadenadas(self):
        self.assertIn("E-SIN-18", codigos("x Entero;\nx = 1;\nSi (1 < x < 3)\nFinSi"))

    def test_si_sin_finsi(self):
        self.assertEqual(codigos("Si (1 == 1)\nMensaje.Texto(\"a\");"), ["E-SIN-09"])

    def test_si_anidado_con_finsi_faltante(self):
        c = codigos("Si (1 == 1)\nSi (2 == 2)\nFinSi")
        self.assertEqual(c, ["E-SIN-09"])

    def test_sino_y_finsi_sueltos(self):
        self.assertEqual(codigos("Sino"), ["E-SIN-10"])
        self.assertEqual(codigos("FinSi"), ["E-SIN-10"])
        self.assertEqual(codigos("Sino\nFinSi"), ["E-SIN-10", "E-SIN-10"])

    def test_sino_repetido(self):
        self.assertEqual(codigos("Si (1 == 1)\nSino\nSino\nFinSi"), ["E-SIN-11"])

    def test_sino_y_finsi_deben_ir_solos(self):
        self.assertEqual(codigos('Si (1 == 1)\nSino Mensaje.Texto("a");\nFinSi'), ["E-SIN-12"])
        self.assertEqual(codigos('Si (1 == 1)\nFinSi Mensaje.Texto("a");'), ["E-SIN-12"])
        self.assertTrue(compilar("Si (1 == 1)\nSino // otro //\nFinSi // fin //")["exitoso"])

    def test_declaracion_dentro_de_si(self):
        self.assertEqual(codigos("Si (1 == 1)\nx Entero;\nFinSi"), ["E-SIN-16"])

    def test_sino_dentro_de_si_anidado_pertenece_al_interno(self):
        src = ('a Entero;\na = 1;\nSi (a > 0)\n  Si (a > 5)\n    Mensaje.Texto("grande");\n  Sino\n'
               '    Mensaje.Texto("chico");\n  FinSi\nSino\n  Mensaje.Texto("negativo");\nFinSi')
        self.assertEqual(ejecutar(src), ["chico"])

    def test_captura_mal_escrita(self):
        for s in ["x Entero;\nx = Captura.Fecha();", "x Entero;\nx = Captura;", "x Entero;\nx = Captura.Entero;",
                  "x Entero;\nx = Captura.Entero(5);", "Captura.Entero();"]:
            self.assertIn("E-SIN-14", codigos(s), s)

    def test_captura_con_operacion(self):
        self.assertIn("E-SIN-24", codigos("x Entero;\nx = Captura.Entero() + 1;"))

    def test_mensaje_mal_escrito(self):
        for s in ['Mensaje.Numero(5);', 'Mensaje("a");', 'Mensaje.Texto();', 'Mensaje.Texto "a";',
                  'Mensaje.Entero("a");']:
            self.assertTrue(any(c in ("E-SIN-15",) for c in codigos(s)), s)

    def test_mensaje_sin_cierre_de_parentesis(self):
        self.assertEqual(codigos('Mensaje.Texto("a";'), ["E-SIN-05"])
        self.assertEqual(codigos('Mensaje.Texto("a" "b");'), ["E-SIN-28"])

    def test_valores_faltantes(self):
        for s in ["x Entero;\nx = ;", "x Entero;\nx = 5 +;", "x Entero;\nx = * 5;", "x Entero;\nx = (5 + );"]:
            self.assertIn("E-SIN-04", codigos(s), s)

    def test_parentesis(self):
        self.assertIn("E-SIN-05", codigos("x Entero;\nx = (5 + 3;"))
        self.assertIn("E-SIN-05", codigos("x Entero;\nx = 5 + 3);"))
        self.assertIn("E-SIN-04", codigos("x Entero;\nx = ();"))

    def test_funciones_inexistentes(self):
        self.assertIn("E-SIN-20", codigos("x Entero;\nx = foo(3);"))
        self.assertIn("E-SIN-20", codigos("foo(3);"))
        self.assertIn("E-SIN-20", codigos("a.b;"))

    def test_palabras_reservadas_mal_usadas(self):
        self.assertIn("E-SIN-19", codigos("x Entero;\nx = Si;"))
        self.assertIn("E-SIN-19", codigos("x Entero;\nx = Entero;"))
        self.assertIn("E-SIN-19", codigos("Verdadero;"))

    def test_captura_y_mensaje_dentro_de_expresiones(self):
        self.assertIn("E-SIN-21", codigos('x Texto;\nx = Mensaje.Texto("a");'))
        self.assertIn("E-SIN-21", codigos("Mensaje.Texto(Captura.Texto());"))

    def test_instruccion_mal_iniciada(self):
        for s in ['"hola";', "5;", "(x);", "= 5;"]:
            self.assertTrue(codigos(s), s)

    def test_un_error_no_genera_cascada_de_errores_falsos(self):
        self.assertEqual(len(codigos("x Entero\ny Entero;\ny = 3;")), 1)

    def test_varios_errores_en_orden_de_linea(self):
        c = compilar("x Entero\nHola Mundo\n;\nx = ;")
        lineas = [e["linea"] for e in c["errores"]]
        self.assertEqual(lineas, sorted(lineas))
        self.assertGreaterEqual(len(lineas), 3)

    def test_errores_lexicos_impiden_la_fase_sintactica(self):
        c = compilar("x = 3.5;\nSi")
        self.assertEqual(c["fase_fallida"], "lexico")
        self.assertTrue(all(e["fase"] == "lexico" for e in c["errores"]))

    def test_limites_de_complejidad(self):
        self.assertEqual(codigos("x Entero;\nx = " + "(" * 100 + "1" + ")" * 100 + ";"), ["E-SIN-25"])
        self.assertEqual(codigos("x Entero;\nx = " + "+".join(["1"] * 400) + ";"), ["E-SIN-25"])
        self.assertEqual(codigos("\n".join(["Si (1 == 1)"] * 60) + "\n" + "\n".join(["FinSi"] * 60)), ["E-SIN-25"])
        self.assertTrue(compilar("x Entero;\nx = " + "+".join(["1"] * 100) + ";")["exitoso"])


class NotasDeClase(unittest.TestCase):
    """Lo que pidió el profesor en la clase del 6 de noviembre (ruta para la presentación final)."""

    def test_un_parentesis_no_puede_ir_pegado_a_un_numero(self):
        for src in ["n Entero;\nn = 1(;", "n Entero;\nn = 1(", "n Entero;\nn = (1 + 2)(3);", "n Entero;\nn = 5 5;",
                    "a Entero;\na = 1;\na = a a;", "n Entero;\nn = 2 (3 + 4);", 'Mensaje.Texto(5 (1));']:
            c = compilar(src)
            self.assertFalse(c["exitoso"], src)
            self.assertEqual([e["codigo"] for e in c["errores"]], ["E-SIN-28"], src)
        self.assertIn("operador", compilar("n Entero;\nn = 1(;")["errores"][0]["mensaje"])

    def test_un_inicio_valido_debe_completarse_y_cerrarse(self):
        for src in ["n Entero;\nn = 1 + (", "n Entero;\nn = 1 + (;", "n Entero;\nn = (", "n Entero;\nn = 1 + (2;",
                    "n Entero;\nn = 1 + ((2 + 3);", "n Entero;\nn = 1 + 2);"]:
            self.assertEqual(codigos(src), ["E-SIN-05"], src)
        self.assertIn("completar y cerrar", compilar("n Entero;\nn = 1 + (")["errores"][0]["mensaje"])

    def test_los_parentesis_bien_usados_siguen_funcionando(self):
        self.assertEqual(ejecutar("n Entero;\nn = 2 * (3 + 4) - (1);\nMensaje.Texto(n);"), ["13"])
        self.assertEqual(ejecutar("n Entero;\nn = ((1 + 2) * (3 + 4));\nMensaje.Texto(n);"), ["21"])

    def test_asignar_a_una_variable_no_declarada(self):
        self.assertEqual(codigos("x = 5;"), ["E-SEM-01"])
        self.assertEqual(codigos("x Entero;\nx = 1;\ny = x;"), ["E-SEM-01"])
        self.assertEqual(codigos("y = Captura.Entero();"), ["E-SEM-01"])

    def test_palabras_reservadas_como_nombres(self):
        for nombre in ("entero", "Entero", "texto", "real", "logico", "si", "sino", "finsi", "captura", "mensaje"):
            self.assertTrue(codigos(f"{nombre} Entero;"), nombre)

    def test_mayusculas_y_minusculas_no_encadenan_errores(self):
        self.assertEqual(codigos("x Entero;\nx = 1;\nsi (x > 1)\nFinSi"), ["E-SIN-26"])
        self.assertEqual(codigos("x Entero;\nx = 1;\nSi (x > 1)\nfinsi"), ["E-SIN-26"])
        self.assertEqual(codigos("x Entero;\nx = 1;\nSi (x > 1)\nsino\nFinSi"), ["E-SIN-26"])
        self.assertEqual(codigos("a entero;"), ["E-SIN-26"])
        self.assertEqual(codigos('MENSAJE.TEXTO("a");'), ["E-SIN-26"])
        self.assertEqual(codigos('Mensaje.texto("a");'), ["E-SIN-15"])

    def test_lo_minimo_funcional(self):
        src = ("nombre Texto;\nedad Entero;\nnombre = Captura.Texto();\nedad = Captura.Entero();\n"
               "Mensaje.Texto(\"Hola \" + nombre);\nSi (edad >= 18)\n Mensaje.Texto(\"Mayor\");\nSino\n Mensaje.Texto(\"Menor\");\nFinSi")
        self.assertEqual(ejecutar(src, ["Ana", "20"]), ["Hola Ana", "Mayor"])
        self.assertEqual(ejecutar(src, ["Ana", "10"]), ["Hola Ana", "Menor"])

    def test_casos_de_la_presentacion(self):
        """Los casos de la sección 13 de MANUAL_PROGRAMADOR.md: cada uno da el código indicado."""
        casos = [("entero Entero;", "E-SIN-27"), ("a entero;", "E-SIN-26"), ("x = 5;", "E-SEM-01"),
                 ("n Entero;\nn = 1(;", "E-SIN-28"), ("n Entero;\nn = 1 + (;", "E-SIN-05"),
                 ("n Entero;\nn = (1 + 2;", "E-SIN-05"), ("edad Entero", "E-SIN-01"),
                 ("x Entero;\nx = 1;\nSi (x > 1)\n", "E-SIN-09"), ('x Entero;\nx = "hola";', "E-SEM-03"),
                 ("x Entero;\nMensaje.Texto(x);", "E-SEM-09"), ("r Real;\nr = 5 / 0;", "E-SEM-10"),
                 ("x = 3.14;", "E-LEX-05"), ('Mensaje.Texto("sin cerrar);', "E-LEX-02"), ("x = 5 @ 3;", "E-LEX-15")]
        for src, esperado in casos:
            self.assertEqual(codigos(src)[0], esperado, src)
        self.assertEqual(ejecutar("x Entero;\nr Real;\nx = Captura.Entero();\nr = 10 / x;", ["0"])[-1], "RUN:E-EJE-02")
        self.assertEqual(ejecutar("x Entero;\nx = Captura.Entero();", ["abc", "1"]), ["INVALIDA"])
        src = 't Texto;\nt = "abc";\n' + "t = t + t;\n" * 25
        self.assertEqual(ejecutar(src)[-1], "RUN:E-EJE-04")

    def test_entradas_inesperadas_al_leer_datos(self):
        raras = ["", " ", "\x00", "\n", "😀" * 5000, "9" * 100000, "-", "+", ",", ".", "1,2,3", "٣", "１２３", "1e5", "0x10",
                 "NaN", "inf", "Infinity", "1_0", "--5", "+-5", "5-", " 42 ", "\t7\t", "verdadero\x00", "V", "true", "ñ" * 20000,
                 "\u202e5", "5\u200b", "٣,٥", "1" * 5000 + ",5"]
        for tipo, var in (("Entero", "e"), ("Real", "r"), ("Logico", "l"), ("Texto", "t")):
            src = f"{var} {tipo};\n{var} = Captura.{tipo}();\nMensaje.Texto({var});"
            c = compilar(src)
            sid, s = Sesiones().crear(c["arbol"])
            r = s.iniciar()
            for rara in raras:
                if r["terminado"]:
                    sid, s = Sesiones().crear(c["arbol"])
                    r = s.iniciar()
                r = s.entregar(rara)                      # nunca debe lanzar una excepción
                self.assertIn("terminado", r)
        self.assertEqual(ejecutar("e Entero;\ne = Captura.Entero();\nMensaje.Texto(e);", [" 42 "]), ["42"])
        self.assertEqual(ejecutar("e Entero;\ne = Captura.Entero();\nMensaje.Texto(e);", ["٣", "１２３", "1e5", "0x10", "7"]),
                         ["INVALIDA", "INVALIDA", "INVALIDA", "INVALIDA", "7"])

    def test_cualquier_locura_no_hace_fallar_al_compilador(self):
        locuras = ["", "\x00", "\x00\x01\x02" * 1000, "🙂" * 1000, "\u202e\u2066abc\u2069", "\ud800", "(" * 100000,
                   ")" * 100000, '"' * 99999, "//" * 50000, "\n" * 100000, " " * 500000, "a" * 100000, "1" * 100000,
                   "Si (" * 5000, "Sino\n" * 5000, "FinSi " * 5000, "= = = =" * 5000, "Entero;" * 10000,
                   "x Entero;\n" * 5000, "Mensaje.Texto(" * 3000, "Captura." * 3000, ";" * 100000, "'" * 100000,
                   "\t\r\n\x0b\x0c" * 5000, "\ufeff" * 1000, "x = " + "-" * 100000 + "1;", "x = " + "(" * 60 + "1" + ")" * 60 + ";"]
        for loco in locuras:
            c = compilar(loco)
            self.assertIn("exitoso", c)
            self.assertIsInstance(c["errores"], list)
            if c["exitoso"]:
                sid, s = Sesiones().crear(c["arbol"])
                s.iniciar()


class Semantica(unittest.TestCase):
    def test_variable_no_declarada(self):
        self.assertEqual(codigos("x = 5;"), ["E-SEM-01"])
        self.assertEqual(codigos("Mensaje.Texto(y);"), ["E-SEM-01"])
        self.assertEqual(codigos("x Entero;\nx = y;"), ["E-SEM-01"])
        self.assertEqual(codigos("x = Captura.Entero();"), ["E-SEM-01"])

    def test_declaracion_repetida(self):
        self.assertEqual(codigos("x Entero;\nx Texto;"), ["E-SEM-02"])
        self.assertEqual(codigos("x Entero;\nx Entero;"), ["E-SEM-02"])

    def test_mayusculas_son_variables_distintas(self):
        c = compilar("Edad Entero;\nedad Entero;\nEdad = 1;\nedad = 2;\nMensaje.Texto(Edad + edad);")
        self.assertTrue(c["exitoso"])
        self.assertIn("A-SEM-05", [a["codigo"] for a in c["advertencias"]])

    def test_tipos_al_asignar(self):
        casos = [("e Entero;", "e = \"hola\";"), ("e Entero;", "e = 3,5;"), ("t Texto;", "t = 5;"),
                 ("l Logico;", "l = 5;"), ("l Logico;", "l = \"a\";"), ("r Real;", "r = \"a\";"),
                 ("e Entero;", "e = Verdadero;"), ("t Texto;", "t = Verdadero;")]
        for decl, asig in casos:
            self.assertEqual(codigos(f"{decl}\n{asig}"), ["E-SEM-03"], asig)

    def test_conversiones_permitidas(self):
        self.assertTrue(compilar("r Real;\nr = 5;\nMensaje.Texto(r);")["exitoso"])
        self.assertTrue(compilar("l Logico;\nl = 3 > 2;\nMensaje.Texto(l);")["exitoso"])

    def test_division_da_real(self):
        self.assertEqual(codigos("e Entero;\ne = 10 / 2;"), ["E-SEM-03"])
        self.assertTrue(compilar("r Real;\nr = 10 / 2;\nMensaje.Texto(r);")["exitoso"])

    def test_operaciones_invalidas(self):
        for e in ['Mensaje.Texto("a" - 1);', 'Mensaje.Texto("a" * 2);', "Mensaje.Texto(Verdadero + 1);",
                  'Mensaje.Texto(-"a");', 'Mensaje.Texto("a" / "b");']:
            self.assertEqual(codigos(e), ["E-SEM-04"], e)

    def test_concatenacion_con_texto(self):
        self.assertTrue(compilar('Mensaje.Texto("a" + 5 + "b" + Verdadero);')["exitoso"])

    def test_condicion_debe_ser_logico(self):
        self.assertEqual(codigos("x Entero;\nx = 1;\nSi (x)\nFinSi"), ["E-SEM-05"])
        self.assertEqual(codigos("Si (5)\nFinSi"), ["E-SEM-05"])
        self.assertEqual(codigos('Si ("a")\nFinSi'), ["E-SEM-05"])
        self.assertTrue(compilar("l Logico;\nl = Verdadero;\nSi (l)\nFinSi\nSi (Falso)\nFinSi")["exitoso"])

    def test_comparaciones(self):
        self.assertEqual(codigos('Si ("a" == 1)\nFinSi'), ["E-SEM-06"])
        self.assertEqual(codigos("Si (Verdadero == 1)\nFinSi"), ["E-SEM-06"])
        self.assertEqual(codigos('Si ("a" < "b")\nFinSi'), ["E-SEM-07"])
        self.assertEqual(codigos("Si (Verdadero > Falso)\nFinSi"), ["E-SEM-07"])
        self.assertTrue(compilar('Si ("a" == "b")\nFinSi\nSi (1 == 1,0)\nFinSi\nSi (Verdadero != Falso)\nFinSi')["exitoso"])

    def test_captura_y_tipo_de_variable(self):
        self.assertEqual(codigos("n Entero;\nn = Captura.Texto();"), ["E-SEM-08"])
        self.assertEqual(codigos("n Entero;\nn = Captura.Real();"), ["E-SEM-08"])
        self.assertEqual(codigos("t Texto;\nt = Captura.Entero();"), ["E-SEM-08"])
        self.assertTrue(compilar("r Real;\nr = Captura.Entero();\nMensaje.Texto(r);")["exitoso"])

    def test_variable_sin_valor(self):
        self.assertEqual(codigos("x Entero;\nMensaje.Texto(x);"), ["E-SEM-09"])
        self.assertEqual(codigos("x Entero;\ny Entero;\ny = x + 1;"), ["E-SEM-09"])
        self.assertEqual(codigos("x Entero;\nx = x + 1;"), ["E-SEM-09"])

    def test_valor_asignado_solo_en_una_rama_advierte(self):
        src = "x Entero;\nSi (1 == 1)\n  x = 1;\nFinSi\nMensaje.Texto(x);"
        c = compilar(src)
        self.assertTrue(c["exitoso"])
        self.assertIn("A-SEM-02", [a["codigo"] for a in c["advertencias"]])

    def test_valor_asignado_en_ambas_ramas_no_advierte(self):
        src = "x Entero;\nSi (1 == 1)\n  x = 1;\nSino\n  x = 2;\nFinSi\nMensaje.Texto(x);"
        c = compilar(src)
        self.assertTrue(c["exitoso"])
        self.assertNotIn("A-SEM-02", [a["codigo"] for a in c["advertencias"]])

    def test_division_por_cero_literal(self):
        self.assertEqual(codigos("r Real;\nr = 5 / 0;"), ["E-SEM-10"])
        self.assertEqual(codigos("r Real;\nr = 5 / 0,0;"), ["E-SEM-10"])

    def test_advertencias_de_variables_sin_uso(self):
        self.assertEqual(avisos("x Entero;"), ["A-SEM-01"])
        self.assertEqual(avisos("x Entero;\nx = 1;"), ["A-SEM-03"])

    def test_los_errores_semanticos_no_se_cascada(self):
        self.assertEqual(codigos("x Entero;\nx = y + z;"), ["E-SEM-01", "E-SEM-01"])
        self.assertEqual(codigos('x Entero;\nx = "a" - 1;'), ["E-SEM-04"])

    def test_tabla_de_simbolos(self):
        c = compilar("a Entero;\nb Texto;\na = 1;\nMensaje.Texto(a);")
        nombres = {s["nombre"]: s for s in c["simbolos"]}
        self.assertEqual(set(nombres), {"a", "b"})
        self.assertTrue(nombres["a"]["usada"] and nombres["a"]["asignada"])
        self.assertFalse(nombres["b"]["usada"])


class Ejecucion(unittest.TestCase):
    def test_operaciones_y_precedencia(self):
        src = ('a Entero;\nb Entero;\nr Entero;\na = Captura.Entero();\nb = Captura.Entero();\n'
               'r = a + b * 2;\nMensaje.Texto(r);\nr = (a + b) * 2;\nMensaje.Texto(r);')
        self.assertEqual(ejecutar(src, ["3", "4"]), ["11", "14"])

    def test_suma_del_enunciado(self):
        src = ("num1 Entero; num2 Entero; num3 Entero; suma Entero;\nnum1 = 2; num2 = 3; num3 = 4;\n"
               "suma=num1+(num2*num3);\nMensaje.Texto(suma);")
        self.assertEqual(ejecutar(src), ["14"])

    def test_real_con_coma(self):
        self.assertEqual(ejecutar("pi Real;\npi = 3,1416;\nMensaje.Texto(pi);"), ["3,1416"])
        self.assertEqual(ejecutar("x Real;\nx = 10 / 4;\nMensaje.Texto(x);"), ["2,5"])
        self.assertEqual(ejecutar("x Real;\nx = 4;\nMensaje.Texto(x);"), ["4,0"])
        self.assertEqual(ejecutar("x Real;\nx = 0,1 + 0,2;\nMensaje.Texto(x);"), ["0,3"])

    def test_texto_logico_y_concatenacion(self):
        self.assertEqual(ejecutar('n Texto;\nn = "Alejandra";\nMensaje.Texto("Hola " + n + "!");'), ["Hola Alejandra!"])
        self.assertEqual(ejecutar("l Logico;\nl = 2 > 1;\nMensaje.Texto(l);"), ["Verdadero"])
        self.assertEqual(ejecutar('Mensaje.Texto("n=" + 5 + " r=" + 2,5);'), ["n=5 r=2,5"])

    def test_mensaje_vacio_es_valido(self):
        self.assertEqual(ejecutar('Mensaje.Texto("");'), [""])

    def test_condicional_y_sino(self):
        src = ('e Entero;\ne = Captura.Entero();\nSi (e >= 18)\n  Mensaje.Texto("Mayor");\nSino\n  Mensaje.Texto("Menor");\nFinSi')
        self.assertEqual(ejecutar(src, ["18"]), ["Mayor"])
        self.assertEqual(ejecutar(src, ["17"]), ["Menor"])

    def test_condicion_con_todas_las_comparaciones(self):
        for op, a, b, esperado in [("==", 1, 1, True), ("!=", 1, 1, False), ("<", 1, 2, True), (">", 1, 2, False),
                                   ("<=", 2, 2, True), (">=", 1, 2, False)]:
            src = f'Si ({a} {op} {b})\n Mensaje.Texto("si");\nSino\n Mensaje.Texto("no");\nFinSi'
            self.assertEqual(ejecutar(src), ["si" if esperado else "no"], f"{a} {op} {b}")

    def test_entrada_invalida_se_vuelve_a_pedir(self):
        src = 'e Entero;\ne = Captura.Entero();\nMensaje.Texto(e);'
        self.assertEqual(ejecutar(src, ["abc", "3,5", "", "25"]), ["INVALIDA", "INVALIDA", "INVALIDA", "25"])

    def test_entrada_real_y_logica_y_texto(self):
        src = ('r Real;\nl Logico;\nt Texto;\nr = Captura.Real();\nl = Captura.Logico();\nt = Captura.Texto();\n'
               'Mensaje.Texto(r);\nMensaje.Texto(l);\nMensaje.Texto(t);')
        self.assertEqual(ejecutar(src, ["2,5", "falso", "Hola; mundo"]), ["2,5", "Falso", "Hola; mundo"])
        self.assertEqual(ejecutar(src, ["2.5", "Verdadero", ""]), ["2,5", "Verdadero", ""])
        self.assertEqual(ejecutar(src, ["x", "2", "si", "verdadero", "t"]),
                         ["INVALIDA", "INVALIDA", "2,0", "Verdadero", "t"][:2] + ["2,0", "Verdadero", "t"])

    def test_entero_en_variable_real(self):
        self.assertEqual(ejecutar("r Real;\nr = Captura.Entero();\nMensaje.Texto(r);", ["7"]), ["7,0"])

    def test_division_por_cero_en_ejecucion(self):
        self.assertEqual(ejecutar("x Entero;\nr Real;\nx = 0;\nr = 5 / x;")[-1], "RUN:E-EJE-02")
        self.assertEqual(ejecutar("x Entero;\nx = Captura.Entero();\nMensaje.Texto(10 / x);", ["0"])[-1], "RUN:E-EJE-02")

    def test_desbordamiento_de_entero(self):
        self.assertEqual(ejecutar("x Entero;\nx = 2147483647;\nx = x + 1;")[-1], "RUN:E-EJE-03")
        self.assertEqual(ejecutar("x Entero;\nx = 100000;\nx = x * x;")[-1], "RUN:E-EJE-03")
        self.assertEqual(ejecutar("x Entero;\nx = Captura.Entero();", ["2147483648"]), ["INVALIDA", "SIN_ENTRADA"])

    def test_variable_sin_valor_por_rama_no_ejecutada(self):
        src = "x Entero;\nSi (1 == 2)\n  x = 1;\nFinSi\nMensaje.Texto(x);"
        self.assertEqual(ejecutar(src), ["RUN:E-EJE-01"])

    def test_desborde_de_real(self):
        src = "x Real;\nx = 1000000000 * 1000000,0;\nx = x * x;\nx = x * x;\nx = x * x;\nx = x * x;\nx = x * x;\nx = x * x;\nx = x * x;\nx = x * x;\nx = x * x;"
        self.assertEqual(ejecutar(src)[-1], "RUN:E-EJE-03")

    def test_negativos_y_signos(self):
        self.assertEqual(ejecutar("x Entero;\nx = -5;\nMensaje.Texto(x);\nMensaje.Texto(-x);\nMensaje.Texto(5 - -3);"),
                         ["-5", "5", "8"])

    def test_el_programa_no_reutiliza_valores_entre_ejecuciones(self):
        src = "x Entero;\nx = 1;\nMensaje.Texto(x);"
        self.assertEqual(ejecutar(src), ["1"])
        self.assertEqual(ejecutar(src), ["1"])

    def test_sesion_terminada_no_falla(self):
        c = compilar('Mensaje.Texto("a");')
        sid, s = Sesiones().crear(c["arbol"])
        s.iniciar()
        r = s.entregar("x")
        self.assertTrue(r["terminado"])


class Topes(unittest.TestCase):
    def test_un_texto_que_se_duplica_se_detiene_con_un_error(self):
        src = 't Texto;\nt = "aaaaaaaaaa";\n' + "t = t + t;\n" * 25 + 'Mensaje.Texto("listo");'
        self.assertEqual(ejecutar(src), ["RUN:E-EJE-04"])
        self.assertEqual(ejecutar('t Texto;\nt = "ab";\nt = t + t + t;\nMensaje.Texto(t);'), ["ababab"])

    def test_la_respuesta_nunca_es_gigante(self):
        c = compilar("\n".join(f"v{i} Entero;" for i in range(30000)))
        self.assertEqual(len(c["tokens"]), 20000)
        self.assertEqual(c["tokens_total"], 90000)
        self.assertEqual(len(c["advertencias"]), 500)
        self.assertEqual(c["advertencias_total"], 30000)
        self.assertEqual(len(c["simbolos"]), 5000)
        self.assertEqual(c["simbolos_total"], 30000)
        self.assertTrue(c["exitoso"])
        self.assertIsNone(comp.publico(c)["arbol"])
        self.assertTrue(comp.publico(c)["arbol_omitido"])
        self.assertIsNotNone(comp.publico(compilar("x Entero;"))["arbol"])

    def test_muchas_variables_no_hacen_lento_el_compilador(self):
        import time
        inicio = time.time()
        c = compilar("\n".join(f"v{i} Entero;\nV{i} Entero;" for i in range(10000)))
        self.assertTrue(c["exitoso"])
        self.assertLess(time.time() - inicio, 8)


class Catalogo(unittest.TestCase):
    def test_todo_codigo_emitido_esta_en_el_catalogo(self):
        en_catalogo = {c["codigo"] for c in catalogo()}
        aqui = os.path.dirname(os.path.abspath(__file__))
        usados = set()
        for archivo in glob.glob(os.path.join(aqui, "costenol_*.py")):
            with open(archivo, encoding="utf-8") as f:
                texto = f.read()
            usados |= set(re.findall(r'"([EA]-(?:LEX|SIN|SEM|EJE)-\d\d)"', texto))
        faltan = usados - en_catalogo
        self.assertEqual(faltan, set(), f"Códigos sin documentar: {sorted(faltan)}")

    def test_todo_catalogo_tiene_textos(self):
        for c in catalogo():
            self.assertTrue(c["titulo"] and c["significa"] and c["corregir"], c["codigo"])


class Ejemplos(unittest.TestCase):
    def test_los_ejemplos_validos_compilan_y_los_de_errores_fallan(self):
        aqui = os.path.dirname(os.path.abspath(__file__))
        for archivo in sorted(glob.glob(os.path.join(aqui, "ejemplos", "*.cst"))):
            with open(archivo, encoding="utf-8-sig") as f:
                texto = f.read()
            nombre = os.path.basename(archivo)
            c = compilar(texto)
            titulo = texto.splitlines()[0]
            if "rror" in titulo:
                self.assertFalse(c["exitoso"], nombre)
            else:
                self.assertTrue(c["exitoso"], f"{nombre}: {[e['mensaje'] for e in c['errores']]}")


class Manual(unittest.TestCase):
    """Los ejemplos del manual deben seguir funcionando: si cambia el lenguaje,
    esta prueba avisa que hay que actualizar web/manual.html."""

    def test_ejemplos_del_manual(self):
        import html
        aqui = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(aqui, "web", "manual.html"), encoding="utf-8") as f:
            texto = f.read()
        texto = re.sub(r"<!--.*?-->", "", texto, flags=re.S)
        ejemplos = re.findall(r'<pre class="codigo"([^>]*)>(.*?)</pre>', texto, re.S)
        self.assertGreaterEqual(len(ejemplos), 8)
        for atributos, codigo in ejemplos:
            codigo = html.unescape(codigo).strip("\n") + "\n"
            c = compilar(codigo)
            if "data-error" in atributos:
                self.assertFalse(c["exitoso"], codigo)
            else:
                self.assertTrue(c["exitoso"], f"{codigo}\n{[e['mensaje'] for e in c['errores']]}")

    def test_salidas_de_ejemplo_del_manual(self):
        self.assertEqual(ejecutar('Mensaje.Texto("Hola Mundo");'), ["Hola Mundo"])
        src = ("num1 Entero;\nnum2 Entero;\nnum3 Entero;\nsuma Entero;\nnombre Texto;\npi Real;\n"
               "num1 = 2;\nnum2 = 3;\nnum3 = 4;\nsuma = num1 + (num2 * num3);\nnombre = \"Alejandra\";\n"
               "pi = 3,1416;\nMensaje.Texto(suma);")
        self.assertEqual(ejecutar(src), ["14"])
        src = ('nombre Texto;\ntotal Entero;\nnombre = "Alejandra";\ntotal = 5 * 4;\n'
               'Mensaje.Texto("Esto es una prueba");\nMensaje.Texto("");\nMensaje.Texto(nombre);\n'
               'Mensaje.Texto("El total es " + total);')
        self.assertEqual(ejecutar(src), ["Esto es una prueba", "", "Alejandra", "El total es 20"])
        self.assertEqual(ejecutar("edad Entero;\nmayor Logico;\nedad = 20;\nmayor = edad >= 18;\nMensaje.Texto(mayor);"),
                         ["Verdadero"])
        self.assertEqual(ejecutar("Mensaje.Texto(2 + 3 * 4);\nMensaje.Texto((2 + 3) * 4);"), ["14", "20"])
        src = ("nota1 Real;\nnota2 Real;\npromedio Real;\nnota1 = 4,5;\nnota2 = 3,5;\n"
               "promedio = (nota1 + nota2) / 2;\nMensaje.Texto(\"Promedio: \" + promedio);")
        self.assertEqual(ejecutar(src), ["Promedio: 4,0"])
        src = ("anioNacimiento Entero;\nanioActual Entero;\nedad Entero;\nanioActual = 2026;\n"
               "Mensaje.Texto(\"Ingrese su año de nacimiento:\");\nanioNacimiento = Captura.Entero();\n"
               "edad = anioActual - anioNacimiento;\nMensaje.Texto(\"Tu edad es: \" + edad + \" años\");")
        self.assertEqual(ejecutar(src, ["1995"]), ["Ingrese su año de nacimiento:", "Tu edad es: 31 años"])


class Robustez(unittest.TestCase):
    PIEZAS = ["x", "y", "Entero", "Texto", "Real", "Logico", "Si", "Sino", "FinSi", "Captura", "Mensaje", ".", "(", ")",
              ";", "=", "==", "<", "+", "-", "*", "/", '"hola"', "5", "3,5", "Verdadero", "\n", "\n", " ", "//c//",
              "@", ",", "!", "'"]

    def test_fuzz_nunca_revienta(self):
        azar = random.Random(12345)
        for _ in range(1500):
            src = " ".join(azar.choice(self.PIEZAS) for _ in range(azar.randint(1, 40)))
            c = compilar(src)
            self.assertIn("exitoso", c)
            if c["exitoso"]:
                sid, s = Sesiones().crear(c["arbol"])
                r = s.iniciar()
                pasos = 0
                while not r["terminado"] and pasos < 50:
                    r = s.entregar("1")
                    pasos += 1

    def test_programas_validos_aleatorios_se_ejecutan(self):
        azar = random.Random(7)
        for _ in range(300):
            lineas = ["a Entero;", "b Entero;", "c Real;", "a = " + str(azar.randint(-50, 50)) + ";",
                      "b = " + str(azar.randint(-50, 50)) + ";"]
            expr = f"a {azar.choice('+-*')} b {azar.choice('+-*')} {azar.randint(1, 9)}"
            lineas.append(f"c = ({expr}) / {azar.randint(1, 9)};")
            lineas.append("Mensaje.Texto(c);")
            lineas.append(f"Si (a {azar.choice(['<', '>', '==', '!=', '<=', '>='])} b)\n Mensaje.Texto(\"si\");\nSino\n Mensaje.Texto(\"no\");\nFinSi")
            salida = ejecutar("\n".join(lineas))
            self.assertFalse(salida[0].startswith("ERR"), salida)
            self.assertIn(salida[-1], ("si", "no"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
