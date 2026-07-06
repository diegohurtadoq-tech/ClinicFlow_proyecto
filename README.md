# 🤖 ClinicFlow — Plataforma Conversacional de Gestión Clínica

Plataforma de gestión clínica conversacional interactiva: backend robusto en **FastAPI** con persistencia real, dashboard web conectado en vivo consumiendo endpoints HTTP, y un asistente inteligente basado en una **arquitectura multi-agente de doble IA** integrado directamente con **Telegram**.

Proyecto final desarrollado para el curso **EL-4203 — Programación Avanzada** de la **Universidad de Chile**.

---

## 🎨 Características del Sistema

### 📊 Dashboard en Tiempo Real
- **Métricas Operacionales en Vivo:** Desglose automatizado de citas del día, estados de confirmación, cancelaciones y pacientes en lista de espera a través de `GET /api/dashboard/stats`.
- **Monitoreo de IA:** Registro de conversaciones del día indexadas por intenciones detectadas.
- **Disponibilidad Médica:** Estado dinámico de médicos (Activo / Agenda Llena / Bloqueada) calculado directamente contra sus bloques horarios.

### 📅 Gestión Integral de Citas
- Abstracción completa del dominio de citas (`/api/appointments`) gobernado por una **máquina de 6 estados**: `pendiente`, `confirmada`, `cancelada`, `reagendada`, `completada` y `no asistió`.
- Reasignación automatizada de cupos cancelados al paciente con mayor prioridad en listas de espera.

### 📋 Lista de Espera Inteligente
- Inscripción clasificada por prioridad de atención (Normal / Alta).
- **Asignación Automática y Manual:** El backend resuelve la búsqueda del próximo bloque disponible real emparejándolo con los pacientes en cola mediante `WaitlistService.assign_now`.

### 📱 Asistente Multi-Agente (Telegram + Web)
- Capacidad de entender peticiones complejas en lenguaje natural ("*Hola, quiero agendar una hora para Cardiología el 15 de julio a las 10:00*") procesando la intención, validando la seguridad y alterando la base de datos de manera atómica.

---

## 🛠️ Tecnologías y Stack Utilizado

- **Backend core:** FastAPI (Asincrónico).
- **ORM & Persistencia:** SQLAlchemy 2.0 (Consultas parametrizadas con mapeo relacional).
- **Validación de Contratos:** Pydantic v2 (Tipado y esquemas estructurados).
- **Cliente HTTP:** httpx (Conexión asíncrona hacia proveedores externos).
- **Modelos de Lenguaje (LLM):** OpenRouter API (`openrouter/free`).
- **Integración Móvil:** python-telegram-bot v20.x+ (Manejo asincrónico por Polling).
- **Base de Datos:** SQLite (Desarrollo local) / PostgreSQL (Producción en la nube).
- **Pruebas:** pytest (Suite completa con simulación determinística sin llamadas de red).

---

## 🚀 Instalación y Configuración Inicial

### 1. Preparar el Entorno Virtual
Abre una terminal de PowerShell en la raíz del proyecto y navega hacia la carpeta `backend`:
```powershell
cd backend
python -m venv .venv
```

Instala todas las dependencias del núcleo del sistema y los componentes de comunicación de Telegram:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-telegram.txt
```

> **⚠️ Nota de Seguridad en Windows (PowerShell):** No utilices los scripts de activación directa (`Activate.ps1`) ya que las políticas restrictivas de ejecución de Windows suelen bloquearlos silenciosamente, haciendo que los comandos apunten al Python global del sistema. Para asegurar el entorno virtual aislado, llama siempre al ejecutable de forma explícita: `.\.venv\Scripts\python.exe`.

### 2. Configurar Variables de Entorno
Genera el archivo de variables locales a partir de la plantilla:
```powershell
copy .env.example .env
```
Abre el archivo `.env` en tu editor de código y completa los valores requeridos:
```env
DATABASE_URL=sqlite:///./clinicflow.db
JWT_SECRET=tu_secreto_jwt_para_tokens_seguros
OPENROUTER_API_KEY=tu_api_key_real_de_openrouter

# Configuración del Bot Móvil
TELEGRAM_BOT_TOKEN=tu_token_real_entregado_by_botfather
FRONT_DESK_MODEL=openrouter/free
ACTION_MODEL=openrouter/free
```

### 3. Poblar la Base de Datos (Seed)
Inicializa y siembra la base de datos local con configuraciones por defecto (4 médicos, 9 pacientes con agendas estructuradas de lunes a viernes de 09:00 a 17:00):
```powershell
.\.venv\Scripts\python.exe seed.py
```
- **Cuenta Administrador (Dashboard Completo):** `admin@clinicflow.cl` / `admin123`
- **Cuentas de Pacientes (Asistente Web):** `<Cualquier email sembrado, ej: ana.torres@example.com>` / `paciente123`

---

## 🏃‍♂️ Ejecución de los Servicios (Por Separado)

Para levantar la plataforma ClinicFlow completa con todas sus integraciones en vivo, **debes ejecutar los siguientes comandos en dos terminales independientes** paradas dentro de la carpeta `backend`:

### 🖥️ Terminal 1: Servidor Web y API (FastAPI + Uvicorn)
Este proceso sirve los endpoints del backend, gestiona la lógica de negocio y expone la aplicación frontend web de cara al usuario:
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```
- **Plataforma Web de Usuario:** [http://localhost:8000/](http://localhost:8000/)
- **Documentación Interactiva Swagger:** [http://localhost:8000/docs](http://localhost:8000/docs)

### 📱 Terminal 2: Orquestador del Bot de Telegram
Este proceso mantiene el canal bidireccional activo con los servidores de Telegram escuchando mensajes en tiempo real:
```powershell
.\.venv\Scripts\python.exe telegram_bot.py
```
El bot confirmará su inicialización exitosa con el log: `🤖 ClinicFlow Telegram Bot iniciado exitosamente`.

---

## 🔐 Flujo de Autenticación de Pacientes (Web ➔ Telegram)

Para cumplir estrictamente con los estándares académicos de aislamiento y protección de identidades, el bot de Telegram implementa un flujo de autenticación seguro basado en **Base de Datos Compartida**. Esto evita problemas de aislamiento de procesos concurrentes (Uvicorn vs Script independiente):

```text
[ Paciente en Frontend Web ] ──► Clic en "Generar Código" ──► Se guarda en BD (telegram_link_codes)
                                                                        │
[ Celular del Paciente ] ──────► Envía /start CODIGO ◄──────────────────┘
                                        │
                         [ Vinculación Exitosa en BD ] ──► telegram_id ◄─► patient_id
```

1. **Generación:** El paciente inicia sesión en el dashboard web y localiza el panel lateral **"Asistente Móvil"**. Al hacer clic en **"Generar nuevo código"**, el servidor web calcula un token seguro alfanumérico de un solo uso que expira en 10 minutos y lo almacena físicamente en la tabla `telegram_link_codes`.
2. **Vinculación:** El paciente se dirige a Telegram, busca el alias de su bot e inicia la conversación enviando el comando estructurado: `/start CODIGO_DE_PANTALLA` (Ejemplo: `/start MQTUHSC3`).
3. **Consumo:** El proceso autónomo del bot intercepta el código, consulta la base de datos relacional compartida y asocia de manera permanente el `telegram_id` del chat con el `patient_id` del usuario del sistema, invalidando el token de manera inmediata de manera transaccional.

---

## 🧠 Arquitectura de IA y Seguridad por Diseño

La lógica conversacional implementa el patrón exigido por el curso para asegurar que las acciones críticas del dominio **no queden a merced de alucinaciones o inyecciones maliciosas del modelo de lenguaje**:

```text
[ Mensaje del Paciente ] 
         │
         ▼
 1. [ FrontDeskAI ] ─────────► Genera texto amigable y respuestas naturales al usuario.
         │
         ▼
 2. [ ActionAI ] ────────────► Extrae y valida la intención en un JSON estructurado (Pydantic).
         │
         ▼
 3. [ ActionGuard ] ─────────► CÓDIGO PYTHON DETERMINÍSTICO (SIN LLM).
         │                     Verifica pertenencia de IDs y sanitiza inyecciones.
         ▼
 4. [ Services de Dominio ] ─► Aplica reglas de negocio reales sobre el ORM (SQLAlchemy).
```

1. **`FrontDeskAI` (`app/ai/front_desk_ai.py`):** Es la capa empática del sistema. Redacta las interacciones hacia el paciente en lenguaje natural fluido. **No tiene permisos de escritura ni lee la base de datos**.
2. **`ActionAI` (`app/ai/action_ai.py`):** Analiza pragmáticamente la conversación del turno actual y mapea la solicitud obligatoriamente hacia un contrato tipado estructurado en Pydantic (`ProposedAction`). Si la IA alucina o el output no cumple con el esquema estricto de intenciones (`CREATE_APPOINTMENT`, `CANCEL_APPOINTMENT`, etc.), la acción se degrada inmediatamente a un estado inocuo (`NONE`).
3. **`ActionGuard` (`app/ai/action_guard.py`):** Componente crítico de código determinístico puro **sin IA**. Actúa como firewall. Intercepta el payload de `ActionAI` antes de que toque las funciones core y valida que el `patient_id` de la sesión coincida exactamente con el dueño del recurso solicitado, impidiendo ataques de suplantación de identidad mediante *prompt injection*.
4. **Services de Dominio (`app/services/`):** Autoridad última de la lógica de la clínica. Los controladores no operan con SQL directo (estructuralmente inmunes a Inyección SQL), utilizando exclusivamente métodos parametrizados del ORM que vuelven a verificar la disponibilidad horaria real.

---

## 🐳 Despliegue Alternativo con Docker Compose

Si deseas desplegar e inicializar de forma unificada toda la infraestructura productiva local mediante contenedores aislados:
```powershell
cd backend
copy .env.example .env   # Asegúrate de rellenar las claves de OpenRouter y Telegram
docker compose up --build
```
Docker compose compilará la imagen expuesta, creará la base de datos SQLite compartida en un volumen persistente y encenderá de manera sincronizada tanto la API FastAPI como el demonio del Bot de Telegram.

---

## ☁️ Despliegue en la Nube (Vercel + Neon PostgreSQL)

La aplicación web y su API están preparadas para despliegues Serverless en **Vercel** utilizando almacenamiento centralizado de alta disponibilidad:
1. **Configuración de Raíz:** Definir en Vercel el *Root Directory* apuntando a la carpeta `/backend` para procesar el archivo de ruteo nativo `vercel.json`.
2. **Persistencia Remota:** Reemplazar el archivo SQLite local configurando la variable `DATABASE_URL` con un string de conexión robusto PostgreSQL (`postgresql+psycopg2://...`). Los drivers nativos se compilan automáticamente desde `requirements.txt`.
3. **Restricción de Tiempos:** El flujo conversacional ejecuta dos llamadas secuenciales asíncronas de IA que toman un aproximado de 5 segundos en completarse bajo condiciones estándar, manteniéndose cómodamente dentro de la ventana de limitación de ejecución (10 segundos) del plan Hobby de Vercel.

---

## 🧪 Suite de Tests Automatizados

El sistema cuenta con una cobertura de 13 pruebas unitarias y de integración para asegurar que las modificaciones de código no rompan flujos de negocio existentes. La suite inyecta un `FakeLLMClient` interceptando peticiones de red hacia OpenRouter, permitiendo pruebas unitarias determinísticas, instantáneas, con manejo óptimo de timestamps locales frente a deprecaciones de entornos (`utcnow()`), y sin coste financiero:
```powershell
.\.venv\Scripts\python.exe -m pytest
```

---

## 👥 Autores
- **Fernando Baez · Diego Hurtado · Abigail Ibarra**
- Curso EL-4203, Programación Avanzada — **Universidad de Chile**.