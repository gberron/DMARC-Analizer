# DMARC Analizer

Aplicación web en Flask para cargar y analizar reportes DMARC en formato XML, GZ o ZIP. Pensada para ejecutarse en servidores Linux y ser accesible desde computadoras de escritorio y dispositivos móviles.

## Requisitos
- Python 3.11+
- Entorno virtual recomendado

## Instalación
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Uso
1. Crea el directorio de datos (donde se guardará la base SQLite por defecto):
```bash
mkdir -p data
```
2. Lanza el servidor Flask:
```bash
flask --app app run --host 0.0.0.0 --port 5000
```
   Si prefieres modo desarrollo con recarga automática: `FLASK_DEBUG=1 flask --app app run`.
3. Abre `http://localhost:5000` en tu navegador desde la misma máquina o usando la IP/puerto en tu red.
4. Carga archivos de reportes desde la sección **Carga**. Se admiten XML, GZ y ZIP (múltiples informes dentro del ZIP).
5. Explora métricas agregadas, filtra por dominio y rango de fechas y descarga un CSV con los registros procesados.
6. Configura el servidor de correo (IMAP/POP3 y SMTP) y crea reportes periódicos desde el menú **Configuración**.

### Envíos automáticos
- Crea reportes programados indicando destinatario, rango en días y filtro opcional de dominio.
- Ejecuta manualmente el envío desde la pantalla de configuración o con:
  ```
  flask --app app send-scheduled
  ```
- Para automatizar, agrega el comando anterior a un cron del servidor Linux con la frecuencia deseada (por ejemplo diaria o semanal).

Los datos se almacenan en SQLite (`data/dmarc.db`) por defecto. Ajusta la variable de entorno `DATABASE_URL` para usar otro backend compatible con SQLAlchemy.
