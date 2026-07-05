# AirKeys

**Ratón y teclado invisibles con una sola webcam.** Mueve el cursor y haz clic con la
mano en el aire, aguanta teclas para gaming, o escribe letras sobre una mesa vacía.

Sin hardware especial: una webcam, MediaPipe para la mano y un motor de **flujo
óptico** (la cámara como el sensor de un ratón óptico gigante) para un movimiento
sub-píxel y estable.

> ⚠️ Windows. Ratón y Gaming funcionan sin entrenar. El Teclado completo (escribir
> letras) es experimental y requiere grabar tus datos.

---

## Modos

| Modo | Qué hace | ¿Entrena? |
|------|----------|-----------|
| **Ratón** | Puño mueve el cursor; levantar índice = clic izq; sacar corazón = clic der; mano plana = congelar. | No |
| **Gaming** | Mano derecha = ratón. Mano izquierda = teclas mantenidas (dedo abajo = tecla apretada, WASD/Shift/Espacio). | No |
| **Teclado** | Escribir letras tocando una mesa invisible. | Sí |

---

## Instalación

### Opción A — Ejecutable (recomendada)
Descarga el instalador de [Releases](../../releases), instálalo y abre **AirKeys**.

### Opción B — Desde código
Necesitas Python 3.11–3.13.
```bash
git clone <este-repo>
cd AirKeys
install.bat            # crea el entorno e instala dependencias
```
Arranca con `Iniciar AirKeys.bat` o `python airkeys.py`.

---

## Uso rápido

```bash
python airkeys.py            # menú interactivo
python airkeys.py mouse      # ratón (prueba, no controla)
python airkeys.py mouse --real
python airkeys.py gaming --real
python airkeys.py check      # comprobar cámara
```

**Coloca bien la cámara** (lo que más importa): de lado para solo-ratón; **elevada a
~45° delante-arriba** para teclado y gaming. Detalles y calibración en **[GUIDE.md](GUIDE.md)**.

---

## Cómo funciona

1. **MediaPipe HandLandmarker** da 21 puntos 3D por mano (procesados a media
   resolución para ir rápido).
2. **Ratón = flujo óptico**: se rastrea la textura de la piel de la mano (Lucas-Kanade
   sub-píxel, mediana de ~100 puntos con máscara de silueta) → movimiento relativo,
   preciso y estable, con aceleración de puntero y clutch por mano plana. Los gestos de
   clic salen de la extensión/elevación de los dedos.
3. **Teclado = tap + modelo por dedo**: un detector geométrico decide *cuándo* y *qué
   dedo* pulsa; un pequeño GRU por dedo (que solo ve los landmarks de ese dedo) decide
   *qué tecla*. Etiquetado sin teclado físico con un grabador guiado por metrónomo
   (evita el *domain gap*). Inspirado en *Typing on Any Surface* (arXiv:2309.00174).

---

## Ajustes

Copia `settings.example.json` a `settings.json` y sobreescribe cualquier parámetro
(sensibilidad, mano, cámara, umbrales…). Ver [GUIDE.md](GUIDE.md).

---

## Desarrollo

```
airkeys.py            punto de entrada (menu + comandos)
config.py             parametros (+ overrides por settings.json)
src/app.py            motor unificado (3 modos, un bucle de camara)
src/hand_tracker.py   MediaPipe -> landmarks + features
src/flow_sensor.py    flujo optico (movimiento del raton)
src/mouse_control.py  raton relativo, clutch, clicks por dedo
src/gaming.py         teclas mantenidas por dedo (gaming, sin modelo)
src/tap.py            deteccion de pulsacion (teclado)
src/fingers.py        mapeo tecla->dedo
src/model.py          modelo multi-experto por dedo
src/train.py          entrenamiento
src/record_air.py     grabador guiado (metronomo)
tools/                calibracion, comprobaciones y smoke tests
packaging/            PyInstaller spec, build script, instalador
```

Pruebas sin cámara:
```bash
python -m tools.smoke_flow      # flujo optico
python -m tools.smoke_tap       # deteccion de tap
python -m tools.smoke_fingers   # modelo por dedo
```

Empaquetar el .exe:
```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

---

## Licencia
MIT — ver [LICENSE](LICENSE).
