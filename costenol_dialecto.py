# -*- coding: utf-8 -*-
"""
Costeñol - Dialecto costeño para los mensajes

El lenguaje se llama Costeñol porque el compilador habla como costeño. Este módulo
convierte cada error o advertencia en una frase con el formato que pidió el profesor:

    <reacción> en la línea N. Error <tipo>: <causa>

    Ejemplo:  Ojo, la cagaste en la línea 5. Error semántico: la variable 'x' no está declarada.

Cómo está pensado
-----------------
* Cada código tiene SU PROPIA reacción (REACCIONES) y SU PROPIA causa (CAUSAS): la expresión
  costeña se escogió porque encaja con lo que pasó, no se reparte al azar. Lo que no encaja
  con ninguna expresión del diccionario queda con un «Ojo, compa» o un «Eche, compa» y una
  explicación clara.
* Familias de reacciones:
      falta algo ............ «Ajá, ¿y el …?»               (Ajá = ¿y entonces?)
      algo no cuadra ........ «Ese cuento no me cuadra»
      finge no saber ........ «No te hagas el loco»
      se pasó de un límite .. «No te pases», «Bájale dos», «Suave ahí»
      enredo de estructura .. «Se formó un bololó», «Mi llave, estás enredado»
      algo raro ............. «¿Qué es esa monda, loco?»
      sorpresa .............. «¡Ave María!», «¡Quedé frío!», «¡Tú sí inventas!»
      aviso ................. «Pilas», «No des papaya», «Ojito»
      sin expresión ......... «Ojo, compa», «Eche, compa»
* «Tú eres la monda, manito» es un ELOGIO («eres lo máximo»): solo se usa cuando todo sale bien
  (ver MENSAJES_PANTALLA y web/app.js), nunca en un error.
* No se usan groserías fuertes, insultos al programador ni expresiones que el diccionario marca
  como ofensivas o discriminatorias (ver PALABRAS_PROHIBIDAS; una prueba lo vigila).
* La frase del profesor («Ojo, la cagaste») solo va en «variable no declarada».

Para cambiar el "habla" basta con editar las tablas REACCIONES y CAUSAS. Si un código no tiene frase
propia se usa una reacción neutral y el mensaje formal como causa, así nunca queda vacío.

En las reacciones y causas se puede usar:
    {n}              número de línea
    {q0} {q1} ...    lo que va entre comillas simples en el mensaje formal (nombres, números)
    {g1} {g2} ...    grupos de la expresión regular propia de esa causa (tipos, líneas)
    {q0coma} {q0cero} {q0sinceros}   el primer valor entre comillas arreglado (3.14 -> 3,14, etc.)
    {correcta}       la palabra bien escrita en los errores de mayúsculas y minúsculas
"""

import re

TIPOS_DE_ERROR = {
    "LEX": "léxico",
    "SIN": "sintáctico",
    "SEM": "semántico",
    "EJE": "de ejecución",
}

# --- reacción de cada código (lleva «en la línea {n}») ------------------------------
REACCIONES = {
    # -- léxico
    "E-LEX-01": "Ajá, dejaste un comentario abierto en la línea {n}.",
    "E-LEX-02": "Eche, compa, ese texto quedó sin cerrar en la línea {n}.",
    "E-LEX-04": "Ojo, compa, en la línea {n} hay un número mal escrito.",
    "E-LEX-05": "Ojo, compa, en la línea {n} usaste punto en un decimal.",
    "E-LEX-06": "Ojo, compa, la coma decimal quedó mal puesta en la línea {n}.",
    "E-LEX-07": "Ey mi llave, qué número tan grande en la línea {n}.",
    "E-LEX-08": "Ojo, compa, en la línea {n} hay un número que empieza con punto.",
    "E-LEX-09": "Ojo, compa, en la línea {n} le sobran ceros a un número.",
    "E-LEX-10": "Ojo, compa, en la línea {n} hay un nombre que empieza con guion bajo.",
    "E-LEX-11": "Ojo, compa, en la línea {n} hay un nombre con tildes o símbolos raros.",
    "E-LEX-12": "Ojo manito, que en la línea {n} hay un nombre larguísimo.",
    "E-LEX-13": "¡Tú sí inventas! En la línea {n} escribiste un operador que no existe.",
    "E-LEX-14": "¡Quedé frío! En la línea {n} hay un carácter invisible.",
    "E-LEX-15": "¿Qué es esa monda, loco? En la línea {n} hay un símbolo que no se usa en Costeñol.",
    "E-LEX-97": "¡Qué vaina! Se enredó algo por dentro en la línea {n}.",
    "E-LEX-98": "Ey cole, ese programa es enorme: ya me pasé en la línea {n}.",
    # -- sintáctico
    "E-SIN-01": "Ajá, ¿y el punto y coma? Se te quedó por fuera en la línea {n}.",
    "E-SIN-02": "¿Qué es esa monda, loco? En la línea {n} esa instrucción empezó con algo que no va.",
    "E-SIN-03": "Ajá, ¿y entonces? Después de '{q0}' en la línea {n} no dijiste qué sigue.",
    "E-SIN-04": "Ajá, ¿y el valor? Se quedó a medias la operación en la línea {n}.",
    "E-SIN-05": "Se formó un bololó con los paréntesis en la línea {n}.",
    "E-SIN-06": "Ojo, compa, en la línea {n} el Si quedó incompleto.",
    "E-SIN-07": "Mucho tilín tilín y nada de paletas: en la línea {n} el Si no trae condición.",
    "E-SIN-08": "Ajá, ¿y el paréntesis? Se te quedó abierta la condición del Si en la línea {n}.",
    "E-SIN-09": "Ajá, ¿y el FinSi? En la línea {n} el Si se quedó abierto.",
    "E-SIN-10": "Eche, compa, ese Sino (o FinSi) está solito en la línea {n}.",
    "E-SIN-11": "Suave ahí, compa, que en la línea {n} el Si ya tiene su Sino.",
    "E-SIN-12": "Ojo, compa, en la línea {n} el Sino (o FinSi) no va con nada más.",
    "E-SIN-13": "Ojo, compa, en la línea {n} le faltó el espacio al Si.",
    "E-SIN-14": "Ojo, compa, en la línea {n} esa Captura está mal escrita.",
    "E-SIN-15": "Ojo, compa, en la línea {n} ese Mensaje está mal escrito.",
    "E-SIN-16": "No te pases, compa: en la línea {n} declaraste una variable dentro de un Si.",
    "E-SIN-17": "Eche, compa, en la línea {n} usaste un solo =.",
    "E-SIN-18": "Bájale dos, compa: en la línea {n} encadenaste comparaciones.",
    "E-SIN-19": "Ojo, compa, en la línea {n} usaste una palabra reservada donde no va.",
    "E-SIN-20": "¿Qué es esa monda, loco? ¿De dónde sacaste esa función en la línea {n}?",
    "E-SIN-21": "Ojo, compa, en la línea {n} metiste Captura (o Mensaje) dentro de una operación.",
    "E-SIN-22": "Suave ahí, compa, que en la línea {n} sobra un punto y coma.",
    "E-SIN-23": "Ojo, compa, en la línea {n} empezaste por el tipo.",
    "E-SIN-24": "Ojo, compa, en la línea {n} le pusiste una operación a la Captura.",
    "E-SIN-25": "Mi llave, estás enredado en la línea {n}.",
    "E-SIN-26": "Ojo, compa, en la línea {n} '{q0}' está mal escrito.",
    "E-SIN-27": "Suave ahí, compa, en la línea {n} '{q0}' no sirve de nombre.",
    "E-SIN-28": "Ajá, ¿y el operador? Se te quedaron dos valores pegados en la línea {n}.",
    "E-SIN-97": "¡Qué vaina! Se enredó algo por dentro en la línea {n}.",
    # -- semántico
    "E-SEM-01": "Ojo, la cagaste en la línea {n}.",
    "E-SEM-02": "Eche, compa, en la línea {n} repetiste la variable '{q0}'.",
    "E-SEM-03": "Ese cuento no me cuadra en la línea {n}.",
    "E-SEM-04": "¿Qué es esa monda, loco? En la línea {n} hay una operación imposible.",
    "E-SEM-05": "Ese cuento no me cuadra en la línea {n}.",
    "E-SEM-06": "No mezcles las vainas, compa: en la línea {n} comparas cosas distintas.",
    "E-SEM-07": "Ojo, compa, en la línea {n} hay una comparación de orden mal puesta.",
    "E-SEM-08": "Ojo, compa, en la línea {n} esa Captura no va con la variable.",
    "E-SEM-09": "No te hagas el loco, compa: en la línea {n} usas '{q0}' sin darle valor.",
    "E-SEM-10": "No inventes, compa, en la línea {n}.",
    "E-SEM-97": "¡Qué vaina! Se enredó algo por dentro en la línea {n}.",
    # -- ejecución
    "E-EJE-01": "No te hagas el loco, compa: en la línea {n} '{q0}' no tenía valor.",
    "E-EJE-02": "No inventes, compa, en la línea {n}.",
    "E-EJE-03": "¡Ave María, ese resultado se fue por las nubes en la línea {n}!",
    "E-EJE-04": "Bájale dos, compa: en la línea {n} ese texto ya está larguísimo.",
    "E-EJE-97": "¡Qué vaina! Se enredó algo mientras se ejecutaba, en la línea {n}.",
    # -- advertencias
    "A-LEX-01": "Ajá, ¿y entonces? En la línea {n} no hay nada escrito.",
    "A-LEX-02": "Pura bulla en la línea {n}.",
    "A-LEX-03": "Ojito, compa, en la línea {n} hay un espacio raro (de Word, seguro).",
    "A-LEX-99": "Hasta aquí llegué, compa: en la línea {n} ya van 200 errores.",
    "A-SIN-99": "Hasta aquí llegué, compa: en la línea {n} ya van 200 errores.",
    "A-SEM-99": "Hasta aquí llegué, compa: en la línea {n} ya van 200 errores.",
    "A-SEM-01": "Pilas, compa: en la línea {n} declaraste '{q0}' y nunca la usas.",
    "A-SEM-02": "No des papaya, compa: en la línea {n} '{q0}' solo recibe valor dentro del Si.",
    "A-SEM-03": "Pilas, compa: en la línea {n} le guardas un valor a '{q0}' que nunca usas.",
    "A-SEM-05": "Ojito, compa: en la línea {n} '{q0}' se parece a '{q1}' (línea {g1}).",
}

# --- causa de cada código: (expresión regular opcional, plantilla) -------------------
CAUSAS = {
    # -- léxico
    "E-LEX-01": (None, "le falta el // de cierre en la misma línea."),
    "E-LEX-02": (None, "ciérralo con la misma comilla y en la misma línea."),
    "E-LEX-04": (None, "'{q0}' trae letras pegadas; un número va solo."),
    "E-LEX-05": (None, "los decimales llevan coma; '{q0}' se escribe '{q0coma}'."),
    "E-LEX-06": (None, "'{q0}' necesita dígitos después de la coma, y solo una coma."),
    "E-LEX-07": (None, "'{q0}' pasa del máximo, que es 2147483647."),
    "E-LEX-08": (None, "'{q0}' se escribe '{q0cero}'."),
    "E-LEX-09": (None, "'{q0}' se escribe '{q0sinceros}'."),
    "E-LEX-10": (None, "los nombres empiezan con una letra."),
    "E-LEX-11": (None, "'{q0}' solo puede llevar letras sin tilde (la ñ sí), números y guion bajo."),
    "E-LEX-12": (None, "el máximo son 30 caracteres."),
    "E-LEX-13": (None, "'{q0}' no sirve; los válidos son = == != < > <= >= + - * /."),
    "E-LEX-14": (None, "seguro lo pegaste de otro programa; borra la línea y escríbela de nuevo."),
    "E-LEX-15": (None, "'{q0}' no forma parte del lenguaje."),
    "E-LEX-97": (None, "vuelve a intentar."),
    "E-LEX-98": (None, "pasa de 2 000 000 de caracteres; pártelo en pedazos."),
    # -- sintáctico
    "E-SIN-01": (None, "toda instrucción termina con ;"),
    "E-SIN-02": (None, "una instrucción empieza con el nombre de una variable, Mensaje o Si."),
    "E-SIN-03": (None, "va un tipo (Texto, Entero, Real o Logico) para declararla, o un = para darle valor."),
    "E-SIN-04": (None, "falta un número, texto, variable o paréntesis."),
    "E-SIN-05": (None, "falta cerrar uno o sobra otro; después de cada ( va un valor y luego el )."),
    "E-SIN-06": (None, "después del Si va un espacio y la condición entre paréntesis."),
    "E-SIN-07": (None, "escribe algo entre los paréntesis."),
    "E-SIN-08": (None, "falta el ) al final."),
    "E-SIN-09": (None, "todo Si termina con FinSi."),
    "E-SIN-10": (None, "no hay un Si abierto arriba."),
    "E-SIN-11": (None, "solo se permite uno."),
    "E-SIN-12": (None, "van solitos en su línea."),
    "E-SIN-13": (None, "va Si, un espacio y luego el paréntesis."),
    "E-SIN-14": (None, "va así: variable = Captura.Tipo();"),
    "E-SIN-15": (None, "va así: Mensaje.Texto(valor);"),
    "E-SIN-16": (None, "las variables se declaran al inicio, fuera de los Si."),
    "E-SIN-17": (None, "dentro del Si se compara con ==; el = es para guardar valores."),
    "E-SIN-18": (None, "haz una sola comparación por condición."),
    "E-SIN-19": (None, "esa palabra es del lenguaje y no sirve de nombre ni de valor."),
    "E-SIN-20": (None, "'{q0}' no existe; solo hay Captura.Tipo() y Mensaje.Texto()."),
    "E-SIN-21": (None, "van solos, en su propia instrucción."),
    "E-SIN-22": (None, "no hay ninguna instrucción antes de ese ;"),
    "E-SIN-23": (None, "primero va el nombre y luego el tipo: edad Entero;"),
    "E-SIN-24": (None, "lo que lees se guarda solo; opera en la línea siguiente."),
    "E-SIN-25": (None, "hay demasiados paréntesis, Si anidados u operaciones (máximo 40 niveles y 150 operaciones); pártelo en pasos."),
    "E-SIN-26": (None, "aquí las mayúsculas importan; se escribe '{correcta}'."),
    "E-SIN-27": (None, "una variable no puede llamarse como un tipo ni como una palabra reservada, ni cambiando las mayúsculas."),
    "E-SIN-28": (None, "entre dos valores va un operador (+ - * /); un número no puede ir pegado a un paréntesis, como en 1("),
    "E-SIN-97": (None, "vuelve a intentar."),
    # -- semántico
    "E-SEM-01": (None, "la variable '{q0}' no está declarada. Decláresela antes con: {q0} Tipo; (por ejemplo {q0} Entero;)"),
    "E-SEM-02": (r"línea (\d+)", "ya la habías declarado en la línea {g1}."),
    "E-SEM-03": (r"valor (\w+) en '([^']*)', que es (\w+)",
                 "no puedes guardar un valor {g1} en '{g2}' porque es {g3}; los tipos no son compatibles."),
    "E-SEM-04": (None, "el '{q0}' solo se puede usar con números (el + es el único que también junta textos)."),
    "E-SEM-05": (r"pero aquí es (\w+)", "la condición del Si tiene que dar Verdadero o Falso, y aquí dio {g1}."),
    "E-SEM-06": (r"comparar (\w+) con (\w+)", "no se puede comparar {g1} con {g2}; tienen que ser del mismo tipo."),
    "E-SEM-07": (None, "< > <= >= solo sirven con números; con otros tipos solo existen == y !="),
    "E-SEM-08": (r"Captura\.(\w+)\(\) lee un valor (\w+), pero '([^']*)' es (\w+)",
                 "Captura.{g1}() lee un {g2}, pero '{g3}' es {g4}; usa Captura.{g4}()."),
    "E-SEM-09": (None, "primero asígnale o léele un valor."),
    "E-SEM-10": (None, "no se puede dividir por cero."),
    "E-SEM-97": (None, "vuelve a intentar."),
    # -- ejecución
    "E-EJE-01": (None, "solo recibe valor dentro de un Si que no se ejecutó."),
    "E-EJE-02": (None, "el divisor valió cero."),
    "E-EJE-03": (None, "se salió del rango permitido (un Entero llega hasta ±2147483647)."),
    "E-EJE-04": (None, "pasó de 1 000 000 de caracteres; no lo sigas duplicando."),
    "E-EJE-97": (None, "vuelve a intentar."),
    # -- advertencias
    "A-LEX-01": (None, "el código está vacío."),
    "A-LEX-02": (None, "solo hay comentarios y ninguna instrucción."),
    "A-LEX-03": (None, "lo tomé como un espacio normal."),
    "A-LEX-99": (None, "no muestro más; arregla estos primero."),
    "A-SIN-99": (None, "no muestro más; arregla estos primero."),
    "A-SEM-99": (None, "no muestro más; arregla estos primero."),
    "A-SEM-01": (None, "bórrala o úsala."),
    "A-SEM-02": (None, "si ese camino no se ejecuta, el programa se detiene."),
    "A-SEM-03": (None, "muéstralo, compáralo o quita la asignación."),
    "A-SEM-05": (r"línea (\d+)", "solo cambian las mayúsculas, pero son variables distintas."),
}

# --- mensajes de la pantalla (no son errores); web/app.js usa estas mismas frases ----
MENSAJES_PANTALLA = {
    "compilacion_limpia": "Tú eres la monda, manito: compiló limpio, sin errores ni advertencias.",
    "compilacion_con_advertencias": "Ahí vamos: compiló, pero ojo con las advertencias.",
    "ejecucion_terminada": "Todo bien, compa: el programa quedó al pelo.",
    "ejecucion_con_error": "Se formó el bololó: el proceso terminó con errores.",
    "antes_de_empezar": "Listo, compa. Escribe tu programa y presiona Ejecutar (F5).",
    "errores_de_una_fase": "Hay {cantidad} en el análisis {fase}. Arréglalos, compa, y vuelve a intentar.",
    "dato_no_valido": "Eche, compa, ese dato no sirve: {detalle}",
}

# --- lo que NUNCA debe aparecer en los mensajes (una prueba lo vigila) -----------------
PALABRAS_PROHIBIDAS = [
    "caremond", "careverga", "mamaguevo", "malparido", "hijueputa", "hijo de puta", "gonorrea",
    "manda huevo", "ni por el putas", "marica", "corroncho", "güevón", "huevón",
    "pendejo", "bobo", "bruto", "idiota", "estúpido", "imbécil", "mondá",
]


def tipo_de(codigo: str) -> str:
    return TIPOS_DE_ERROR.get(codigo.split("-")[1] if codigo.count("-") >= 2 else "", "")


def _valores(mensaje: str, patron=None) -> dict:
    valores = {}
    citas = re.findall(r"'([^']*)'", mensaje)
    for i, q in enumerate(citas):
        valores[f"q{i}"] = q
    q0 = citas[0] if citas else ""
    valores["q0coma"] = q0.replace(".", ",")
    valores["q0cero"] = "0" + q0.replace(".", ",") if q0.startswith(".") else q0.replace(".", ",")
    valores["q0sinceros"] = q0.lstrip("0") or "0"
    m = re.search(r"[Qq]uiso decir '([^']*)'", mensaje) or re.search(r"se escribe (\w+)", mensaje)
    if m:
        valores["correcta"] = m.group(1)             # la palabra bien escrita (para mayúsculas y minúsculas)
    if patron:
        m = re.search(patron, mensaje)
        if m:
            for i, g in enumerate(m.groups(), start=1):
                valores[f"g{i}"] = g
    valores.setdefault("correcta", "eso")
    for i in range(0, 8):                        # lo que no se encontró queda como «eso»
        valores.setdefault(f"q{i}", "eso")
        valores.setdefault(f"g{i + 1}", "eso")
    return valores


def frase(codigo: str, linea: int, mensaje: str) -> str:
    """Mensaje en costeño con el formato del profesor: reacción + línea + tipo + causa."""
    es_aviso = codigo.startswith("A-")
    etiqueta = "Advertencia" if es_aviso else f"Error {tipo_de(codigo)}".rstrip()
    reaccion = REACCIONES.get(codigo)
    regla = CAUSAS.get(codigo)
    patron, causa = regla if regla else (None, None)
    valores = _valores(mensaje, patron)
    valores["n"] = linea
    try:
        reaccion = (reaccion or "Ojo, compa, en la línea {n}.").format(**valores)
        causa = causa.format(**valores) if causa else mensaje
    except (KeyError, IndexError, ValueError):
        reaccion = f"Ojo, compa, en la línea {linea}."
        causa = mensaje
    return f"{reaccion} {etiqueta}: {causa}"
