"""
Antigravity — Gestor de Cartera Financiera
Dynamia Soluciones Financieras

main.py — Backend v2.0
Arquitectura: FastAPI + SQLite3 nativo
Seguridad:    Anti SQL-Injection (Parameterized Queries)
              CORS Restringido (orígenes locales)
              Saneamiento XSS de entradas de texto
              Manejo seguro de errores (sin Data Leakage)
              Validación estricta con Pydantic
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import uuid
from contextlib import asynccontextmanager
from typing import List, Literal, Optional

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ──────────────────────────────────────────────────────────────
# Logging — registro interno; nunca se expone al cliente
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("antigravity")

# ──────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────
DB_NAME = "antigravity.db"
BASE_DIR = Path(__file__).parent

# Orígenes permitidos: desarrollo + producción
# En producción, esto se configura desde variable de entorno
import os

ALLOWED_ORIGINS: List[str] = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5500",   # Live Server (VS Code)
    "http://127.0.0.1:5500",
    "null",  # file:// — abrir index.html directamente en el navegador
]

# Agregar origins de producción si existen en variables de entorno
PROD_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",")
if PROD_ORIGINS and PROD_ORIGINS[0]:
    ALLOWED_ORIGINS.extend([origin.strip() for origin in PROD_ORIGINS])

# Adicionar dominio Heroku automáticamente
HEROKU_APP = os.getenv("HEROKU_APP_NAME")
if HEROKU_APP:
    ALLOWED_ORIGINS.extend([
        f"https://{HEROKU_APP}.herokuapp.com",
        f"http://{HEROKU_APP}.herokuapp.com",
    ])

# ──────────────────────────────────────────────────────────────
# Capa de Base de Datos
# ──────────────────────────────────────────────────────────────

def _open_connection() -> sqlite3.Connection:
    """
    Abre y configura una conexión SQLite.
    - row_factory permite acceso por nombre de columna.
    - PRAGMA foreign_keys = ON activa la integridad referencial
      y el ON DELETE CASCADE en cada sesión (SQLite lo requiere
      explícitamente por conexión).
    """
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")   # mejor concurrencia
    return conn


def get_db() -> sqlite3.Connection:
    """
    Dependency de FastAPI: proporciona una conexión por request
    y garantiza su cierre al terminar.
    """
    conn = _open_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """
    Crea las tablas si no existen.
    Todos los índices se crean para acelerar búsquedas frecuentes.
    """
    with _open_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS clientes (
                id            TEXT PRIMARY KEY,
                cedula        TEXT UNIQUE NOT NULL,
                name          TEXT NOT NULL,
                phone         TEXT,
                initial_debt  REAL NOT NULL CHECK (initial_debt > 0),
                start_date    TEXT NOT NULL,
                interest_rate REAL NOT NULL CHECK (interest_rate >= 0),
                interest_type TEXT NOT NULL CHECK (interest_type IN ('simple', 'compuesto')),
                notes         TEXT
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_clientes_cedula
                ON clientes (cedula);

            CREATE TABLE IF NOT EXISTS payments (
                id        TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                amount    REAL NOT NULL CHECK (amount > 0),
                date      TEXT NOT NULL,
                FOREIGN KEY (client_id)
                    REFERENCES clientes (id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_payments_client
                ON payments (client_id);
        """)
        conn.commit()
    logger.info("Base de datos inicializada correctamente.")


# ──────────────────────────────────────────────────────────────
# Lifespan (reemplaza el deprecado @app.on_event)
# ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Servidor Antigravity iniciado — listo para recibir conexiones.")
    yield
    logger.info("Servidor Antigravity detenido.")


# ──────────────────────────────────────────────────────────────
# Aplicación FastAPI
# ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Antigravity API",
    description="Gestor de Cartera Financiera — Dynamia Soluciones",
    version="2.0.0",
    lifespan=lifespan,
    # Desactiva la re-exposición de schemas internos en producción
    # (dejar en True solo durante desarrollo)
    docs_url="/docs",
    redoc_url=None,
)

# ── CORS Restringido ──────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)


# ──────────────────────────────────────────────────────────────
# Saneamiento XSS — Anti Cross-Site Scripting
# ──────────────────────────────────────────────────────────────

# Detecta cualquier etiqueta HTML (<script>, <img onerror=...>, etc.)
_HTML_TAG_RE = re.compile(r"<[^>]+>", re.IGNORECASE)
# Detecta atributos de evento JS (onclick=, onerror=, etc.)
_JS_EVENT_RE = re.compile(r"\bon\w+\s*=", re.IGNORECASE)
# Detecta URLs javascript:
_JS_PROTO_RE = re.compile(r"javascript\s*:", re.IGNORECASE)


def sanitize_text(value: str | None) -> str | None:
    """
    Elimina etiquetas HTML, manejadores de eventos JS y URIs peligrosas
    de cualquier campo de texto antes de persistirlo.
    Devuelve None si el valor de entrada es None o vacío.
    """
    if value is None:
        return None
    cleaned = _HTML_TAG_RE.sub("", value)
    cleaned = _JS_EVENT_RE.sub("", cleaned)
    cleaned = _JS_PROTO_RE.sub("", cleaned)
    # Elimina caracteres de control (excepto tabulación y salto de línea)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)
    return cleaned.strip() or None


# ──────────────────────────────────────────────────────────────
# Modelos Pydantic — Validación Estricta de Entrada / Salida
# ──────────────────────────────────────────────────────────────

class PaymentBase(BaseModel):
    amount: float = Field(..., gt=0, description="Monto del abono (debe ser > 0)")
    date: str     = Field(..., description="Timestamp ISO 8601 del abono")


class PaymentCreate(PaymentBase):
    pass


class PaymentResponse(PaymentBase):
    id:        str
    client_id: str

    model_config = ConfigDict(from_attributes=True)


class ClientBase(BaseModel):
    cedula:        str   = Field(..., min_length=1, max_length=20,
                                  description="Número de cédula (solo dígitos)")
    name:          str   = Field(..., min_length=1, max_length=150,
                                  description="Nombre completo del cliente")
    phone:         Optional[str] = Field(None, max_length=30)
    initial_debt:  float = Field(..., gt=0, alias="initialDebt",
                                  description="Monto inicial de la deuda (debe ser > 0)")
    start_date:    str   = Field(..., alias="startDate",
                                  description="Fecha de inicio (YYYY-MM-DD)")
    interest_rate: float = Field(..., ge=0, alias="interestRate",
                                  description="Tasa de interés mensual (>= 0)")
    interest_type: Literal["simple", "compuesto"] = Field(
        ..., alias="interestType",
        description="Tipo de interés: 'simple' o 'compuesto'"
    )
    notes: Optional[str] = Field(None, max_length=500)

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("cedula")
    @classmethod
    def cedula_solo_digitos(cls, v: str) -> str:
        if not re.fullmatch(r"\d{1,20}", v):
            raise ValueError("La cédula solo puede contener dígitos (máx. 20).")
        return v

    @field_validator("start_date")
    @classmethod
    def fecha_formato_valido(cls, v: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError("La fecha de inicio debe tener el formato YYYY-MM-DD.")
        return v


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    """
    Todos los campos son opcionales para soportar actualizaciones parciales.
    Se reutilizan las restricciones de dominio (gt/ge/Literal).
    """
    cedula:        Optional[str]   = Field(None, min_length=1, max_length=20)
    name:          Optional[str]   = Field(None, min_length=1, max_length=150)
    phone:         Optional[str]   = Field(None, max_length=30)
    initial_debt:  Optional[float] = Field(None, gt=0,  alias="initialDebt")
    start_date:    Optional[str]   = Field(None,         alias="startDate")
    interest_rate: Optional[float] = Field(None, ge=0,  alias="interestRate")
    interest_type: Optional[Literal["simple", "compuesto"]] = Field(
        None, alias="interestType"
    )
    notes: Optional[str] = Field(None, max_length=500)

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("cedula")
    @classmethod
    def cedula_solo_digitos(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"\d{1,20}", v):
            raise ValueError("La cédula solo puede contener dígitos (máx. 20).")
        return v

    @field_validator("start_date")
    @classmethod
    def fecha_formato_valido(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError("La fecha de inicio debe tener el formato YYYY-MM-DD.")
        return v


class ClientResponse(BaseModel):
    id:            str
    cedula:        str
    name:          str
    phone:         Optional[str]
    initialDebt:   float
    startDate:     str
    interestRate:  float
    interestType:  str
    notes:         Optional[str]
    payments:      List[PaymentResponse] = []

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────────────────────
# Motor Matemático Financiero — Cálculo de Intereses Diarios Exactos
# ──────────────────────────────────────────────────────────────

from datetime import datetime

def calc_daily_interest_rate(monthly_rate: float, interest_type: str) -> float:
    """
    Convierte una tasa de interés mensual a una tasa diaria equivalente.
    
    - Simple:   rDiaria = (TasaMensual / 100) / 30
    - Compuesto: rDiaria = (1 + TasaMensual/100)^(1/30) - 1
    
    Args:
        monthly_rate: Tasa mensual en porcentaje (ej. 5 para 5%)
        interest_type: 'simple' o 'compuesto'
    
    Returns:
        Tasa diaria como fracción decimal (ej. 0.00167 para simple 5%)
    """
    monthly_fraction = monthly_rate / 100
    
    if interest_type == "simple":
        return monthly_fraction / 30
    else:  # compuesto
        return (1 + monthly_fraction) ** (1 / 30) - 1


def calc_accumulated_interest(
    initial_debt: float,
    start_date: str,
    interest_rate: float,
    interest_type: str,
    today: datetime = None,
) -> float:
    """
    Calcula el interés acumulado exacto desde start_date hasta hoy.
    
    Args:
        initial_debt: Monto inicial de la deuda
        start_date: Fecha de inicio (formato YYYY-MM-DD)
        interest_rate: Tasa mensual en porcentaje
        interest_type: 'simple' o 'compuesto'
        today: Fecha de referencia (por defecto, hoy)
    
    Returns:
        Interés acumulado en COP (float)
    """
    if today is None:
        today = datetime.now()
    
    start = datetime.strptime(start_date, "%Y-%m-%d")
    days_passed = max(0, (today.date() - start.date()).days)
    
    r_daily = calc_daily_interest_rate(interest_rate, interest_type)
    
    if interest_type == "simple":
        return initial_debt * r_daily * days_passed
    else:  # compuesto
        return initial_debt * ((1 + r_daily) ** days_passed - 1)


def get_total_payments(conn: sqlite3.Connection, client_id: str) -> float:
    """
    Obtiene la suma total de abonos registrados para un cliente.
    
    Returns:
        Total de abonos en COP (float)
    """
    row = conn.execute(
        "SELECT SUM(amount) as total FROM payments WHERE client_id = ?",
        (client_id,),
    ).fetchone()
    return row["total"] if row["total"] is not None else 0.0


def get_client_financials(
    conn: sqlite3.Connection,
    client_id: str,
    initial_debt: float,
    start_date: str,
    interest_rate: float,
    interest_type: str,
) -> dict:
    """
    Calcula intereses, pagos y saldo pendiente de un cliente.
    
    Returns:
        {
            'accumulated_interest': float,
            'total_payments': float,
            'total_due': float,  # saldo pendiente
            'status': 'pendiente' | 'parcial' | 'saldado'
        }
    """
    accumulated_interest = calc_accumulated_interest(
        initial_debt, start_date, interest_rate, interest_type
    )
    total_payments = get_total_payments(conn, client_id)
    total_due = max(0, initial_debt + accumulated_interest - total_payments)
    
    status = "saldado" if total_due <= 0 else ("parcial" if total_payments > 0 else "pendiente")
    
    return {
        "accumulated_interest": accumulated_interest,
        "total_payments": total_payments,
        "total_due": total_due,
        "status": status,
    }


# ──────────────────────────────────────────────────────────────
# Helpers de Base de Datos (Queries Parametrizadas)
# ──────────────────────────────────────────────────────────────

def _row_to_client(row: sqlite3.Row, payments: list[dict]) -> dict:
    """Convierte una sqlite3.Row de clientes al dict esperado por ClientResponse."""
    return {
        "id":           row["id"],
        "cedula":       row["cedula"],
        "name":         row["name"],
        "phone":        row["phone"],
        "initialDebt":  row["initial_debt"],
        "startDate":    row["start_date"],
        "interestRate": row["interest_rate"],
        "interestType": row["interest_type"],
        "notes":        row["notes"],
        "payments":     payments,
    }


def _row_to_payment(row: sqlite3.Row) -> dict:
    return {
        "id":        row["id"],
        "client_id": row["client_id"],
        "amount":    row["amount"],
        "date":      row["date"],
    }


def _fetch_payments(conn: sqlite3.Connection, client_id: str) -> list[dict]:
    """
    Obtiene los abonos de un cliente ordenados del más reciente al más antiguo.
    Usa consulta parametrizada — NUNCA concatenación de strings.
    """
    cursor = conn.execute(
        "SELECT id, client_id, amount, date FROM payments "
        "WHERE client_id = ? ORDER BY date DESC",
        (client_id,),           # ← tupla de parámetro seguro
    )
    return [_row_to_payment(r) for r in cursor.fetchall()]


# ──────────────────────────────────────────────────────────────
# Servicio de archivos estáticos (frontend)
# ──────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def serve_index():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/script.js", include_in_schema=False)
def serve_script():
    return FileResponse(BASE_DIR / "script.js", media_type="application/javascript")


@app.get("/style.css", include_in_schema=False)
def serve_style():
    return FileResponse(BASE_DIR / "style.css", media_type="text/css")


# ──────────────────────────────────────────────────────────────
# ENDPOINTS REST
# ──────────────────────────────────────────────────────────────

# ── GET /api/clientes ─────────────────────────────────────────
@app.get(
    "/api/clientes",
    response_model=List[ClientResponse],
    summary="Lista todos los clientes con su historial de abonos",
)
def get_clients(conn: sqlite3.Connection = Depends(get_db)):
    try:
        rows = conn.execute(
            "SELECT id, cedula, name, phone, initial_debt, start_date, "
            "interest_rate, interest_type, notes FROM clientes ORDER BY name ASC"
        ).fetchall()

        result = []
        for row in rows:
            payments = _fetch_payments(conn, row["id"])
            result.append(_row_to_client(row, payments))
        return result

    except Exception as exc:
        logger.error("get_clients — error interno: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor. Por favor intente más tarde.",
        )


# ── POST /api/clientes ────────────────────────────────────────
@app.post(
    "/api/clientes",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registra un nuevo cliente",
)
def create_client(
    client: ClientCreate,
    conn: sqlite3.Connection = Depends(get_db),
):
    # ── Saneamiento XSS de campos de texto libre
    safe_name  = sanitize_text(client.name)
    safe_phone = sanitize_text(client.phone)
    safe_notes = sanitize_text(client.notes)

    if not safe_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El nombre del cliente no puede quedar vacío tras el saneamiento.",
        )

    new_id = str(uuid.uuid4())

    try:
        conn.execute(
            """
            INSERT INTO clientes
                (id, cedula, name, phone, initial_debt, start_date,
                 interest_rate, interest_type, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (                               # ← parámetros seguros, nunca f-string
                new_id,
                client.cedula,
                safe_name,
                safe_phone,
                client.initial_debt,
                client.start_date,
                client.interest_rate,
                client.interest_type,
                safe_notes,
            ),
        )
        conn.commit()

    except sqlite3.IntegrityError as exc:
        logger.warning("create_client — cédula duplicada: %s | %s", client.cedula, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Atención: Cédula ya registrada en el sistema.",
        )
    except Exception as exc:
        conn.rollback()
        logger.error("create_client — error interno: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al registrar el cliente.",
        )

    return _row_to_client(
        conn.execute(
            "SELECT id, cedula, name, phone, initial_debt, start_date, "
            "interest_rate, interest_type, notes FROM clientes WHERE id = ?",
            (new_id,),
        ).fetchone(),
        [],
    )


# ── PUT /api/clientes/{id} ────────────────────────────────────
@app.put(
    "/api/clientes/{client_id}",
    response_model=ClientResponse,
    summary="Actualiza los datos de un cliente existente",
)
def update_client(
    client_id: str,
    client_update: ClientUpdate,
    conn: sqlite3.Connection = Depends(get_db),
):
    # Verificar existencia — consulta parametrizada
    existing = conn.execute(
        "SELECT id FROM clientes WHERE id = ?",
        (client_id,),
    ).fetchone()

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado.",
        )

    # Construir actualización dinámica con campos provistos
    update_data = client_update.model_dump(exclude_unset=True, by_alias=False)

    if not update_data:
        # Nada que actualizar: devolver registro actual
        payments = _fetch_payments(conn, client_id)
        row = conn.execute(
            "SELECT id, cedula, name, phone, initial_debt, start_date, "
            "interest_rate, interest_type, notes FROM clientes WHERE id = ?",
            (client_id,),
        ).fetchone()
        return _row_to_client(row, payments)

    # Mapa de nombres de campo Python → columnas SQLite
    FIELD_TO_COLUMN: dict[str, str] = {
        "cedula":        "cedula",
        "name":          "name",
        "phone":         "phone",
        "initial_debt":  "initial_debt",
        "start_date":    "start_date",
        "interest_rate": "interest_rate",
        "interest_type": "interest_type",
        "notes":         "notes",
    }

    # Saneamiento XSS en campos de texto libres
    if "name" in update_data:
        safe = sanitize_text(update_data["name"])
        if not safe:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El nombre no puede quedar vacío tras el saneamiento.",
            )
        update_data["name"] = safe
    if "phone" in update_data:
        update_data["phone"] = sanitize_text(update_data["phone"])
    if "notes" in update_data:
        update_data["notes"] = sanitize_text(update_data["notes"])

    set_clauses: list[str] = []
    params: list           = []

    for field, value in update_data.items():
        col = FIELD_TO_COLUMN.get(field)
        if col is None:
            continue
        set_clauses.append(f"{col} = ?")   # nombre de columna es literal, no var de usuario
        params.append(value)

    if not set_clauses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se proporcionaron campos válidos para actualizar.",
        )

    params.append(client_id)               # parámetro del WHERE

    try:
        conn.execute(
            f"UPDATE clientes SET {', '.join(set_clauses)} WHERE id = ?",
            tuple(params),                 # ← parámetros seguros
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        logger.warning("update_client — conflicto de cédula: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Atención: La cédula indicada ya pertenece a otro cliente.",
        )
    except Exception as exc:
        conn.rollback()
        logger.error("update_client — error interno: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al actualizar el cliente.",
        )

    row = conn.execute(
        "SELECT id, cedula, name, phone, initial_debt, start_date, "
        "interest_rate, interest_type, notes FROM clientes WHERE id = ?",
        (client_id,),
    ).fetchone()
    payments = _fetch_payments(conn, client_id)
    return _row_to_client(row, payments)


# ── DELETE /api/clientes/{id} ─────────────────────────────────
@app.delete(
    "/api/clientes/{client_id}",
    status_code=status.HTTP_200_OK,
    summary="Elimina un cliente y todo su historial de abonos (CASCADE)",
)
def delete_client(
    client_id: str,
    conn: sqlite3.Connection = Depends(get_db),
):
    try:
        cursor = conn.execute(
            "DELETE FROM clientes WHERE id = ?",
            (client_id,),               # ← parámetro seguro
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error("delete_client — error interno: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al eliminar el cliente.",
        )

    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado.",
        )

    return {"message": "Cliente y sus abonos eliminados correctamente."}


# ── POST /api/clientes/{id}/payments ─────────────────────────
@app.post(
    "/api/clientes/{client_id}/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registra un abono para un cliente existente",
)
def create_payment(
    client_id: str,
    payment: PaymentCreate,
    conn: sqlite3.Connection = Depends(get_db),
):
    # Verificar que el cliente exista — consulta parametrizada
    client_row = conn.execute(
        "SELECT id, initial_debt, start_date, interest_rate, interest_type "
        "FROM clientes WHERE id = ?",
        (client_id,),
    ).fetchone()

    if not client_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado.",
        )

    # Validación extra: el monto debe ser un número finito positivo
    if not (isinstance(payment.amount, (int, float)) and payment.amount > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El monto del abono debe ser un número positivo.",
        )

    # ── Validación: el abono no debe superar el saldo pendiente
    financials = get_client_financials(
        conn,
        client_id,
        client_row["initial_debt"],
        client_row["start_date"],
        client_row["interest_rate"],
        client_row["interest_type"],
    )
    
    if payment.amount > financials["total_due"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El abono (${payment.amount:,.2f}) no puede superar el saldo pendiente (${financials['total_due']:,.2f}).",
        )

    new_payment_id = str(uuid.uuid4())

    try:
        conn.execute(
            "INSERT INTO payments (id, client_id, amount, date) VALUES (?, ?, ?, ?)",
            (new_payment_id, client_id, payment.amount, payment.date),  # ← params seguros
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error("create_payment — error interno: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al registrar el abono.",
        )

    return {
        "id":        new_payment_id,
        "client_id": client_id,
        "amount":    payment.amount,
        "date":      payment.date,
    }


# ──────────────────────────────────────────────────────────────
# Punto de Entrada — Ejecución Directa
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,           # False en producción
        log_level="info",
    )
