#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pruebas del analizador léxico de Costeñol.

Ejecutar:   python pruebas_lexico.py
Cada prueba indica el código de entrada y lo que debe ocurrir. Sirve como
lista de chequeo antes de las revisiones y de la sustentación.
"""

import unittest

from costenol_lexico import (
    analizar, COMENTARIO, CADENA, PALABRA_RESERVADA, IDENTIFICADOR, NUMERO_ENTERO,
    NUMERO_REAL, VALOR_LOGICO, OPERADOR_ASIGNACION, OPERADOR_RELACIONAL,
    OPERADOR_ARITMETICO, PARENTESIS_APERTURA, PARENTESIS_CIERRE, PUNTO_Y_COMA, PUNTO,
)


def tipos(codigo):
    return [t.tipo for t in analizar(codigo).tokens]


def valores(codigo):
    return [t.valor for t in analizar(codigo).tokens]


def errores(codigo):
    return analizar(codigo).errores


class Validos(unittest.TestCase):
    def test_declaraciones(self):
        for linea, tipo in [("num1 Entero;", "Entero"), ("nombre Texto;", "Texto"),
                            ("n1 Real;", "Real"), ("asis Logico;", "Logico")]:
            r = analizar(linea)
            self.assertTrue(r.exitoso, linea)
            self.assertEqual([t.tipo for t in r.tokens],
                             [IDENTIFICADOR, PALABRA_RESERVADA, PUNTO_Y_COMA])
            self.assertEqual(r.tokens[1].valor, tipo)

    def test_captura(self):
        r = analizar("nombre = Captura.Texto();")
        self.assertTrue(r.exitoso)
        self.assertEqual([t.tipo for t in r.tokens], [
            IDENTIFICADOR, OPERADOR_ASIGNACION, PALABRA_RESERVADA, PUNTO, PALABRA_RESERVADA,
            PARENTESIS_APERTURA, PARENTESIS_CIERRE, PUNTO_Y_COMA])

    def test_asignaciones_del_enunciado(self):
        for c in ["A=b;", "suma=num1+(num2*num3);", 'nombre="Alejandra";', "pi=3,1416;"]:
            self.assertTrue(analizar(c).exitoso, c)

    def test_ejemplo_suma(self):
        self.assertEqual(valores("suma=num1+(num2*num3);"),
                         ["suma", "=", "num1", "+", "(", "num2", "*", "num3", ")", ";"])

    def test_mensaje(self):
        r = analizar('Mensaje.Texto("Esto es una prueba");')
        self.assertTrue(r.exitoso)
        self.assertEqual([t.tipo for t in r.tokens], [
            PALABRA_RESERVADA, PUNTO, PALABRA_RESERVADA, PARENTESIS_APERTURA, CADENA,
            PARENTESIS_CIERRE, PUNTO_Y_COMA])

    def test_condicional_completo(self):
        codigo = "Si (edad >= 18)\nMensaje.Texto(\"Mayor\");\nSino\nMensaje.Texto(\"Menor\");\nFinSi"
        r = analizar(codigo)
        self.assertTrue(r.exitoso)
        reservadas = [t.valor for t in r.tokens if t.tipo == PALABRA_RESERVADA]
        self.assertEqual(reservadas, ["Si", "Mensaje", "Texto", "Sino", "Mensaje", "Texto", "FinSi"])

    def test_comentario(self):
        r = analizar("// esto es un comentario //")
        self.assertTrue(r.exitoso)
        self.assertEqual(tipos("// hola //"), [COMENTARIO])

    def test_comentario_en_medio_de_la_linea(self):
        self.assertEqual(tipos("a = 5; // nota // b = 6;"),
                         [IDENTIFICADOR, OPERADOR_ASIGNACION, NUMERO_ENTERO, PUNTO_Y_COMA,
                          COMENTARIO, IDENTIFICADOR, OPERADOR_ASIGNACION, NUMERO_ENTERO, PUNTO_Y_COMA])

    def test_comentario_vacio(self):
        self.assertEqual(tipos("////"), [COMENTARIO])

    def test_comentario_con_simbolos_raros(self):
        self.assertTrue(analizar("// @#$%& ñ ó ¿? { } //").exitoso)

    def test_cadenas_rectas_y_tipograficas(self):
        self.assertEqual(tipos('"hola"'), [CADENA])
        self.assertEqual(tipos("\u201chola\u201d"), [CADENA])
        self.assertEqual(tipos('""'), [CADENA])

    def test_cadena_con_simbolos_y_palabras_reservadas(self):
        for texto in ['"hola; adiós"', '"(prueba)"', '"Si"', '"a // b"', '"ñandú ¿qué?"', '"3,14"']:
            r = analizar(texto)
            self.assertTrue(r.exitoso, texto)
            self.assertEqual([t.tipo for t in r.tokens], [CADENA], texto)

    def test_numeros(self):
        self.assertEqual(tipos("0"), [NUMERO_ENTERO])
        self.assertEqual(tipos("25"), [NUMERO_ENTERO])
        self.assertEqual(tipos("3,1416"), [NUMERO_REAL])
        self.assertEqual(tipos("0,5"), [NUMERO_REAL])
        self.assertEqual(tipos("2147483647"), [NUMERO_ENTERO])

    def test_valores_logicos(self):
        self.assertEqual(tipos("Verdadero Falso"), [VALOR_LOGICO, VALOR_LOGICO])

    def test_operadores(self):
        self.assertEqual(tipos("= == != < > <= >="),
                         [OPERADOR_ASIGNACION] + [OPERADOR_RELACIONAL] * 6)
        self.assertEqual(tipos("+ - * /"), [OPERADOR_ARITMETICO] * 4)

    def test_sin_espacios(self):
        self.assertEqual(valores("Si(edad>5)"), ["Si", "(", "edad", ">", "5", ")"])

    def test_espacios_y_tabulaciones(self):
        self.assertEqual(valores("Captura . Entero ( )"),
                         ["Captura", ".", "Entero", "(", ")"])
        self.assertTrue(analizar("\t\ta\t=\t5\t;").exitoso)

    def test_ene_en_identificador(self):
        self.assertEqual(tipos("año_1 = 5;")[0], IDENTIFICADOR)
        self.assertTrue(analizar("teñido Texto;").exitoso)

    def test_identificadores_con_numeros_y_guion(self):
        self.assertTrue(analizar("num_1 = 5; x2 = 1;").exitoso)

    def test_posiciones(self):
        r = analizar("a = 5;\n  b = 6;")
        self.assertEqual((r.tokens[0].linea, r.tokens[0].columna), (1, 1))
        b = [t for t in r.tokens if t.valor == "b"][0]
        self.assertEqual((b.linea, b.columna), (2, 3))

    def test_lineas_vacias_no_alteran_la_numeracion(self):
        r = analizar("\n\n\nnum Entero;\n\n$")
        self.assertEqual(r.errores[0].linea, 6)
        self.assertEqual(r.tokens[0].linea, 4)

    def test_saltos_de_linea_windows_y_mac(self):
        self.assertEqual(analizar("a=1;\r\nb=2;\r\nc=3;").tokens[-1].linea, 3)
        self.assertEqual(analizar("a=1;\rb=2;\rc=3;").tokens[-1].linea, 3)

    def test_bom_inicial(self):
        self.assertTrue(analizar("\ufeffa = 1;").exitoso)


class Vacios(unittest.TestCase):
    def test_vacio_solo_advierte(self):
        for c in ["", "   ", "\n\n", "\t \n"]:
            r = analizar(c)
            self.assertTrue(r.exitoso)
            self.assertEqual(len(r.advertencias), 1)

    def test_solo_comentarios_advierte(self):
        r = analizar("// uno //\n// dos //")
        self.assertTrue(r.exitoso)
        self.assertEqual(len(r.advertencias), 1)

    def test_none(self):
        self.assertTrue(analizar(None).exitoso)


class Comentarios(unittest.TestCase):
    def test_sin_cerrar(self):
        e = errores("// hola")
        self.assertEqual(len(e), 1)
        self.assertIn("Comentario sin cerrar", e[0].mensaje)

    def test_solo_apertura(self):
        self.assertEqual(len(errores("//")), 1)

    def test_tres_barras(self):
        self.assertEqual(len(errores("///")), 1)

    def test_multilinea_no_permitido(self):
        e = errores("// primera\nsegunda //")
        self.assertGreaterEqual(len(e), 1)
        self.assertEqual(e[0].linea, 1)

    def test_el_resto_de_la_linea_no_genera_errores_falsos(self):
        self.assertEqual(len(errores("// sin cerrar @#$%")), 1)

    def test_la_siguiente_linea_se_sigue_analizando(self):
        r = analizar("// sin cerrar\nnum Entero;")
        self.assertEqual(len(r.errores), 1)
        self.assertEqual(len(r.tokens), 3)

    def test_division_no_es_comentario(self):
        self.assertEqual(tipos("a / b"), [IDENTIFICADOR, OPERADOR_ARITMETICO, IDENTIFICADOR])


class Cadenas(unittest.TestCase):
    def test_sin_cerrar(self):
        e = errores('"hola')
        self.assertEqual(len(e), 1)
        self.assertIn("sin cerrar", e[0].mensaje)

    def test_solo_una_comilla(self):
        self.assertEqual(len(errores('"')), 1)

    def test_tipografica_sin_cerrar(self):
        self.assertEqual(len(errores("\u201chola")), 1)

    def test_comillas_distintas(self):
        e = errores('"hola\u201d')
        self.assertEqual(len(e), 1)
        self.assertIn("mal cerrada", e[0].mensaje)
        e = errores("\u201chola\"")
        self.assertEqual(len(e), 1)
        self.assertIn("mal cerrada", e[0].mensaje)

    def test_comilla_simple(self):
        e = errores("'hola'")
        self.assertTrue(e)
        self.assertIn("comillas dobles", e[0].mensaje)

    def test_comilla_de_cierre_suelta(self):
        self.assertTrue(errores("\u201d"))

    def test_cadena_no_cruza_lineas(self):
        e = errores('"hola\nmundo"')
        self.assertEqual(len(e), 2)


class Numeros(unittest.TestCase):
    def test_punto_decimal(self):
        e = errores("x = 3.1416;")
        self.assertEqual(len(e), 1)
        self.assertIn("coma", e[0].mensaje)

    def test_coma_final(self):
        self.assertEqual(len(errores("x = 3,;")), 1)

    def test_coma_al_inicio(self):
        self.assertTrue(errores("x = ,5;"))

    def test_dos_comas(self):
        e = errores("x = 1,2,3;")
        self.assertEqual(len(e), 1)
        self.assertIn("una coma", e[0].mensaje)

    def test_numero_pegado_a_letras(self):
        for c in ["5abc", "1num", "3,14abc", "10_000", "0x1F"]:
            self.assertTrue(errores(c), c)
        self.assertEqual(len(errores("x = 5abc;")), 1)

    def test_ceros_a_la_izquierda(self):
        for c in ["007", "00", "01,5"]:
            e = errores(c)
            self.assertEqual(len(e), 1, c)
            self.assertIn("ceros", e[0].mensaje)

    def test_punto_al_inicio(self):
        self.assertTrue(errores(".5"))

    def test_entero_fuera_de_rango(self):
        e = errores("2147483648")
        self.assertEqual(len(e), 1)
        self.assertIn("fuera de rango", e[0].mensaje)
        self.assertTrue(errores("9" * 400))

    def test_numero_negativo_son_dos_tokens(self):
        self.assertEqual(tipos("-5"), [OPERADOR_ARITMETICO, NUMERO_ENTERO])


class Identificadores(unittest.TestCase):
    def test_empieza_con_guion_bajo(self):
        self.assertTrue(errores("_x"))

    def test_tildes_en_identificador(self):
        e = errores("Lógico")
        self.assertEqual(len(e), 1)
        self.assertIn("¿Quiso decir 'Logico'?", e[0].mensaje)
        self.assertTrue(errores("edád = 5;"))

    def test_demasiado_largo(self):
        self.assertTrue(errores("a" * 31 + " Entero;"))
        self.assertTrue(analizar("a" * 30 + " Entero;").exitoso)

    def test_variantes_de_reservadas_son_nombres_para_el_lexico(self):
        # El analizador léxico solo separa piezas; que un nombre se parezca a una palabra
        # reservada lo rechaza el analizador sintáctico (E-SIN-27 / E-SIN-26).
        for palabra in ["si", "SI", "sino", "FINSI", "finsi", "entero", "TEXTO", "captura", "mensaje"]:
            r = analizar(palabra)
            self.assertEqual([t.tipo for t in r.tokens], [IDENTIFICADOR], palabra)
            self.assertTrue(r.exitoso)

    def test_reservadas_exactas_son_reservadas(self):
        for p in ["Entero", "Texto", "Real", "Logico", "Captura", "Mensaje", "Si", "Sino", "FinSi"]:
            self.assertEqual(tipos(p), [PALABRA_RESERVADA], p)

    def test_emoji(self):
        e = errores("x = 5; \U0001F600")
        self.assertEqual(len(e), 1)


class Operadores(unittest.TestCase):
    def test_invalidos(self):
        for op in ["=>", "=<", "<>", "!", "===", "!==", "<<", "==="]:
            e = errores(f"a {op} b")
            self.assertEqual(len(e), 1, op)

    def test_aritmeticos_repetidos_no_son_error_lexico(self):
        self.assertEqual(len(errores("a ** b")), 0)
        self.assertEqual(len(errores("a ++ b")), 0)


class Simbolos(unittest.TestCase):
    def test_caracteres_invalidos(self):
        for c in "@#$%&^~|\\{}[]:?¿¡'`,":
            e = errores(f"x {c} y")
            self.assertEqual(len(e), 1, c)

    def test_cada_caracter_invalido_se_reporta(self):
        self.assertEqual(len(errores("@#$")), 3)

    def test_espacio_duro_advierte(self):
        r = analizar("a\u00a0=\u00a05;")
        self.assertTrue(r.exitoso)
        self.assertEqual(len(r.advertencias), 2)

    def test_caracteres_invisibles(self):
        self.assertTrue(errores("a\u200b = 5;"))
        self.assertTrue(errores("a = 5;\x00"))


class Robustez(unittest.TestCase):
    def test_nunca_revienta(self):
        casos = ["", "\x00\x01\x02", "\\" * 1000, '"' * 1001, "//" * 777, "(" * 5000,
                 "\ud800", "a" * 100000, "1" * 100000, "\n" * 20000, "x = 5;\n" * 20000,
                 "\u202e\u2066", "𝒜𝒷𝒸 = 5;", 12345, ["lista"]]
        for c in casos:
            r = analizar(c)
            self.assertIsNotNone(r)
            r.a_dict()

    def test_limite_de_errores(self):
        r = analizar("@" * 1000)
        self.assertEqual(len(r.errores), 200)
        self.assertTrue(any("máximo" in a.mensaje for a in r.advertencias))

    def test_tamano_maximo(self):
        r = analizar("a" * 2_000_001)
        self.assertFalse(r.exitoso)

    def test_el_resultado_es_serializable(self):
        import json
        json.dumps(analizar("x = 5; @").a_dict())


class ProgramaCompleto(unittest.TestCase):
    PROGRAMA = '''// Programa de prueba //
edad Entero;
nombre Texto;
promedio Real;
activo Logico;

nombre = Captura.Texto();
edad = Captura.Entero();
promedio = (4,5 + 3,5) / 2;
activo = Verdadero;

Si (edad >= 18)
    Mensaje.Texto("Mayor de edad");
Sino
    Mensaje.Texto("Menor de edad");
FinSi
'''

    def test_programa_valido(self):
        r = analizar(self.PROGRAMA)
        self.assertTrue(r.exitoso)
        self.assertEqual(r.advertencias, [])
        self.assertGreater(len(r.tokens), 50)

    def test_programa_con_varios_errores_los_reporta_todos_en_orden(self):
        codigo = "a Entero;\nb = 3.5;\nc = @;\n// sin cerrar\nd = \"hola;\n"
        r = analizar(codigo)
        self.assertEqual([e.linea for e in r.errores], [2, 3, 4, 5])


if __name__ == "__main__":
    unittest.main(verbosity=1)
