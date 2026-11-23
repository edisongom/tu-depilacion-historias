# -*- coding: utf-8 -*-
"""
CONFIGURACIÓN ÚNICA DEL ESTUDIO · Clínica Alemana de Santiago (CAS)
====================================================================

Es el único archivo que hay que editar. Todos los notebooks (01 a 08) lo importan.

No hace falta adivinar qué completar: la primera celda de cada notebook revisa lo que ese notebook necesita (decisiones,
archivos, columnas, resultados previos, memoria) y, si falta algo, se DETIENE y muestra la línea exacta que hay que
escribir aquí. Para ver el estado de todo el estudio de una vez:  python revisar_insumos.py

1. MODO = "real" en el PC de trabajo (lee las bases desde el bucket de Equifax).
   MODO = "simulacion" lee las bases simuladas de `datos_simulados/` (las crea el notebook 00).
2. DECISIONES: grafos viales a usar (GRAFOS_VIALES, por nombre de archivo), cómo vendrá el RUT de los pacientes
   (RUT_PACIENTES, RUT_CON_DV), la unidad de los montos de venta (UNIDAD_MONTO) y el perfil de cómputo (PERFIL).
3. Las rutas reales y los nombres de columnas ya vienen con los nombres originales de las bases Equifax.
4. Cuando llegue la data de Clínica Alemana, completa RUTAS_REALES["ventas_cliente"], ["sedes_cliente"] y,
   si viene, ["origen_pacientes"]. Los nombres de columnas del cliente se reconocen solos (ver COLUMNAS_CLIENTE);
   si alguno no se reconoce, el notebook lo pide con el nombre que encontró en el archivo.
"""
import copy
import os

MODO = "simulacion"            # "real" | "simulacion"

# --------------------------------------------------------------------------------------------- DECISIONES
# ¿Cómo vendrá el RUT de los pacientes en el archivo de origen de la clínica? (solo modo real; se necesita desde la
# ingesta, porque personas y empresas se seudonimizan con la misma sal que los pacientes para poder cruzarlos)
#   "en_claro"       la clínica manda el RUT tal cual: se seudonimiza al leerlo con una sal secreta del proyecto
#                    (se crea sola en trabajo/.sal_proyecto). El RUT nunca se guarda en claro.
#   "seudonimizado"  la clínica manda sha256(SAL + RUT): define la variable de entorno GEOVENTAS_SAL_RUT con esa SAL
#                    (no la escribas en este archivo).
#   "sin_rut"        el origen vendrá por zona/comuna o no vendrá: no se leen ni seudonimizan RUT (ingesta más rápida).
#   None             aún no se decide: los notebooks 01 y 05 se detienen y lo preguntan.
RUT_PACIENTES = None

# ¿El RUT de los pacientes trae el dígito verificador? Se acepta cualquier escritura (0190270254, 190270254, 19027025-4,
# 19.027.025-4, números de Excel…): todo se lleva a la misma forma canónica (cuerpo + DV, sin ceros ni signos).
#   "auto"  se detecta en la columna completa: con DV, > 80% de los RUT calza con su dígito verificador; sin DV, ~9%.
#           Si la columna es ambigua (p. ej. mezcla RUT con y sin DV), el notebook 05 se detiene y pide True o False.
#   True    el último carácter es el dígito verificador · False  viene solo el número (el DV se calcula)
RUT_CON_DV = "auto"

# ¿En qué unidad vienen los montos de venta de la clínica? Todo el estudio trabaja en PESOS (y los informes en millones).
#   "auto"      se reconoce por el nombre de la columna (monto_clp → pesos, venta_mm → millones, venta_miles → miles,
#               monto_uf → UF) o, si el nombre no lo dice, por la magnitud (venta mediana de una sede al mes y ticket por
#               atención). Si no se puede saber con certeza, el notebook 02 se detiene y la pide.
#   "pesos" | "miles" | "millones" | "uf"   fija la unidad (con "uf" hay que indicar VALOR_UF).
UNIDAD_MONTO = "auto"
VALOR_UF = None                # valor de la UF (pesos) del último mes de la serie; solo si UNIDAD_MONTO = "uf"

# Grafos viales de la carpeta RUTAS_REALES["grafos"]:
#   "todos"   se usan TODOS los .graphml de la carpeta: se carga cada uno, se recorta al área de estudio y se descartan
#             los que no la tocan (no hay que pensar cuál elegir; es más lento porque lee todos los archivos).
#   [lista]   solo esos archivos, por su NOMBRE EXACTO (más rápido). Los disponibles en prioritarias/graph:
#   CL-AI_aysen_del_general_carlos_ibanez_del_campo.graphml   CL-AN_antofagasta.graphml          CL-AP_arica_y_parinacota.graphml
#   CL-AR_araucania.graphml     CL-AT_atacama.graphml          CL-BI_biobio.graphml               CL-CO_coquimbo.graphml
#   CL-LI_libertador_general_bernardo_o_higgins.graphml        CL-LL_los_lagos.graphml            CL-LR_los_rios.graphml
#   CL-MA_magallanes_y_de_la_antartica_chilena.graphml         CL-ML_maule.graphml                CL-NB_nuble.graphml
#   CL-RM_metropolitana_de_santiago.graphml                    CL-TA_tarapaca.graphml             CL-VS_valparaiso.graphml
GRAFOS_VIALES = "todos"            # o, para ir más rápido: ["CL-RM_metropolitana_de_santiago.graphml"]

# Perfil de cómputo: "completo" para la entrega; "rapido" para revisar el flujo en menos tiempo (menos réplicas de
# bootstrap, menos candidatos y validación cruzada más corta). Los resultados del perfil rápido no son para entregar.
PERFIL = "completo"

AQUI = os.path.dirname(os.path.abspath(__file__))
BUCKET = "gs://dfa-dna-ws0066-la-prd-landing-zone"

# --------------------------------------------------------------------------------------------- RUTAS
RUTAS_REALES = {
    # Bases Equifax (nombres y carpetas tal como están en el bucket)
    "censo": f"{BUCKET}/Cartografia/CENSO_2026/SD06_SOCIODEMOGRAPHIC_BLOCK_2026.gpkg",
    "pois": f"{BUCKET}/Cartografia/POIS/PI01_POI.gpkg",
    "bbrr": f"{BUCKET}/2026/BBRR_1_SEMESTRE_2026/MKTS_BBRR_2026_01.txt",
    "street": f"{BUCKET}/Cartografia/BC08_STREET.gpkg",
    "per": f"{BUCKET}/DATOS_CHILE/2026_BASE_PERSONAS/personas_20260825_tramos_sociedades.parquet",
    "emp": f"{BUCKET}/2026/REZEPKA_BODEGAS/BD_EMPRESAS_ACTIVAS_3007.txt",
    # Carpeta con los grafos viales por región (los archivos se eligen en GRAFOS_VIALES). Ruta local de Jupyter: si los
    # notebooks no están en la misma carpeta raíz, escribe la ruta completa (p. ej. "/home/jupyter/prioritarias/graph").
    "grafos": "prioritarias/graph",
    # GTFS de transporte público (opcional; p. ej. GTFS de DTPM/Red Movilidad en .zip o carpeta). None = aproximación por red vial.
    "gtfs": None,
    # Datos de Clínica Alemana (completar al recibirlos; csv, txt, xlsx o parquet, local o gs://)
    "ventas_cliente": None,           # ventas por sede y mes (5 años). Obligatorio.
    "sedes_cliente": None,            # hoja "Sedes" (código, nombre, formato, dirección, apertura, cierre, m2, ...). Recomendado.
    "origen_pacientes": None,         # atenciones con RUT del paciente (se cruza con per y emp) o, si no, ventas por zona. Deseable.
    "areas_verdes": None,             # capa opcional de áreas verdes/parques (gpkg/shp) para descartar manzanas que son parque
    "eventos_cliente": None,          # aperturas, cierres, obras, cambios de convenio. Opcional.
    "sitios_propuestos": None,        # hasta 5 ubicaciones propuestas por la clínica (dirección o lat/lon). Opcional.
    "ipc": None,                      # serie IPC mensual del INE (periodo, indice). None = aproximación incluida.
    # Insumos propios del estudio (levantamiento 19/20-11-2026, en la carpeta insumos/)
    "maestro_sedes": os.path.join(AQUI, "insumos", "sucursales_red_alemana.csv"),
    "competencia": os.path.join(AQUI, "insumos", "pois_salud_nacional.csv"),
}

SIM = os.path.join(AQUI, "datos_simulados")
RUTAS_SIMULACION = {
    "censo": os.path.join(SIM, "SD06_SOCIODEMOGRAPHIC_BLOCK_2026.gpkg"),
    "pois": os.path.join(SIM, "PI01_POI.gpkg"),
    "bbrr": os.path.join(SIM, "MKTS_BBRR_2026_01.txt"),
    "street": os.path.join(SIM, "BC08_STREET.gpkg"),
    "per": os.path.join(SIM, "personas_20260825_tramos_sociedades.parquet"),
    "emp": os.path.join(SIM, "BD_EMPRESAS_ACTIVAS_3007.txt"),
    # en simulación se usa el grafo REAL de la RM (repositorio de grafos viales)
    "grafos": os.environ.get("GEOVENTAS_GRAFOS", r"C:\Users\Edison\Downloads\Grafos_peru_20261103\grafos_chile\regiones"),
    "gtfs": os.path.join(SIM, "gtfs_metro_simulado.zip"),
    "ventas_cliente": os.path.join(SIM, "cliente", "ventas_sede_mes_linea.csv"),
    "sedes_cliente": os.path.join(SIM, "cliente", "sedes_cliente.csv"),
    "origen_pacientes": os.path.join(SIM, "cliente", "atenciones_rut.csv"),
    "origen_pacientes_por_zona": os.path.join(SIM, "cliente", "ventas_origen_zona.csv"),   # formato alternativo (prueba)
    "origen_pacientes_sin_dv": os.path.join(SIM, "cliente", "atenciones_rut_sin_dv.csv"),  # RUT sin dígito verificador (prueba)
    "areas_verdes": os.path.join(SIM, "areas_verdes.gpkg"),
    "eventos_cliente": os.path.join(SIM, "cliente", "eventos_cliente.csv"),
    "sitios_propuestos": os.path.join(SIM, "cliente", "sitios_propuestos.csv"),
    "ipc": None,
    "maestro_sedes": RUTAS_REALES["maestro_sedes"],
    "competencia": RUTAS_REALES["competencia"],
}

# --------------------------------------------------------------------------------------------- COLUMNAS EQUIFAX
# {nombre lógico usado en el código: nombre real en la base}. Son los nombres originales de las bases.
COLUMNAS = {
    "censo": {
        "id": "ID_BLOCK", "cod_comuna": "COD_APD3", "gse_predominante": "PRED", "pob": "POB", "hog": "HOG", "viv": "VIV",
        "ing": "ING", "gasto": "GASTO", "hombres": "H", "mujeres": "M", "casas": "CASAS", "deptos": "DEPARTAMEN",
        "tipo_viv": "TIPO_VIV", "uso_suelo": "USO_SUELO", "comuna": "COMUNA", "provincia": "PROVINCIA",
        "region": "REGION", "id_region": "ID_REG", "cod_ine": "REDCODE",
        # patrones por GSE (el código reemplaza {gse} por AB, C1A, ...) y por categoría de gasto
        "pob_gse": "POB_{gse}", "hog_gse": "HOG_{gse}", "viv_gse": "VIV_{gse}", "ing_gse": "ING_{gse}",
        "gasto_cat_gse": "G_{cat}_{gse}", "gasto_cat": "G_{cat}",
        "edades": ["POB_0_5", "POB_6_13", "POB_14_17", "POB_18_24", "POB_25_44", "POB_45_59", "POB_60_MAS"],
    },
    "per": {
        "id": "RUTID", "edad": "EDAD", "sexo": "SEXO", "fecha_defuncion": "FECHA_DEFUNCION", "defuncion": "DEFUNCION", "gse": "GSE_PART",
        "lat": "LATITUD_PART", "lon": "LONGITUD_PART", "comuna": "COMUNA_PART", "region": "REGION_PART",
        "personas_hogar": "CANT_PERSONAS_HH", "vehiculos": "CANT_VEHICULOS", "bbrr": "CANT_BBRR", "hijos": "CANT_HIJOS_TOTAL",
        "dicom": "DICOM", "renta_hogar": "RENTA_TOTAL_HH", "ise": "ISE", "direccion_verificada": "DIRECC_VERIFICADA_PART",
    },
    "emp": {
        "id": "RUTID", "activa": "ACTIVA", "trabajadores": "CANTIDAD_TRAB", "rango_trabajadores": "RANGO_TRABAJADORES",
        "tamano": "TAMANO_EMPRESAS", "rubro": "RUBRO", "actividad": "ACTIVIDAD_PRINCIPAL", "cod_actividad": "CODIGO_ACTIVIDAD",
        "lat": "LATITUD_COMER", "lon": "LONGITUD_COMER", "comuna": "COMUNA_COMER", "region": "REGION_COMER", "gse": "GSE_COMER",
    },
    "bbrr": {
        "id": "ROL", "destino": "CODIGO_DESTINO", "glosa_destino": "GLOSA_DESTINO", "avaluo": "AVALUO_FISCAL",
        "sup_terreno": "SUPERFICIE_TERRENO", "tipo_propiedad": "TIPO_PROPIEDAD", "comuna": "COMUNA", "region": "REGION",
        "lat": "LATITUD", "lon": "LONGITUD",
    },
    "pois": {
        "id": "ID_POI", "cod_comuna": "COD_APD3", "cat1": "CAT1_DES", "cat2": "CAT2_DES", "cat3": "CAT3_DES", "marca": "BRAND",
        "nombre": "TRADENAME", "direccion": "ADDRESS", "estado": "STATUS", "lon": "LON_X", "lat": "LAT_Y", "cadena": "CHAIN",
        "fuente": "SOURCE", "actualizado": "UPD_DATE",
    },
    "street": {
        "id": "ID_STREET", "cod_comuna": "COD_APD3", "cod_comuna_izq": "COD_APD3_L", "cod_comuna_der": "COD_APD3_R",
        "tipo": "TYP_STREET", "nombre": "NAM_STREET", "sinonimo1": "SYNONYM1", "sinonimo2": "SYNONYM2",
        "ini_izq": "START_LEFT", "fin_izq": "END_LEFT", "ini_der": "START_RIG", "fin_der": "END_RIG",
        "jerarquia": "HIERARCHY", "sentido": "DIRECTION",
    },
}

# Separador de los .txt de Equifax (bbrr y emp vienen con "|")
SEPARADOR_TXT = "|"

# --------------------------------------------------------------------------------------------- COLUMNAS DEL CLIENTE
# El formato exacto de la data del cliente aún no se conoce: el lector prueba estos sinónimos (sin tildes ni mayúsculas).
# Si la columna real tiene otro nombre, agrégalo a la lista o fija el nombre exacto como primer elemento.
COLUMNAS_CLIENTE = {
    "sede": ["id_sede", "cod_sede", "codigo_sede", "sede", "centro", "sucursal", "cod_centro", "establecimiento", "unidad"],
    "periodo": ["mes", "periodo", "fecha", "anio_mes", "ano_mes", "year_month", "fecha_atencion", "fecha_prestacion", "anio", "ano"],
    "linea": ["linea_prestacion", "linea", "linea_servicio", "servicio", "especialidad", "area", "tipo_prestacion", "unidad_negocio"],
    "prevision": ["prevision", "prevision_salud", "isapre_fonasa", "financiador", "aseguradora", "convenio"],
    "monto": ["monto_clp", "venta", "venta_neta", "monto", "ingreso", "ingresos", "facturacion", "venta_clp", "valor"],
    "atenciones": ["n_atenciones", "atenciones", "prestaciones", "cantidad", "sesiones", "n_prestaciones", "volumen"],
    "pacientes": ["n_pacientes", "pacientes", "pacientes_unicos", "n_ruts"],
    "ticket": ["ticket", "ticket_promedio"],
    "zona": ["zona_domicilio", "zona", "manzana", "zona_censal", "cod_manzana", "comuna_domicilio", "comuna_paciente", "comuna"],
    "rut_hash": ["rut_hash", "rut_seudonimizado", "id_paciente_hash", "paciente_hash", "hash_rut"],
    "rut": ["rut", "rut_paciente", "rutid", "run", "rut_cliente", "rut_beneficiario", "id_paciente", "rut_titular"],
    "dv": ["dv", "dv_rut", "rut_dv", "digito_verificador", "dig_verificador", "digito", "dv_paciente"],   # si el DV viene aparte
    "fecha": ["fecha", "fecha_atencion", "fecha_prestacion", "fecha_servicio", "mes", "periodo"],
    "lat": ["lat", "latitud", "lat_domicilio"],
    "lon": ["lon", "lng", "longitud", "lon_domicilio"],
    # hoja Sedes
    "nombre": ["nombre_sede", "nombre", "sede_nombre", "descripcion"],
    "formato": ["formato", "tipo_sede", "tipo", "formato_sede"],
    "direccion": ["direccion", "direccion_sede", "domicilio"],
    "comuna_sede": ["comuna", "comuna_sede"],
    "fecha_apertura": ["fecha_apertura", "apertura", "inicio_operacion"],
    "fecha_cierre": ["fecha_cierre", "cierre", "termino_operacion"],
    "m2": ["m2", "superficie", "superficie_util", "metros_cuadrados"],
    "boxes": ["boxes", "n_boxes", "consultas_box"],
    "camas": ["camas", "n_camas"],
    "pabellones": ["pabellones", "n_pabellones"],
    "prestaciones": ["prestaciones", "lineas", "cartera_servicios"],
    # eventos
    "desde": ["desde", "fecha_inicio", "inicio"],
    "hasta": ["hasta", "fecha_fin", "fin", "termino"],
    "tipo_evento": ["tipo", "tipo_evento", "evento"],
    "descripcion": ["descripcion", "detalle", "comentario"],
}
# Código de sede del cliente -> id del maestro (CAS-01, ...). Vacío = se empareja solo por nombre/dirección (notebook 02).
MAPA_SEDES = {}
# Sal (secreto) acordada con la clínica para seudonimizar RUT: sha256(SAL + RUT normalizado). Solo si envían RUT seudonimizado.
SAL_RUT = os.environ.get("GEOVENTAS_SAL_RUT", "")

# --------------------------------------------------------------------------------------------- PARÁMETROS
GSE = ["AB", "C1A", "C1B", "C2", "C3", "D", "E"]            # sufijos tal como vienen en el censo (POB_C1A, G_SAL_C1A, ...)

PARAMETROS = {
    "computo": {
        # núcleos para los cálculos en paralelo (Dijkstra, isócronas, bootstrap, validaciones). -1 = todos menos uno.
        "n_jobs": -1,
        # memoria por proceso en paralelo (GB). Antes de cada cálculo en paralelo se mide la memoria libre y se usan solo
        # los procesos que caben (con 20% de margen); si igual falta, se reintenta con la mitad. Medido en la RM completa:
        # ~0,6 GB de base + ~0,6 GB en la isócrona más grande (auto 30 min). No hace falta tocarlo.
        "gb_por_proceso": 1.2,
        "lote_dijkstra": 24,                  # destinos por tarea de Dijkstra (más grande = menos tareas, más RAM por tarea)
    },
    "estudio": {
        "nombre": "Estimación de Ventas y Localización Óptima · Clínica Alemana de Santiago",
        "nombre_area": "Santiago",           # nombre corto del área de estudio para los títulos de mapas e informes
        "id_regiones": [13],                 # ID_REG del censo (13 = Metropolitana): solo filtra las manzanas del censo.
        "bbox": None,                        # (lon_min, lat_min, lon_max, lat_max) opcional para recortar el área
        "crs_metrico": "EPSG:32719",         # UTM 19S (Chile continental entre 72°W y 66°W)
        # coordenadas válidas (las que vienen con escala, signo o lat/lon intercambiados se corrigen para caer aquí;
        # ver geoventas/coordenadas.py). None = Chile completo, con Isla de Pascua.
        "limites_coordenadas": None,
        "semilla": 2026,
    },
    "gse_objetivo": ["AB", "C1A", "C1B"],    # FRF 2.3
    "censo": {
        "categoria_gasto_salud": "SAL",      # G_SAL_{gse}
        # unidad del gasto del censo: "mensual_total" (CLP/mes de la manzana), "anual_total", "mensual_por_hogar", "mensual_por_persona"
        "unidad_gasto": "mensual_total",
        "categorias_gasto": ["ALI", "ALC", "VES", "SER", "VIV", "SAL", "TRA", "COM", "REC", "EDU", "RES", "BIE"],
    },
    "per": {"excluir_fallecidos": True, "edad_min": 0, "edad_max": 110},
    "emp": {
        "solo_activas": True,
        # trabajadores si CANTIDAD_TRAB viene vacío: se usa el PROMEDIO de las empresas del mismo tamaño que sí traen el dato
        # (en la misma base). Estos valores fijos solo se usan si un tamaño tiene < min_empresas_por_tamano empresas con dato.
        "trabajadores_por_tamano_desde_base": True,
        "min_empresas_por_tamano": 30,
        "trabajadores_por_tamano": {"micro": 3, "pequena": 25, "mediana": 125, "grande": 600, "sin informacion": 2},
        "regex_salud": r"salud|medic|clinic|laborator|odontol|hospital|kinesi|psicol|enfermer",
    },
    "pois": {   # variable -> expresión regular sobre CAT1|CAT2|CAT3 (sin tildes, minúsculas)
        "poi_metro": r"metro|estacion de tren|tren urbano",
        "poi_paradero": r"paradero|terminal de buses|transporte publico",
        "poi_mall": r"mall|centro comercial|outlet|strip center",
        "poi_supermercado": r"supermercado|hipermercado",
        "poi_educacion": r"colegio|universidad|instituto|jardin infantil|educacion|preuniversitario",
        "poi_oficinas": r"oficina|banco|financ|seguro|notaria",
        "poi_salud": r"^salud|clinica|hospital|centro medico|laboratorio|farmacia",
        "poi_gimnasio": r"gimnasio|deporte",
        "poi_restaurant": r"restaurant|comida|cafe|alimentacion",
    },
    "bbrr": {   # CODIGO_DESTINO del SII -> grupo
        "destinos": {"H": "habitacional", "C": "comercio", "O": "oficina", "S": "salud", "E": "educacion", "I": "industria",
                     "L": "bodega", "Z": "estacionamiento", "W": "sitio_eriazo", "G": "hotel", "P": "publico"},
    },
    "street": {"jerarquia_principal": [1, 2, 3], "tipos_principales": ["AV", "AVENIDA", "AUT", "AUTOPISTA", "CAM", "CAMINO", "CARR"]},
    # UNIDAD DE ANÁLISIS: la MANZANA del censo (polígono de SD06). Demanda, tiempos, calibración, venta estimada,
    # candidatos, mapas y capas GIS se trabajan sobre los polígonos de manzana.
    "filtro_manzanas": {                      # se descartan ANTES de calcular (cada descarte queda con su motivo)
        "descartar_vacias": True,             # sin población, sin trabajadores y sin POIs
        "usos_excluir": ["area verde", "areas verdes", "parque", "plaza", "cementerio", "aeropuerto", "rio", "cerro",
                         "bien nacional de uso publico", "sitio eriazo"],   # palabras en USO_SUELO
        "pob_max_uso_excluido": 0,            # el uso excluido solo descarta si la manzana tiene ≤ esta población
        "area_verde_min_pct": 0.80,           # con capa de áreas verdes: se descarta si ≥ 80% de su superficie es área verde…
        "pob_max_area_verde": 10,             # …y tiene ≤ 10 habitantes
        "dist_max_punto_manzana_m": 60.0,     # personas fuera de toda manzana (en la calle): a la manzana más cercana a ≤ 60 m
        "dist_max_actividad_m": 300.0,        # empresas, POIs y propiedades (predios grandes, zonas industriales): hasta 300 m
    },
    "red": {
        "horizonte_min": 60.0,                # tiempo máximo de viaje considerado (una clínica atrae de lejos; más allá, aporte ≈ 0)
        # velocidad en punta = velocidad del grafo × factor por tipo de vía (congestión AM de Santiago)
        "factor_punta": {"motorway": 0.55, "trunk": 0.55, "primary": 0.60, "secondary": 0.65, "tertiary": 0.70, "default": 0.80},
        "velocidad_por_defecto_kph": {"motorway": 100, "trunk": 80, "primary": 50, "secondary": 50, "tertiary": 40, "residential": 30, "default": 30},
        "velocidad_caminata_kmh": 4.8,
        "acceso_auto_kmh": 15.0,              # tramo punto interior de la manzana -> nodo de la red (estacionar, calles locales)
        "isocronas_min": {"auto_punta": [5, 10, 15, 20, 30], "auto_valle": [5, 10, 15, 20, 30], "pie": [5, 10, 15, 20], "tp": [15, 30, 45]},
        "buffer_isocrona_m": 60.0,            # ancho de la franja alrededor de los tramos alcanzados al dibujar el polígono
    },
    "tp": {   # transporte público
        "bus_aproximado": True,               # buses sobre vías principales si el GTFS no trae buses
        "vias_bus": ["trunk", "primary", "secondary", "tertiary"],
        "velocidad_bus_kmh": {"trunk": 19, "primary": 17, "secondary": 15, "tertiary": 13},
        "espera_bus_min": 5.0,                # mitad de un intervalo típico de 10 min en punta
        "espera_metro_min": 2.0,
        "max_espera_min": 10.0,
        "ventana_punta_gtfs": ("07:00:00", "09:00:00"),
        "transbordo_min": 1.0,
    },
    "ventas": {
        "meses_calibracion": 24,              # ventana para la venta "madura" que calibra el modelo (FRF: 24 a 36 meses)
        "meses_madurez": 36,                  # una sede con menos meses abiertos se considera en maduración
        "umbral_atipico_z": 4.5,              # residuo robusto (MAD) para marcar meses atípicos (4,5 evita falsas alarmas)
        "umbral_quiebre": 0.08,               # cambio de nivel ≥ 8% (y ≥ 4 veces el ruido) entre semestres consecutivos = quiebre
        "anio_base_precios": None,            # None = último mes de la serie (pesos del último mes)
        # IPC aproximado (variación anual, INE) si no se entrega la serie: reemplazar por la serie oficial
        "ipc_anual_aprox": {2021: 0.072, 2022: 0.128, 2023: 0.039, 2024: 0.045, 2025: 0.040, 2026: 0.035},
        "rampa_por_defecto": [0.60, 0.85, 1.00],  # maduración años 1-3 si no hay aperturas en la ventana
    },
    "origen": {
        "nivel_calibracion": "auto",          # "auto" | "unidad" (manzana) | "zona" | "comuna" | "total" (auto: manzana con RUT, zona si el origen viene por zonas)
        "min_pacientes_publicacion": 5,       # anonimato: en mapas y entregables solo manzanas con ≥ 5 pacientes
        "rut_min_empresa": 50_000_000,        # RUT ≥ 50 millones = persona jurídica (se cruza con emp); menor = persona (per)
        "solo_direccion_verificada": False,   # True: solo pacientes con DIRECC_VERIFICADA_PART = "S" ubican la demanda
        "min_cruce_aceptable": 0.70,          # alerta si menos del 70% de las atenciones cruza con per o emp
    },
    "formatos": {   # texto del formato (cliente o maestro) -> formato del modelo
        "clinica": ["clinica hospitalaria", "clinica (", "clinica alta", "hospital", "clinica"],
        "centro_medico": ["centro medico", "centro ambulatorio", "consultas"],
        "toma_muestras": ["toma de muestras", "toma muestras", "laboratorio", "tm "],
    },
    "excluir_sedes": ["estacional", "registro deis", "verificar", "edificio del campus", "domicilio"],
    "competencia": {
        # grupo del modelo -> valores de formato_FRF del universo de competencia
        "grupos": {"comp_clinica": ["Clínica de Alta Complejidad", "Clínica (mediana o baja complejidad)"],
                   "comp_centro_medico": ["Centro Médico Ambulatorio"],
                   "comp_laboratorio": ["Toma de Muestras / Laboratorio"]},
        "tipos_relevantes": ["Directa: red listada en el FRF", "Directa: otra clínica de alta complejidad", "Indirecta",
                             "Contexto: oferta pública"],
        "peso_segmento": {"Premium": 1.0, "Medio-alto": 0.8, "Medio": 0.55, "Masivo": 0.35, "s/i": 0.5, "Público": 0.2, "Seguro laboral": 0.3},
        "excluir_marcas": ["alemana"],        # la red propia no es competencia
        # POIs de salud de Equifax (PI01): se suman al levantamiento los que NO estén ya (el levantamiento tiene prioridad)
        "pois_equifax": {
            # es de salud si CAT1|CAT2|CAT3 (sin tildes, minúsculas) cumple `incluir` y no `excluir`
            "incluir": r"\bsalud\b|clinic|hospital|medic|laborator|toma de muestra|dental|odontolog|dentist|farmac|kinesi|"
                       r"optica|psicolog|vacunatorio|imagenolog|radiolog|policlinic|consultorio|cesfam|urgencia",
            "excluir": r"veterinari|mascota|animal|canin|felin|pet ?shop",
            # tipo de lugar según categoría + nombre (la primera regla que calza). Sirve para no unir lugares de tipos
            # incompatibles (una farmacia junto a un centro médico) y para dar formato a los POIs nuevos.
            "familias": [("farmacia", r"farmac|drogueria"), ("optica", r"\boptica"),
                         ("dental", r"dental|odontolog|dentist|ortodonc|implant"),
                         ("laboratorio", r"laborator|toma de muestra|toma muestra|examenes"),
                         ("kine", r"kinesi|rehabilit|fisioterap|fisiatr"), ("eleam", r"residencia|eleam|adulto mayor|hogar de ancianos"),
                         ("insumos", r"insumo|ortopedi"), ("ambulancia", r"ambulancia|samu"),
                         ("hospital", r"clinica|hospital"),
                         ("medica", r"medic|consulta|policlinic|cesfam|cecosf|sapu|urgencia|psicolog|psiquiatr|salud mental|"
                                    r"vacunatorio|imagenolog|radiolog|dialisis|mutual|atencion primaria|nutricion|fonoaudiolog|"
                                    r"audiolog|podolog|oncolog|oftalmolog|banco de sangre|estetica|cirugia")],
            # nombre que delata oferta pública (APS, urgencias municipales, hospitales públicos)
            "publico": r"cesfam|cecosf|sapu|\bsar\b|\bsur\b|consultorio|posta|hospital|complejo asistencial|servicio de salud|municipal",
        },
        # Unificación levantamiento + Equifax por coordenadas, nombre, dirección y tipo (ver geoventas/unificacion_pois.py)
        "unificacion": {
            "radio_max_m": 300.0,             # se comparan los lugares a ≤ 300 m
            "cerca_m": 30.0,                  # a ≤ 30 m basta un parecido de nombre de 0,50…
            "nombre_min_cerca": 0.50,
            "nombre_min_lejos": 0.90,         # …que sube en línea recta hasta 0,90 a 300 m
            "bonus_misma_direccion": 0.20,    # misma calle y número: el mínimo baja 0,20
            "castigo_tipo_afin": 0.10,        # tipos afines pero distintos (centro médico ↔ laboratorio): sube 0,10
            "cadena_lugares_min": 2,          # nombre presente en ≥ 2 lugares del mismo tipo = cadena o topónimo…
            "cadena_max_m": 120.0,            # …solo se une a ≤ 120 m o con la misma dirección
            "generico_max_m": 25.0,           # nombre genérico ("Centro Médico"): solo a ≤ 25 m o misma dirección…
            "generico_nombre_min": 0.85,      # …y casi idéntico
            "margen_revision": 0.12,          # pares a menos de 0,12 del mínimo: se listan para revisión manual
            "buffer_borde_m": 500.0,          # el levantamiento se mira hasta 500 m fuera del área (lugares en el borde)
        },
        # potencial de competencia exacto por manzana (notebook 04): Σ w·e^(−β·t) precalculado en una grilla de β e
        # interpolado (Hermite) durante el ajuste. 48 valores entre 0,004 y 1,5 dan error < 0,01% (0,1% en la derivada). No hace falta tocarlo.
        "n_grilla_beta": 48,
        "beta_min": 0.004,
        "beta_max": 1.5,
        "lote_competidores": 200,             # competidores por lote al calcular tiempos (acota la memoria)
    },
    "entorno": {   # análisis de entorno de cada sede de la red (base de puntos del levantamiento: RUTAS["maestro_sedes"])
        "modos": ["auto_valle", "auto_punta"],   # agregar "pie" y/o "tp" para analizar también caminando o en transporte público
        "minutos": [5, 10, 15, 20, 30],          # cortes de las zonas (isócronas)
        "minutos_referencia": 15,                # corte con que se comparan las sedes y se escriben las conclusiones
        "minutos_tipologia": 10,                 # corte con que se clasifica el tipo de entorno (lo inmediato)
        "minutos_traslape": 5,                   # corte con que se mide el traslape entre sedes (a 15 min en Santiago oriente todo se traslapa)
        "personas_objetivo_meta": 100_000,       # ¿en cuántos minutos reúne cada sede esta cantidad de personas del segmento?
        "registros": ["Sede oficial"],           # tipo_registro del maestro que entra (los "por verificar" no)
        "misma_sede_m": 500,                     # puntos a menos de esto son el mismo recinto (no cuentan como traslape)
    },
    "influencia": {   # zonas de influencia MODELADAS (notebook 04b): se pueden calcular ANTES de recibir RUT y ventas
        "modos": ["auto_punta", "auto_valle"],
        "cortes": [0.6, 0.8],                    # primaria = 60% de la demanda captada; secundaria = hasta 80% (igual que las reales del 05)
        # Supuestos mientras no haya ventas (se reemplazan al calibrar el modelo en el notebook 06). Atractivo en log:
        # una clínica atrae e^1 ≈ 2,7 veces lo que un centro médico a igual distancia; una toma de muestras, e^-0,7 ≈ 0,5.
        "atractivo_formato": {"clinica": 1.0, "centro_medico": 0.0, "toma_muestras": -0.7},
        "peso_trabajadores": 0.3,                # λ: peso de un trabajador (demanda de día) frente a un residente
        "sensibilidad_beta": [0.75, 1.25],       # rango: la gente viaja más (β × 0,75) o menos (β × 1,25) de lo supuesto
    },
    "modelo": {
        "hora": "auto_punta",                 # tiempos usados en el modelo
        "pesos_gse_iniciales": {"AB": 1.0, "C1A": 0.8, "C1B": 0.55, "C2": 0.25, "C3": 0.1, "D": 0.04, "E": 0.02},
        "estimar_pesos_gse": True,
        "prior_sd": 1.0,
        # priors de β (caída por minuto) por formato: se usan sobre todo si no hay datos de origen (nivel "total")
        "beta_prior": {"clinica": 0.06, "centro_medico": 0.12, "toma_muestras": 0.20},
        "capacidad": "m2",                    # columna de la hoja Sedes que mide el tamaño (m2, boxes…); sin dato = tamaño típico
        "n_bootstrap": 40,
        "n_bloques_cv": 8,
    },
    "expansion": {
        # escenarios P10/P90 de sitios nuevos = incertidumbre de parámetros (bootstrap) + error propio de una sede nueva
        # (σ medido en la validación "sede nueva" del notebook 06). False = solo parámetros (bandas más angostas).
        "incluir_error_sede": True,
        "n_top": 20,
        "max_por_formato": {"clinica": 3, "centro_medico": 10, "toma_muestras": 10},
        "dist_min_propia_km": {"clinica": 8.0, "centro_medico": 2.5, "toma_muestras": 1.2},
        "dist_min_entre_nuevas_km": {"clinica": 10.0, "centro_medico": 3.0, "toma_muestras": 1.5},
        # MANZANAS CANDIDATAS a sede nueva: manzanas urbanas (o en polos laborales) que dan a una vía terciaria o superior.
        # El "entorno" de una manzana son las manzanas a ≤ radio_entorno_m (población y trabajadores del barrio).
        "radio_entorno_m": 600,
        "pob_entorno_min": 1700,              # ≈ 1.500 hab/km² en el círculo de 600 m: zona urbana
        "trabajadores_entorno_min": 1500,     # o polo laboral
        "dist_max_via_m": 150,                # el sitio es el nodo de una vía terciaria o superior a ≤ 150 m de la manzana
        "separacion_min_m": 250,              # dos manzanas candidatas a menos de esto: queda la de mayor prioridad
        "max_candidatos": 2500,               # candidatos evaluados con tiempos exactos de red (los de mayor prioridad)
        "max_eval_paso": 800,                 # selección secuencial: candidatos reevaluados exacto por formato en cada paso
        "umbral_viabilidad_percentil": 25,    # venta neta ≥ P25 de la venta predicha de las sedes actuales del formato
        "pesos_scoring": {"venta_neta": 0.40, "hogares_objetivo": 0.15, "gasto_potencial": 0.10, "saturacion_inv": 0.10,
                          "accesibilidad": 0.10, "canibalizacion_inv": 0.10, "poblacion_flotante": 0.05},
        "isocrona_scoring_min": {"clinica": 30, "centro_medico": 15, "toma_muestras": 10},
        "macrozona_frac": 0.80,               # macrozona clínica: sitios con ≥80% de la venta neta del mejor
        "macrozona_radio_km": 5.0,
        "n_macrozonas": 3,
    },
}

# Ajustes de cada perfil sobre PARAMETROS (solo las claves que cambian)
PERFILES = {
    "completo": {},
    "rapido": {"modelo": {"n_bootstrap": 12, "n_bloques_cv": 4},
               "expansion": {"max_candidatos": 1000, "max_eval_paso": 300}},
}

SUPUESTOS = [
    ("Unidad de análisis", "Manzana del censo (SD06), sin las vacías, de uso de suelo excluido o de áreas verdes", "Es la unidad con que se estima siempre la venta y la que permite ubicar cada RUT en su domicilio exacto (FRF 2.4: microterritorio)."),
    ("Origen de los pacientes", "RUT de cada atención cruzado con personas (domicilio) y empresas (convenios), seudonimizado con SHA-256 + sal", "Ubica a cada paciente en su manzana sin guardar el RUT; la calibración se hace manzana por manzana."),
    ("Isócronas", "Tiempos sobre el grafo vial OSM (OSMnx) con Dijkstra; polígono = tramos alcanzados + franja de 60 m", "Reemplaza los buffers: respeta la red, los sentidos de tránsito y las barreras (ríos, autopistas, cerros)."),
    ("Hora punta", "Velocidad del grafo × 0,55–0,80 según tipo de vía", "Reproduce la congestión de Santiago en punta (autopistas y avenidas pierden más velocidad relativa)."),
    ("Caminata", "4,8 km/h sobre toda la red, sin sentido de tránsito", "Velocidad peatonal urbana estándar."),
    ("Transporte público", "Caminata + bus sobre vías principales (13–19 km/h, espera 5 min) + líneas GTFS (espera = ½ intervalo)", "Sin GTFS de buses se aproxima el bus por la red vial; con GTFS se usan los tiempos programados."),
    ("Demanda potencial", "Gasto mensual en salud por GSE (censo) × peso de afinidad del GSE", "El censo trae el gasto por GSE; los pesos se estiman con el origen de los pacientes."),
    ("Población flotante", "Trabajadores por empresa (CANTIDAD_TRAB; si falta, el promedio de las empresas del mismo tamaño que sí lo traen)", "Demanda diurna de centros médicos y tomas de muestras (FRF 2.3); un valor fijo por tramo de ventas sesga el peso de esta demanda."),
    ("Elección de sede", "Modelo de Huff: atractivo por formato y caída exponencial con el tiempo", "Modelo estándar de interacción espacial; parámetros por máxima verosimilitud penalizada."),
    ("Competencia", "Universo levantado (19/20-11-2026, con prioridad) + POIs de salud Equifax que no estaban, unidos por coordenadas, nombre, dirección y tipo (un registro por lugar); agrupado en clínicas, centros médicos y laboratorios, ponderado por segmento; tiempo exacto de cada manzana a cada competidor", "Captura la oferta alternativa en la cuota de cada sede sin contar dos veces el mismo lugar."),
    ("Candidatos", "Manzanas urbanas (o en polos laborales) que dan a una vía terciaria o superior, separadas ≥ 250 m; el sitio es el nodo de la vía", "Una sede nueva necesita frente a una vía relevante; la separación evita evaluar dos veces el mismo lugar."),
    ("Precios", "Ventas en pesos reales del último mes (deflactadas por IPC); montos en miles, millones o UF se llevan a pesos al leerlos", "Cinco años con inflación alta (2022) no son comparables en pesos nominales."),
    ("Venta madura", "Promedio de los últimos 24 meses sin meses atípicos; sedes en maduración llevadas a régimen con la curva de rampa", "El modelo representa el régimen estable de cada sede."),
    ("Maduración", "Curva estimada con las aperturas de la ventana de 5 años (si no hay, 60% / 85% / 100%)", "Proyección de los años 1 a 3 de una sede nueva."),
    ("Escenarios", "P10 / P50 / P90 del bootstrap de los parámetros combinado con el error propio de una sede nueva (validación \"sede nueva\")", "Conservador, base y optimista con la incertidumbre del modelo y la de cada sitio concreto (FRF Hito 2)."),
    ("Viabilidad", "Venta neta ≥ percentil 25 de la venta predicha de las sedes actuales del mismo formato", "Evita recomendar sitios por debajo del desempeño de la red actual."),
]


def _mezclar(base, cambios):
    """Aplica `cambios` sobre `base` (diccionarios anidados)."""
    for k, v in cambios.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _mezclar(base[k], v)
        else:
            base[k] = copy.deepcopy(v)
    return base


def obtener_config(modo=None):
    """Devuelve un diccionario con rutas, columnas y parámetros del modo pedido (por defecto, MODO).

    Solo en simulación, para probar escenarios sin tocar este archivo (los usa el probador de escenarios):
      GEOVENTAS_ESCENARIO = nombre   carpetas de trabajo y salida propias (trabajo_simulacion_<nombre>)
      GEOVENTAS_SIN = "gtfs,origen_pacientes"         esas rutas quedan vacías (como si el insumo no viniera)
      GEOVENTAS_USAR = "origen_pacientes=origen_pacientes_por_zona"   una ruta toma el archivo de otra
      GEOVENTAS_PERFIL = "rapido"                     perfil de cómputo
      GEOVENTAS_MAPA_SEDES = '{"S100": "CAS-01"}'     MAPA_SEDES (JSON), como si el equipo lo hubiera completado
      GEOVENTAS_RUT_CON_DV = "auto" | "True" | "False"  RUT_CON_DV
      GEOVENTAS_RUT_PACIENTES = "sin_rut"             RUT_PACIENTES (por defecto "en_claro" en simulación)
      GEOVENTAS_UNIDAD_MONTO = "miles"                UNIDAD_MONTO
      GEOVENTAS_RUTAS = '{"ventas_cliente": "ruta.csv"}'   rutas que apuntan a otro archivo (variantes de prueba)
    """
    modo = modo or MODO
    os.environ["GEOVENTAS_MODO"] = modo           # los mapas muestran el aviso "DATOS SIMULADOS" cuando corresponde
    sim = modo == "simulacion"
    perfil = (os.environ.get("GEOVENTAS_PERFIL") or PERFIL) if sim else PERFIL
    if perfil not in PERFILES:
        raise ValueError(f"PERFIL = {perfil!r} no existe; usa uno de {list(PERFILES)}")
    cfg = _mezclar(copy.deepcopy(PARAMETROS), PERFILES[perfil])
    cfg["modo"], cfg["perfil"] = modo, perfil
    cfg["rutas"] = copy.deepcopy(RUTAS_SIMULACION if sim else RUTAS_REALES)
    escenario = os.environ.get("GEOVENTAS_ESCENARIO", "") if sim else ""
    if sim:
        if os.environ.get("GEOVENTAS_RUTAS"):
            import json
            cfg["rutas"].update(json.loads(os.environ["GEOVENTAS_RUTAS"]))
        for k in filter(None, os.environ.get("GEOVENTAS_SIN", "").split(",")):
            cfg["rutas"][k.strip()] = None
        for par in filter(None, os.environ.get("GEOVENTAS_USAR", "").split(",")):
            k, _, origen = par.partition("=")
            cfg["rutas"][k.strip()] = cfg["rutas"][origen.strip()]
    cfg["rut_pacientes"] = (os.environ.get("GEOVENTAS_RUT_PACIENTES") or "en_claro") if sim else RUT_PACIENTES
    cfg["rut_con_dv"] = (os.environ.get("GEOVENTAS_RUT_CON_DV") or RUT_CON_DV) if sim else RUT_CON_DV
    if cfg["rut_con_dv"] in ("True", "False"):
        cfg["rut_con_dv"] = cfg["rut_con_dv"] == "True"
    cfg["unidad_monto"] = (os.environ.get("GEOVENTAS_UNIDAD_MONTO") or UNIDAD_MONTO) if sim else UNIDAD_MONTO
    cfg["valor_uf"] = VALOR_UF
    grafos = GRAFOS_VIALES
    if sim:      # en la simulación basta la RM (la carpeta de prueba trae las 16 regiones); GEOVENTAS_GRAFOS_VIALES="todos" prueba la otra opción
        grafos = os.environ.get("GEOVENTAS_GRAFOS_VIALES") or ["CL-RM_metropolitana_de_santiago.graphml"]
    cfg["estudio"]["grafos"] = list(grafos) if isinstance(grafos, (list, tuple)) else grafos
    cfg["columnas"] = copy.deepcopy(COLUMNAS)
    cfg["columnas_cliente"] = copy.deepcopy(COLUMNAS_CLIENTE)
    cfg["mapa_sedes"] = dict(MAPA_SEDES)
    if sim and os.environ.get("GEOVENTAS_MAPA_SEDES"):
        import json
        cfg["mapa_sedes"].update(json.loads(os.environ["GEOVENTAS_MAPA_SEDES"]))
    cfg["sal_rut"] = SAL_RUT
    cfg["gse"] = list(GSE)
    cfg["separador_txt"] = SEPARADOR_TXT
    cfg["supuestos"] = list(SUPUESTOS)
    sufijo = ("_simulacion" if sim else "") + (f"_{escenario}" if escenario else "")
    cfg["carpetas"] = {"trabajo": os.path.join(AQUI, "trabajo" + sufijo), "salidas": os.path.join(AQUI, "salidas" + sufijo),
                       "cache": os.path.join(AQUI, "cache_gcs")}
    if modo == "simulacion":
        # factor_ventas: en los escenarios con ventas × k (probar_escenarios.py) la "verdad" simulada también se multiplica
        cfg["simulacion"] = {"verdad": os.path.join(SIM, "verdad.json"), "factor_ventas": float(os.environ.get("GEOVENTAS_FACTOR_VENTAS") or 1)}
        cfg["sal_rut"] = "SAL-SIMULADA-2026"
    for c in cfg["carpetas"].values():
        os.makedirs(c, exist_ok=True)
    return cfg
