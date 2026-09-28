import os
import sys
import uuid
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
import httpx
from fastapi import FastAPI, HTTPException, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client

# Asegurar codificación utf-8 para caracteres especiales y emojis en Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

app = FastAPI(title="ProsperAI - Clinic EHR Engine")

# Habilitar CORS para que el dashboard de Next.js pueda comunicarse sin bloqueos
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Conexión a Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Modelos
class SlotSearch(BaseModel):
    specialty: str
    date: str

class BookRequest(BaseModel):
    slot_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    patient_name: Optional[str] = None
    phone: str
    patient_dob: str
    insurance_payer: Optional[str] = None
    insurance_member_id: Optional[str] = None

class VerifyInsuranceRequest(BaseModel):
    payer: str
    member_id: str
    patient_dob: str

# Slots predeterminados en memoria para pruebas rápidas
AVAILABLE_SLOTS = [
    {"id": "slot-01", "doctor": "Dr. Sarah Adams", "specialty": "primary care", "time": "2026-09-25 10:00 AM", "status": "available"},
    {"id": "slot-02", "doctor": "Dr. Sarah Adams", "specialty": "primary care", "time": "2026-09-25 02:30 PM", "status": "available"},
    {"id": "slot-03", "doctor": "Dr. Robert Chen", "specialty": "cardiology", "time": "2026-09-26 11:00 AM", "status": "available"}
]

# Registro local en memoria como fallback si Supabase tiene restricciones RLS o cortes de red
LOCAL_CALLS = []

async def send_telegram_appointment_notification(data: dict) -> bool:
    """Envía la confirmación de la cita médica directamente por Telegram."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    is_recovery = data.get("type") == "cancellation_recovered"
    header = "🎉 <b>¡CITA RECUPERADA POR LISTA DE ESPERA!</b>" if is_recovery else "🏥 <b>CONFIRMACIÓN DE CITA - METROHEALTH CLINIC</b>"

    message = (
        f"{header}\n\n"
        f"👤 <b>Paciente:</b> {data.get('patient_name')}\n"
        f"🎂 <b>Fecha Nac.:</b> {data.get('patient_dob', 'N/A')}\n"
        f"📞 <b>Teléfono:</b> {data.get('phone', 'N/A')}\n"
        f"🛡️ <b>Seguro:</b> {data.get('insurance', 'N/A')}\n"
        f"──────────────────────────\n"
        f"🩺 <b>Doctor/a:</b> {data.get('doctor')}\n"
        f"🏷️ <b>Especialidad:</b> {data.get('specialty')}\n"
        f"📅 <b>Fecha y Hora:</b> {data.get('time')}\n"
        f"🔑 <b>Código de Reserva:</b> <code>{data.get('confirmation')}</code>\n\n"
        f"📍 <i>MetroHealth Clinic, Suite 300\n"
        f"Le recordamos acudir 10 minutos antes de su cita.</i>"
    )

    if not bot_token or not chat_id:
        print("\n" + "="*65)
        print(" [TELEGRAM SIMULADOR] (Configura TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en .env)")
        print(f" Destinatario Chat ID: {chat_id or 'No configurado en .env'}")
        print(" Texto del mensaje preparado para el paciente:")
        clean_text = (
            message.replace("<b>", "")
            .replace("</b>", "")
            .replace("<code>", "")
            .replace("</code>", "")
            .replace("<i>", "")
            .replace("</i>", "")
        )
        try:
            print(clean_text)
        except Exception:
            print(clean_text.encode("ascii", errors="replace").decode("ascii"))
        print("="*65 + "\n")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                print(f"[TELEGRAM] ✅ Notificación enviada con éxito a Telegram (chat_id: {chat_id})")
                return True
            else:
                print(f"[TELEGRAM ERROR] Código {resp.status_code}: {resp.text}")
                return False
    except Exception as exc:
        print(f"[TELEGRAM EXCEPCIÓN] Error enviando mensaje a Telegram: {exc}")
        return False

@app.get("/")
def health_check():
    """Endpoint de estado del servicio."""
    return {
        "service": "ProsperAI Clinic EHR Engine",
        "status": "online",
        "available_endpoints": [
            "GET  /slots/available",
            "POST /slots/book",
            "POST /insurance/verify",
            "POST /cancellations/trigger-recovery",
            "POST /notifications/test-telegram",
            "GET  /telemetry/live-calls"
        ]
    }

@app.get("/slots/available")
def get_available_slots(specialty: str):
    """El agente consulta qué horarios existen según la especialidad solicitada."""
    matches = [s for s in AVAILABLE_SLOTS if s["status"] == "available" and specialty.lower() in s["specialty"].lower()]
    return {"status": "success", "count": len(matches), "slots": matches}

@app.post("/slots/book")
def book_slot(req: BookRequest, background_tasks: BackgroundTasks):
    """El agente confirma y reserva el horario verificando y guardando doctor, especialidad, horario y fecha de nacimiento."""
    full_name = ""
    if req.first_name and req.last_name:
        full_name = f"{req.first_name.strip()} {req.last_name.strip()}"
    elif req.patient_name:
        full_name = req.patient_name.strip()

    if not full_name:
        raise HTTPException(status_code=400, detail="Nombre y Apellidos son obligatorios para reservar.")
    if not req.phone:
        raise HTTPException(status_code=400, detail="El número de teléfono es obligatorio.")
    if not req.patient_dob:
        raise HTTPException(status_code=400, detail="La fecha de nacimiento (birth date) es obligatoria.")

    for s in AVAILABLE_SLOTS:
        if s["id"] == req.slot_id and s["status"] == "available":
            s["status"] = "booked"
            s["booked_by"] = full_name
            confirmation_code = f"CONF-{uuid.uuid4().hex[:6].upper()}"

            # 1. Guardar o actualizar datos del paciente en Supabase (tabla 'patients')
            patient_id = None
            try:
                patient_payload = {
                    "full_name": full_name,
                    "phone": req.phone.strip(),
                    "dob": req.patient_dob.strip(),
                    "insurance_payer": req.insurance_payer or "Self-Pay",
                    "insurance_member_id": req.insurance_member_id or "N/A",
                    "insurance_status": "verified" if req.insurance_member_id else "pending"
                }
                existing = supabase.table("patients").select("id").eq("phone", req.phone.strip()).limit(1).execute()
                if existing.data:
                    patient_id = existing.data[0]["id"]
                    supabase.table("patients").update(patient_payload).eq("id", patient_id).execute()
                else:
                    patient_id = str(uuid.uuid4())
                    patient_payload["id"] = patient_id
                    supabase.table("patients").insert(patient_payload).execute()
            except Exception as exc:
                print(f"[ALERTA SUPABASE] No se pudo guardar paciente en tabla 'patients': {exc}")

            # 2. Registrar llamada con metadata completa de la cita
            appointment_info = {
                "doctor": s["doctor"],
                "specialty": s["specialty"],
                "appointment_time": s["time"],
                "slot_id": s["id"],
                "patient_dob": req.patient_dob
            }

            call_record = {
                "id": str(uuid.uuid4()),
                "direction": "inbound",
                "patient_id": patient_id,
                "patient_info": {
                    "full_name": full_name,
                    "phone": req.phone,
                    "dob": req.patient_dob,
                    "insurance": f"{req.insurance_payer} ({req.insurance_member_id})" if req.insurance_payer else "N/A"
                },
                "appointment": appointment_info,
                "outcome": "booked",
                "duration_seconds": 135,
                "avg_latency_ms": 740,
                "cost_usd": 0.2850,
                "transcript": [
                    {
                        "role": "assistant",
                        "content": f"Appointment booked with {s['doctor']} ({s['specialty']}) on {s['time']} for {full_name} (DOB: {req.patient_dob}). Phone: {req.phone}.",
                        "appointment": appointment_info
                    }
                ],
                "started_at": datetime.now().isoformat()
            }
            LOCAL_CALLS.insert(0, call_record)
            
            # Registrar llamada resuelta en Supabase (tolerante a fallos si RLS bloquea anon)
            try:
                supabase.table("calls").insert({
                    "direction": call_record["direction"],
                    "patient_id": patient_id,
                    "outcome": call_record["outcome"],
                    "duration_seconds": call_record["duration_seconds"],
                    "avg_latency_ms": call_record["avg_latency_ms"],
                    "cost_usd": call_record["cost_usd"],
                    "transcript": call_record["transcript"]
                }).execute()
            except Exception as exc:
                print(f"[ALERTA SUPABASE] No se pudo guardar en Supabase (verifique políticas RLS en 'calls'): {exc}")

            # 3. Disparar notificación por Telegram en segundo plano
            background_tasks.add_task(send_telegram_appointment_notification, {
                "type": "appointment_confirmed",
                "patient_name": full_name,
                "patient_dob": req.patient_dob,
                "phone": req.phone,
                "insurance": f"{req.insurance_payer} ({req.insurance_member_id})" if req.insurance_payer else "N/A",
                "doctor": s["doctor"],
                "specialty": s["specialty"],
                "time": s["time"],
                "confirmation": confirmation_code
            })

            return {
                "confirmation": confirmation_code,
                "doctor": s["doctor"],
                "specialty": s["specialty"],
                "time": s["time"],
                "patient": full_name,
                "patient_dob": req.patient_dob,
                "phone": req.phone,
                "insurance": f"{req.insurance_payer} ({req.insurance_member_id})" if req.insurance_payer else "N/A",
                "telegram_notification": "queued"
            }
    raise HTTPException(status_code=400, detail="Slot no disponible")

@app.post("/insurance/verify")
def verify_insurance(req: VerifyInsuranceRequest):
    """Valida cobertura y copago en tiempo real."""
    # Regla mock: ID terminado en número par = cobertura activa
    last_char = req.member_id[-1] if req.member_id else ""
    is_covered = last_char.isdigit() and int(last_char) % 2 == 0

    if is_covered:
        return {
            "eligible": True,
            "payer": req.payer,
            "copay_usd": 25.0,
            "deductible_met": True,
            "requires_referral": False,
            "note": "Standard copay applies at check-in"
        }
    return {
        "eligible": False,
        "payer": req.payer,
        "reason": "Policy inactive or invalid Member ID",
        "action": "Needs human verification"
    }

@app.post("/cancellations/trigger-recovery")
def trigger_cancellation(slot_id: str, background_tasks: BackgroundTasks):
    """
    Simula una cancelación:
    1. Libera el slot.
    2. Consulta el primer paciente en waitlist de Supabase (o fallback).
    3. Retorna la orden para disparar la llamada proactiva de recuperación y envía Telegram.
    """
    for s in AVAILABLE_SLOTS:
        if s["id"] == slot_id:
            s["status"] = "available"
            s.pop("booked_by", None)
            
            # Buscar en waitlist de Supabase
            patient_to_call = None
            try:
                response = supabase.table("waitlist").select("*, patients(*)").eq("status", "waiting").order("priority").limit(1).execute()
                if response.data and response.data[0].get("patients"):
                    patient_to_call = response.data[0]["patients"]
            except Exception as exc:
                print(f"[ALERTA SUPABASE] Error consultando waitlist: {exc}")
            
            # Fallback demostrativo si la base de datos aún no tiene registros en waitlist
            if not patient_to_call:
                patient_to_call = {
                    "id": "pat-waitlist-01",
                    "full_name": "Maria Garcia",
                    "phone": "+1 (555) 987-6543",
                    "dob": "1988-06-20",
                    "priority": 1,
                    "reason": "Waiting for primary care cancellation"
                }

            # Registrar la llamada saliente proactiva (Outbound Recovery) en telemetría
            outbound_appointment = {
                "doctor": s["doctor"],
                "specialty": s["specialty"],
                "appointment_time": s["time"],
                "slot_id": s["id"],
                "patient_dob": patient_to_call.get("dob", "1988-06-20")
            }

            outbound_call = {
                "id": str(uuid.uuid4()),
                "direction": "outbound",
                "outcome": "recovered",
                "duration_seconds": 85,
                "avg_latency_ms": 620,
                "cost_usd": 0.1950,
                "patient_info": {
                    "full_name": patient_to_call.get("full_name"),
                    "phone": patient_to_call.get("phone"),
                    "dob": patient_to_call.get("dob", "1988-06-20"),
                    "insurance": "In-network"
                },
                "appointment": outbound_appointment,
                "transcript": [
                    {
                        "role": "assistant",
                        "content": f"Outbound call to {patient_to_call.get('full_name')} for {s['doctor']} ({s['specialty']} on {s['time']}). Patient accepted rebooking.",
                        "appointment": outbound_appointment
                    }
                ],
                "started_at": datetime.now().isoformat()
            }
            LOCAL_CALLS.insert(0, outbound_call)

            try:
                supabase.table("calls").insert({
                    "direction": outbound_call["direction"],
                    "outcome": outbound_call["outcome"],
                    "duration_seconds": outbound_call["duration_seconds"],
                    "avg_latency_ms": outbound_call["avg_latency_ms"],
                    "cost_usd": outbound_call["cost_usd"],
                    "transcript": outbound_call["transcript"]
                }).execute()
            except Exception as exc:
                print(f"[ALERTA SUPABASE] No se pudo guardar llamada saliente: {exc}")

            recovery_code = f"REC-{uuid.uuid4().hex[:6].upper()}"

            # Disparar notificación por Telegram
            background_tasks.add_task(send_telegram_appointment_notification, {
                "type": "cancellation_recovered",
                "patient_name": patient_to_call.get("full_name"),
                "patient_dob": patient_to_call.get("dob", "1988-06-20"),
                "phone": patient_to_call.get("phone"),
                "insurance": "In-network (Verified)",
                "doctor": s["doctor"],
                "specialty": s["specialty"],
                "time": s["time"],
                "confirmation": recovery_code
            })

            return {
                "message": "Cancellation processed. Slot reopened and rebooked via proactive call.",
                "reopened_slot": s,
                "target_patient_for_call": patient_to_call,
                "call_logged": outbound_call,
                "telegram_notification": "queued"
            }
            
    raise HTTPException(status_code=404, detail="Slot ID no encontrado")

@app.post("/notifications/test-telegram")
async def test_telegram_notification():
    """Endpoint interactivo para probar el bot de Telegram."""
    test_data = {
        "type": "appointment_confirmed",
        "patient_name": "Juan Perez",
        "patient_dob": "1985-04-12",
        "phone": "+1 (555) 234-5678",
        "insurance": "Aetna (AET12348)",
        "doctor": "Dr. Sarah Adams",
        "specialty": "primary care",
        "time": "2026-09-25 10:00 AM",
        "confirmation": "CONF-TELEGRAM"
    }
    sent = await send_telegram_appointment_notification(test_data)
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    return {
        "sent": sent,
        "bot_configured": bool(bot_token and chat_id),
        "chat_id": chat_id,
        "message": (
            "Notificación enviada con éxito a Telegram"
            if sent
            else "Mensaje simulado en consola. Configura TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en tu archivo .env para recibirlo en tu Telegram real."
        )
    }

@app.get("/telemetry/live-calls")
def get_live_metrics(response: Response, t: Optional[str] = None):
    """Consulta métricas para el dashboard garantizando datos en tiempo real sin caché."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    try:
        res = supabase.table("calls").select("*, patients(*)").order("started_at", desc=True).limit(15).execute()
        if res.data:
            for c in res.data:
                if not c.get("appointment") and c.get("transcript"):
                    for item in c["transcript"]:
                        if isinstance(item, dict) and item.get("appointment"):
                            c["appointment"] = item["appointment"]
                            break
            return {"calls": res.data, "source": "supabase"}
    except Exception as exc:
        print(f"[ALERTA SUPABASE] No se pudieron obtener llamadas de Supabase: {exc}")

    return {"calls": LOCAL_CALLS[:15], "source": "local_memory"}