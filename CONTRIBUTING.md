# 🤝 Guía de Contribución

¡Gracias por tu interés en contribuir!

## 🚀 Cómo Contribuir

### 1. Reportar Bugs
- Usa GitHub Issues
- Describe el problema claramente
- Incluye pasos para reproducir
- Especifica tu sistema operativo y versión de Python

### 2. Proponer Features
- Abre un Issue con el tag "enhancement"
- Describe el caso de uso
- Explica por qué sería útil

### 3. Enviar Pull Requests
```bash
# 1. Fork el repo
# 2. Crea una rama
git checkout -b feature/mi-feature

# 3. Haz tus cambios
# 4. Commit
git commit -m "Add: descripción del feature"

# 5. Push
git push origin feature/mi-feature

# 6. Abre PR en GitHub
```

## 📝 Estilo de Código

- Python: PEP 8
- Bash: ShellCheck compliant
- Documentar funciones complejas
- Tests para features nuevos

## 🧪 Testing
```bash
# Antes de PR, ejecuta:
./test_pipeline.sh
python3 -m pytest tests/
```

## 📖 Documentación

Si agregas un feature, actualiza:
- README.md
- Documentación en /docs
- Ejemplos si aplica
