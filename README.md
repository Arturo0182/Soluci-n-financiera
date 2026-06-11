# Antigravity v2.0 — Sistema de Gestión de Cartera Financiera

## 🎯 Descripción

Antigravity es un **sistema empresarial de gestión de cartera financiera** que calcula intereses diarios exactos, registra abonos y audita recaudos en **Pesos Colombianos (COP)**.

## ✨ Características

- ✅ Cálculo exacto de intereses diarios (simple & compuesto)
- ✅ Gestión de cartera de clientes con UUID
- ✅ Auditoría de recaudos con historial completo
- ✅ Validación en tiempo real de saldo pendiente
- ✅ Exportación a Excel (CSV con BOM UTF-8)
- ✅ Importación de backups JSON
- ✅ UI de alta densidad con acordeón desplegable
- ✅ Seguridad OWASP completa (SQL Injection, XSS, CORS)
- ✅ Integridad referencial garantizada (SQLite + CASCADE)

## 🚀 Deployment

### Local Development

```bash
# 1. Clonar repositorio
git clone <repo-url>
cd antigravity

# 2. Crear entorno virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # Windows
source .venv/bin/activate      # Linux/Mac

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Ejecutar servidor
python main.py
```

Accede a: **http://localhost:8000**

### Deployment en Heroku

#### Prerequisitos:
- Cuenta en [Heroku.com](https://www.heroku.com)
- Git instalado
- Heroku CLI instalado

#### Pasos:

```bash
# 1. Login en Heroku
heroku login

# 2. Crear aplicación
heroku create your-app-name

# 3. Configurar variables de entorno (opcional)
heroku config:set HEROKU_APP_NAME=your-app-name

# 4. Deploy
git push heroku main

# 5. Abrir aplicación
heroku open
```

Tu app estará disponible en: **https://your-app-name.herokuapp.com**

## 🏗️ Estructura del Proyecto

```
antigravity/
├── main.py              # Backend FastAPI
├── script.js            # Frontend JavaScript
├── index.html           # UI HTML5
├── style.css            # Estilos CSS3
├── antigravity.db       # Database SQLite
├── requirements.txt     # Dependencias Python
├── Procfile             # Configuración Heroku
├── runtime.txt          # Version Python
├── .gitignore           # Git ignore
└── README.md            # Este archivo
```

## 🔗 API Endpoints

```
GET    /api/clientes              # Obtener todos los clientes
POST   /api/clientes              # Crear nuevo cliente
PUT    /api/clientes/{id}         # Actualizar cliente
DELETE /api/clientes/{id}         # Eliminar cliente
POST   /api/clientes/{id}/payments # Registrar abono
```

### Documentación Interactiva
- Swagger UI: `/docs`
- ReDoc: `/redoc`

## 🔒 Seguridad

- **SQL Injection**: Prepared Statements (?, ?)
- **XSS**: Saneamiento centralizado de entrada
- **CORS**: Whitelist configurado
- **Validación**: Pydantic schemas
- **Logging**: Centralizado sin data leakage

## 📊 Stack Técnico

- **Backend**: FastAPI (Python)
- **Database**: SQLite (Relacional)
- **Frontend**: HTML5 + CSS3 + JavaScript
- **Server**: Uvicorn
- **Deployment**: Heroku, Railway, Render, etc.

## 🧪 Testing

Todos los endpoints fueron validados:
- ✓ CREATE Cliente (HTTP 201)
- ✓ READ Clientes (HTTP 200)
- ✓ UPDATE Cliente (HTTP 200)
- ✓ DELETE Cliente (HTTP 200)
- ✓ POST Payment (HTTP 201)
- ✓ Validación de abonos (HTTP 400)
- ✓ Cascada FK (verificada)

## 📚 Documentación

- `IMPLEMENTATION_SUMMARY.md` — Especificación técnica
- `CHANGES_SUMMARY.md` — Detalle de cambios
- `QUICK_START.md` — Guía de uso rápido
- `plan.md` — Plan de proyecto

## 🆘 Troubleshooting

### "Error al conectar con servidor"
```
Solución: Verifica que el servidor está ejecutándose
$ python main.py
```

### "Port 8000 ya está en uso"
```
Solución: Cambia el puerto en main.py
uvicorn.run(..., port=8001)
```

### "Database corrupted"
```
Solución: Respalda datos, elimina antigravity.db y reinicia
```

## 📞 Soporte

Para preguntas técnicas, revisa:
- Documentación en README.md
- API Docs en `/docs`
- Código fuente comentado en main.py

## 📄 Licencia

Proyecto privado — Dynamia Soluciones Financieras

---

**Versión**: 2.0.0  
**Status**: Production Ready ✅  
**Última actualización**: 2026-06-09
