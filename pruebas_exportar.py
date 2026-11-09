#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pruebas de Exportar: cada formato debe comportarse igual que el compilador.

Para cada programa se ejecuta el intérprete y el programa exportado (Python,
JavaScript con Node.js y Java con un JDK) con los mismos datos de entrada, y se
comparan la salida y los errores. Los formatos cuya herramienta no esté
instalada en este computador se omiten.

Ejecutar:   python pruebas_exportar.py
"""

import glob
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

import costenol_exportar as ex
from costenol_compilador import Sesiones, compilar

AQUI = os.path.dirname(os.path.abspath(__file__))
HAY_NODE = shutil.which("node") is not None
HAY_JDK = ex.jdk_disponible()


# -- referencia: el intérprete del compilador ------------------------------------------
def referencia(arbol, entradas):
    """Devuelve (lineas_de_salida, error_o_None)."""
    sid, s = Sesiones().crear(arbol)
    entradas = list(entradas)
    salida = []
    r = s.iniciar()
    while True:
        salida += r["salida"]
        if r["error"]:
            e = r["error"]
            return salida, f"Error de ejecución (línea {e['linea']}): {e['mensaje']}"
        if r["terminado"]:
            return salida, None
        if not entradas:
            return salida, "FIN"
        r = s.entregar(entradas.pop(0))
        if r.get("invalida"):
            salida.append("Valor no válido: " + r["invalida"])


def lineas(texto):
    t = texto.replace("\r\n", "\n")
    if t.endswith("\n"):
        t = t[:-1]
    return t.split("\n") if t != "" else []


def correr(cmd, entradas, cwd):
    p = subprocess.run(cmd, input="".join(l + "\n" for l in entradas), capture_output=True, text=True,
                       encoding="utf-8", cwd=cwd, timeout=60)
    return p.stdout, p.stderr, p.returncode


def comparar(caso, esperado_salida, esperado_error, stdout, stderr, codigo, etiqueta):
    caso.assertEqual(lineas(stdout), esperado_salida, f"[{etiqueta}] salida distinta\n--- stderr ---\n{stderr}")
    if esperado_error is None:
        caso.assertEqual(codigo, 0, f"[{etiqueta}] terminó con error: {stderr}")
    elif esperado_error == "FIN":
        caso.assertEqual(codigo, 1, etiqueta)
        caso.assertIn("no hay más datos", stderr, etiqueta)
    else:
        caso.assertEqual(codigo, 1, f"[{etiqueta}] debía fallar")
        caso.assertEqual(stderr.strip(), esperado_error, etiqueta)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.carpeta = tempfile.mkdtemp()

    def arbol(self, codigo):
        c = compilar(codigo)
        self.assertTrue(c["exitoso"], [e["mensaje"] for e in c["errores"]])
        return c["arbol"]

    def verificar_python(self, codigo, entradas=()):
        arbol = self.arbol(codigo)
        sal, err = referencia(arbol, entradas)
        ruta = os.path.join(self.carpeta, "p.py")
        with open(ruta, "wb") as f:
            f.write(ex.exportar(arbol, "python", "p")["contenido"])
        comparar(self, sal, err, *correr([sys.executable, ruta], entradas, self.carpeta), "python")

    def verificar_js(self, codigo, entradas=()):
        if not HAY_NODE:
            return
        arbol = self.arbol(codigo)
        sal, err = referencia(arbol, entradas)
        ruta = os.path.join(self.carpeta, "p.js")
        with open(ruta, "wb") as f:
            f.write(ex.exportar(arbol, "javascript", "p")["contenido"])
        comparar(self, sal, err, *correr(["node", ruta], entradas, self.carpeta), "javascript")

    def verificar_java(self, codigo, entradas=()):
        if not HAY_JDK:
            return
        arbol = self.arbol(codigo)
        sal, err = referencia(arbol, entradas)
        carpeta = tempfile.mkdtemp(dir=self.carpeta)
        fuente = ex.exportar(arbol, "java_fuente")
        self.assertEqual(fuente["archivo"], "Programa.java")
        with open(os.path.join(carpeta, "Programa.java"), "wb") as f:
            f.write(fuente["contenido"])
        c = subprocess.run([ex._herramienta("javac"), "-encoding", "UTF-8", "Programa.java"], cwd=carpeta,
                           capture_output=True, text=True, timeout=90)
        self.assertEqual(c.returncode, 0, "javac rechazó el código:\n" + c.stderr)
        comparar(self, sal, err, *correr(["java", "-cp", carpeta, "Programa"], entradas, carpeta), "java")

    def verificar_todo(self, codigo, entradas=()):
        self.verificar_python(codigo, entradas)
        self.verificar_js(codigo, entradas)
        self.verificar_java(codigo, entradas)


# ---------------------------------------------------------------------------------------
PROGRAMAS = [
    ("hola", 'Mensaje.Texto("Hola Mundo");', []),
    ("vacio", "", []),
    ("solo_declaraciones", "a Entero; b Real; c Texto; d Logico;", []),
    ("enunciado",
     "num1 Entero; num2 Entero; num3 Entero; suma Entero;\nnum1 = 2; num2 = 3; num3 = 4;\n"
     "suma=num1+(num2*num3);\nMensaje.Texto(suma);", []),
    ("reales",
     "pi Real;\npi = 3,1416;\nMensaje.Texto(pi);\nMensaje.Texto(pi * 2);\nMensaje.Texto(10 / 4);\n"
     "Mensaje.Texto(4 / 2);\nMensaje.Texto(0,1 + 0,2);\nMensaje.Texto(-0,0);\nMensaje.Texto(1 / 3);\n"
     "Mensaje.Texto(2 / 3);\nMensaje.Texto(1000000 * 1000000,5);", []),
    ("reales_grandes",
     "x Real;\nx = 1000000000 * 1000000,0;\nMensaje.Texto(x);\nx = x * x;\nMensaje.Texto(x);\n"
     "x = x * x;\nMensaje.Texto(x);\nMensaje.Texto(0,00000000004);\nMensaje.Texto(0,0000000001);\n"
     "Mensaje.Texto(0,00048828125);", []),
    ("texto_y_concatenacion",
     'n Texto;\nn = "Alejandra";\nMensaje.Texto("Hola " + n + "!");\nMensaje.Texto("n=" + 5 + " r=" + 2,5 + " " + Verdadero);\n'
     'Mensaje.Texto(1 + 2 + "x" + 3 + 4);\nMensaje.Texto("");\nMensaje.Texto("a" + "");', []),
    ("caracteres_raros",
     'Mensaje.Texto("tildes: áéíóú ñ Ñ ü ¿¡?!");\nMensaje.Texto("emoji: \U0001F600 y \u4e2d\u6587");\n'
     'Mensaje.Texto("barra \\ y \\n y \\u0041 y \\\\");\nMensaje.Texto("comillas \u201cdobles\u201d y \'simples\'");\n'
     'Mensaje.Texto("</script> <!-- --> <b>x</b> & &amp;");\nMensaje.Texto("tab\tadentro");\n'
     'Mensaje.Texto(\u201ccurvas\u201d);\nMensaje.Texto("100% %d %s {} ${x} `x`");', []),
    ("nombres_con_ene_y_palabras_de_otros_lenguajes",
     "año Entero;\nclass Entero;\ndef Entero;\nint Entero;\nprint Entero;\nSystem Entero;\nmain Entero;\nnew Entero;\n"
     "año = 2026;\nclass = 1;\ndef = 2;\nint = 3;\nprint = 4;\nSystem = 5;\nmain = 6;\nnew = 7;\n"
     "Mensaje.Texto(año + class + def + int + print + System + main + new);", []),
    ("comparaciones",
     'a Entero; r Real; t Texto; l Logico;\na = 5; r = 5,0; t = "x"; l = Verdadero;\n'
     'Mensaje.Texto(a == r);\nMensaje.Texto(a != r);\nMensaje.Texto(a < r);\nMensaje.Texto(a <= r);\n'
     'Mensaje.Texto(a > 4,99);\nMensaje.Texto(a >= 5);\nMensaje.Texto(0,1 + 0,2 == 0,3);\nMensaje.Texto(0,1 + 0,2 <= 0,3);\n'
     'Mensaje.Texto(0,1 + 0,2 < 0,3);\nMensaje.Texto(0,1 + 0,2 > 0,3);\n'
     'Mensaje.Texto(t == "x");\nMensaje.Texto(t != "x");\nMensaje.Texto(l == Verdadero);\nMensaje.Texto(l != Falso);\n'
     'Mensaje.Texto(1 == 1 == 1);' if False else
     'a Entero; r Real; t Texto; l Logico;\na = 5; r = 5,0; t = "x"; l = Verdadero;\n'
     'Mensaje.Texto(a == r);\nMensaje.Texto(a != r);\nMensaje.Texto(a < r);\nMensaje.Texto(a <= r);\n'
     'Mensaje.Texto(a > 4,99);\nMensaje.Texto(a >= 5);\nMensaje.Texto(0,1 + 0,2 == 0,3);\nMensaje.Texto(0,1 + 0,2 <= 0,3);\n'
     'Mensaje.Texto(0,1 + 0,2 < 0,3);\nMensaje.Texto(0,1 + 0,2 > 0,3);\n'
     'Mensaje.Texto(t == "x");\nMensaje.Texto(t != "x");\nMensaje.Texto(l == Verdadero);\nMensaje.Texto(l != Falso);', []),
    ("logicos_en_variables",
     "a Logico; b Logico;\na = 3 > 2;\nb = a == Falso;\nMensaje.Texto(a);\nMensaje.Texto(b);\n"
     "Si (a)\n Mensaje.Texto(\"a verdadero\");\nFinSi\nSi (b)\n Mensaje.Texto(\"b verdadero\");\nSino\n Mensaje.Texto(\"b falso\");\nFinSi", []),
    ("condicionales_anidados_y_vacios",
     "n Entero;\nn = Captura.Entero();\nSi (n > 0)\n  Si (n > 10)\n    Mensaje.Texto(\"grande\");\n  Sino\n    Mensaje.Texto(\"chico\");\n  FinSi\n"
     "Sino\n  Si (n == 0)\n  FinSi\n  Mensaje.Texto(\"no positivo\");\nFinSi\nSi (n > 100)\nSino\nFinSi\nSi (n > 5)\nFinSi\nMensaje.Texto(\"fin\");", ["50"]),
    ("signos",
     "x Entero;\nx = -5;\nMensaje.Texto(x);\nMensaje.Texto(-x);\nMensaje.Texto(5 - -3);\nMensaje.Texto(- - 4);\nMensaje.Texto(+x);\n"
     "Mensaje.Texto(-(2 + 3) * 2);\nMensaje.Texto(-2,5);", []),
    ("precedencia", "Mensaje.Texto(2 + 3 * 4);\nMensaje.Texto((2 + 3) * 4);\nMensaje.Texto(10 - 2 - 3);\nMensaje.Texto(100 / 10 / 5);\nMensaje.Texto(7 - 2 * 3 + 1);", []),
    ("entero_en_real",
     "r Real;\nr = 7;\nMensaje.Texto(r);\nr = Captura.Entero();\nMensaje.Texto(r);\nr = r + 1;\nMensaje.Texto(r);", ["12"]),
    ("lectura_de_todo",
     "n Texto; e Entero; r Real; l Logico;\nn = Captura.Texto();\ne = Captura.Entero();\nr = Captura.Real();\nl = Captura.Logico();\n"
     "Mensaje.Texto(n + \"|\" + e + \"|\" + r + \"|\" + l);", ["  Ana  Pérez ", " 42 ", "2,5", "FALSO"]),
    ("entradas_invalidas",
     "e Entero; r Real; l Logico;\ne = Captura.Entero();\nr = Captura.Real();\nl = Captura.Logico();\n"
     "Mensaje.Texto(e);\nMensaje.Texto(r);\nMensaje.Texto(l);",
     ["abc", "3,5", "", "+7", "99999999999", "2147483648", "-2147483647", "1,5", "1.5", ".5", "1,", "-3.25", "si", "no", "0", "1" + "0" * 400,
      "Verdadero"]),
    ("entero_gigante_de_miles_de_digitos", "e Entero;\ne = Captura.Entero();\nMensaje.Texto(e);", ["9" * 5000, "007"]),
    ("texto_largo", "t Texto;\nt = Captura.Texto();\nMensaje.Texto(t);", ["x" * 10001, "ñ" * 10000]),
    ("division_por_cero", "x Entero;\nr Real;\nx = Captura.Entero();\nr = 10 / x;\nMensaje.Texto(r);", ["0"]),
    ("desborde_suma", "x Entero;\nx = 2147483647;\nMensaje.Texto(x);\nx = x + 1;\nMensaje.Texto(x);", []),
    ("desborde_producto", "x Entero;\nx = 100000;\nx = x * x;", []),
    ("desborde_negativo", "x Entero;\nx = -2147483647;\nx = x - 1;", []),
    ("desborde_real", "x Real;\nx = 1000000000 * 1000000,0;\n" + "x = x * x;\n" * 9 + "Mensaje.Texto(x);", []),
    ("variable_sin_valor_en_ejecucion", "x Entero;\nSi (1 == 2)\n  x = 1;\nFinSi\nMensaje.Texto(\"antes\");\nMensaje.Texto(x);", []),
    ("variable_con_valor_en_una_rama",
     "x Entero;\nn Entero;\nn = Captura.Entero();\nSi (n > 0)\n  x = 1;\nFinSi\nMensaje.Texto(x);", ["5"]),
    ("variable_real_en_rama", "x Real; t Texto;\nSi (1 == 1)\n  x = 2;\n  t = \"a\";\nFinSi\nMensaje.Texto(x + 1);\nMensaje.Texto(t);", []),
    ("variable_logica_en_rama", "l Logico;\nSi (1 == 1)\n  l = Verdadero;\nFinSi\nMensaje.Texto(l);", []),
    ("fin_de_los_datos", "e Entero;\ne = Captura.Entero();\nMensaje.Texto(e);", []),
    ("texto_que_se_duplica", 't Texto;\nt = "aaaaaaaaaa";\nMensaje.Texto("antes");\n' + "t = t + t;\n" * 25 + 'Mensaje.Texto("listo");', []),
    ("division_de_enteros_a_real", "a Entero; b Entero; r Real;\na = 7; b = 2;\nr = a / b;\nMensaje.Texto(r);\nMensaje.Texto(a / b * b);", []),
]


class PorPrograma(Base):
    def test_programas(self):
        for nombre, codigo, entradas in PROGRAMAS:
            with self.subTest(programa=nombre):
                self.verificar_python(codigo, entradas)
                self.verificar_js(codigo, entradas)

    @unittest.skipUnless(HAY_JDK, "no hay JDK en este computador")
    def test_programas_en_java(self):
        for nombre, codigo, entradas in PROGRAMAS:
            with self.subTest(programa=nombre):
                self.verificar_java(codigo, entradas)


class Ejemplos(Base):
    def test_los_ejemplos_validos_se_exportan_igual(self):
        entradas = {"02_programa_completo": ["Ana", "30"], "03_operaciones": ["2", "3", "4"],
                    "04_condicionales_anidados": ["4,7"], "05_ejemplos_del_enunciado": ["Luz", "3,5", "8", "Verdadero"],
                    "13_division_por_cero_al_ejecutar": ["0"]}
        for ruta in sorted(glob.glob(os.path.join(AQUI, "ejemplos", "*.cst"))):
            with open(ruta, encoding="utf-8-sig") as f:
                codigo = f.read()
            if "rror" in codigo.splitlines()[0]:
                continue
            clave = os.path.splitext(os.path.basename(ruta))[0]
            with self.subTest(ejemplo=clave):
                self.verificar_todo(codigo, entradas.get(clave, []))


class Aleatorios(Base):
    def test_programas_aleatorios(self):
        azar = random.Random(2024)
        textos = ['"hola"', '"añ\\o"', '""', '"x y"', '"\U0001F600"']
        for i in range(120):
            lineas = ["a Entero;", "b Entero;", "r Real;", "s Real;", "t Texto;", "l Logico;",
                      f"a = {azar.randint(-40, 40)};", f"b = {azar.randint(-40, 40)};"]
            def ent():
                return azar.choice(["a", "b", str(azar.randint(0, 9)), f"({azar.choice(['a', 'b'])} {azar.choice('+-*')} {azar.randint(1, 9)})"])
            def real():
                return azar.choice(["r", "s", f"{azar.randint(0, 9)},{azar.randint(0, 99)}", f"({ent()} / {azar.randint(1, 9)})"])
            lineas += [f"r = {ent()} {azar.choice('+-*')} {real()};",
                       f"s = {real()} {azar.choice('+-*/')} {azar.randint(1, 9)};",
                       f"t = {azar.choice(textos)};",
                       f"l = {ent()} {azar.choice(['<', '>', '==', '!=', '<=', '>='])} {real()};",
                       f"Mensaje.Texto(r);", "Mensaje.Texto(s);", "Mensaje.Texto(l);",
                       f"Mensaje.Texto(t + \" \" + {ent()} + \" \" + {real()} + \" \" + l);",
                       f"Si ({real()} {azar.choice(['<', '>', '==', '!=', '<=', '>='])} {real()})\n Mensaje.Texto(\"si\");\nSino\n Mensaje.Texto(\"no\");\nFinSi"]
            codigo = "\n".join(lineas)
            if compilar(codigo)["exitoso"]:
                with self.subTest(i=i):
                    self.verificar_python(codigo)
                    self.verificar_js(codigo)
                    if HAY_JDK and i % 10 == 0:
                        self.verificar_java(codigo)


class Formatos(Base):
    def test_lista_de_formatos(self):
        ids = [f["id"] for f in ex.formatos()]
        self.assertEqual(ids, ["python", "javascript", "html", "java_jar", "java_fuente"])
        self.assertTrue(all(f["extension"].startswith(".") and f["como"] for f in ex.formatos()))

    def test_nombres_de_archivo(self):
        arbol = self.arbol('Mensaje.Texto("x");')
        for nombre, esperado in (("mi programa.cst", "mi_programa.py"), ("../../etc/pas swd", "pas_swd.py"),
                                 ("", "programa.py"), (None, "programa.py"), ("año.cst", "año.py"),
                                 ("a" * 200, "a" * 60 + ".py"), ("<script>.txt", "script.py")):
            self.assertEqual(ex.exportar(arbol, "python", nombre)["archivo"], esperado, nombre)
        self.assertEqual(ex.exportar(arbol, "java_fuente", "loquesea")["archivo"], "Programa.java")
        self.assertEqual(ex.exportar(arbol, "html", "x")["archivo"], "x.html")

    def test_formato_desconocido(self):
        with self.assertRaises(ex.ErrorExportacion):
            ex.exportar(self.arbol('Mensaje.Texto("x");'), "cobol", "x")

    def test_un_texto_con_codigo_dentro_no_se_ejecuta_ni_rompe_el_archivo(self):
        # El texto del usuario solo puede salir como literal: nunca como código del otro lenguaje.
        codigo = r'Mensaje.Texto("*/ ; System.exit(0); // /* \u000a \");'
        self.verificar_todo(codigo)
        arbol = self.arbol(codigo)
        for formato in ("python", "javascript", "html", "java_fuente"):
            texto = ex.exportar(arbol, formato, "x")["contenido"].decode("utf-8")
            self.assertEqual(texto.count("System.exit(0)"), 1, formato)

    @unittest.skipUnless(HAY_JDK, "no hay JDK en este computador")
    def test_jar_ejecutable(self):
        codigo = ('n Texto;\ne Entero;\nn = Captura.Texto();\ne = Captura.Entero();\n'
                  'Mensaje.Texto("Hola " + n + ", tienes " + e + " años");')
        arbol = self.arbol(codigo)
        r = ex.exportar(arbol, "java_jar", "mi programa")
        self.assertEqual(r["archivo"], "mi_programa.jar")
        self.assertEqual(r["contenido"][:2], b"PK")
        ruta = os.path.join(self.carpeta, r["archivo"])
        with open(ruta, "wb") as f:
            f.write(r["contenido"])
        p = subprocess.run(["java", "-jar", ruta], input="Ana\n30\n", capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(lineas(p.stdout), ["Hola Ana, tienes 30 años"])

    def test_jar_sin_jdk_da_un_error_claro(self):
        anterior = ex._herramienta
        ex._herramienta = lambda n: None
        try:
            with self.assertRaises(ex.ErrorExportacion) as c:
                ex.construir_jar("class X {}")
            self.assertEqual(c.exception.estado, 501)
            self.assertIn("JDK", c.exception.mensaje)
            self.assertFalse(ex.jdk_disponible())
            self.assertFalse(next(f for f in ex.formatos() if f["id"] == "java_jar")["disponible"])
        finally:
            ex._herramienta = anterior

    def test_html_tiene_la_estructura_esperada(self):
        arbol = self.arbol('n Texto;\nn = Captura.Texto();\nMensaje.Texto("</script>" + n);')
        html = ex.exportar(arbol, "html", "x")["contenido"].decode("utf-8")
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertEqual(html.count("</script>"), 1)       # solo el que cierra la etiqueta
        self.assertIn('id="salida"', html)
        self.assertNotIn("require(", html)                  # nada de Node dentro de la página


if __name__ == "__main__":
    unittest.main(verbosity=1)
