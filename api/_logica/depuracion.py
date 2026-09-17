"""
Modulo: depuracion.py
Implementa las 4 fases de depuracion de una Gramatica Libre de Contexto:

    1. Eliminacion de variables inutiles (no generadoras)
    2. Eliminacion de variables inalcanzables
    3. Eliminacion de producciones nulas
    4. Eliminacion de producciones unitarias

NOTA: cada produccion es una tupla de simbolos, ej. ('A','A','B').
La produccion nula (epsilon) es la tupla vacia: ().

IMPORTANTE - Orden de nulas vs unitarias:
    Normalmente se eliminan primero las nulas y luego las unitarias.
    Sin embargo, si existe un CICLO de unitarias entre variables que
    tambien son anulables (ej. A -> B, B -> A, ambas anulables), el
    proceso de eliminar nulas nunca converge. En ese caso se invierte
    el orden: primero unitarias, luego nulas. Ademas, invertir el
    orden puede generar NUEVAS unitarias (ej. autociclos A->A), por
    lo que se hace una limpieza final extra en ese caso.
"""

from itertools import combinations
from .utils import formatear_produccion


# ----------------------------------------------------------------------
# FASE 1: Variables inutiles (no generadoras)
# ----------------------------------------------------------------------

def obtener_variables_generadoras(gramatica):
    """
    Calcula el conjunto de variables generadoras: aquellas que,
    en algun numero finito de derivaciones, pueden producir una
    cadena compuesta unicamente por terminales.
    """
    generadoras = set()
    cambio = True

    while cambio:
        cambio = False
        for variable, lista_producciones in gramatica.producciones.items():
            if variable in generadoras:
                continue
            for produccion in lista_producciones:
                if produccion == gramatica.NULA:
                    generadoras.add(variable)
                    cambio = True
                    break
                if all(
                    (s in gramatica.terminales) or (s in generadoras)
                    for s in produccion
                ):
                    generadoras.add(variable)
                    cambio = True
                    break

    return generadoras


def _incorporar_simbolos_desconocidos(gramatica):
    """
    Busca simbolos usados en alguna produccion que NO esten declarados
    ni como variable ni como terminal (ej. una variable G que aparece
    en A -> GF2 pero nunca se declaro ni tiene su propia produccion).

    Estos simbolos se incorporan como variables SIN producciones
    propias, para que el algoritmo de variables generadoras los
    detecte automaticamente como no generadoras (inutiles) y sean
    eliminados junto con las producciones que los contienen.

    Retorna:
        set[str]: los simbolos desconocidos que se incorporaron (para
        reportarlos en el historial).
    """
    alfabeto_conocido = gramatica.variables | gramatica.terminales
    desconocidos = set()

    for lista_producciones in gramatica.producciones.values():
        for produccion in lista_producciones:
            for simbolo in produccion:
                if simbolo not in alfabeto_conocido:
                    desconocidos.add(simbolo)

    for simbolo in desconocidos:
        gramatica.variables.add(simbolo)
        gramatica.producciones.setdefault(simbolo, [])  # sin producciones propias

    return desconocidos


def eliminar_variables_inutiles(gramatica, historial=None):
    """
    Elimina las variables no generadoras (inutiles). Esto incluye:
        - Variables declaradas sin ninguna produccion propia (ej. F).
        - Simbolos usados en producciones pero nunca declarados
          (ej. G), que se incorporan primero como variables fantasma
          y luego se eliminan por no ser generadoras.

    Parametros:
        gramatica (Gramatica): gramatica a depurar (se modifica una copia).
        historial (Historial, opcional): si se provee, se registra el paso.

    Retorna:
        Gramatica: nueva gramatica sin variables inutiles.
    """
    gramatica_antes = gramatica.copia()
    nueva = gramatica.copia()

    simbolos_incorporados = _incorporar_simbolos_desconocidos(nueva)

    generadoras = obtener_variables_generadoras(nueva)
    inutiles = nueva.variables - generadoras

    for var in inutiles:
        nueva.eliminar_variable(var)

    if historial is not None:
        etiquetas = sorted(inutiles) if inutiles else ["Ninguna"]
        if simbolos_incorporados:
            etiquetas = [
                f"{s} (simbolo no declarado, tratado como inutil)"
                if s in simbolos_incorporados else s
                for s in etiquetas
            ]
        historial.registrar(
            fase="Eliminacion de variables inutiles (no generadoras)",
            gramatica_antes=gramatica_antes,
            elementos_identificados=etiquetas,
            producciones_eliminadas=None,
            producciones_agregadas=[],
            gramatica_despues=nueva.copia(),
        )

    return nueva


# ----------------------------------------------------------------------
# FASE 2: Variables inalcanzables
# ----------------------------------------------------------------------

def obtener_variables_alcanzables(gramatica):
    """Calcula el conjunto de variables alcanzables desde el simbolo inicial."""
    alcanzables = {gramatica.inicial}
    pendientes = [gramatica.inicial]

    while pendientes:
        var = pendientes.pop()
        for produccion in gramatica.producciones.get(var, []):
            for simbolo in produccion:
                if simbolo in gramatica.variables and simbolo not in alcanzables:
                    alcanzables.add(simbolo)
                    pendientes.append(simbolo)

    return alcanzables


def eliminar_variables_inalcanzables(gramatica, historial=None):
    """Elimina las variables que no son alcanzables desde el simbolo inicial."""
    gramatica_antes = gramatica.copia()
    nueva = gramatica.copia()

    alcanzables = obtener_variables_alcanzables(nueva)
    inalcanzables = nueva.variables - alcanzables

    for var in inalcanzables:
        nueva.eliminar_variable(var)

    if historial is not None:
        historial.registrar(
            fase="Eliminacion de variables inalcanzables",
            gramatica_antes=gramatica_antes,
            elementos_identificados=sorted(inalcanzables) if inalcanzables else ["Ninguna"],
            producciones_eliminadas=None,
            producciones_agregadas=[],
            gramatica_despues=nueva.copia(),
        )

    return nueva


# ----------------------------------------------------------------------
# FASE 3: Producciones nulas
# ----------------------------------------------------------------------

def obtener_variables_anulables(gramatica):
    """Calcula el conjunto de variables anulables (pueden derivar en epsilon)."""
    anulables = set()
    cambio = True

    while cambio:
        cambio = False
        for variable, lista_producciones in gramatica.producciones.items():
            if variable in anulables:
                continue
            for produccion in lista_producciones:
                if produccion == gramatica.NULA:
                    anulables.add(variable)
                    cambio = True
                    break
                if produccion and all(s in anulables for s in produccion):
                    anulables.add(variable)
                    cambio = True
                    break

    return anulables


def _generar_combinaciones_sin_anulables(produccion, posiciones_anulables):
    """
    Dada una produccion (tupla de simbolos) y las posiciones (indices)
    de simbolos anulables dentro de ella, genera todas las variantes
    posibles quitando subconjuntos de esas posiciones.

    Se devuelve como LISTA (no set) para preservar un orden
    deterministico: primero r=0 (la produccion original, sin quitar
    nada), luego r=1,2,3... (quitando progresivamente mas simbolos
    anulables). Con un set, Python no garantiza ningun orden
    consistente, lo que desordenaba el resultado final.

    Retorna:
        list[tuple]: lista de variantes, sin duplicados (puede incluir
        la tupla vacia () si se quitan TODOS los simbolos).
    """
    variantes = []
    n = len(posiciones_anulables)

    for r in range(n + 1):
        for combo in combinations(posiciones_anulables, r):
            quitar = set(combo)
            nueva = tuple(
                simbolo for i, simbolo in enumerate(produccion) if i not in quitar
            )
            if nueva not in variantes:
                variantes.append(nueva)

    return variantes


def eliminar_producciones_nulas(gramatica, historial=None):
    """
    Elimina las producciones nulas, UNA VARIABLE ANULABLE A LA VEZ
    (no todas de un solo golpe). Por cada variable con produccion
    lambda directa se registra un PASO independiente de historial:

        1. Se elimina esa lambda (variable -> λ) de una vez, en el
           mismo paso (no se deja para un paso de "limpieza" final).
        2. Se propaga su desaparicion a TODAS las producciones de
           TODA la gramatica que la contengan (incluidas las de la
           propia variable), generando las combinaciones necesarias
           y evitando duplicados.

    Si al propagar, alguna OTRA variable queda con una nueva
    produccion vacia (una variable que se volvio anulable de forma
    indirecta, ej. D -> A y A se anula => D tambien se anula), esa
    variable se encola para procesarse en un paso posterior (nunca en
    el mismo paso).

    El orden de procesamiento es el orden de aparicion de las
    variables en la gramatica; las que se descubren indirectamente se
    procesan despues de las que ya estaban en cola.
    """
    nueva = gramatica.copia()

    procesadas = set()
    pendientes = [
        v for v in nueva.producciones if nueva.NULA in nueva.producciones[v]
    ]

    while pendientes:
        variable = pendientes.pop(0)
        if variable in procesadas:
            continue
        if nueva.NULA not in nueva.producciones.get(variable, []):
            continue
        procesadas.add(variable)

        gramatica_antes = nueva.copia()

        # 1. Se quita la lambda propia de 'variable' de una vez.
        nueva.producciones[variable] = [
            p for p in nueva.producciones[variable] if p != nueva.NULA
        ]

        producciones_eliminadas = [f"{variable} -> λ"]
        producciones_agregadas = []
        nuevos_pendientes = []

        # 2. Se propaga la desaparicion de 'variable' a TODA la
        #    gramatica (incluida ella misma).
        nuevas_producciones = {}
        for var_afectada, lista in nueva.producciones.items():
            original = set(lista)
            nuevas_de_var = []

            for produccion in lista:
                if variable not in produccion:
                    if produccion not in nuevas_de_var:
                        nuevas_de_var.append(produccion)
                    continue

                posiciones = [i for i, s in enumerate(produccion) if s == variable]
                variantes = _generar_combinaciones_sin_anulables(produccion, posiciones)

                for variante in variantes:
                    if variante == nueva.NULA and var_afectada == variable:
                        # Una autoproduccion remanente (ej. "C -> C",
                        # creada en un paso anterior) NO puede
                        # regenerar la lambda propia de 'variable'
                        # dentro de su propio paso: esa lambda ya se
                        # elimino explicitamente arriba.
                        continue
                    if variante not in nuevas_de_var:
                        nuevas_de_var.append(variante)

            # Solo se reporta como "agregada" lo que de verdad es nuevo
            # respecto a las producciones ORIGINALES de esa variable
            # (evita marcar como agregada una produccion que ya
            # existia de antes y que el proceso simplemente volvio a
            # generar, ej. ABC o BC si A -> ABAC/ABC/BC/... ).
            for p in nuevas_de_var:
                if p in original:
                    continue
                if p == nueva.NULA:
                    producciones_agregadas.append(f"{var_afectada} -> λ")
                    if (
                        var_afectada not in procesadas
                        and var_afectada not in pendientes
                        and var_afectada not in nuevos_pendientes
                    ):
                        nuevos_pendientes.append(var_afectada)
                else:
                    producciones_agregadas.append(
                        f"{var_afectada} -> {formatear_produccion(p)}"
                    )

            nuevas_producciones[var_afectada] = nuevas_de_var

        nueva.producciones = nuevas_producciones
        pendientes = pendientes + nuevos_pendientes

        if historial is not None:
            historial.registrar(
                fase=f"Eliminación de producción nula: {variable} → λ",
                gramatica_antes=gramatica_antes,
                elementos_identificados=[variable],
                producciones_eliminadas=producciones_eliminadas,
                producciones_agregadas=producciones_agregadas,
                gramatica_despues=nueva.copia(),
            )

    return nueva


# ----------------------------------------------------------------------
# FASE 4: Producciones unitarias
# ----------------------------------------------------------------------

def obtener_pares_unitarios(gramatica):
    """Identifica todas las producciones unitarias (A -> B)."""
    pares = []
    for variable, lista_producciones in gramatica.producciones.items():
        for produccion in lista_producciones:
            if len(produccion) == 1 and produccion[0] in gramatica.variables:
                pares.append((variable, produccion[0]))
    return pares


def _cierre_unitario(gramatica, variable):
    """
    Cierre unitario: variables alcanzables solo via producciones
    unitarias. Se devuelve como LISTA (no set), preservando orden:
    la variable misma siempre queda primera (para que sus propias
    producciones se mantengan primero al fusionar), y las demas en
    el orden en que se van descubriendo. Esto evita que el orden
    final de las producciones quede aleatorio.
    """
    cierre = [variable]
    vistos = {variable}
    pendientes = [variable]

    while pendientes:
        actual = pendientes.pop(0)
        for produccion in gramatica.producciones.get(actual, []):
            if len(produccion) == 1 and produccion[0] in gramatica.variables:
                destino = produccion[0]
                if destino not in vistos:
                    vistos.add(destino)
                    cierre.append(destino)
                    pendientes.append(destino)

    return cierre


def eliminar_producciones_unitarias(gramatica, historial=None):
    """
    Elimina las producciones unitarias usando el cierre unitario de
    cada variable, UNA VARIABLE DE ORIGEN A LA VEZ (no todas de un
    solo golpe). Por cada variable que tenga al menos una produccion
    unitaria directa se registra un PASO independiente de historial.

    Si una misma variable tiene VARIAS producciones unitarias propias
    (ej. A -> B y A -> C), ambas se resuelven JUNTAS en un solo paso
    (el cierre unitario de A ya las cubre a las dos de una vez); lo
    que se hace secuencial, paso a paso, es cada VARIABLE DE ORIGEN
    distinta, en el orden en que aparecen en la gramatica. Cada paso
    parte de la gramatica ya actualizada por el paso anterior.
    """
    nueva = gramatica.copia()

    # IMPORTANTE: se itera sobre nueva.producciones (un diccionario,
    # que preserva el orden de insercion original) y NO sobre
    # nueva.variables (un set, cuyo orden de iteracion no esta
    # garantizado). Esto asegura que el orden de las variables se
    # mantenga estable y coincida con el orden original de la
    # gramatica.
    orden_variables = list(nueva.producciones.keys())

    for variable in orden_variables:
        pares_variable = [
            p for p in nueva.producciones.get(variable, [])
            if len(p) == 1 and p[0] in nueva.variables
        ]
        if not pares_variable:
            continue  # esta variable no tiene unitarias propias, no genera paso

        gramatica_antes = nueva.copia()

        producciones_eliminadas = [f"{variable} -> {p[0]}" for p in pares_variable]
        producciones_agregadas = []

        cierre = _cierre_unitario(nueva, variable)
        producciones_finales = []

        for var_en_cierre in cierre:
            for produccion in nueva.producciones.get(var_en_cierre, []):
                if len(produccion) == 1 and produccion[0] in nueva.variables:
                    continue  # se descarta, ya esta representada por el cierre
                if produccion == nueva.NULA and var_en_cierre != variable:
                    # Una produccion nula NO se propaga a otras variables a
                    # traves del cierre unitario.
                    continue
                if produccion not in producciones_finales:
                    producciones_finales.append(produccion)
                    if var_en_cierre != variable:
                        producciones_agregadas.append(
                            f"{variable} -> {formatear_produccion(produccion)}"
                        )

        nueva.producciones[variable] = producciones_finales

        if historial is not None:
            historial.registrar(
                fase=f"Eliminación de producción(es) unitaria(s) de {variable}",
                gramatica_antes=gramatica_antes,
                elementos_identificados=[f"{variable} -> {p[0]}" for p in pares_variable],
                producciones_eliminadas=producciones_eliminadas,
                producciones_agregadas=producciones_agregadas,
                gramatica_despues=nueva.copia(),
            )

    return nueva


# ----------------------------------------------------------------------
# Orquestacion: deteccion de orden nulas/unitarias
# ----------------------------------------------------------------------

def existe_ciclo_unitarias_entre_anulables(gramatica):
    """Detecta ciclos de unitarias entre variables anulables (DFS con colores)."""
    anulables = obtener_variables_anulables(gramatica)
    pares = obtener_pares_unitarios(gramatica)

    grafo = {}
    for origen, destino in pares:
        if origen in anulables and destino in anulables:
            grafo.setdefault(origen, set()).add(destino)

    if not grafo:
        return False

    blanco, gris, negro = 0, 1, 2
    color = {v: blanco for v in grafo}
    for vecinos in grafo.values():
        for v in vecinos:
            color.setdefault(v, blanco)

    def dfs(nodo):
        color[nodo] = gris
        for vecino in grafo.get(nodo, []):
            if color[vecino] == gris:
                return True
            if color[vecino] == blanco and dfs(vecino):
                return True
        color[nodo] = negro
        return False

    for nodo in list(color.keys()):
        if color[nodo] == blanco:
            if dfs(nodo):
                return True

    return False


def depurar_gramatica(gramatica, historial=None):
    """
    Ejecuta el proceso completo de depuracion:
        1. Eliminar variables inutiles
        2. Eliminar variables inalcanzables
        3. Decidir orden nulas/unitarias segun si hay ciclo
        4. Eliminar nulas y unitarias en el orden decidido
           (con limpieza extra si se invirtio el orden)
    """
    actual = gramatica.copia()

    actual = eliminar_variables_inutiles(actual, historial)
    actual = eliminar_variables_inalcanzables(actual, historial)

    hay_ciclo = existe_ciclo_unitarias_entre_anulables(actual)

    if hay_ciclo:
        actual = eliminar_producciones_unitarias(actual, historial)
        actual = eliminar_producciones_nulas(actual, historial)
        if obtener_pares_unitarios(actual):
            actual = eliminar_producciones_unitarias(actual, historial)
    else:
        actual = eliminar_producciones_nulas(actual, historial)
        actual = eliminar_producciones_unitarias(actual, historial)

    return actual