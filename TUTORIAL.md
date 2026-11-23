# Tutorial de Acomoda, paso a paso

Acomoda le dice **dónde poner cada producto y qué estantes usar** para que los pedidos se armen caminando menos, y le dice
con claridad **si conviene hacerlo o no**. También le entrega el **borrador de su artículo** en Word con sus cifras ya escritas.

No necesita saber estadística: la app hace los cálculos y le muestra un recuadro **🎯 Decisión** con lo que debe hacer.

---

## Antes de empezar: qué necesita tener a mano

| Archivo | De dónde sale | ¿Obligatorio? |
|---|---|---|
| **Lista de productos** (catálogo) en Excel | Su sistema de ventas o inventario | Sí |
| **Reporte de ventas** en Excel (una fila por producto vendido en cada comprobante) | Su sistema de facturación | Sí |
| **Medidas del local** (largo, ancho, alto, puertas, columnas) | Una wincha y 20 minutos | Sí (puede usar el ejemplo para aprender) |
| Medidas de los productos que más vende | Wincha y balanza | Recomendado |

> 💾 **Su avance se guarda solo.** La dirección de la página termina en `?p=` seguido de un código (por ejemplo
> `?p=4f3a9c1b22d0`). **Guarde esa dirección en favoritos.** Si recarga la página (F5 o Ctrl+Shift+R), cierra el
> navegador o cambia de computadora, al abrir esa misma dirección sigue donde se quedó.
> **No comparta el enlace:** quien lo tenga ve su proyecto.

En la barra de la izquierda verá los 8 pasos. Cada uno tiene un ícono:
✅ listo · ⚠️ listo con advertencias · ⏳ falta hacerlo · 🔒 se abre cuando termine el anterior.

---

## Paso 1. Catálogo con magnitudes

1. Escriba su nombre en **Responsable** (barra izquierda). Elija su **Perfil de rubro** (por ejemplo, bazar) y el
   **Modo**: *Almacén* si arma pedidos en un depósito, *Tienda* si los clientes recorren los estantes.
2. Si no tiene un catálogo ordenado, pulse **Descargar plantilla de catálogo**, llénela y súbala.
   Si ya tiene uno, súbalo directamente con **Subir catálogo**.
3. La app le muestra qué entendió. Revise y pulse **Usar estos productos**.
4. En **Medidas que faltan** verá los productos sin medidas. Pulse **Preparar plantilla prellenada**: descarga un Excel
   con esos productos ordenados del que más vende al que menos. **Mida al menos los primeros (clase A)** y vuelva a subirlo.
   Si no mide, la app usa medidas típicas y se lo advierte.
5. Marque la casilla de confirmación y pulse **Confirmar y continuar ➜**.

## Paso 2. Plano o medidas del local

1. Elija cómo entregará el local. Lo más fácil es **Formulario paso a paso**: responde preguntas (medidas, puertas,
   columnas, zona de despacho) y la app dibuja el plano.
   Otras opciones: plantilla Excel, archivo DXF (AutoCAD) o una foto/PDF del plano sobre la que traza con el mouse.
2. **No tiene que medir estantes**: la app los diseña. Si ya tiene estantes y quiere reutilizarlos, regístrelos en la
   hoja opcional `ESTANTES_EXISTENTES`.
3. La app revisa el plano. Si hay errores (una columna fuera del local, una puerta tapada), pulse
   **🪄 Corregir automáticamente**.
4. Responda las preguntas de confirmación y pulse **Confirmo que el local está bien interpretado**.

> Para aprender sin medir nada, use **Cargar el local de ejemplo**. Aparecerá un aviso rojo "EJEMPLO, NO ES REAL":
> sus resultados no servirán para decidir hasta que cargue el local real.

## Paso 3. Reporte de ventas

1. Suba el Excel de ventas (puede pesar decenas de MB; la primera vez tarda hasta un minuto).
2. La app adivina qué columna es la fecha, el producto, la cantidad, el total y el comprobante. Si se equivocó,
   corrija en **Asistente de columnas** y pulse **Aplicar equivalencias**.
3. Revise **Cómo se interpretó** (por ejemplo, que la fecha 05-11-2026 sea 5 de noviembre) y el periodo.
4. Confirme.

## Paso 4. Normativas consideradas

La app ya trae marcadas las normas de seguridad típicas de su rubro (ancho de pasillos, salidas, peso por nivel,
productos que no pueden ir juntos). Solo revise que tengan sentido y confirme.
Las que dicen **"por verificar"** debe confirmarlas en el texto oficial.

## Paso 5. Diseñar y optimizar

1. Elija el modo de diseño: **A** (diseñar desde cero), **B** (solo reubicar en los estantes que ya tiene, sin comprar)
   o **C** (mixto). Si su presupuesto es limitado, escríbalo.
2. Pulse **Propuesta rápida** (unos segundos) para ver un primer resultado.
3. Pulse **Optimización completa** para el mejor resultado (hasta 1 minuto; verá una barra de avance).
   No cierre la pestaña mientras calcula.
4. Revise el diseño y confirme.

## Paso 6. Resultados

Use el selector **Ver** para mirar el plano 2D, la vista 3D (puede girarla con el mouse), la comparación antes y
después, y la lista de productos con su ubicación. Confirme.

## Paso 7. Evidencia: ¿de verdad funciona?

1. (Opcional) Escriba el nombre de su empresa y el problema con sus palabras en **Planteamiento del problema**.
   Aparecerá en el artículo.
2. Pulse **Calcular la evidencia**. La app repite por computadora miles de pedidos reales con la distribución de antes y
   con la nueva, y mide cuántos metros se caminan.
3. **Lea solo el recuadro 🎯 Decisión.** Le dice en una línea qué hacer:
   - 🟢 **SÍ conviene:** implemente la propuesta.
   - 🟡 **Pruebe primero en pequeño:** reubique solo los productos más vendidos y mida.
   - 🔴 **NO compre racks todavía / NO cambie la distribución:** el ahorro no paga la inversión o la mejora no está demostrada.

   Debajo verá cuatro cifras (cuánto menos se camina, cuánto se ahorra al mes, cuánto cuesta y en cuántos meses se paga)
   y la lista **Qué hacer ahora**.
4. El interruptor **Ver el detalle técnico** muestra gráficos y estadística. **No hace falta leerlo para decidir**:
   todo eso ya va escrito en el borrador del artículo.
5. Confirme.

## Paso 8. Costeo y entregables

1. Arriba vuelve a ver la **🎯 Decisión**.
2. **📝 Para su artículo** → pulse **Preparar los archivos del artículo** y descargue:
   - **Borrador del artículo (Word)**: título, resumen, introducción, metodología, resultados, discusión y conclusiones,
     con sus cifras ya puestas. Lo que está **resaltado en amarillo** lo completa usted.
   - **Tablas (Word)**: las tablas numeradas para copiar y pegar.
   - **Todo junto (.zip)**: borrador, tablas, figuras en alta calidad y la decisión en una página.
3. **Costeo editable:** cuando tenga cotizaciones reales, cambie los precios en la tabla. El ahorro, la recuperación y
   la decisión se recalculan al instante.
4. **Informe gerencial:** documento de 1 a 2 páginas para el dueño o gerente.
5. En **Más archivos** encontrará el Excel completo de la propuesta, la vista 3D y el acta de confirmaciones.

---

## Cómo convertir el borrador en su artículo (sin saber de investigación)

1. Abra **BORRADOR_articulo.docx**. Busque lo resaltado en amarillo `[COMPLETAR: …]` y rellénelo.
2. **Introducción:** busque en Google Académico 3 a 5 artículos sobre *distribución de almacenes*, *slotting* o
   *asignación de ubicaciones*. Cite solo lo que haya leído. **La app no inventa referencias** y usted tampoco debe.
3. **Resultados:** no cambie las cifras: salen de sus datos. Si vuelve a calcular, descargue de nuevo el borrador.
4. **Discusión:** compare su porcentaje de reducción con el de los artículos que citó.
5. Reescriba cada párrafo con sus palabras y pida a su asesor que lo revise.
6. Diga siempre que la mejora es **simulada** con pedidos reales (no medida en el local). El borrador ya lo dice en
   *Limitaciones*.

---

## Preguntas frecuentes

**Recargué la página y aparece vacía.** Abra la dirección que guardó en favoritos (la que termina en `?p=…`).
Si la abrió sin ese código, se creó un proyecto nuevo; el anterior sigue guardado en su enlace.

**¿Cuánto tiempo se guarda mi proyecto?** 60 días desde la última vez que lo abrió.

**¿Puedo empezar otro proyecto?** Sí: **Empezar un proyecto nuevo** (barra izquierda). Le da otro enlace; guarde los dos.

**El cálculo se cortó.** Si recargó la página mientras calculaba, vuelva a pulsar el botón. Lo demás sigue guardado.

**La decisión dice "NO compre racks".** Es un resultado válido y honesto: con los precios supuestos, el ahorro no
paga la inversión. Consiga cotizaciones reales, cámbielas en el Paso 8 y vea si cambia.

---

## Para quien administra la app: publicarla en Render (gratis, con Postgres)

El repositorio trae un archivo `render.yaml` que crea **la app y su base de datos Postgres gratuita** de una vez.

1. Entre a [render.com](https://render.com) e inicie sesión con su cuenta de GitHub.
2. **New → Blueprint** → elija el repositorio `ACOMODA` → **Apply**. Render crea dos cosas:
   - `acomoda` (la app web, plan gratuito);
   - `acomoda-db` (Postgres gratuito, donde se guarda el progreso de cada proyecto).

   La primera construcción tarda de 5 a 10 minutos.
3. Abra la dirección que Render le da (`https://acomoda-xxxx.onrender.com`). El tutorial está en la misma web:
   botón **📘 Tutorial** o `https://SU-DOMINIO/?vista=tutorial`.
4. **Dominio propio (opcional):** servicio `acomoda` → **Settings → Custom Domains** → agregue su dominio y cree en su
   proveedor el registro CNAME que Render le indique.

### Lo que hay que saber del plan gratuito de Render

| Límite | Qué significa para usted |
|---|---|
| La app **se duerme tras 15 minutos** sin visitas | La primera visita después tarda ~1 minuto en abrir. El progreso no se pierde (está en Postgres). |
| **512 MB de memoria** | Reportes de ventas muy grandes o la optimización completa pueden hacer que la app se reinicie. Si pasa, use la *Propuesta rápida* o suba el plan del servicio web (Starter). |
| **El Postgres gratuito vence a los 30 días** de creado (luego hay 14 días de gracia y se borra) | Antes de que venza: pase la base a un plan pagado, **o** cree otra base gratuita y cambie la variable `DATABASE_URL` del servicio. Los proyectos guardados en la base vieja se pierden si no la mejora. |
| Base de **1 GB** | Alcanza para decenas de proyectos. Los proyectos sin abrir en 25 días se borran solos (variable `ACOMODA_DIAS_CONSERVAR`). |
| 750 horas gratis al mes | Suficiente para una app que se duerme cuando no se usa. |

### Alternativa: Railway

También funciona en Railway (archivos `Dockerfile` y `railway.json`): **New Project → Deploy from GitHub repo**, agregue
un Postgres (**+ New → Database → PostgreSQL**) y en el servicio cree la variable `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`.
