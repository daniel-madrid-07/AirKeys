# Guía de AirKeys

Ratón y teclado invisibles con una webcam. Tres modos: **Ratón**, **Teclado**, **Gaming**.

---

## 1. Coloca la cámara

La posición de la cámara es lo que más afecta a la precisión.

| Modo | Mejor posición de cámara |
|------|--------------------------|
| **Solo ratón** | De lado / baja, mirando la mano a través de la mesa. Muy cómodo. |
| **Teclado** | **Elevada y en ángulo (~45–60°)**, delante-arriba mirando las manos. Así ve el golpe vertical del dedo *y* la posición de cada tecla. |
| **Gaming** (ratón+teclado) | La misma de ~45° delante-arriba: sirve para las dos. |

> Recomendación general: una webcam en un brazo/tripode **elevada y mirando abajo en ángulo (~45–60°)** sobre la mesa, delante-arriba de tus manos, cubre los tres modos. Es el punto óptimo: ve el golpe vertical del dedo (teclado/clics) y el plano (ratón). Perfectamente vertical (90°) NO es lo ideal: pierde el gesto vertical.

**Orientación (montaje cenital/arriba).** Al montar la cámara arriba suele quedar girada. Ajusta en **Ajustes → o en `settings.json`**:
- `CAM_ROTATE`: `0` / `90` / `180` / `270`. Cámbialo hasta que tus manos salgan naturales, **dedos hacia arriba de la imagen** e izquierda a la izquierda.
- `FLIP_HORIZONTAL`: `true`/`false` si izquierda y derecha salen cambiadas.
- Marca `CAM_VIEW` = `"overhead"` (informativo).

**Importante:** deja `CAM_ROTATE`/`FLIP_HORIZONTAL` fijos y **recalibra** (ratón y tap) en esa posición. Deben ser iguales al calibrar, grabar y usar.

Buena luz y fondo de mesa mate ayudan.

---

## 2. Arranca

- **Instalado (.exe)**: abre **AirKeys** desde el menú Inicio o el escritorio.
- **Desde código**: doble clic en `Iniciar AirKeys.bat`, o `python airkeys.py`.

Verás un menú. Empieza por **8) Comprobar cámara** para confirmar que se ve tu webcam.

> Cada modo abre primero en **MODO PRUEBA** (no controla el ratón/teclado de verdad).
> Cuando te fíes, elige control **REAL**.

---

## 3. Modo RATÓN

1. Menú → **4) Calibrar ratón**: haz dos gestos cuando te los pida (mano a la
   **derecha**, luego mano **alante**). ~8 segundos. Solo una vez por posición de cámara.
2. Menú → **1) Ratón** (cámara CENITAL, posición normal = **puño**). Gestos:
   - **Puño** y mover la mano → mueve el cursor (relativo).
   - **Abrir/alejar el pulgar** de la mano → clic **izquierdo** mantenido.
   - **Estirar el índice** → clic **derecho** mantenido.
   - **Mano plana** (todos los dedos rectos) → congela el cursor (recolocar sin mover).

Sensación (en `settings.json`): `MOUSE_GAIN` (sensibilidad), `MOUSE_SMOOTH`
(suavizado), `MOUSE_DEADZONE` (tembleque en reposo).

---

## 4. Modo GAMING (ratón + teclado, sin entrenar)

- **Mano derecha** = ratón (igual que arriba).
- **Mano izquierda** = teclas mantenidas. Cada dedo es una tecla; **bajar el dedo**
  la aprieta y se mantiene mientras siga abajo (como aguantar W para correr).
- Mapeo por defecto (`GAMING_KEYS` en settings.json):
  meñique=Shift, anular=A, corazón=W, índice=D, pulgar=Espacio.

Menú → **3) Gaming**. No necesita entrenar nada.

---

## 5. Modo TECLADO completo (escribir letras)

Este es el difícil. Escribe letras sobre una mesa vacía. **Necesita entrenar** con
tus propios datos (cada persona teclea distinto).

1. Cámara a ~45° (ver arriba).
2. Menú → **6) Grabar teclado**: sigue el metrónomo, pulsa en el aire cada letra que
   aparece. Haz varias sesiones (más datos = mejor).
3. Menú → **5) Calibrar tap**: copia los valores sugeridos a `settings.json`.
4. Menú → **7) Entrenar**.
5. Menú → **2) Teclado**: prueba. Si va bien, control real.

> Realista: el teclado es investigación. La precisión depende mucho de la cámara y de
> cuántos datos grabes. El ratón y el gaming funcionan sin entrenar.

---

## 6. Ajustes (`settings.json`)

Copia `settings.example.json` a `settings.json` (junto al programa) y cambia lo que
quieras. Cualquier valor de `config.py` se puede sobreescribir. Ejemplos:

```json
{ "MOUSE_HAND": "Left", "MOUSE_GAIN": 1.4, "CAM_NAME": "Logitech" }
```

---

## 7. Problemas típicos

- **No ve la cámara / ve otra (DroidCam, OBS)**: pon `CAM_NAME` con parte del nombre
  de tu webcam en `settings.json`.
- **El cursor tiembla en reposo**: sube `MOUSE_DEADZONE`.
- **Movimiento a tirones**: baja `MOUSE_SMOOTH`.
- **Clic izquierdo salta/no responde**: mira el valor `t:` en pantalla al abrir el
  pulgar y ajusta `MOUSE_THUMB_OPEN` justo por debajo de ese valor. Clic derecho:
  mira `i:` al estirar el índice y ajusta `MOUSE_INDEX_EXTEND`.
- **El teclado no escribe nada**: casi siempre es la cámara (no ve el golpe vertical)
  o pocos datos. Cámara a ~45° y graba más.
- **Izquierda/derecha cambiadas**: pon `"SWAP_HANDS": true`.
