# Prompt de rediseño — AirKeys

> Copia todo lo de abajo y pásaselo a la IA de diseño.

---

Eres un diseñador de producto e ingeniero frontend de primer nivel. Vas a **rediseñar
por completo la interfaz de AirKeys** hasta dejarla espectacular, con una identidad
propia y NO genérica. Tienes libertad creativa total dentro de las restricciones
técnicas. Dalo TODO: formas, color, tipografía, iconografía, ilustración, motion,
microinteracciones, jerarquía. Que se note que alguien con criterio la diseñó.

## Qué es AirKeys

AirKeys convierte una **webcam cenital** (montada arriba, mirando hacia abajo a las
manos sobre la mesa) en un **ratón y teclado invisibles**: no hay periférico, tu mano
en el aire ES el dispositivo. Detecta la mano con visión por computador y traduce
gestos a movimiento de cursor, clics y teclas.

Tono del producto: preciso, casi mágico, un instrumento. "Tu mano es el mando".
Futurista pero cálido, tangible, gestual. No es un SaaS más.

## Cómo funciona (para que entiendas qué comunicar)

- **Rastreo de mano**: MediaPipe HandLandmarker da 21 puntos 3D por mano.
- **Movimiento del cursor**: NO por los landmarks (tiemblan), sino por **flujo óptico**
  (la cámara actúa como el sensor de un ratón óptico gigante: rastrea la textura de la
  piel y mide el desplazamiento sub-píxel). Relativo, como un ratón real.
- **Gestos (modo ratón, cámara cenital):**
  - PUÑO + mover la mano → mueve el cursor.
  - ABRIR el PULGAR (separarlo de la mano) → clic izquierdo mantenido.
  - ESTIRAR el ÍNDICE → clic derecho mantenido.
  - MANO PLANA (todos los dedos rectos) → congela el cursor (recolocar sin mover).
- **Modo teclado**: escribir letras en el aire (red neuronal por dedo; requiere grabar
  y entrenar). **Modo teclado + ratón**: mano derecha = ratón, mano izquierda = teclas
  mantenidas (tipo WASD).
- Todo corre 100% local, sin internet.

## Arquitectura (relevante para el diseño)

- App de escritorio: **ventana nativa WebView2 (Chromium) vía pywebview**. Dentro corre
  un **servidor Flask local** que sirve la UI y el **vídeo en vivo por MJPEG**.
- **La interfaz es UN SOLO archivo**: `src/webgui/static/index.html` (HTML + CSS + JS
  inline, vanilla, sin build ni frameworks). Ese es el archivo que debes reescribir.
- El backend Python (motor de visión) NO se toca; solo consumes su API.

## RESTRICCIONES TÉCNICAS (obligatorias, la app va empaquetada y OFFLINE)

1. **Todo self-contained en index.html**. Sin CDNs, sin Google Fonts por URL, sin
   imágenes externas, sin fetch a dominios. Cero red. Si quieres una fuente de marca,
   **incrústala como @font-face base64 (woff2)** o usa fuentes de Windows (p.ej.
   **Bahnschrift**, geométrica y distintiva, ya instalada). Iconos e ilustraciones =
   **SVG inline** o data URIs. Vanilla JS (nada de React/CDN).
2. **Vídeo en vivo**: hay un `<img id="cam" src="/video">` que recibe un stream MJPEG
   (multipart). Debe existir un elemento que muestre ese stream; los overlays van
   **posicionados en absoluto encima** del vídeo. No lo quites.
3. **APIs que debes seguir usando** (mismos endpoints):
   - `GET /api/status` cada ~180ms → `{running, mode, real, fps, info:{frozen, left,
     right, idx(0..1), thumb(0..1), keys(str), hand(bool)}}`.
   - `POST /api/start {mode, real}` · `POST /api/stop`.
   - `GET/POST /api/settings {...}` (se aplican EN VIVO al arrastrar).
   - `POST /api/tool {name}` con name ∈ `calibrate-mouse|check|record|train|calibrate-tap`.
4. **Modos** (claves internas y etiquetas): `mouse`="Modo ratón", `keyboard`="Modo
   teclado", `gaming`="Modo teclado + ratón".
5. **Ajustes a exponer** (sliders/controles, con sus rangos actuales): `MOUSE_GAIN`
   0.3–3, `MOUSE_SMOOTH` 0.1–0.8, `MOUSE_DEADZONE` 0–0.003, `MOUSE_ACCEL` 0–3,
   `CAM_ROTATE` (0/90/180/270), `FLIP_HORIZONTAL` (bool), `MOUSE_THUMB_OPEN` 0.2–1.2,
   `MOUSE_INDEX_EXTEND` 0.4–0.98.
6. **Debe mostrar en vivo**: el vídeo con los landmarks, el modo activo, FPS, estado
   (moviendo / congelado), los **medidores 0..1 de `thumb` (clic izq) e `idx` (clic
   der) con su valor numérico**, e indicadores IZQ/DER que se encienden al clicar.
   Texto en **español**.
7. Responsivo a redimensionar la ventana (mínimo ~880×680). Tema oscuro (la webcam
   luce mejor sobre fondo oscuro), pero comprométete con una dirección, no un gris medio.

## Lo que quiero del diseño (personalizado, NO genérico)

- **Identidad propia ligada al producto**: manos, gestos, aire, movimiento, precisión,
  cámara cenital, esqueleto de landmarks, sensor óptico. Que las formas y motivos SALGAN
  de eso (líneas de landmarks, trayectorias, retícula de cámara, siluetas de gestos...).
- **Iconografía a medida**: dibuja los GESTOS como iconos SVG propios (puño, pulgar
  abierto, índice estirado, mano plana). Son el corazón de la UX: haz una **leyenda de
  gestos** clara y bonita, casi un panel de instrucciones de un instrumento.
- **Color**: elige una paleta con carácter y comprométete (dominante + un acento
  afilado). Evita el azul-gris SaaS y los degradados violeta sobre blanco. El acento
  actual es un verde lima sobre casi-negro; puedes reinventarlo, pero que sea intencional.
- **Tipografía**: una display con personalidad (geométrica/editorial), jerarquía
  dramática. Offline (Bahnschrift o woff2 embebida).
- **Motion**: una entrada bien orquestada; feedback de gesto (cuando clica, cuando
  congela); el marco del vídeo debe "sentirse vivo" en marcha; medidores animados.
- **Composición**: rompe la retícula obvia, algo de asimetría, negativo controlado. Que
  al menos una zona sorprenda. El vídeo es la estrella: trátalo como el visor de un
  instrumento de precisión, no como un recuadro cualquiera.

## Evita (señales de diseño "de IA")

Emojis como iconos; tarjetas icono-arriba+título+2líneas en fila; hero centrado H1+2
botones; todo rectángulo redondeado; `box-shadow:0 4px 6px rgba(0,0,0,.1)` en todo;
paletas azul-gris; degradado violeta genérico.

## Skills que tienes instaladas — ÚSALAS

Antes de diseñar, invoca la que mejor encaje (o combina varias):
- **`frontend-design`** — interfaces frontend distintivas y con calidad de producción.
- **`impeccable`** (o `impeccable:impeccable`) — diseño/redesign, jerarquía, motion,
  efectos ambiciosos, pulido.
- **`taste`** — Senior UI/UX, reglas por métricas, arquitectura de componentes.
- **`huashu-design`** — prototipos HTML hi-fi, anti-slop, variantes, dirección de arte.
- **`ui-ux-pro-max:ui-ux-pro-max`** — estilos, paletas, pairings tipográficos, guías UX.
- **`theme-factory`** — sistema de tema (colores/fuentes) coherente.
- **`artifact-design`** — fundamentos de diseño para artefactos.

## Entrega

Reescribe `src/webgui/static/index.html` completo (self-contained). Mantén intactos el
`<img>` del vídeo, el polling de `/api/status`, y todas las llamadas a la API y sus
campos. Cuando termines, la app debe verse como algo que la gente QUIERE abrir.

**Hazlo lo mejor que puedas. Sorpréndeme.**
