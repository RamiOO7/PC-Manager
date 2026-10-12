# ⚡ PC Manager

Administrador de tareas con estilo moderno para Windows: monitoriza el rendimiento del PC, limpia procesos, archivos temporales y apps, y incluye una prueba de estrés/render.

## Funciones
- **Rendimiento:** CPU, RAM, disco, red y uso por núcleo en tiempo real.
- **Procesos:** lista, finalizar procesos, limpiar apps en segundo plano y liberar RAM.
- **Limpieza:** borrado de archivos temporales y desinstalación de apps.
- **Prueba de render:** estrés de CPU/RAM con render gráfico y puntuación.

## Uso
```
pip install -r requirements.txt
python pc_manager.py
```

## Crear el .exe
```
pip install pyinstaller
pyinstaller --onefile --windowed --collect-all customtkinter --name PCManager pc_manager.py
```
El ejecutable queda en `dist/PCManager.exe`.

## Aviso
La prueba de estrés lleva el hardware al límite. Úsala bajo tu responsabilidad y vigila las temperaturas. Guarda tu trabajo antes de cerrar procesos.
