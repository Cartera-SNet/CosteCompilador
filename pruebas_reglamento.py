#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Matriz de cumplimiento del reglamento de Costeñol.

Cada regla del enunciado del proyecto (PDF del profesor) y de las notas de la clase del
6 de noviembre tiene aquí sus casos:
    validos    programas (o fragmentos) que el compilador DEBE aceptar sin errores
    invalidos  programas que el compilador DEBE rechazar, con el código del primer error

Se usa de dos formas:
    python pruebas_reglamento.py             corre las pruebas
    python pruebas_reglamento.py --informe   imprime la matriz en Markdown (para la documentación)

Fuentes:  PDF = enunciado del proyecto · CLASE = notas de la clase del 6 de noviembre
          EQ  = regla propuesta por el equipo (pendiente de confirmar con el profesor)
"""

import sys
import unittest

from costenol_compilador import Sesiones, compilar

REGLAS = [
    # ------------------------------------------------------------------ tipos y declaración
    dict(id="R01", fuente="PDF", regla="Hay cuatro tipos de dato: Texto, Entero, Real y Logico (escritos exactamente así).",
         validos=["a Texto;\nb Entero;\nc Real;\nd Logico;"],
         invalidos=[("a Cadena;", "E-SIN-03"), ("a Booleano;", "E-SIN-03"), ("a texto;", "E-SIN-26"),
                    ("a ENTERO;", "E-SIN-26"), ("a real;", "E-SIN-26"), ("a logico;", "E-SIN-26")]),
    dict(id="R02", fuente="PDF", regla="Declarar una variable: nombre, tipo y punto y coma (num1 Entero;).",
         validos=["num1 Entero;\nnombre Texto;\nn1 Real;\nasis Logico;"],
         invalidos=[("Entero num1;", "E-SIN-23"), ("num1 Entero", "E-SIN-01"), ("num1;", "E-SIN-03"),
                    ("num1 Entero Entero;", "E-SIN-01"), ("a Entero;\na Entero;", "E-SEM-02")]),
    dict(id="R03", fuente="PDF", regla="Leer datos: variable = Captura.Tipo(); con Tipo = Texto, Entero, Real o Logico.",
         validos=["nombre Texto;\nn1 Entero;\nnum1 Real;\nasis Logico;\nnombre = Captura.Texto();\nn1 = Captura.Entero();\n"
                  "num1 = Captura.Real();\nasis = Captura.Logico();\nMensaje.Texto(nombre);\nMensaje.Texto(n1);\n"
                  "Mensaje.Texto(num1);\nMensaje.Texto(asis);"],
         invalidos=[("x Entero;\nx = Captura.Entero;", "E-SIN-14"), ("x Entero;\nx = Captura.Foo();", "E-SIN-14"),
                    ("x Entero;\nx = Captura.Entero(5);", "E-SIN-14"), ("x Entero;\nx = Captura();", "E-SIN-14"),
                    ("x Entero;\nx = captura.Entero();", "E-SIN-26"), ("x Entero;\nx = Captura.entero();", "E-SIN-14"),
                    ("x Entero;\nx = Captura . Entero();", "E-SIN-14"), ("x Entero;\nx = Captura.// c //Entero();", "E-SIN-14"), ("x Entero;\nx = Captura.\nEntero();", "E-SIN-14")]),
    dict(id="R04", fuente="PDF/CLASE", regla="El tipo de Captura debe ser el de la variable: no se lee un Entero en una variable Real "
                                             "ni al revés (ni ningún otro tipo cruzado).",
         validos=["r Real;\nr = Captura.Real();\nMensaje.Texto(r);"],
         invalidos=[("r Real;\nr = Captura.Entero();", "E-SEM-08"), ("e Entero;\ne = Captura.Real();", "E-SEM-08"),
                    ("t Texto;\nt = Captura.Entero();", "E-SEM-08"), ("e Entero;\ne = Captura.Texto();", "E-SEM-08"),
                    ("l Logico;\nl = Captura.Real();", "E-SEM-08"), ("r Real;\nr = Captura.Logico();", "E-SEM-08")]),
    # ------------------------------------------------------------------ asignaciones, números y texto
    dict(id="R05", fuente="PDF", regla="Se permite cualquier asignación, incluso con operaciones y paréntesis (A=b; suma=num1+(num2*num3);).",
         validos=["A Entero;\nb Entero;\nb = 4;\nA=b;\nMensaje.Texto(A);",
                  "num1 Entero;\nnum2 Entero;\nnum3 Entero;\nsuma Entero;\nnum1=2;\nnum2=3;\nnum3=4;\nsuma=num1+(num2*num3);\nMensaje.Texto(suma);",
                  "x Entero;\nx = 2 * (3 + 4) - (1);\nMensaje.Texto(x);"],
         invalidos=[("e Entero;\ne = \"hola\";", "E-SEM-03"), ("e Entero;\nr Real;\nr = 1,5;\ne = r;", "E-SEM-03"),
                    ("t Texto;\nt = 5;", "E-SEM-03")]),
    dict(id="R06", fuente="PDF", regla="Los decimales se escriben con coma (pi=3,1416;); con punto es un error.",
         validos=["pi Real;\npi=3,1416;\nMensaje.Texto(pi);"],
         invalidos=[("pi Real;\npi = 3.1416;", "E-LEX-05"), ("pi Real;\npi = 3,;", "E-LEX-06"), ("pi Real;\npi = .5;", "E-LEX-08")]),
    dict(id="R07", fuente="PDF", regla="El texto va entre comillas (rectas o curvas): nombre=“Alejandra”;",
         validos=["nombre Texto;\nnombre=“Alejandra”;\nMensaje.Texto(nombre);", "nombre Texto;\nnombre=\"Alejandra\";\nMensaje.Texto(nombre);"],
         invalidos=[("nombre Texto;\nnombre = \"Alejandra;", "E-LEX-02"), ("nombre Texto;\nnombre = Alejandra;", "E-SEM-01")]),
    dict(id="R08", fuente="PDF", regla="Escribir mensajes: Mensaje.Texto(contenido); (el contenido va entre comillas o es un valor).",
         validos=["Mensaje.Texto(“Esto es una prueba”);", "Mensaje.Texto(\"Hola Mundo\");", "x Entero;\nx = 1;\nMensaje.Texto(x);"],
         invalidos=[("Mensaje(\"x\");", "E-SIN-15"), ("Mensaje.Texto(\"x\")", "E-SIN-01"), ("Mensaje.Texto();", "E-SIN-15"),
                    ("mensaje.texto(\"x\");", "E-SIN-26"), ("Mensaje.texto(\"x\");", "E-SIN-15"),
                    ("MENSAJE.TEXTO(\"x\");", "E-SIN-26"), ("Mensaje . Texto(\"x\");", "E-SIN-15"),
                    ("Mensaje.Texto(\"x\";", "E-SIN-05")]),
    # ------------------------------------------------------------------ condicional
    dict(id="R09", fuente="PDF", regla="Condicional: Si, UN espacio y la condición entre paréntesis; Sino opcional; siempre termina con FinSi.",
         validos=["x Entero;\nx = 5;\nSi (x > 3)\nMensaje.Texto(\"grande\");\nFinSi",
                  "x Entero;\nx = 5;\nSi (x > 3)\nMensaje.Texto(\"grande\");\nSino\nMensaje.Texto(\"chico\");\nFinSi"],
         invalidos=[("x Entero;\nx = 5;\nSi(x > 3)\nFinSi", "E-SIN-13"),
                    ("x Entero;\nx = 5;\nSi  (x > 3)\nFinSi", "E-SIN-29"),
                    ("x Entero;\nx = 5;\nSi     (x > 3)\nFinSi", "E-SIN-29"),
                    ("x Entero;\nx = 5;\nSi\t(x > 3)\nFinSi", "E-SIN-29"),
                    ("x Entero;\nx = 5;\nSi // c // (x > 3)\nFinSi", "E-SIN-29"),
                    ("x Entero;\nx = 5;\nSi (x > 3)", "E-SIN-09"),
                    ("x Entero;\nx = 5;\nSi x > 3\nFinSi", "E-SIN-06"),
                    ("x Entero;\nx = 5;\nSi\n(x > 3)\nFinSi", "E-SIN-06"),
                    ("x Entero;\nx = 5;\nSi ()\nFinSi", "E-SIN-07"),
                    ("x Entero;\nx = 5;\nSi (x > 3\nFinSi", "E-SIN-08"),
                    ("Sino\nFinSi", "E-SIN-10"), ("FinSi", "E-SIN-10"),
                    ("x Entero;\nx = 5;\nSi (x > 3)\nSino\nSino\nFinSi", "E-SIN-11"),
                    ("x Entero;\nx = 5;\nSi (x > 3)\nFinSi Mensaje.Texto(1);", "E-SIN-12"),
                    ("x Entero;\nx = 5;\nSi (x > 3)\nSino Mensaje.Texto(1);\nFinSi", "E-SIN-12")]),
    dict(id="R10", fuente="PDF/CLASE", regla="Las mayúsculas y minúsculas importan: Si, Sino, FinSi, Mensaje, Captura y los tipos se escriben exactamente así.",
         validos=["x Entero;\nx = 1;\nSi (x == 1)\nMensaje.Texto(x);\nSino\nMensaje.Texto(0);\nFinSi"],
         invalidos=[("x Entero;\nx = 1;\nsi (x == 1)\nFinSi", "E-SIN-26"), ("x Entero;\nx = 1;\nSI (x == 1)\nFinSi", "E-SIN-26"),
                    ("x Entero;\nx = 1;\nSi (x == 1)\nsino\nFinSi", "E-SIN-26"), ("x Entero;\nx = 1;\nSi (x == 1)\nFINSI", "E-SIN-26"),
                    ("x Entero;\nx = 1;\nSi (x == 1)\nFinsi", "E-SIN-26"), ("a entero;", "E-SIN-26")]),
    # ------------------------------------------------------------------ comentarios y símbolos
    dict(id="R11", fuente="PDF", regla="Comentarios de una línea: // al comienzo y // al final.",
         validos=["// esto es un comentario //\nx Entero;\nx = 1;\nMensaje.Texto(x);", "x Entero;\nx = 1; // nota //\nMensaje.Texto(x);"],
         invalidos=[("// sin cierre\nx Entero;", "E-LEX-01"), ("x Entero; // sin cierre", "E-LEX-01")]),
    dict(id="R12", fuente="PDF", regla="Operadores + - * / y =; símbolos ( ) ; . ; cualquier otro símbolo no pertenece al lenguaje.",
         validos=["x Entero;\nx = 1 + 2 - 3 * 4 / 2;\nMensaje.Texto(x);".replace("x Entero", "x Real")],
         invalidos=[("x Entero;\nx = 5 @ 3;", "E-LEX-15"), ("x Entero;\nx = 5 # 3;", "E-LEX-15"), ("x Entero;\nx = 5 => 3;", "E-LEX-13"),
                    ("x Entero;\nx = 5 $ 3;", "E-LEX-15"), ("¡x Entero;", "E-LEX-15")]),
    # ------------------------------------------------------------------ notas de la clase
    dict(id="R13", fuente="CLASE", regla="Paréntesis: no se permite «(» después de un número sin operador; todo paréntesis se cierra "
                                         "(num = 1( es incorrecto; 1 + ( debe completarse y cerrarse).",
         validos=["num Entero;\nnum = 1 * (2 + 3);\nMensaje.Texto(num);"],
         invalidos=[("num Entero;\nnum = 1(;", "E-SIN-28"), ("num Entero;\nnum = 1(", "E-SIN-28"), ("num Entero;\nnum = 1 + (;", "E-SIN-05"),
                    ("num Entero;\nnum = 1 + (", "E-SIN-05"), ("num Entero;\nnum = (1 + 2;", "E-SIN-05"),
                    ("num Entero;\nnum = 1 + 2);", "E-SIN-05"), ("num Entero;\nnum = (1 + 2)(3);", "E-SIN-28"),
                    ("num Entero;\nnum = 5 5;", "E-SIN-28")]),
    dict(id="R14", fuente="CLASE", regla="Se rechazan las asignaciones (y lecturas) a variables que no hayan sido declaradas.",
         validos=["x Entero;\nx = 5;\nMensaje.Texto(x);"],
         invalidos=[("x = 5;", "E-SEM-01"), ("y = Captura.Entero();", "E-SEM-01"), ("x Entero;\nx = 1;\nz = x;", "E-SEM-01"),
                    ("x Entero;\nx = y;", "E-SEM-01"), ("Mensaje.Texto(w);", "E-SEM-01")]),
    dict(id="R15", fuente="CLASE", regla="Las palabras reservadas y los tipos no se pueden usar como nombre de variable (entero Entero; se rechaza).",
         validos=["edad Entero;\nedad = 1;\nMensaje.Texto(edad);"],
         invalidos=[("entero Entero;", "E-SIN-27"), ("Entero Entero;", ("E-SIN-23", "E-SIN-27")), ("texto Texto;", "E-SIN-27"),
                    ("Real Real;", ("E-SIN-23", "E-SIN-27")), ("Logico Logico;", ("E-SIN-23", "E-SIN-27")), ("si Entero;", "E-SIN-27"),
                    ("Si Entero;", ("E-SIN-06", "E-SIN-09", "E-SIN-27")), ("FinSi Entero;", ("E-SIN-10", "E-SIN-27")), ("Mensaje Entero;", ("E-SIN-15", "E-SIN-27")),
                    ("Captura Entero;", ("E-SIN-14", "E-SIN-27")), ("Sino Texto;", ("E-SIN-10", "E-SIN-27")), ("ENTERO Entero;", "E-SIN-27")]),
    dict(id="R16", fuente="PDF/EQ", regla="Cada instrucción termina en punto y coma.",
         validos=["x Entero;\nx = 1;\nMensaje.Texto(x);"],
         invalidos=[("x Entero\nx = 1;", "E-SIN-01"), ("x Entero;\nx = 1\nMensaje.Texto(x);", "E-SIN-01"),
                    ("x Entero;\nx = 1;\nMensaje.Texto(x)", "E-SIN-01"), ("x Entero;\nx = Captura.Entero()", "E-SIN-01")]),
    # ------------------------------------------------------------------ tipos al operar y comparar
    dict(id="R17", fuente="PDF/EQ", regla="Los valores deben ser válidos para el tipo de la variable (no se guarda un Real en un Entero, "
                                          "ni un Texto en un Entero); un Entero cabe en un Real.",
         validos=["r Real;\nr = 5;\nMensaje.Texto(r);", "r Real;\nr = 2,5;\nMensaje.Texto(r);"],
         invalidos=[("e Entero;\ne = 2,5;", "E-SEM-03"), ("e Entero;\ne = \"2\";", "E-SEM-03"), ("l Logico;\nl = 1;", "E-SEM-03"),
                    ("t Texto;\nt = Verdadero;", "E-SEM-03"), ("e Entero;\ne = 10 / 2;", "E-SEM-03")]),
    dict(id="R18", fuente="EQ", regla="La condición del Si debe dar Verdadero o Falso; no se comparan tipos distintos.",
         validos=["x Entero;\nx = 5;\nSi (x >= 3)\nMensaje.Texto(x);\nFinSi"],
         invalidos=[("x Entero;\nx = 5;\nSi (x)\nFinSi", "E-SEM-05"), ("x Entero;\nx = 5;\nSi (x == \"5\")\nFinSi", "E-SEM-06"),
                    ("x Entero;\nx = 5;\nSi (x = 5)\nFinSi", "E-SIN-17")]),
    dict(id="R19", fuente="EQ", regla="Una variable debe tener valor antes de usarse (se le asigna o se lee con Captura).",
         validos=["x Entero;\nx = Captura.Entero();\nMensaje.Texto(x);"],
         invalidos=[("x Entero;\nMensaje.Texto(x);", "E-SEM-09"), ("a Entero;\nb Entero;\nb = 1;\na = b + a;", "E-SEM-09")]),
    dict(id="R20", fuente="CLASE", regla="Los errores indican (en costeño) la línea, el tipo de error y la causa.",
         validos=[], invalidos=[]),     # se comprueba aparte (pruebas_dialecto.py y abajo)
]


def primer_error(src):
    c = compilar(src)
    return (c["errores"][0]["codigo"] if c["errores"] else None), c


class Reglamento(unittest.TestCase):
    def test_cada_regla_con_sus_casos(self):
        fallas = []
        for r in REGLAS:
            for src in r["validos"]:
                cod, c = primer_error(src)
                if cod is not None:
                    fallas.append(f"{r['id']} debería ACEPTAR y da {cod}: {src!r}")
            for src, esperado in r["invalidos"]:
                cod, c = primer_error(src)
                if cod not in (esperado if isinstance(esperado, tuple) else (esperado,)):
                    fallas.append(f"{r['id']} debería dar {esperado} y da {cod}: {src!r}")
        self.assertEqual(fallas, [], "\n" + "\n".join(fallas))

    def test_los_validos_tambien_se_ejecutan(self):
        """Lo que se acepta debe poder correr sin falla (con datos de ejemplo para Captura)."""
        datos = {"Texto": "Ana", "Entero": "7", "Real": "2,5", "Logico": "Verdadero"}
        for r in REGLAS:
            for src in r["validos"]:
                c = compilar(src)
                if not c["exitoso"]:
                    continue
                _, s = Sesiones().crear(c["arbol"])
                res = s.iniciar()
                pasos = 0
                while not res["terminado"] and pasos < 20:
                    tipo = (res.get("espera") or {}).get("tipo_dato", "Entero")
                    res = s.entregar(datos.get(tipo, "1"))
                    pasos += 1
                self.assertTrue(res["terminado"], f"{r['id']}: no terminó {src!r}")
                self.assertIsNone(res.get("error"), f"{r['id']}: falló al ejecutar {src!r}: {res.get('error')}")

    def test_todo_error_trae_linea_tipo_y_causa_en_costeno(self):
        total = 0
        for r in REGLAS:
            for src, _ in r["invalidos"]:
                c = compilar(src)
                e = c["errores"][0]
                f = e["mensaje_costeno"]
                total += 1
                self.assertRegex(f, r"(?i)en la línea \d+", f"{r['id']} {src!r}")
                self.assertRegex(f, r"Error (léxico|sintáctico|semántico|de ejecución):", f"{r['id']} {src!r}")
                self.assertTrue(e["linea"] >= 1 and e["mensaje"], f"{r['id']} {src!r}")
        self.assertGreater(total, 100)

    def test_ningun_caso_hace_fallar_al_compilador(self):
        for r in REGLAS:
            for src, _ in r["invalidos"]:
                c = compilar(src)
                self.assertFalse(c["exitoso"], f"{r['id']} {src!r}")
                self.assertTrue(all(e["codigo"] != "E-SIN-97" for e in c["errores"]))


def informe():
    """Matriz en Markdown: regla, fuente, ejemplo aceptado, ejemplo rechazado y el mensaje que se ve."""
    filas = ["| Regla | Fuente | Se acepta | Se rechaza (y qué dice el compilador) | Casos |",
             "| --- | --- | --- | --- | --- |"]
    def un_renglon(s, n=70):
        s = s.replace("\n", " ⏎ ").replace("\t", "→").replace("|", "\\|")
        return s if len(s) <= n else s[:n - 1] + "…"
    for r in REGLAS:
        ok = f"`{un_renglon(r['validos'][0])}`" if r["validos"] else "—"
        if r["invalidos"]:
            src, cod = r["invalidos"][0]
            c = compilar(src)
            e = c["errores"][0]
            mal = f"`{un_renglon(src)}` → **{e['codigo']}**: {e['mensaje_costeno'].replace('|', chr(92) + '|')}"
        else:
            mal = "Todos los errores"
        n = len(r["validos"]) + len(r["invalidos"])
        filas.append(f"| **{r['id']}** {r['regla'].replace('|', chr(92) + '|')} | {r['fuente']} | {ok} | {mal} | {n} |")
    return "\n".join(filas)


if __name__ == "__main__":
    if "--informe" in sys.argv:
        print(informe())
    else:
        unittest.main(verbosity=1)
