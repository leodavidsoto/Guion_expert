# 🚀 Scripts de Control

## Comandos Principales

### Iniciar Sistema
```bash
./start.sh
```
Inicia todo el sistema: verifica prerequisitos, inicia Ollama, inicia servidor web.

### Detener Sistema
```bash
./stop.sh
```
Detiene todos los procesos de forma segura.

### Reiniciar Sistema
```bash
./restart.sh
```
Equivalente a `./stop.sh && ./start.sh`

### Ver Estado
```bash
./status.sh
```
Muestra el estado actual de todos los componentes.

### Ver Logs
```bash
./logs.sh
```
Muestra logs en tiempo real del servidor.

## Pipeline Directo

### Generar Guion desde Terminal
```bash
./ejecutar.sh "Una comedia romántica sobre dos astronautas"
```

## Troubleshooting

### Si el servidor no inicia:
```bash
./stop.sh
rm .server.pid
./start.sh
```

### Si Ollama no responde:
```bash
pkill ollama
sleep 2
ollama serve &
sleep 5
./start.sh
```

### Ver todos los procesos:
```bash
ps aux | grep -E "(ollama|python3 server)"
```

### Limpiar todo:
```bash
./stop.sh
pkill ollama
lsof -ti :5001 | xargs kill -9
```
