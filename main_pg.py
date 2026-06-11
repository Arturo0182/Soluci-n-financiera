"""
Antigravity — Gestor de Cartera Financiera
Dynamia Soluciones Financieras

main.py — Backend v2.1 (PostgreSQL on Heroku)
Arquitectura: FastAPI + PostgreSQL (Heroku Add-on)
Seguridad:    Anti SQL-Injection (Parameterized Queries - %s syntax)
              CORS Restringido (orígenes locales + Heroku)
              Saneamiento XSS de entradas de texto
              Manejo seguro de errores (sin Data Leakage)
              Validación estricta con Pydantic
"""

from __future__ import annotations

import logging
import os
import re
import psycopg2
import psycopg2.extras
import uuid
from contextlib import contextmanager
from typing import List, Literal, Optional, Any, Dict

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
BASE_DIR = Path(__file__).parent

# Orígenes permitidos: desarrollo + producción
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
# Capa de Base de Datos — PostgreSQL via Heroku Add-on
# ──────────────────────────────────────────────────────────────

def _get_database_url() -> str:
    """
    Extrae la URL de conexión a PostgreSQL desde las variables de entorno.
    
    Heroku proporciona DATABASE_URL automáticamente cuando se agrega el addon:
    postgresql://user:password@host:port/database
    
    Falls back a una conexión local si no está configurada (para desarrollo).
    """
    database_url = os.getenv("DATABASE_URL")
    
    if database_url:
        # Heroku usa postgresql://, pero psycopg2 espera postgres://
        # Hacer la conversión si es necesario
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgres://", 1)
        logger.info("Conectando a base de datos desde DATABASE_URL (Heroku)")
        return database_url
    
    # Fallback para desarrollo local
    logger.warning("DATABASE_URL no configurada. Usando conexión local (desarrollo).")
    return "postgres://localhost/antigravity"


@contextmanager
def get_connection():
    """
    Context manager para obtener una conexión a PostgreSQL.
    Garantiza el cierre automático de la conexión tras su uso.
    
    En psycopg2, usamos psycopg2.extras.RealDictCursor para acceso
    a columnas por nombre (similar a sqlite3.Row).
    """
    try:
        conn = psycopg2.connect(
            _get_database_url(),
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        yield conn
    except psycopg2.Error as exc:
        logger.error("Error de conexión a PostgreSQL: %s", exc)
        raise
    finally:
        conn.close()


def get_db():
    """
    Dependency de FastAPI: proporciona una conexión por request
    y garantiza su cierre al terminar.
    """
    try:
        conn = psycopg2.connect(
            _get_database_url(),
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        yield conn
    except psycopg2.Error as exc:
        logger.error("Error de conexión a PostgreSQL: %s", exc)
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    Crea las tablas si no existen en PostgreSQL.
    Utiliza tipos de datos nativos de PostgreSQL optimizados para COP (Pesos Colombianos).
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS clientes (
                    id            VARCHAR(36) PRIMARY KEY,
                    cedula        VARCHAR(20) UNIQUE NOT NULL,
                    name          VARCHAR(150) NOT NULL,
                    phone         VARCHAR(30),
                    initial_debt  NUMERIC(15, 2) NOT NULL CHECK (initial_debt > 0),
                    start_date    DATE NOT NULL,
                    interest_rate NUMERIC(5, 2) NOT NULL CHECK (interest_rate >= 0),
                    interest_type VARCHAR(10) NOT NULL CHECK (interest_type IN ('simple', 'compuesto')),
                    notes         TEXT
                );
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_clientes_cedula
                ON clientes (cedula);
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id        VARCHAR(36) PRIMARY KEY,
                    client_id VARCHAR(36) NOT NULL,
                    amount    NUMERIC(15, 2) NOT NULL CHECK (amount > 0),
                    date      TIMESTAMP NOT NULL,
                    FOREIGN KEY (client_id)
                        REFERENCES clientes (id)
                        ON DELETE CASCADE
                );
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_payments_client
                ON payments (client_id);
            """)
            
            conn.commit()
    
    logger.info("Base de datos PostgreSQL inicializada correctamente.")


# ──────────────────────────────────────────────────────────────
# Aplicación FastAPI
# ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Antigravity API",
    description="Gestor de Cartera Financiera — Dynamia Soluciones",
    version="2.1.0",
    docs_url="/docs",
    redoc_url=None,
)

# Inicializar base de datos al arrancar
@app.on_event("startup")
async def startup_event():
    try:
        init_db()
        logger.info("Servidor Antigravity iniciado — listo para recibir conexiones.")
    except Exception as exc:
        logger.error("Error durante el startup: %s", exc)
        raise

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Servidor Antigravity detenido.")

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

_HTML_TAG_RE = re.compile(r"<[^>]+>", re.IGNORECASE)
_JS_EVENT_RE = re.compile(r"\bon\w+\s*=", re.IGNORECASE)
_JS_PROTO_RE = re.compile(r"javascript\s*:", re.IGNORECASE)


def sanitize_text(value: str | None) -> str | None:
    """
    Elimina etiquetas HTML, manejadores de eventos JS y URIs peligrosas
    de cualquier campo de texto antes de persistirlo.
    """
    if value is None:
        return None
    cleaned = _HTML_TAG_RE.sub("", value)
    cleaned = _JS_EVENT_RE.sub("", cleaned)
    cleaned = _JS_PROTO_RE.sub("", cleaned)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)
    return cleaned.strip() or None


# ──────────────────────────────────────────────────────────────
# Modelos Pydantic — Validación Estricta
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
    cedula:        str   = Field(..., min_length=1, max_length=20)
    name:          str   = Field(..., min_length=1, max_length=150)
    phone:         Optional[str] = Field(None, max_length=30)
    initial_debt:  float = Field(..., gt=0, alias="initialDebt")
    start_date:    str   = Field(..., alias="startDate")
    interest_rate: float = Field(..., ge=0, alias="interestRate")
    interest_type: Literal["simple", "compuesto"] = Field(..., alias="interestType")
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
    cedula:        Optional[str]   = Field(None, min_length=1, max_length=20)
    name:          Optional[str]   = Field(None, min_length=1, max_length=150)
    phone:         Optional[str]   = Field(None, max_length=30)
    initial_debt:  Optional[float] = Field(None, gt=0,  alias="initialDebt")
    start_date:    Optional[str]   = Field(None,         alias="startDate")
    interest_rate: Optional[float] = Field(None, ge=0,  alias="interestRate")
    interest_type: Optional[Literal["simple", "compuesto"]] = Field(None, alias="interestType")
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
# Motor Matemático Financiero
# ──────────────────────────────────────────────────────────────

from datetime import datetime

def calc_daily_interest_rate(monthly_rate: float, interest_type: str) -> float:
    """Convierte tasa mensual a diaria equivalente."""
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
    """Calcula interés acumulado exacto desde start_date hasta hoy."""
    if today is None:
        today = datetime.now()
    
    start = datetime.strptime(start_date, "%Y-%m-%d")
    days_passed = max(0, (today.date() - start.date()).days)
    
    r_daily = calc_daily_interest_rate(interest_rate, interest_type)
    
    if interest_type == "simple":
        return initial_debt * r_daily * days_passed
    else:  # compuesto
        return initial_debt * ((1 + r_daily) ** days_passed - 1)


def get_total_payments(conn, client_id: str) -> float:
    """Obtiene suma total de abonos para un cliente."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT SUM(amount) as total FROM payments WHERE client_id = %s",
            (client_id,),  # ← Parámetro seguro (%s para PostgreSQL)
        )
        row = cur.fetchone()
    return float(row["total"]) if row["total"] is not None else 0.0


def get_client_financials(
    conn,
    client_id: str,
    initial_debt: float,
    start_date: str,
    interest_rate: float,
    interest_type: str,
) -> dict:
    """Calcula intereses, pagos y saldo pendiente."""
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
# Helpers de Base de Datos
# ──────────────────────────────────────────────────────────────

def _row_to_client(row: Dict, payments: list[dict]) -> dict:
    """Convierte una fila de PostgreSQL al formato ClientResponse."""
    return {
        "id":           row["id"],
        "cedula":       row["cedula"],
        "name":         row["name"],
        "phone":        row["phone"],
        "initialDebt":  float(row["initial_debt"]),
        "startDate":    row["start_date"].isoformat() if hasattr(row["start_date"], "isoformat") else row["start_date"],
        "interestRate": float(row["interest_rate"]),
        "interestType": row["interest_type"],
        "notes":        row["notes"],
        "payments":     payments,
    }


def _row_to_payment(row: Dict) -> dict:
    return {
        "id":        row["id"],
        "client_id": row["client_id"],
        "amount":    float(row["amount"]),
        "date":      row["date"].isoformat() if hasattr(row["date"], "isoformat") else row["date"],
    }


def _fetch_payments(conn, client_id: str) -> list[dict]:
    """Obtiene abonos ordenados del más reciente al más antiguo."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, client_id, amount, date FROM payments "
            "WHERE client_id = %s ORDER BY date DESC",
            (client_id,),  # ← Parámetro seguro (%s para PostgreSQL)
        )
        rows = cur.fetchall()
    return [_row_to_payment(r) for r in rows]


# ──────────────────────────────────────────────────────────────
# Servicio de Archivos Estáticos (Frontend)
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

@app.get(
    "/api/clientes",
    response_model=List[ClientResponse],
    summary="Lista todos los clientes con su historial de abonos",
)
def get_clients(conn=Depends(get_db)):
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, cedula, name, phone, initial_debt, start_date, "
                "interest_rate, interest_type, notes FROM clientes ORDER BY name ASC"
            )
            rows = cur.fetchall()

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


@app.post(
    "/api/clientes",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registra un nuevo cliente",
)
def create_client(client: ClientCreate, conn=Depends(get_db)):
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
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO clientes
                    (id, cedula, name, phone, initial_debt, start_date,
                     interest_rate, interest_type, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    new_id,
                    client.cedula,
                    safe_name,
                    safe_phone,
                    client.initial_debt,
                    client.start_date,
                    client.interest_rate,
                    client.interest_type,
                    safe_notes,
                ),  # ← Parámetros seguros (%s para PostgreSQL)
            )
        conn.commit()

    except psycopg2.IntegrityError as exc:
        conn.rollback()
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

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, cedula, name, phone, initial_debt, start_date, "
            "interest_rate, interest_type, notes FROM clientes WHERE id = %s",
            (new_id,),
        )
        row = cur.fetchone()

    return _row_to_client(row, [])


@app.put(
    "/api/clientes/{client_id}",
    response_model=ClientResponse,
    summary="Actualiza los datos de un cliente existente",
)
def update_client(client_id: str, client_update: ClientUpdate, conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM clientes WHERE id = %s",
            (client_id,),
        )
        existing = cur.fetchone()

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado.",
        )

    update_data = client_update.model_dump(exclude_unset=True, by_alias=False)

    if not update_data:
        payments = _fetch_payments(conn, client_id)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, cedula, name, phone, initial_debt, start_date, "
                "interest_rate, interest_type, notes FROM clientes WHERE id = %s",
                (client_id,),
            )
            row = cur.fetchone()
        return _row_to_client(row, payments)

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
        set_clauses.append(f"{col} = %s")  # ← %s para PostgreSQL
        params.append(value)

    if not set_clauses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se proporcionaron campos válidos para actualizar.",
        )

    params.append(client_id)

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE clientes SET {', '.join(set_clauses)} WHERE id = %s",
                tuple(params),
            )
        conn.commit()
    except psycopg2.IntegrityError as exc:
        conn.rollback()
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

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, cedula, name, phone, initial_debt, start_date, "
            "interest_rate, interest_type, notes FROM clientes WHERE id = %s",
            (client_id,),
        )
        row = cur.fetchone()
    payments = _fetch_payments(conn, client_id)
    return _row_to_client(row, payments)


@app.delete(
    "/api/clientes/{client_id}",
    status_code=status.HTTP_200_OK,
    summary="Elimina un cliente y todo su historial de abonos (CASCADE)",
)
def delete_client(client_id: str, conn=Depends(get_db)):
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM clientes WHERE id = %s",
                (client_id,),
            )
            rowcount = cur.rowcount
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error("delete_client — error interno: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al eliminar el cliente.",
        )

    if rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado.",
        )

    return {"message": "Cliente y sus abonos eliminados correctamente."}


@app.post(
    "/api/clientes/{client_id}/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registra un abono para un cliente existente",
)
def create_payment(client_id: str, payment: PaymentCreate, conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, initial_debt, start_date, interest_rate, interest_type "
            "FROM clientes WHERE id = %s",
            (client_id,),
        )
        client_row = cur.fetchone()

    if not client_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado.",
        )

    if not (isinstance(payment.amount, (int, float)) and payment.amount > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El monto del abono debe ser un número positivo.",
        )

    financials = get_client_financials(
        conn,
        client_id,
        client_row["initial_debt"],
        str(client_row["start_date"]),
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
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO payments (id, client_id, amount, date) VALUES (%s, %s, %s, %s)",
                (new_payment_id, client_id, payment.amount, payment.date),
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
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
