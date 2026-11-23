# GeoVentas · Clínica Alemana de Santiago

Estudio de estimación de ventas y localización óptima según el FRF del proyecto. Son 9 notebooks, uno por fase, y un paquete de funciones reutilizables (`geoventas/`).

## Estructura

```
GeoVentas_CAS/
├── config_estudio.py            ← ÚNICO archivo a editar (decisiones, rutas, columnas, parámetros, supuestos)
├── revisar_insumos.py           ← revisa TODO el estudio y dice qué falta (python revisar_insumos.py)
├── 00_simulacion_de_datos.ipynb ← solo para probar sin datos reales (NO correr en el PC de trabajo)
├── 01_ingesta_y_calidad.ipynb
├── 02_ventas_historicas_y_sedes.ipynb
├── 03_territorio_y_competencia.ipynb
├── 04_red_vial_e_isocronas.ipynb
├── 04b_zonas_de_influencia_preliminares.ipynb ← zonas de influencia SIN datos de la clínica (se corre antes: 01 → 03 → 04b)
├── 05_origen_destino_y_areas_de_influencia.ipynb
├── 06_modelo_de_ventas.ipynb
├── 07_expansion_scoring_y_ranking.ipynb
├── 08_entregables.ipynb
├── geoventas/                   ← funciones, un módulo por tema (ver geoventas/__init__.py)
├── insumos/                     ← maestro de sedes, universo de competencia, comunas RM
├── ejecutados_simulacion/       ← los 9 notebooks ya ejecutados con datos simulados (para mirar sin correr)
├── ejecutados_escenarios/       ← los mismos notebooks en escenarios con insumos faltantes o ventas distintas (ver "Escenarios probados")
├── constructor/                 ← fuentes .py de los notebooks, y el probador de escenarios (solo para regenerar/probar)
├── version_anterior_notebook_unico/ ← primera versión (un solo notebook autocontenido), como referencia
├── trabajo[_simulacion]/        ← resultados intermedios entre notebooks (se crea solo)
└── salidas[_simulacion]/        ← mapas HTML, gráficos y entregables finales (se crea solo)
```

## Flujo entre notebooks

| # | Notebook | Fase del FRF | Usa | Deja en `trabajo/` |
|---|---|---|---|---|
| 01 | Ingesta y calidad | Hito 1 · ingesta de fuentes | bases Equifax (gs://) | censo, per, emp, bbrr, pois, calles, área de estudio |
| 02 | Ventas históricas y sedes | Hito 1 · validación de datos y diagnóstico | ventas, sedes y eventos del cliente | sedes del estudio, panel mensual, venta madura, curva de maduración |
| 03 | Territorio y competencia | Hito 1 · mapeo de competencia | 01, 02 | manzanas útiles con variables (`unidades.parquet`), manzanas descartadas con su motivo, personas y empresas con su manzana, competencia |
| 04 | Red vial e isócronas | Hito 2 · isócronas (auto punta/valle, a pie, TP) | grafo GraphML, GTFS opcional, 03, maestro de sedes | red, tiempos manzana → sede, potencial de competencia exacto por manzana, manzanas candidatas y sus tiempos, isócronas de sedes, **análisis de entorno de cada sede** (punta y fuera de punta, 5 a 30 min), accesibilidad y brechas por manzana |
| 04b | Zonas de influencia preliminares | Hito 1 y 2 · áreas de influencia antes de recibir datos de la clínica | 01, 03, maestro de sedes, grafo vial (no necesita 02 ni 04) | zonas primaria y secundaria de cada sede (punta y fuera de punta), zona total de la red, territorio de cada sede, sensibilidad, Excel + GeoPackage + mapa en `salidas/preliminar/` |
| 05 | Origen–destino y áreas de influencia | Hito 1 y 2 · comportamiento de pacientes | atenciones con RUT (o origen por zona), 02–04 | cruce RUT con personas y empresas, flujos manzana → sede, áreas de influencia reales, afinidad, fidelidad, multisede, convenios, unidades de calibración |
| 06 | Modelo de ventas | Hito 2 · modelo y validación de desempeño | 03–05 | modelo calibrado, parámetros, validación "sede nueva" |
| 07 | Expansión, scoring y ranking | Hito 2 · scoring, ranking, formato · Hito 3 · sitios propuestos | 04–06 | manzanas candidatas evaluadas en los 3 formatos, Top 20, macrozonas, sitios propuestos |
| 08 | Entregables | Hito 3 · documentación, capas GIS y Mapdrive | todo | `salidas/entregables/` (incluye conclusiones e indicadores) |

Cada notebook cumple 4 reglas:

- Parte explicando qué hace, qué recibe y qué entrega.
- Su primera celda **revisa los insumos** y, si falta algo, se detiene y dice exactamente qué completar (ver "Asistente de insumos").
- Trae mapas interactivos de manzanas entre los pasos. Se ven dentro del notebook y quedan en `salidas/mapas/*.html` (ver "Mapas de manzanas").
- Termina con indicadores clave y conclusiones que se adaptan a los datos (02, 05, 06, 07 y 08) y con una tabla de verificaciones ✅ / ❌.

## Asistente de insumos: el estudio pide explícitamente lo que necesita

Nada se supone en silencio. La primera celda de cada notebook llama a `insumos.exigir(cfg, "NN")`, que revisa:

| Qué revisa | Ejemplo de lo que pide si falta |
|---|---|
| **Decisiones** que solo el equipo puede tomar: modo, región, qué grafo vial usar, cómo vendrá el RUT de los pacientes | `GRAFOS_VIALES = ["CL-RM_metropolitana_de_santiago.graphml"]` (sugerido según la región del censo); `RUT_PACIENTES = "en_claro"` / `"seudonimizado"` / `"sin_rut"`; `RUT_CON_DV = True` / `False` si la columna de RUT es ambigua |
| **Archivos**: que estén configurados, existan (local o en el bucket) y se puedan abrir | `RUTAS_REALES["ventas_cliente"] = "gs://…"`, y si la ruta está mal, qué archivos hay en esa carpeta |
| **Columnas de las bases Equifax**, leyendo solo el encabezado, contra la estructura real de cada base (`geoventas/esquemas.py`) | `COLUMNAS["per"]["lat"] = "LAT_PARTICULAR"`, con las columnas parecidas que encontró en el archivo; y un aviso si la base cambió (columnas que ya no vienen o nuevas) |
| **Formato del RUT** en personas, empresas y pacientes (muestra de 50 mil filas, sin cargar la base) | "trae dígito verificador (99,7% lo cumple)" o "trae solo el número: el dígito verificador se calcula"; si es ambiguo, pide `RUT_CON_DV` |
| **Columnas de la clínica**: qué reconoció y cuáles no | `COLUMNAS_CLIENTE["monto"].insert(0, "Venta Neta $")`, con la lista de columnas del archivo |
| **Unidad de los montos de venta** (pesos, miles, millones o UF), por el nombre de la columna o por la magnitud | "miles de pesos, según el nombre de la columna 'venta_miles' → venta mediana de una sede $160 millones al mes"; si dos unidades son posibles, pide `UNIDAD_MONTO = "pesos"` / `"miles"` / … mostrando cómo quedaría la venta en cada una |
| **Coherencia del RUT**: que el archivo de origen calce con la decisión y que pacientes, personas y empresas usen la misma sal | "el archivo trae RUT ya seudonimizados: cambia a `seudonimizado` y define `GEOVENTAS_SAL_RUT`" |
| **Resultados previos** | "Corre primero el notebook 03 · Territorio y competencia" |
| **Grafo vial y memoria** | el nombre exacto del archivo (con "¿quisiste decir…?" si está mal escrito), que cubra todas las regiones del censo leído, y si hay memoria suficiente para cargarlo |
| **Parámetros** contradictorios | pesos del scoring que no suman 1, GSE objetivo que no existen, CRS inválido… |

Además, dentro de los notebooks se detienen y piden confirmación dos cosas que solo se ven con los datos:

- **Unidad del gasto del censo** (notebook 01): si el gasto en salud por hogar sale ~12 veces mayor de lo esperable, parece anual y no mensual.
- **Emparejamiento de sedes** (notebook 02): con datos reales, una sede de la clínica que no se asocia con seguridad al levantamiento se pide confirmar en `MAPA_SEDES`, con la mejor coincidencia ya escrita.

Lo opcional que no viene se informa con su consecuencia (➖), y lo que conviene revisar con ⚠️. Para ver el estado de todo el estudio de una vez, sin correr nada:

```
python revisar_insumos.py            # el modo de config_estudio.py
python revisar_insumos.py real       # el modo real, antes de cambiar MODO
```

Los resultados opcionales que una corrida no produce (por ejemplo, los flujos si ya no viene el origen) se borran, para que ningún notebook siguiente use por error uno de una corrida anterior.

## Escenarios que soporta

| Escenario | Cómo se adapta |
|---|---|
| Sin origen de pacientes | calibra con la venta total por sede y valores de referencia; las áreas de influencia son modeladas |
| Origen por zona censal / comuna, o por coordenadas | calibra por zona (sin repartir antes de ajustar) o ubica cada coordenada en su manzana |
| RUT en claro, RUT seudonimizado por la clínica, o sin RUT | `RUT_PACIENTES`; sin RUT ni siquiera se lee la columna de RUT de personas y empresas |
| RUT escrito de cualquier forma: `0190270254`, `190270254`, `19027025-4`, `19.027.025-4`, `190270254.0` de Excel, con espacios, k minúscula | todo se lleva a la misma forma canónica (`190270254`) en personas, empresas y pacientes |
| RUT sin dígito verificador, o con el dígito en otra columna | se detecta en la columna completa y el dígito se calcula (o se toma de la columna `dv`); si es ambiguo, se pide `RUT_CON_DV` |
| Archivos `.txt`/`.csv` en latin-1 (Windows) en vez de UTF-8 | se detecta la codificación: "MÉDICO" no se convierte en "M�DICO" |
| Ventas en **miles, millones o UF** en vez de pesos | se reconoce la unidad (nombre de la columna o magnitud) y todo se lleva a pesos; si es ambigua, se pide `UNIDAD_MONTO` (ver "Ventas de cualquier tamaño y formato") |
| Ventas **transaccionales** (una fila por atención, fecha diaria, millones de filas) | las filas idénticas se conservan (pueden ser atenciones distintas) y todo se suma a sede × mes × línea × previsión; los archivos de más de 150 MB se leen por bloques |
| Una red que vende **mucho más o mucho menos** (o 3 sedes, o 30) | el modelo es invariante a la escala: mismos parámetros y mismo ranking, solo cambia la escala κ; todo lo que se informa es relativo (%, razones, minutos) |
| Números escritos `1.234.567`, `1,234,567`, `945,803526`, `(1.234)` | la convención de separadores (chilena o anglosajona) se decide para toda la columna; los negativos contables se leen como negativos |
| **Coordenadas** con coma o punto decimal, sin punto decimal, con separadores de miles, en grados/minutos/segundos, sin signo menos o con latitud y longitud intercambiadas | `geoventas/coordenadas.py` las lee todas igual en todas las bases (personas, empresas, BBRR, POIs, maestro de sedes, competencia, archivos de la clínica) y el notebook 01 informa cuántas corrigió en cada base (ver "Coordenadas en cualquier formato") |
| Historia de ventas corta (menos de 24 meses) | el estudio corre; avisa lo que no se puede medir (crecimiento anual, estacionalidad) y usa la rampa supuesta |
| Sin hoja de sedes, sin eventos, sin sitios propuestos, sin IPC, sin GTFS, sin áreas verdes | cada uno informa su consecuencia y el flujo sigue |
| Otra región o varias regiones | `id_regiones = [13, 5]`. Con `GRAFOS_VIALES = "todos"` no hay que tocar nada más: se cargan todos los grafos, se recorta cada uno al área y se unen los que la tocan. También se pueden listar por nombre de archivo (más rápido); el asistente avisa si falta el grafo de alguna región del censo |
| Lugares de salud repetidos entre el levantamiento y los POIs de Equifax | se unen por coordenadas, nombre, dirección y tipo; queda uno por lugar, con prioridad para el levantamiento (ver "Competencia") |
| Equipo con poca memoria | los cálculos en paralelo usan solo los procesos que caben y reintentan con la mitad si falta |
| Prueba rápida | `PERFIL = "rapido"`: menos réplicas de bootstrap, menos candidatos y validación cruzada más corta (no es para entregar) |

### Escenarios probados (23-11-2026, v3.6, datos simulados)

`python constructor/probar_escenarios.py --kernel <kernel>` corre cada escenario en su propia carpeta, partiendo de una copia de los resultados de la corrida completa (así también prueba que ningún notebook use un resultado viejo). `--solo nombre` corre uno y actualiza su fila del resumen. Las variantes de ventas se generan desde la tabla simulada (`simulacion.variantes_ventas`, en `datos_simulados/cliente/variantes/`) y, cuando representan la misma venta (o la misma × un factor), el resultado se **compara con la corrida base**.

**Insumos que faltan o cambian** (perfil rápido):

| Escenario | Notebooks | Errores | Verificaciones | Calidad del modelo |
|---|---|---|---|---|
| RUT **sin dígito verificador** (`19027025`, `19.027.025`, `019027025`) | 05–08 | 0 | 44 de 44 | se detecta solo (9% "calza" por azar) y el dígito se calcula · "sede nueva" 18,5%, igual que con dígito |
| Origen por zona censal (sin RUT) | 05–08 | 0 | 40 de 40 | "sede nueva" 18,3% · validación cruzada 95% |
| Sin origen de pacientes | 05–08 | 0 | 35 de 36 | "sede nueva" 18,7%. Falla la recuperación de λ (0,20 vs 0,30): sin el domicilio de los pacientes, 11 ventas totales no bastan para separar residentes de trabajadores |
| Mínimo: solo ventas (sin hoja de sedes, eventos, sitios, GTFS, áreas verdes ni origen) | 02–08 | 0 | 82 de 87 | "sede nueva" 54%: las 5 verificaciones que fallan son del modelo (sin m² no se separa el tamaño de la distancia). La conclusión del informe cambia a "confiabilidad baja: usar el ranking solo como orden relativo" |

**Ventas distintas** (la misma data de ventas escrita de otra forma, o una red de otro tamaño):

| Escenario | Notebooks | Errores | Verificaciones | Comparación con la corrida base |
|---|---|---|---|---|
| Montos en **miles** (`venta_miles`) | 02 | 0 | 13 de 13 | ✅ venta madura idéntica (diferencia 5·10⁻¹⁰): unidad reconocida por el nombre |
| Montos en **millones** con coma decimal (`945,803526`), sin la unidad en el nombre | 02 | 0 | 13 de 13 | ✅ idéntica (8·10⁻¹⁰): unidad reconocida por la magnitud y el ticket |
| **Unidad ambigua** (sin atenciones ni unidad en el nombre: pesos y miles son posibles) | 02 | 0 | — | ✅ el notebook **se detiene** y pide `UNIDAD_MONTO`, mostrando cómo quedaría la venta en cada unidad |
| La misma tabla con `UNIDAD_MONTO = "pesos"` | 02 | 0 | 13 de 13 | ✅ idéntica (0) |
| **Transaccional**: 94 mil filas con fecha diaria y filas idénticas legítimas | 02 | 0 | 13 de 13 | ✅ idéntica (4·10⁻¹⁰): las filas idénticas se conservan y todo se agrega |
| Red que vende **10 veces más** (perfil completo) | 02–08 | 0 | 96 de 96 | ✅ venta madura × 10 · parámetros iguales (diferencia 0,00002; solo cambia κ) · **Top 20 idéntico** (mismas manzanas, formatos y orden; venta × 10) |
| Red que vende **20 veces menos** (perfil completo) | 02–08 | 0 | 96 de 96 | ✅ venta madura ÷ 20 · parámetros iguales (0,00002) · **Top 20 idéntico** (venta ÷ 20) |
| **Historia corta**: solo 18 meses | 02–08 | 0 | 91 de 95 | las 4 que fallan son esperadas (serie < 24 meses; mes faltante, pico y quiebre simulados que quedan fuera de los 18 meses). El informe avisa que no se puede medir el crecimiento anual; "sede nueva" 14,4% |

**Antes de recibir datos de la clínica:**

| Escenario | Notebooks | Errores | Verificaciones | Comparación con la corrida base |
|---|---|---|---|---|
| Carpeta de trabajo **vacía**, sin ventas, sin hoja de sedes y sin RUT | 01, 03, 04b | 0 | 38 de 38 | ✅ no se usó ningún dato de la clínica · **mismas zonas de influencia** que la corrida con todos los datos (diferencia 0) |

**Coordenadas en formatos mezclados:**

| Escenario | Notebooks | Errores | Verificaciones | Comparación con la corrida base |
|---|---|---|---|---|
| Personas, empresas, BBRR, maestro de sedes y competencia con coordenadas en 8 formatos mezclados (punto, coma, sin punto decimal, miles de Excel, grados/minutos/segundos, sin signo, lat/lon intercambiadas, signo tipográfico) | 01–04 | 0 | 58 de 58 | ✅ mismos registros en personas (275.968), empresas (135.810) y BBRR (200.000), coordenadas iguales (diferencia ≤ 0,0000005°) · sedes en el mismo lugar · mismas 45.355 manzanas con la misma población y trabajadores · **mismo entorno de las 14 sedes** |

En el escenario de origen por zona, con datos reales el asistente se detiene antes de calcular y pide `RUT_PACIENTES = "sin_rut"` (el archivo no trae RUT); en la prueba se simula que el equipo ya lo cambió, igual que `MAPA_SEDES` en el mínimo.

**Lección del escenario mínimo:** sin la hoja de sedes no hay m², y el modelo no puede separar el efecto del tamaño (γ queda en 0): lo confunde con la distancia (β de la clínica sale 0,18 en vez de 0,055). Por eso el asistente marca la hoja de sedes, y en particular la columna de tamaño, como lo más importante después de las ventas. Sin hoja de sedes, además, los códigos de la clínica no se pueden emparejar por nombre: con datos reales el notebook 02 se detiene y pide `MAPA_SEDES` (en la prueba se simuló que el equipo lo completó).

**Lección del escenario sin origen:** el modelo sigue funcionando, pero el peso de los trabajadores (λ) queda mal identificado. El origen de los pacientes, aunque sea por zona censal, es lo que permite separarlo.

## Antes de que la clínica mande sus datos: zonas de influencia preliminares (notebook 04b)

**Ya se pueden armar las zonas de influencia de cada sede, sin RUT ni ventas**, con toda la data disponible:

| Insumo | De dónde sale |
|---|---|
| Demanda de cada manzana: gasto en salud por GSE + trabajadores | censo, personas y empresas Equifax (notebooks 01 y 03) |
| Competencia ponderada por segmento | levantamiento propio + POIs de salud Equifax sin duplicados (notebook 03) |
| Tiempos reales por la red vial, punta y fuera de punta | grafo vial (el 04b lo arma si el 04 aún no corrió) |
| Sedes | base de puntos del levantamiento (`insumos/sucursales_red_alemana.csv`), con la misma regla del 02 para decidir cuáles entran |

**Cómo correrlo en el PC de trabajo, hoy:**

1. En `config_estudio.py`: `MODO = "real"` y `RUT_PACIENTES` (la decisión ya se puede tomar: si la clínica mandará el RUT tal cual, `"en_claro"`; el archivo no hace falta todavía y así no hay que repetir la ingesta cuando llegue).
2. Correr **01 → 03 → 04b**. El 02 no hace falta (necesita las ventas); el 03 usa las sedes del maestro para sus mapas mientras no exista la hoja de sedes de la clínica.
3. Resultado en `salidas/preliminar/`: `Zonas_Influencia_Preliminares_CAS.xlsx`, `Zonas_Influencia_Preliminares_CAS.gpkg` (para QGIS o Mapdrive®) y el mapa `salidas/mapas/04b_zonas_influencia_preliminares.html`.

**Qué entrega:**

| Resultado | Definición |
|---|---|
| Zona primaria y secundaria de cada sede (punta y fuera de punta) | manzanas más cercanas (en minutos) que reúnen el 60% y hasta el 80% de la demanda que captaría la sede — **la misma regla que las zonas reales del notebook 05** |
| t50, t60 y t80 de cada sede | minutos que reúnen el 50, 60 y 80% de esa demanda |
| Zona de influencia total de la red | manzanas más cercanas a alguna sede que reúnen el 60% / 80% de la demanda de toda la red |
| Territorio de cada sede | manzanas donde es la clínica, el centro médico o la toma de muestras de la red que más captaría (reparte el área entre las sedes de cada formato) y cuánto de su demanda viene de ahí |
| Sensibilidad | las zonas si la gente viaja más (β × 0,75) o menos (β × 1,25) de lo supuesto |
| Indicadores y conclusiones | tema "Zonas de influencia modeladas" (siempre con la advertencia de que son preliminares) |

**Cómo se calcula:** el mismo modelo de Huff con competencia del notebook 06, con **parámetros de referencia** en vez de calibrados (todos en `config_estudio.py` y en la hoja Supuestos del Excel): β por formato (`PARAMETROS["modelo"]["beta_prior"]`), atractivo por formato (`PARAMETROS["influencia"]["atractivo_formato"]`), peso de los trabajadores y de cada GSE. Tiempos con Dijkstra en paralelo; las cuotas de todas las manzanas y sedes son operaciones de matrices; los contornos se dibujan en paralelo (en la simulación: 0,5 s el modelo, 3 s los contornos; con la red ya armada el notebook completo toma ~30 s).

**Qué pasa cuando lleguen los RUT:** el notebook 05 compara automáticamente las zonas preliminares con las reales (qué parte de la venta real de cada sede cae dentro de su zona preliminar, donde 80% es el calce perfecto, y el t80 real frente al modelado) y lo informa como conclusión. Con las ventas, el notebook 06 calibra los parámetros.

**Prueba (datos simulados):**

- Escenario "sin datos de la clínica": carpeta de trabajo **vacía**, sin ventas, sin hoja de sedes y sin RUT. 01 → 03 → 04b corren completos (14/14, 16/16 y 8/8 verificaciones) y dan **exactamente las mismas zonas** que la corrida con todos los datos (diferencia 0).
- Comparación con las zonas reales (con RUT): la zona preliminar contiene entre 76% y 82% de la venta real de cada sede (mediana 79%; el calce perfecto es 80%). El t80 modelado queda a ±1,2 min del real.
- **Ojo:** en la simulación los parámetros de referencia están cerca de los verdaderos. Con datos reales el calce depende de qué tan buenos sean esos supuestos. Por eso se informa el rango con β ± 25%: el t80 de una sede se mueve unos 3 min.

## Uso en el PC de trabajo (Vertex AI Workbench / Jupyter)

1. Sube y descomprime la carpeta. Debe quedar `config_estudio.py` al lado de los notebooks.
2. Revisa los requisitos (casi todos ya están en la imagen de Vertex):
   ```
   pip install pandas numpy scipy scikit-learn geopandas shapely pyogrio pyarrow osmnx networkx openpyxl matplotlib joblib gcsfs
   ```
3. Corre `python revisar_insumos.py real`: lista lo que falta, con la línea exacta a escribir.
4. En `config_estudio.py`:
   - `MODO = "real"`.
   - `RUT_PACIENTES`: cómo enviará la clínica el RUT (`"en_claro"`, `"seudonimizado"` o `"sin_rut"`). Se decide antes del notebook 01, porque personas y empresas se seudonimizan con la misma sal que los pacientes.
   - `RUTAS_REALES["grafos"]`: la carpeta `.../prioritarias/graph` (ruta completa si los notebooks están en otra carpeta).
   - `GRAFOS_VIALES = "todos"` (así viene): se usan todos los `.graphml` de la carpeta; cada uno se carga, se recorta al área de estudio y se descarta si no la toca. No hay que elegir nada. Para ir más rápido, se puede escribir solo los del área por su nombre exacto, p. ej. `["CL-RM_metropolitana_de_santiago.graphml"]`.
   - `RUT_CON_DV = "auto"`: se detecta si el RUT de los pacientes trae dígito verificador. Solo hay que fijarlo (`True`/`False`) si el notebook 05 lo pide.
   - `UNIDAD_MONTO = "auto"`: se reconoce si las ventas vienen en pesos, miles, millones o UF. Solo hay que fijarla si el asistente lo pide (con `"uf"`, además `VALOR_UF`).
   - Las 6 rutas Equifax ya vienen con el bucket y los nombres de las capturas, igual que las columnas originales en `COLUMNAS`.
   - Cuando llegue la data de la clínica, completa:
     - `ventas_cliente`
     - `sedes_cliente`
     - `origen_pacientes`
     - `eventos_cliente`
     - `sitios_propuestos`

     No hace falta saber el formato: el lector reconoce las columnas por sinónimos (`COLUMNAS_CLIENTE`) y avisa lo que no encuentra.
   - `origen_pacientes`: el archivo de atenciones con RUT (una fila por atención o por paciente-año). Acepta RUT con o sin puntos, guion y dígito verificador.
   - La sal del RUT nunca se escribe en el código:
     - con `RUT_PACIENTES = "en_claro"`, el estudio crea una sal secreta al azar en `trabajo/.sal_proyecto` y la reutiliza (o usa la de la variable de entorno `GEOVENTAS_SAL_RUT`, si la defines);
     - con `"seudonimizado"`, define `GEOVENTAS_SAL_RUT` con la sal que usó la clínica. Sin ella el notebook se detiene;
     - si la sal cambia después de la ingesta, el notebook 05 lo detecta (huella de la sal) y pide volver a correr el 01 y el 03.
   - Si tienen una capa de áreas verdes (parques, plazas), ponla en `RUTAS_REALES["areas_verdes"]`. Es opcional: sin ella, el filtro usa la columna `USO_SUELO` del censo.
   - `PARAMETROS["computo"]["n_jobs"]`: núcleos en paralelo. `-1` usa todos menos uno.
     - Antes de cada cálculo en paralelo, el estudio mide la memoria libre y usa solo los procesos que caben (~1,2 GB cada uno).
     - Si igual falta memoria, reintenta con la mitad de procesos en vez de caerse.
     - Al terminar cada cálculo cierra los procesos auxiliares, para que no queden ocupando memoria entre celdas.
     - Por eso no hace falta ajustarlo a mano en una VM chica: solo correrá más lento.
     - Igual conviene cerrar los programas pesados (navegador con muchas pestañas, bases de datos locales) antes de correr el 04, el 06 y el 07.
     - Memoria mínima: cargar el grafo vial de la RM con OSMnx ocupa ~3,7 GB. Conviene tener ≥ 10 GB libres. El estudio arma de inmediato una red compacta y libera el grafo apenas termina la verificación del notebook 04.
5. Corre los notebooks 01 → 08 en orden (*Run All* en cada uno). Si algo falta, la primera celda lo dice.

Tiempo aproximado con la RM completa en una VM de 8 núcleos:

- 01: 10–25 min la primera vez, porque descarga desde GCS.
- 04: 3–6 min.
- 06: 3–8 min, por el bootstrap y las validaciones en paralelo sobre ~50 mil manzanas. Para revisar rápido, `PERFIL = "rapido"`.
- 07: 3–5 min.
- El resto: 1–3 min cada uno.

## Qué data de la clínica espera (y qué pasa si no viene)

| Dato | Formato esperado (flexible) | Si no viene |
|---|---|---|
| Ventas 5 años | sede, mes, línea, previsión, atenciones, pacientes, monto. Acepta un mes por columna | obligatorio |
| Sedes | código, nombre, formato, dirección, apertura, cierre, m² | se usan los códigos de ventas y el maestro levantado |
| Origen de pacientes (preferido) | RUT del paciente, sede, fecha, línea, previsión, monto. Una fila por atención o por paciente-año | ver las dos filas siguientes |
| Origen por zona (alternativa) | zona censal, comuna o manzana × sede, con pacientes o monto | se usa si no hay RUT |
| Origen con lat/lon (alternativa) | coordenadas del domicilio × sede | se usa si no hay RUT ni zona |
| Sin origen | — | el modelo se calibra con la venta total por sede y se apoya en valores de referencia |
| Eventos | sede, desde, hasta, tipo, descripción | los quiebres se detectan solos y quedan marcados para revisar |
| Sitios propuestos | nombre, dirección (o lat/lon) | se omite esa sección |

**Recomendación para la clínica:** que envíe el RUT de cada atención de los 5 años (con sede, fecha, línea, previsión y monto). Con eso el estudio ubica a cada paciente en su manzana y calibra el modelo manzana por manzana, que es lo más preciso. Si no puede, que mande el origen por zona censal y por año.

## Datos sensibles

- De personas y BBRR nunca se leen nombres ni direcciones.
- El RUT de los pacientes se lleva a su forma canónica y se transforma de inmediato en un código (SHA-256 + sal secreta). El RUT en claro no se guarda en ningún archivo ni se muestra en los notebooks (los formatos se informan como conteos). Las bases `per` y `emp` se codifican con la misma sal, y el cruce se hace por ese código.
- Los mapas muestran solo manzanas con 5 o más pacientes; las demás no se pintan (`min_pacientes_publicacion`).
- Las capas GIS y el Excel no traen conteos de pacientes por manzana: el origen se entrega como áreas de influencia por sede.
- No se piden diagnósticos (FRF 2.6).

## Unidad de análisis: la manzana del censo

Todo el estudio trabaja sobre los **polígonos de manzana** del censo (`SD06_SOCIODEMOGRAPHIC_BLOCK`), sin grillas ni agregaciones:

- la demanda;
- los tiempos de viaje y la competencia;
- la calibración del modelo y la venta estimada;
- los candidatos a sede nueva;
- los mapas y las capas GIS.

**Filtros previos (notebook 03).** Antes de calcular se descartan las manzanas que no aportan demanda. Cada descarte queda guardado con su motivo en `manzanas_descartadas.parquet` y en un mapa:

| Motivo | Regla (editable en `PARAMETROS["filtro_manzanas"]`) |
|---|---|
| Vacía | sin población, sin trabajadores y sin POIs |
| Uso excluido | `USO_SUELO` es área verde, parque, plaza, cementerio, aeropuerto, río, cerro, bien nacional de uso público o sitio eriazo, y la manzana tiene 0 habitantes |
| Área verde | con la capa de áreas verdes: ≥ 80% de la superficie es área verde y la manzana tiene ≤ 10 habitantes |

**Asignación de puntos a manzanas.** Cada persona, empresa, POI o propiedad se asigna a la manzana que lo contiene. Si cae fuera de toda manzana (en la calle), se asigna a la más cercana:

- personas y calles: hasta 60 m;
- empresas, POIs y propiedades: hasta 300 m (predios grandes, zonas industriales).

Si un punto cae en una manzana descartada, pasa a la manzana útil más cercana. Así no se pierde nada.

**Tiempos de viaje.** Cada manzana se conecta al nodo de la red más cercano a su punto interior. Muchas manzanas comparten nodo, así que el costo depende de los nodos y no de las ~50 mil manzanas.

**Competencia exacta por manzana (notebook 04).** El modelo necesita, para cada manzana, Σ peso × e^(−β·minutos) sobre los ~2 mil competidores. Guardar todos los pares manzana–competidor pesaría decenas de millones de filas. Por eso la suma se calcula una vez, con el tiempo exacto de cada manzana a cada competidor, para 48 valores de β. Durante el ajuste se interpola con un polinomio de Hermite:

- el error es menor a 0,01% en la suma y a 0,1% en su derivada (el notebook 04 lo verifica contra el cálculo directo en 400 manzanas al azar);
- el gradiente usa la derivada del mismo polinomio, así que el ajuste es consistente;
- ocupa ~50 MB.

**Manzanas candidatas (notebook 04).** Una manzana es candidata a sede nueva si cumple dos condiciones:

- está en zona urbana o en un polo laboral: en su entorno (≤ 600 m) viven ≥ 1.700 personas o trabajan ≥ 1.500;
- da a una vía terciaria o superior: hay un nodo de esa vía a ≤ 150 m. Ese nodo es el sitio desde el que se miden los tiempos.

Se priorizan por la demanda objetivo y los trabajadores de su entorno. Entre dos candidatas a menos de 250 m queda la de mayor prioridad. Se evalúan las 2.500 de mayor prioridad.

## Mapas de manzanas

Los mapas están pensados para mostrarlos al cliente y para que los entienda cualquier persona, sin saber de estadística ni de mapas:

- **Lenguaje simple.** Por ejemplo:
  - "Personas de nivel socioeconómico alto (AB, C1a y C1b)" en vez de "pob_objetivo";
  - "Venta nueva si se abre un centro médico aquí" en vez de "venta neta";
  - "Mucha demanda y LEJOS (más de 15 min): oportunidad" en vez de "brecha".
- **Leyendas claras.** Tienen 5 niveles con nombre: "Muy alto" … "Muy bajo", o "Muy cerca" … "Muy lejos" para los tiempos. Los rangos van redondeados, con la unidad escrita ("personas por manzana", "$ millones al mes", "minutos en auto, hora punta") y con cuántas manzanas hay en cada nivel.
- **Botón "¿Cómo leer este mapa?"** en cada mapa, con 3 a 5 frases que explican qué se ve.
- **Nombres reales de las sedes** (por ejemplo "Clínica Alemana Vitacura (campus principal)" o "Toma de Muestras El Golf"), con un ícono de cruz coloreado por formato. El nombre aparece escrito al acercarse.
- **Ubicaciones recomendadas** como círculos con su número de orden de apertura. Los sitios que propone la clínica van como rombos (P1, P2…).
- **Fichas tipo tarjeta** al hacer clic, con valores en pesos, minutos o personas. La de una ubicación recomendada muestra:
  - la venta nueva para la red;
  - el rango conservador–optimista;
  - lo que les quita a las sedes actuales, y a cuáles.
- **Nombres de calles y comunas** sobre las manzanas, para ubicarse. Fondos a elegir: mapa gris, mapa de calles o satélite.
- **Panel "Qué mostrar en el mapa":** indicador, sede (filtra isócronas y zonas reales), comuna e intensidad del color. Botón ⟲ para volver a la vista inicial.
- **Al pie:** las fuentes de los datos y, cuando corresponde, el aviso de privacidad. Si los datos son simulados, se avisa con una etiqueta naranja.

**Técnica:**

- La geometría de las ~50 mil manzanas va cuantizada (~1 m), en diferencias y comprimida dentro del propio HTML. Cada mapa pesa entre 0,5 y 2 MB y no necesita servidor.
- Se dibuja en un canvas propio, por nivel de color, así que se mueve fluido.
- La manzana bajo el mouse se encuentra con un índice espacial.

## Coordenadas en cualquier formato (todas las bases)

Las coordenadas llegan escritas de muchas formas: el Excel en español usa coma decimal, algunos sistemas guardan enteros sin punto decimal y otros exportan grados, minutos y segundos. `geoventas/coordenadas.py` las lee todas igual, vectorizado, en **todas** las lecturas: personas, empresas y BBRR (por bloques), POIs (si la geometría viene vacía, desde `LON_X`/`LAT_Y`), maestro de sedes, universo de competencia, hoja de sedes, origen con coordenadas y sitios propuestos.

| Cómo viene | Ejemplo | Se lee como |
|---|---|---|
| decimal con punto o con coma | `-33.4372` · `-33,4372` · `−33,4372` (signo tipográfico) | -33,4372 |
| sin punto decimal | `-334372000` · `-3,34372E+08` | -33,4372 (la potencia de 10 que la deja en Chile) |
| con separadores de miles de Excel | `-33.437.200` | -33,4372 |
| grados, minutos y segundos | `33°26'14,5"S` · `33 26 14.5 S` · `33°26.24'S` | -33,4374 |
| sin signo menos | `33.4372` | -33,4372 |
| latitud y longitud intercambiadas en la fila | lat `-70.57`, lon `-33.39` | se intercambian |
| vacío, 0, texto, fuera del país | `""`, `0`, `s/i`, `-3.34` | se descarta y se cuenta |

**Por qué es seguro corregir escala, signo e intercambio en Chile:** la latitud va de −56,6 a −17,4 y la longitud de −109,6 a −66,3 (con Isla de Pascua). En escala logarítmica esos rangos no se tocan, así que un número cabe a lo más en **una** de las dos coordenadas y con **una** sola potencia de 10: cada corrección es única y no se adivina nada. Los límites se cambian en `PARAMETROS["estudio"]["limites_coordenadas"]`.

El notebook 01 muestra, por base, cuántas coordenadas venían con coma, sin punto, en grados/minutos/segundos, sin signo o intercambiadas, y verifica que las inválidas sean ≤ 1% de las que traen dato. Rendimiento: 2 millones de coordenadas en texto en 4,7 s (0,9 s si ya son números).

Prueba (escenario "coordenadas mixtas"): personas, empresas, BBRR, maestro de sedes y competencia reescritos con 8 formatos mezclados (40% punto, 30% coma, 8% sin punto decimal, 5% miles de Excel, 5% grados/minutos/segundos, 5% sin signo, 4% intercambiadas, 3% signo tipográfico) dan **los mismos registros, las mismas coordenadas (diferencia ≤ 0,0000005°) y el mismo entorno de cada sede** que la corrida base.

## Análisis de entorno de cada sede (notebook 04)

Usa la **base de puntos del levantamiento** (`RUTAS["maestro_sedes"]`, `insumos/sucursales_red_alemana.csv`): todas las sedes oficiales de la red, no solo las del modelo. Las que están fuera del área de estudio (Temuco, Osorno, Valdivia, Maitencillo) se informan; para analizarlas basta agregar su región en `id_regiones` y su grafo en `GRAFOS_VIALES`.

Para cada sede, cada modo (`PARAMETROS["entorno"]["modos"]`: auto **fuera de punta** y en **hora punta**; se puede agregar a pie y transporte público) y cada corte (**5, 10, 15, 20 y 30 minutos**), se mide qué hay en la zona desde la que se llega a la sede por las calles reales:

| Tema | Indicadores |
|---|---|
| Personas | población, hogares, segmento objetivo (AB, C1a, C1b) y su %, mezcla de los 7 GSE, % menores de 18 y 60+, superficie y densidad |
| Poder de compra | gasto en salud al mes (total, del segmento y por persona), renta media del hogar, avalúo medio de la vivienda |
| Actividad | trabajadores, trabajadores por habitante, empresas, empresas de salud |
| Generadores de flujo | estaciones de metro, paraderos, malls, supermercados, educación, oficinas, restaurantes, gimnasios, lugares de salud; viviendas, locales comerciales, oficinas y propiedades de salud (BBRR); calles y vías principales |
| Competencia | clínicas, centros médicos y laboratorios del modelo, competidores por 10.000 personas del segmento, oferta de contexto (dental, kine, farmacias), **los 5 competidores más cercanos en minutos** |
| Red propia | otras sedes de la red a pocos minutos y **traslape**: qué parte del segmento de su zona inmediata (5 min) también está a 5 min de otra sede (los edificios de un mismo recinto, a menos de 500 m, no cuentan) |
| Congestión | segmento objetivo y superficie que **pierde cada sede en hora punta** frente a fuera de punta, y en cuántos minutos reúne 100.000 personas del segmento en cada hora |
| Tipo de entorno | residencial de alto ingreso, polo laboral, comercial, urbano denso, baja densidad (reglas a la vista en `entorno._tipologia`, a 10 min en punta) |

**Cómo se calcula (vectorizado y en paralelo):** tiempos manzana → sede con Dijkstra repartido entre los núcleos (una matriz manzanas × sedes por modo) y, para todos los cortes, una multiplicación de matrices `(T ≤ m)ᵀ · V` que da las sumas de las ~70 variables de todas las sedes a la vez. Los polígonos de las isócronas se dibujan en paralelo solo para el mapa (se reutilizan los de las sedes del modelo). En la simulación: 14 sedes × 2 modos × 5 cortes en 5,5 s, más 10 s de polígonos. La población por matrices coincide con la de los polígonos (diferencia mediana 2%).

**Dónde queda:** en el notebook 04 (tabla, resumen en palabras de cada sede, curvas de público objetivo por minuto en punta y fuera de punta, mapa `04_entorno_sedes.html` con selector de sede y hora, conclusiones), en `trabajo/entorno_sedes.csv` y `entorno_sedes_detalle.csv`, y en los entregables: hojas **Entorno sedes** y **Entorno detalle** del Excel, capa `11_isocronas_entorno_sedes` del GeoPackage, gráfico y conclusiones del tema "Entorno de las sedes" en el informe ejecutivo.

Ejemplo de resumen en palabras (datos simulados): *"Toma de Muestras Nueva Providencia. Entorno polo laboral y residencial de alto ingreso. En 15 min en auto en hora punta llegan 678.206 personas del segmento objetivo, similar a una sede típica de su formato. Fuera de punta llegan 1.065.018: la congestión le quita 36%. … En su zona inmediata (5 min) comparte 76% del segmento objetivo con otras sedes de la red, sobre todo con Toma de Muestras El Golf (46%)."*

## Ventas de cualquier tamaño y formato (notebook 02 y modelo)

La data real puede venir muy distinta de la simulada: montos en otra unidad, una fila por atención en vez de una por mes, una red mucho más grande o más chica. El código está hecho para eso:

| Situación | Qué hace el código | Cómo se comprobó |
|---|---|---|
| Montos en **miles, millones o UF** | `cliente.unidad_monto`: (1) `UNIDAD_MONTO` si no es `"auto"`; (2) el nombre de la columna (`monto_clp`, `venta_mm`, `venta_miles`, `monto_uf`, `M$`, `MM$`); (3) la magnitud: la venta mediana de una sede en un mes debe quedar entre $3 millones y $300.000 millones y el ticket por atención entre $2 mil y $10 millones. Si una sola unidad cumple, se usa; si ninguna o varias, el notebook **se detiene y la pide** | escenarios "en miles", "en millones" y "unidad ambigua" |
| Montos en UF | se multiplican por `VALOR_UF` y no se deflactan (la UF ya se reajusta con la inflación) | — |
| Tabla **transaccional** | si más del 5% de las combinaciones sede × mes × línea × previsión tiene varias filas, la tabla es transaccional: las filas idénticas **no** se borran (en una tabla agregada sí, porque son errores de carga) y todo se suma. Fechas diarias: cada fecha distinta se interpreta una sola vez (2 millones de fechas en 0,2 s). Archivos de más de 150 MB: se leen por bloques de 2 millones de filas, solo con las columnas reconocidas | escenario "transaccional": 94 mil filas → misma venta madura que la tabla agregada |
| Red **mucho más grande o más chica** | la dispersión del modelo (φ) tiene la unidad de la venta y no tiene piso fijo: la verosimilitud es la misma con ventas × 1.000 o × 0,000001, así que β, pesos GSE, λ, competencia y γ no cambian (solo κ). Los umbrales de viabilidad son relativos a la red actual, y todos los indicadores son %, razones o minutos | notebook 06, sección 8 (en cada corrida) y escenarios "× 10" y "÷ 20": mismo Top 20 |
| Números con separadores distintos | `1.234.567` y `1234,5` (chilena) o `1,234,567` y `0.4567` (anglosajona): se decide para la columna completa. `(1.234)` es negativo | prueba unitaria |
| Control final de unidades | la venta de la red debe ser entre 0,1% y 60% del gasto en salud de toda el área (notebook 05). Fuera de eso, los montos o el gasto del censo vienen en otra unidad | verificación del notebook 05 |

**Corrección que salió de esta revisión:** antes la dispersión φ tenía un piso de 1. Con ventas en pesos no importaba (φ ≈ 370.000), pero con ventas en millones φ habría sido 0,37 → 1, y los datos habrían pesado casi 3 veces menos frente a los supuestos iniciales del modelo. Ahora el ajuste da los mismos parámetros en cualquier escala (diferencia ≤ 0,00003).

**Única ambigüedad que no se puede resolver sola:** una columna cuyos valores tienen todos exactamente 3 decimales con coma (`945,804`) puede ser 945,804 o 945.804. La coma se interpreta como separador de miles, y si eso deja la venta fuera de rango lo detecta el control de unidades del notebook 05.

## Indicadores clave y conclusiones que se adaptan a los datos

Cada fase termina con una tabla de **indicadores clave** (`geoventas/metricas.py`) y con **conclusiones en palabras** (`geoventas/conclusiones.py`) que cambian según los valores: el mismo código escribe "la red crece con fuerza" o "la venta cae en términos reales", "modelo confiable" o "usar el ranking solo como orden relativo", "canibalización baja" o "alta", con su recomendación ("qué hacer"). Lo que no se puede medir con la data entregada no aparece o se reemplaza por la advertencia que corresponde.

| Tema | Notebook | Indicadores | Ejemplos de conclusiones que cambian con los datos |
|---|---|---|---|
| Ventas | 02 | venta 12 meses, crecimiento real total y **a red constante**, atenciones vs ticket real (volumen o precio), CAGR, estacionalidad (meses fuerte y débil), volatilidad, concentración (sede principal, top 3, número efectivo de sedes), línea y previsión principales, **venta por m²** por formato, meses atípicos, faltantes, quiebres (y si hay un **quiebre común a la red**), sedes en maduración | crece con fuerza / crece / estable / cae · la red depende de una sede / venta repartida · estacionalidad marcada / moderada / casi nula · alta exposición a una previsión · una sede vende 4,9 veces menos por m² que otra del mismo formato · series consistentes / meses que confirmar |
| Mercado | 05 | población y segmento objetivo, gasto en salud, **venta de la red como % del gasto** (y control de unidades), cobertura a 15 min, brechas y sus comunas, competidores por 10.000 personas del segmento | brecha grande (oportunidad) / acotada / la red ya cubre casi todo · cifra fuera de rango → revisar unidades |
| Entorno | 04 | sedes analizadas y fuera del área, segmento a 15 min (mediana, mayor y menor), pérdida en hora punta (mediana y máxima), minutos para reunir la meta del segmento, competencia, traslape entre sedes, sedes con metro, tipos de entorno | la congestión quita mucho / poco · sedes que se pisan en su zona inmediata / red sin traslape · qué sedes quedan fuera del área y qué agregar para analizarlas |
| Pacientes | 05 | cruce del RUT, pacientes y atenciones, alcance t80 por formato, venta a ≤ 15 min, sede más local y más regional, retención, una sola atención, multisede, GSE más y menos afín, comunas que reúnen la mitad de la venta | cruce bajo (alerta) / bueno · sustitución entre sedes · retención baja / buena · sin origen → qué se pierde |
| Modelo | 06 | error "sede nueva", % dentro de ±25%, sesgo, sede peor explicada, σ de sede, ajuste dentro y fuera de muestra, Huff vs machine learning, vida media y pérdida con 5 min más por formato, demanda flotante, atractivo frente a la competencia por formato, pesos GSE, efecto del tamaño, **confiabilidad alta / media / baja** | la recomendación de uso cambia con la confiabilidad (P50 para priorizar / decidir con P10 y validar en terreno / solo orden relativo) · tiende a sobreestimar o subestimar · le falta una variable (si el ML gana) |
| Plan | 07 | venta nueva y crecimiento de la red, canibalización, P10 y P90 del plan, amplitud de los escenarios, primer año, mejor ubicación, concentración en las 5 mejores, comunas, venta de un sitio nuevo frente a una sede actual, **cobertura del segmento objetivo antes y después del plan**, candidatas viables, sitios propuestos viables, macrozonas | canibalización baja / moderada / alta · escenarios amplios → decidir con P10 · ningún sitio viable → qué ajustar |

Dónde quedan: en cada notebook (tarjetas de colores ✅ fortaleza · ⚠️ alerta · 💡 oportunidad · ℹ️ dato), en `trabajo/metricas_*.json`, y en los entregables del notebook 08: hojas **Conclusiones** e **Indicadores** del Excel (las primeras después de LEEME), la portada y la sección "Conclusiones del estudio" del **informe ejecutivo PDF** (reemplazan a los textos fijos), una sección del anexo metodológico y `Conclusiones_CAS.md`.

## Competencia: levantamiento + POIs de Equifax sin duplicados (notebook 03)

El universo de competencia parte del **levantamiento propio** (`insumos/pois_salud_nacional.csv`: DEIS, Superintendencia, OSM, Farmanet, Overture y webs oficiales), que tiene **prioridad** y se conserva completo. A eso se suman los **POIs de salud de Equifax** (`PI01_POI`, filtrados por `CAT1_DES`/`CAT2_DES`/`CAT3_DES`, sin veterinarias) que **no** estén ya. Un mismo lugar suele aparecer en las dos fuentes con otro nombre y otras coordenadas, así que cada POI de Equifax se compara con los lugares del levantamiento a ≤ 300 m (`geoventas/unificacion_pois.py`):

| Qué se mira | Cómo |
|---|---|
| **Nombre** | sin tildes, mayúsculas ni signos; abreviaturas expandidas (C.M., Ctro., Lab., Dr., Sta.); sin SpA, Ltda., S.A. ni "Inversiones". Parecido de trigramas de letras (tolera errores de tipeo), solo de las palabras distintivas, y "un nombre contiene al otro". Se comparan todos los alias: nombre, otros nombres y marca del levantamiento; `TRADENAME`, `BRAND` y `CHAIN` de Equifax |
| **Palabras genéricas** | "centro", "médico", "clínica", "dental", "laboratorio", "sucursal", "CESFAM", "SAPU"… no bastan para unir: "Clínica Dental Pizarro" ≠ "Clínica Dental Sense" |
| **Distancia** | el parecido mínimo del nombre sube de 0,50 (a ≤ 30 m) a 0,90 (a 300 m) |
| **Dirección** | misma calle y número rebaja el mínimo en 0,20 |
| **Tipo de lugar** | farmacia, dental, óptica, laboratorio, centro médico, clínica, kine… Tipos incompatibles nunca se unen; afines (centro médico ↔ laboratorio) exigen más |
| **Cadenas y topónimos** | un nombre presente en ≥ 2 lugares del mismo tipo ("Cruz Verde", "Integramédica", "Dental Vitacura") solo une a ≤ 120 m o con la misma dirección; y si cada nombre tiene una parte propia distinta ("Cruz Verde Los Leones" vs "Cruz Verde Providencia") son dos sucursales |
| **Duplicados dentro de Equifax** | los POIs nuevos se comparan entre sí con la misma regla y queda el registro más completo y reciente |

Entre varios candidatos gana el de nombre más parecido (no el más cercano). Cada decisión queda con su motivo en `salidas/competencia/unificacion_pois_decisiones.csv`, y los casos cerca del umbral (o con la misma dirección y tipo pero otro nombre, típicamente otra razón social) en `unificacion_pois_revisar.csv`, para revisarlos a mano si se quiere. Los umbrales están en `PARAMETROS["competencia"]["unificacion"]`; los tipos y las categorías de salud de PI01, en `PARAMETROS["competencia"]["pois_equifax"]`.

## Bases Equifax: estructura verificada

`geoventas/esquemas.py` tiene la lista exacta de columnas (nombre y orden) de las 6 bases del bucket, transcrita de las bases reales, y los 16 nombres de archivo de los grafos de `prioritarias/graph`. Con eso:

- se comprobó que **todas** las columnas que usa `config_estudio.COLUMNAS` existen en las bases reales (0 diferencias);
- la simulación genera archivos idénticos en estructura (el notebook 00 se detiene si no);
- el asistente avisa si una base del bucket cambia (por ejemplo, si `BC08_STREET` trae `START_LEFT2` en vez de `START_LEF2`).

| Base | Archivo | Filas | Columnas | Detalles que importan |
|---|---|---|---|---|
| censo | `Cartografia/CENSO_2026/SD06_SOCIODEMOGRAPHIC_BLOCK_2026.gpkg` | 231.036 | 153 | `COD_APD3` es texto con cero a la izquierda (`05101`) |
| pois | `Cartografia/POIS/PI01_POI.gpkg` | 146.345 | 28 | `CAT1_DES`/`CAT2_DES`/`CAT3_DES` sin tildes; `BRAND` y `CHAIN` se usan como alias del nombre |
| bbrr | `2026/BBRR_1_SEMESTRE_2026/MKTS_BBRR_2026_01.txt` (`|`) | 9.528.541 | 23 | no se leen `RUTID` ni nombres de propietarios |
| street | `Cartografia/BC08_STREET.gpkg` | 712.668 | 33 | numeración secundaria `START_LEF2`/`END_LEF2` (10 caracteres) |
| per | `DATOS_CHILE/2026_BASE_PERSONAS/personas_20260825_tramos_sociedades.parquet` | 17.239.671 | 72 | `RUTID` texto de 10 caracteres con ceros (`0216897560`); fallecidos por `FECHA_DEFUNCION` o `DEFUNCION` |
| emp | `2026/REZEPKA_BODEGAS/BD_EMPRESAS_ACTIVAS_3007.txt` (`|`) | 787.826 | 31 | `RUTID` sin ceros (`784372936`); se lee como texto para no perder ceros |

## RUT de pacientes: cómo se cruza (notebook 05)

1. **Lectura por bloques.** El archivo de atenciones se lee en bloques de 2 millones de filas, así que sirve aunque sean 5 años completos.
2. **Forma canónica y validación.** Cualquier escritura del RUT se lleva a una sola forma: cuerpo + dígito verificador, sin puntos, guion, espacios ni ceros a la izquierda, K mayúscula (`geoventas/rut.py`):

   | Cómo viene | Forma canónica |
   |---|---|
   | `0190270254` · `190270254` · `19027025-4` · `19.027.025-4` · ` 19027025 - 4 ` | `190270254` |
   | `190270254.0` o `1,90270254E+08` (número de Excel) | `190270254` |
   | `RUTID` de personas `0216897560` · de empresas `784372936` | `216897560` · `784372936` |
   | solo el cuerpo `19027025` · `19.027.025` (sin dígito verificador) | `190270254` (el dígito se calcula) |

   Si trae o no dígito verificador se decide **una vez para toda la columna**: con dígito verificador, más del 80% de los RUT lo cumple (los mal digitados son pocos); sin él, solo ~9% "calza" por azar. Entre medio la columna es ambigua y el notebook pide `RUT_CON_DV`. Los RUT con dígito inválido se cuentan; un RUT vacío nunca se cruza con otro vacío. Si la clínica seudonimiza por su cuenta, debe aplicar `sha256(SAL + forma canónica)`.
3. **Código.** `sha256(sal + RUT)`. El RUT en claro se descarta en ese mismo paso.
4. **Cruce:**
   - RUT < 50 millones → base de **personas**: domicilio, GSE, edad y sexo. El paciente queda en su manzana.
   - RUT ≥ 50 millones → base de **empresas**: son convenios. Se reportan aparte y no entran al modelo de domicilio.
   - Sin cruce o fuera del área de estudio → se cuentan en la tabla de calidad. El modelo escala los flujos a la venta madura de cada sede, así que la venta no se pierde.
5. **Análisis por paciente:**
   - áreas de influencia **reales** de cada sede: las manzanas que suman el 60% y el 80% de su venta, ordenadas por tiempo de viaje;
   - **afinidad** por GSE, edad y sexo, comparada con la población que vive dentro del área del 80%;
   - pacientes que usan **varias sedes**;
   - **fidelidad** (años activos, retención);
   - **convenios** con empresas.
6. **Calibración.** Con RUT, el modelo se calibra **manzana por manzana**. Sin RUT, se calibra por zona censal o comuna, y luego con la venta total por sede.

## Prueba completa con datos simulados

`00_simulacion_de_datos.ipynb` crea bases con exactamente los mismos nombres de archivo y de columnas que las reales:

- Censo: 153 columnas.
- Personas: 72.
- Empresas: 31.
- BBRR: 23.
- POIs: 28.
- Calles: 33.

Usa el grafo real de la RM y genera toda la data de la clínica. Las ventas salen del mismo modelo con parámetros conocidos (`datos_simulados/verdad.json`) más ruido, para comprobar que el estudio los recupera. Los resultados están en `ejecutados_simulacion/`.

### Resultado de la prueba (23-11-2026, v3.6, RM completa, todo por manzana y con RUT)

**Verificaciones:** 110 de 110 OK en las 9 fases, 0 errores y 0 advertencias en los 10 notebooks ejecutados con Jupyter. Las 8 nuevas de v3.6 son del notebook 04b (zonas de influencia preliminares): sedes en el análisis, zonas anidadas (t50 ≤ t60 ≤ t80), en punta la zona de la red es más chica que fuera de punta, sensibilidad coherente, territorios que cubren el área, contornos válidos, entregables generados y, en la simulación, t80 preliminar frente al de los parámetros verdaderos (diferencia mediana 0,3 min). Las 8 de v3.5: coordenadas inválidas ≤ 1% en personas, empresas, BBRR y POIs (notebook 01), y en el entorno de las sedes (notebook 04): todas las sedes del maestro dentro del área analizadas, la zona crece con los minutos, en punta nunca se llega a más población que fuera de punta, y la población por matrices coincide con la de los polígonos (diferencia mediana 2,3%). Las 6 de v3.4: unidad de los montos reconocida, duplicados resueltos según el tipo de tabla, venta de la red entre 0,1% y 60% del gasto en salud del área (control de unidades), invariancia de escala del modelo (diferencia máxima 0,00002), conclusiones escritas para todos los temas y archivo `Conclusiones_CAS.md` generado.

v3.4 no cambia los resultados de v3.3: mismos parámetros, mismo error "sede nueva" (18,5%) y mismo plan ($17.778 millones al mes). Lo nuevo son las defensas ante datos distintos (ver "Ventas de cualquier tamaño y formato") y los 116 indicadores con 34 conclusiones (ver "Indicadores clave y conclusiones").

Los datos simulados se regeneraron para v3.3: ahora los POIs de salud de Equifax repiten lugares del levantamiento con otro nombre y otras coordenadas, el RUT de los pacientes viene en formatos mezclados y el maestro de calles usa los nombres reales de columnas. Por eso las cifras cambian algo respecto de v3.2 (otra realización del azar), no por cambios en el modelo.

**Estructura de las bases (notebook 00):** las 6 bases simuladas tienen exactamente las columnas, nombres y orden de las reales. Esta revisión encontró y corrigió tres diferencias de la simulación anterior: `START_LEF2`/`END_LEF2` en calles, `CASAS` antes de `DEPARTAMEN` en el censo y `LONGITUD_COMER` antes de `LATITUD_COMER` en empresas.

**Territorio y competencia (notebook 03):**

- 48.819 manzanas en el censo simulado. 3.464 (7,1%) se descartaron antes de calcular: vacías, de uso excluido o áreas verdes, con 17 habitantes en total. Quedan 45.355 manzanas útiles. Personas ubicadas en su manzana: 100%. Trabajadores: 98,3%.
- **Unificación levantamiento + POIs de Equifax** (8.357 POIs de salud de Equifax en el área; el levantamiento tiene 8.951 lugares y se conserva completo):

  | Resultado | POIs de Equifax |
  |---|---|
  | Duplicado de un lugar del levantamiento (se descarta el de Equifax) | 5.627 |
  | Duplicado de otro POI de Equifax (queda uno) | 15 |
  | Lugar nuevo (se agrega) | 2.715 |
  | Casos dudosos listados para revisión manual | 363 |

  Contra la verdad de la simulación: el **99,4%** de los duplicados se unió al lugar correcto; solo el **0,65%** de los lugares realmente nuevos se unió por error (14 de 2.166; la mayoría son dos registros con el mismo apellido y tipo a menos de 300 m); y se encontró el **95,7%** de los duplicados (91% contando los que en Equifax figuran con otra razón social, que no tienen cómo reconocerse por el nombre y quedan en la lista de revisión cuando comparten dirección). Ninguna veterinaria entró. Por tipo de variación del nombre: abreviado 98%, sin tildes 98%, sin la palabra genérica 98%, igual 99%, marca + sucursal 94%, con error de tipeo 88%.

**Red y competencia (notebook 04):**

- Las 45.355 manzanas comparten 41.147 nodos de la red. El acceso mediano a la calle es de 44 m.
- Potencial de competencia exacto por manzana con 2.685 competidores (122 clínicas, 2.057 centros médicos, 506 laboratorios). Interpolado vs cálculo directo en 400 manzanas al azar: error máximo 0,005% en la suma y 0,08% en su derivada.
- 2.500 manzanas candidatas, todas sobre una vía terciaria o superior y separadas al menos 250 m.
- Brechas: 2.072 manzanas con alta demanda a más de 15 min de un centro médico o clínica de la red Clínica Alemana. Ahí viven 83.281 personas del segmento objetivo (6% del total).

**RUT (notebook 05):**

- 99.988 atenciones de 28.180 RUT distintos, escritos de 6 formas distintas (con puntos y guion, con guion, sin nada, con ceros a la izquierda, con espacios y como decimal de Excel). Todos se llevan a la misma forma canónica.
- 0,29% de los RUT tiene el dígito verificador inválido (en la simulación se puso un 0,3% mal digitado).
- El 95,2% del monto queda ubicado en una persona (domicilio) o en una empresa (convenio).
- El t80 de cada sede calculado con RUT coincide con el calculado por zona censal (diferencia mediana 0,3 min).
- 1.616 manzanas tienen 5 o más pacientes y concentran el 53% de los pacientes ubicados.

**Parámetros que el modelo recupera, comparados con los verdaderos** (calibración manzana por manzana):

| Parámetro | Verdadero | Estimado | Banda P10–P90 (bootstrap) |
|---|---|---|---|
| Caída por minuto β, clínica | 0,055 | 0,053 | 0,051–0,056 |
| Caída por minuto β, centro médico | 0,110 | 0,105 | 0,103–0,108 |
| Caída por minuto β, toma de muestras | 0,190 | 0,184 | 0,182–0,188 |
| Peso GSE C1a (AB = 1) | 0,70 | 0,80 | 0,70–0,93 |
| Peso GSE C1b | 0,45 | 0,44 | 0,37–0,48 |
| Peso GSE C2 | 0,20 | 0,18 | 0,15–0,21 |
| Peso GSE C3 | 0,08 | 0,08 | 0,07–0,09 |
| Peso GSE D | 0,030 | 0,038 | 0,031–0,050 |
| Peso GSE E | 0,015 | 0,019 | 0,014–0,030 |
| Peso de la demanda flotante λ (trabajadores) | 0,30 | 0,30 | 0,29–0,33 |
| Efecto del tamaño de la sede γ | 0,80 | 1,00 | 0,98–1,03 |
| Rampa: % del régimen al abrir | 35% | 34% | — |
| Rampa: meses característicos | 10 | 12,9 | — |

**Cómo leer las bandas.** El bootstrap remuestrea manzanas, así que mide la incertidumbre que viene de los datos de pacientes. No captura el atractivo propio no observado de cada sede. Por eso los parámetros que dependen de comparar sedes entre sí (γ, C1a) tienen bandas más angostas que su error real. Con 11 sedes es lo esperable. En esta realización el atractivo propio de las sedes salió más disperso que lo nominal (4 de las 11 sedes entre −0,22 y −0,26 en escala log, cuando lo típico es ±0,10), y eso empuja γ hacia arriba.

Ese error de sede sí se mide con la validación "sede nueva" (σ = 19% en escala log en esta realización) y se suma a los escenarios P10/P90 de cada sitio nuevo. Así la banda de una apertura es realista: P90/P10 mediano de 1,64 en el Top 20.

**Validación:**

- **"Sede nueva"** (se predice cada sede sin usar sus datos): error absoluto mediano de 18,5%; 9 de las 11 sedes quedan dentro de ±25%. El error sigue al atractivo propio de cada sede, que el modelo no puede ver: las sedes con el efecto más negativo son las sobreestimadas (CAS-06 +27%, CAS-12 +22%). En la realización de v3.2, con efectos más chicos, el error fue 10,3%.
- **Validación cruzada espacial** (8 bloques de manzanas vecinas): el modelo Huff explica el 76% del desvío. Un *gradient boosting* con la misma validación explica el 56%.
- **Ajuste por manzana:** explica el 76% del desvío de la venta observada manzana por manzana. El error absoluto medio por sede es de 8,5%.

**Expansión (notebook 07):**

- 20 ubicaciones en el Top: 9 centros médicos, 2 clínicas y 9 tomas de muestras. Cada una es una manzana candidata.
- 3 macrozonas de clínica.
- 17.778 MM CLP al mes de venta neta incremental en régimen para el plan completo (≈ 213.300 MM al año). Es menos que en v3.2 porque ahora la competencia incluye los POIs de Equifax que son lugares nuevos (2.685 competidores en el modelo).

**Serie de ventas (notebook 02):** detecta los errores puestos a propósito y los eventos simulados:

- el mes duplicado;
- el mes faltante;
- el pico por error de digitación;
- las notas de crédito;
- el quiebre por convenio;
- la remodelación;
- la cola de la pandemia.

**Isócronas:** coinciden en un 96% con la receta clásica de OSMnx (`nx.ego_graph`), y se calculan unas 200 veces más rápido.

**Peso de los resultados:**

- Los 9 notebooks ejecutados suman 16 MB.
- Las 20 fichas técnicas en PDF pesan 4 MB (la capa de manzanas va rasterizada a 200 ppp).
- El mapa de demanda con las 45 mil manzanas y 8 indicadores pesa 1,5 MB.
- El mapa final de resultados pesa 1,7 MB.

**Tiempos de cada notebook** (Jupyter, PC de 16 núcleos con ~15 GB de memoria libre: 8–9 procesos en paralelo):

| Notebook | v3.1 | v3.2 (optimizada) | v3.3 | v3.4 | v3.6 | Qué cambió |
|---|---|---|---|---|---|---|
| 00 | 5 s | 4 s | 1 min 52 s | 4 s | 4 s | v3.3 regeneró los datos simulados (si ya existen, ~5 s) |
| 01 | 23 s | 25 s | 25 s | 27 s | 23 s | v3.5: coordenadas en cualquier formato (por bloques) |
| 02 | 9 s | 9 s | 9 s | 9 s | 8 s | v3.4: fechas diarias interpretadas una vez por valor distinto (2 millones en 0,2 s) |
| 03 | 19 s | 29 s | 24 s | 25 s | 23 s | incluye la unificación de POIs (~5 s) |
| 04 | 4 min 27 s | **2 min 56 s** | 2 min 34 s | 2 min 44 s | 2 min 51 s | v3.5: análisis de entorno de 14 sedes (~20 s); potencial de competencia 150 s → 19 s; isócronas 81 s → 34 s |
| 04b | – | – | – | – | 31 s | v3.6: zonas de influencia preliminares (sin la red del 04: ~75 s, porque arma la red) |
| 05 | 18 s | 25 s | 20 s | 14 s | 13 s | |
| 06 | 3 min 26 s | **2 min 22 s** | 2 min 19 s | 2 min 51 s | 2 min 45 s | bootstrap 122 s → 64 s; v3.4 agrega la prueba de invariancia de escala (~25 s) |
| 07 | 3 min 18 s | **2 min 10 s** | 2 min 21 s | 2 min 7 s | 2 min 11 s | escenarios de candidatos 28–40 s → 15–17 s por formato |
| 08 | 1 min | **43 s** | 44 s | 44 s | 39 s | fichas PDF 48 s → 22 s |
| **Total (01–08)** | **~13 min** | **~9 min** | **~9 min** | **~9,5 min** | **~10 min** | con el 04b |

**Optimizaciones (todas verificadas contra la versión anterior):**

- **Potencial de competencia:** cada proceso calcula los tiempos de su bloque de competidores **y** su suma en la grilla de β (antes la suma iba en serie), con exponenciales en float32 acumuladas en float64. Los bloques se suman a medida que llegan, así la memoria no crece. Diferencia con el cálculo anterior: 1e-5 en log S.
- **Isócronas:** los recorridos se hacen una vez; los polígonos de todos los modos se reparten en lotes de costo parejo (antes, un modo a la vez y los procesos esperaban a la isócrona más grande). Isócronas chicas con la franja exacta; las muy extensas (auto 30 min) con celdas de hasta ~80 m. Misma área (±1,5%) y 96% de coincidencia con la receta OSMnx, igual que antes.
- **Ajuste del modelo:** solo entran las manzanas que aportan a la verosimilitud (peso > 0 y con datos). Es exacto (diferencia 6e-6 en θ) y en el bootstrap ~37% de las manzanas tiene peso 0.
- **Escenarios de candidatos:** cada lote de la matriz de tiempos se convierte una vez y sirve a las 40 réplicas, en float32 (diferencia 2e-5 en P10/P50/P90). La evaluación central sigue en float64.
- **Fichas PDF:** las manzanas se dibujan como una sola colección rasterizada.

## Decisiones de método (por qué está hecho así)

- **Isócronas por la red, no buffers.** El notebook 04 muestra con datos que, a la misma distancia en línea recta, el tiempo real varía de 8 a 25+ minutos. Las isócronas usan la geometría real de cada calle.
- **Calibración por manzana con RUT.** Cada manzana es una observación del modelo, con la venta de sus pacientes en cada sede.
- **Calibración por zona, si no hay RUT.** Cada zona censal es una unidad del modelo. Lo que la clínica sumó a la comuna (grupos con menos de 5 pacientes) forma una unidad de "resto de comuna" por sede. Las zonas no se reparten antes de ajustar, porque eso diluye el efecto de la distancia y del GSE (se comprobó en la simulación).
- **Cuasi-verosimilitud con dispersión φ.** Los montos en pesos varían más que un conteo. φ pone en la escala correcta los datos, los priors y las bandas P10/P90.
- **Suavidad de los pesos GSE.** C1a, C1b y C2 viven en las mismas zonas, así que sus columnas son casi colineales. La curva AB → E se penaliza para que baje sin zigzag.
- **Trabajadores cuando falta `CANTIDAD_TRAB`.** Se usa el promedio de las empresas del mismo tamaño que sí traen el dato en la misma base (recortado en el p99). El tamaño SII se define por ventas, no por empleo, así que un valor fijo puede errar mucho. En la simulación, el valor fijo "grande = 600" dejaba los trabajadores un 25% bajo y el peso λ de la demanda flotante salía 0,43 en vez de 0,30. Los valores fijos de `config_estudio.py` solo se usan si un tamaño tiene menos de 30 empresas con dato. Su tabla se ve en el notebook 01.
- **Tamaño de la sede.** El atractivo de una sede es proporcional a (m² / m² típico del formato)^γ. Las sedes nuevas se evalúan con el tamaño típico de su formato.
- **Horizonte de 60 minutos.** Más allá de eso el aporte es casi nulo. Los pares fuera del horizonte no entran al ajuste.
- **Escenarios P10/P50/P90 = parámetros + error propio de sede.** El bootstrap mide cuánto se mueven los parámetros. La validación "sede nueva" mide cuánto se equivoca el modelo con una sede concreta, por su atractivo no observado. Los escenarios de cada sitio nuevo combinan las dos fuentes de incertidumbre. Si solo se usara el bootstrap, la banda de una apertura quedaría demasiado angosta.
- **Selección del Top 20 incremental.** Abrir una sede solo suma un término al denominador del modelo. Por eso cada paso de la selección cuesta casi nada y considera la canibalización entre las sedes nuevas.

## Supuestos principales

Todos se editan en `config_estudio.py`. La lista completa, con su justificación, está en `SUPUESTOS` y en el Anexo Metodológico.

- **Hora punta**: velocidad del grafo × factor por tipo de vía, entre 0,55 y 0,80.
- **Caminata**: 4,8 km/h.
- **Bus aproximado**: 13–19 km/h con 5 min de espera, cuando no hay GTFS de buses.
- **Unidad**: manzana del censo, sin las vacías, de uso excluido o de áreas verdes.
- **Candidatos**: manzanas urbanas que dan a una vía terciaria o superior, separadas ≥ 250 m.
- **Horizonte de viaje**: 60 min.
- **Pesos de la competencia por segmento**: Premium 1,0 · Medio-alto 0,8 · Medio 0,55 · Masivo 0,35 · Público 0,2.
- **Viabilidad**: venta neta ≥ P25 de las sedes actuales del mismo formato.
- **Precios**: pesos reales del último mes. Sin la serie IPC del INE se usa una aproximación, que conviene reemplazar.
