# PLAUD Email Manager

Gestor de correos de PLAUD con análisis inteligente usando Google Gemini AI.

## 🚀 Despliegue en Render

### 1. Variables de Entorno

Configura estas variables en tu servicio de Render:

- `GEMINI_API_KEY`: Tu API key de Google Gemini
- `GMAIL_USER`: Tu email de Gmail
- `GMAIL_APP_PASSWORD`: App Password de Gmail (16 caracteres)

### 2. Configuración del Servicio

- **Runtime**: Python 3
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python main.py`

### 3. Desarrollo Local

1. Clona el repositorio
2. Crea un entorno virtual: `python -m venv venv`
3. Activa el entorno: `venv\Scripts\activate` (Windows)
4. Instala dependencias: `pip install -r requirements.txt`
5. Crea `secrets.toml` o configura variables de entorno
6. Ejecuta: `python main.py`

## 📧 Configuración de Gmail

1. Ve a [Google Account Settings](https://myaccount.google.com/)
2. Activa 2-Factor Authentication
3. Genera una App Password en "Security" > "App passwords"
4. Usa esa password (16 caracteres sin espacios)

## 🤖 Configuración de Gemini

1. Ve a [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Crea una API key
3. Configura la variable `GEMINI_API_KEY`

## 📁 Estructura del Proyecto

```
├── main.py                 # Punto de entrada FastAPI
├── controller/             # Controladores de la API
├── services/               # Servicios (Gmail, Gemini, Config)
├── views/                  # Templates Jinja2
├── processed_data/         # Almacenamiento de reportes JSON
└── requirements.txt        # Dependencias Python
```