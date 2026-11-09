# -*- coding: utf-8 -*-
"""
Costeñol - Dialecto costeño para los mensajes

El lenguaje se llama Costeñol porque el compilador habla como costeño. Este módulo
convierte cada error o advertencia en una frase con el formato que pidió el profesor:

    <apertura> en la línea N. Error <tipo>: <causa>

    Ejemplo:  Ojo, la cagaste en la línea 5. Error semántico: la variable 'x' no está declarada.

Todo lo que se dice está en tablas (APERTURAS_* y CAUSAS), pensadas para editarse sin
tocar el código: basta con cambiar o agregar frases. Si un código no tiene frase propia
se usa el mensaje formal como causa, así que nunca queda un mensaje vacío.

En las causas se puede usar:
    '{q0}' '{q1}' ...   lo que va entre comillas simples en el mensaje formal (nombres, números)
    {g1} {g2} ...   grupos de la expresión regular propia de esa causa (tipos, líneas)
La apertura se elige según la línea y el código, de modo que el mismo error siempre se
dice igual (y las pruebas son estables).
"""

import re

TIPOS_DE_ERROR = {
    "LEX": "léxico",
    "SIN": "sintáctico",
    "SEM": "semántico",
    "EJE": "de ejecución",
}

# --- aperturas (el {n} es el número de línea) ------------------------------------
APERTURAS_ERROR = [
    "Ojo, la cagaste en la línea {n}.",
    "Ey compa, tienes un error en la línea {n}.",
    "Ajá, compa, aquí hay un problema en la línea {n}.",
    "Eche, mi llave, ahí en la línea {n} hay un error.",
    "Pilas, compa, algo falló en la línea {n}.",
    "Mira, mi llave, en la línea {n} hay un enredo.",
]

APERTURAS_AVISO = [
    "Ojito, compa, en la línea {n}.",
    "Ey, ojo con lo que hay en la línea {n}.",
    "Ajá, mi llave, mira lo que hay en la línea {n}.",
]

# --- causas: código -> (expresión regular opcional, plantilla) ---------------------
CAUSAS = {
    # -- léxico
    "E-LEX-01": (None, "dejaste un comentario abierto: le falta el // de cierre en la misma línea."),
    "E-LEX-02": (None, "ese texto entre comillas quedó sin cerrar (o lo cerraste con otra comilla); ciérralo con la misma comilla y en la misma línea."),
    "E-LEX-04": (None, "'{q0}' está mal escrito: un número no puede llevar letras pegadas."),
    "E-LEX-05": (None, "los decimales van con coma, no con punto: '{q0}' escríbelo con coma."),
    "E-LEX-06": (None, "esa coma decimal está mal puesta en '{q0}': lleva una sola coma y dígitos después."),
    "E-LEX-07": (None, "ese entero '{q0}' es demasiado grande, mi llave: el máximo es 2147483647."),
    "E-LEX-08": (None, "un número no puede empezar con punto; ponle el cero delante, como 0,5."),
    "E-LEX-09": (None, "'{q0}' tiene ceros de más a la izquierda; quítaselos."),
    "E-LEX-10": (None, "el nombre '{q0}' no puede empezar con guion bajo; empieza con una letra."),
    "E-LEX-11": (None, "el nombre '{q0}' tiene tildes o símbolos raros; solo se aceptan letras sin tilde, ñ, números y guion bajo."),
    "E-LEX-12": (None, "ese nombre es larguísimo: el máximo son 30 caracteres."),
    "E-LEX-13": (None, "ese operador no existe en Costeñol; los buenos son = == != < > <= >= + - * /."),
    "E-LEX-14": (None, "hay un carácter invisible en esa línea (seguro lo pegaste de otro lado); bórralo y escribe la línea de nuevo."),
    "E-LEX-15": (None, "ese símbolo no se usa en Costeñol."),
    "E-LEX-97": (None, "se enredó algo por dentro del analizador léxico; vuelve a intentar."),
    "E-LEX-98": (None, "ese programa es demasiado grande; pártelo en pedazos más pequeños."),
    # -- sintáctico
    "E-SIN-01": (None, "te faltó el punto y coma al final de la instrucción."),
    "E-SIN-02": (None, "esa instrucción empezó mal: tiene que empezar con un nombre de variable, Mensaje o Si."),
    "E-SIN-03": (None, "después del nombre '{q0}' va un tipo (Texto, Entero, Real o Logico) para declararla, o un = para asignarle un valor."),
    "E-SIN-04": (None, "falta un valor: completa la expresión."),
    "E-SIN-05": (None, "los paréntesis no cuadran: falta cerrar uno o sobra otro."),
    "E-SIN-06": (None, "después del Si va un espacio y la condición entre paréntesis."),
    "E-SIN-07": (None, "la condición del Si está vacía; escribe algo entre los paréntesis."),
    "E-SIN-08": (None, "a la condición del Si le falta el paréntesis de cierre."),
    "E-SIN-09": (None, "ese Si no tiene su FinSi."),
    "E-SIN-10": (None, "ese Sino o FinSi no tiene su Si por ningún lado."),
    "E-SIN-11": (None, "ese Si ya tiene su Sino; solo se permite uno."),
    "E-SIN-12": (None, "Sino y FinSi van solitos en su línea."),
    "E-SIN-13": (None, "te faltó el espacio entre el Si y el paréntesis."),
    "E-SIN-14": (None, "Captura está mal escrita; va así: variable = Captura.Tipo();"),
    "E-SIN-15": (None, "Mensaje está mal escrito; va así: Mensaje.Texto(valor);"),
    "E-SIN-16": (None, "no declares variables dentro de un Si; hazlo antes, al inicio del programa."),
    "E-SIN-17": (None, "dentro del Si se compara con ==; un solo = es para guardar valores."),
    "E-SIN-18": (None, "no se pueden encadenar comparaciones; haz una sola por condición."),
    "E-SIN-19": (None, "esa palabra reservada no se puede usar así."),
    "E-SIN-20": (None, "eso no es una función de Costeñol; solo existen Captura.Tipo() y Mensaje.Texto()."),
    "E-SIN-21": (None, "Captura y Mensaje no van metidos dentro de una operación."),
    "E-SIN-22": (None, "hay un punto y coma de más."),
    "E-SIN-23": (None, "un tipo de dato no puede ir de primero ni ser nombre de variable; se escribe nombre Tipo;"),
    "E-SIN-24": (None, "lo que lees con Captura se guarda solo, sin operaciones en la misma línea."),
    "E-SIN-25": (None, "esa instrucción está demasiado enredada; pártela en varias."),
    "E-SIN-26": (None, "'{q0}' está mal escrito: en Costeñol las mayúsculas y minúsculas importan, escríbelo tal cual se llama."),
    "E-SIN-27": (None, "el nombre '{q0}' no sirve: una variable no puede llamarse como un tipo de dato ni como una palabra reservada, ni cambiando las mayúsculas."),
    "E-SIN-28": (None, "falta un operador entre dos valores (como en 1( o en 5 5)."),
    "E-SIN-97": (None, "se enredó algo por dentro del analizador sintáctico; vuelve a intentar."),
    # -- semántico
    "E-SEM-01": (None, "la variable '{q0}' no está declarada."),
    "E-SEM-02": (r"línea (\d+)", "la variable '{q0}' ya la habías declarado en la línea {g1}."),
    "E-SEM-03": (r"valor (\w+) en '([^']*)', que es (\w+)",
                 "no puedes guardar un valor {g1} en '{g2}' porque esa variable es {g3}; los tipos no son compatibles."),
    "E-SEM-04": (None, "esa operación no se puede hacer con esos tipos."),
    "E-SEM-05": (r"pero aquí es (\w+)", "la condición del Si tiene que dar Verdadero o Falso, y aquí te dio {g1}."),
    "E-SEM-06": (r"comparar (\w+) con (\w+)", "no se pueden comparar {g1} con {g2}: tienen que ser del mismo tipo."),
    "E-SEM-07": (None, "los símbolos < > <= >= solo sirven con números."),
    "E-SEM-08": (r"Captura\.(\w+)\(\) lee un valor (\w+), pero '([^']*)' es (\w+)",
                 "Captura.{g1}() lee un {g2}, pero '{g3}' es {g4}; usa Captura.{g4}()."),
    "E-SEM-09": (None, "la variable '{q0}' la estás usando antes de darle un valor."),
    "E-SEM-10": (None, "no se puede dividir por cero, compa."),
    "E-SEM-97": (None, "se enredó algo por dentro del analizador semántico; vuelve a intentar."),
    # -- ejecución
    "E-EJE-01": (None, "la variable '{q0}' no tiene valor en este punto de la ejecución."),
    "E-EJE-02": (None, "dividiste por cero, compa; eso no se puede."),
    "E-EJE-03": (None, "ese resultado se salió del rango permitido."),
    "E-EJE-04": (None, "ese texto quedó larguísimo; no lo sigas duplicando."),
    "E-EJE-97": (None, "se enredó algo mientras se ejecutaba el programa; vuelve a intentar."),
    # -- advertencias
    "A-LEX-01": (None, "el código está vacío; no hay nada que revisar."),
    "A-LEX-02": (None, "solo hay comentarios, no hay instrucciones."),
    "A-LEX-03": (None, "hay un espacio raro (de Word, seguro); lo tomé como un espacio normal."),
    "A-SEM-01": (None, "la variable '{q0}' la declaraste y nunca la usas."),
    "A-SEM-02": (None, "la variable '{q0}' solo recibe valor en algunos caminos del Si; si no entra por ahí, el programa se detiene."),
    "A-SEM-03": (None, "a la variable '{q0}' le guardas un valor pero nunca lo usas."),
    "A-SEM-05": (None, "'{q0}' se parece a '{q1}' y solo cambia en las mayúsculas: son variables distintas, ojo."),
}


def tipo_de(codigo: str) -> str:
    return TIPOS_DE_ERROR.get(codigo.split("-")[1] if codigo.count("-") >= 2 else "", "")


def _causa(codigo: str, mensaje: str) -> str:
    regla = CAUSAS.get(codigo)
    if regla is None:
        return mensaje
    patron, plantilla = regla
    valores = {}
    for i, q in enumerate(re.findall(r"'([^']*)'", mensaje)):
        valores[f"q{i}"] = q
    if patron:
        m = re.search(patron, mensaje)
        if m:
            for i, g in enumerate(m.groups(), start=1):
                valores[f"g{i}"] = g
    for i in range(0, 6):                       # lo que no se encontró queda como «eso»
        valores.setdefault(f"q{i}", "eso")
        valores.setdefault(f"g{i + 1}", "eso")
    try:
        return plantilla.format(**valores)
    except (KeyError, IndexError, ValueError):
        return mensaje


def frase(codigo: str, linea: int, mensaje: str) -> str:
    """Mensaje en costeño con el formato del profesor."""
    es_aviso = codigo.startswith("A-")
    lista = APERTURAS_AVISO if es_aviso else APERTURAS_ERROR
    indice = (int(linea) * 7 + sum(ord(c) for c in codigo)) % len(lista)
    apertura = lista[indice].format(n=linea)
    etiqueta = "Advertencia" if es_aviso else f"Error {tipo_de(codigo)}".rstrip()
    return f"{apertura} {etiqueta}: {_causa(codigo, mensaje)}"
