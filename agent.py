import os
import logging
import httpx
from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    JobProcess,
    TurnHandlingOptions,
    WorkerOptions,
    cli,
    llm,
)
from livekit.plugins import deepgram, openai, cartesia, silero
from supabase import create_client, Client

load_dotenv()
logging.basicConfig(level=logging.INFO)

EHR_BASE_URL = os.getenv("EHR_BASE_URL", "http://127.0.0.1:8000")
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

def prewarm(proc: JobProcess):
    # Carga el detector de actividad por voz (VAD) en memoria
    proc.userdata["vad"] = silero.VAD.load()

# Herramientas clínicas expuestas al LLM (LiveKit Agents 1.0+)
@llm.function_tool(description="Busca horarios de citas médicas disponibles por especialidad.")
async def check_availability(specialty: str) -> str:
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{EHR_BASE_URL}/slots/available", params={"specialty": specialty})
        data = res.json()
        slots = data.get("slots", [])
        if not slots:
            return "No openings found for that specialty this week."
        return "; ".join([f"Slot ID {s['id']}: {s['doctor']} at {s['time']}" for s in slots])

@llm.function_tool(description="Verifica cobertura del seguro de salud y consulta el copago.")
async def verify_insurance(payer: str, member_id: str, patient_dob: str) -> str:
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{EHR_BASE_URL}/insurance/verify",
            json={"payer": payer, "member_id": member_id, "patient_dob": patient_dob}
        )
        data = res.json()
        if data.get("eligible"):
            return f"Coverage verified with {payer}. Copay is ${data.get('copay_usd')}."
        return f"Coverage verification failed: {data.get('reason')}."

@llm.function_tool(
    description=(
        "Confirma formalmente la reserva de la cita médica. "
        "REQUISITOS ESTRICTOS: Debes tener los datos del paciente: "
        "slot_id, first_name (Nombre), last_name (Apellidos), patient_dob (Fecha de nacimiento, ej: '1985-04-12'), "
        "phone (Teléfono), insurance_payer (Aseguradora) y insurance_member_id (Número de póliza). "
        "Si falta cualquiera de ellos, no llames a esta función y pídeselo al paciente."
    )
)
async def book_appointment(
    slot_id: str,
    first_name: str,
    last_name: str,
    patient_dob: str,
    phone: str,
    insurance_payer: str,
    insurance_member_id: str,
) -> str:
    missing = []
    if not first_name or not first_name.strip():
        missing.append("First Name (Nombre)")
    if not last_name or not last_name.strip():
        missing.append("Last Name (Apellidos)")
    if not patient_dob or not patient_dob.strip():
        missing.append("Date of Birth / Birth Date (Fecha de nacimiento)")
    if not phone or not phone.strip():
        missing.append("Phone Number (Teléfono)")
    if not insurance_payer or not insurance_payer.strip():
        missing.append("Insurance Provider (Seguro)")
    if not insurance_member_id or not insurance_member_id.strip():
        missing.append("Insurance Member ID (Número de póliza)")

    if missing:
        return f"CANNOT BOOK YET: Missing mandatory patient details: {', '.join(missing)}. Please ask the caller for these details before calling book_appointment."

    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{EHR_BASE_URL}/slots/book",
            json={
                "slot_id": slot_id,
                "first_name": first_name.strip(),
                "last_name": last_name.strip(),
                "patient_dob": patient_dob.strip(),
                "phone": phone.strip(),
                "insurance_payer": insurance_payer.strip(),
                "insurance_member_id": insurance_member_id.strip(),
            }
        )
        if res.status_code == 200:
            data = res.json()
            return (
                f"Appointment confirmed! Code: {data.get('confirmation')}. "
                f"Doctor: {data.get('doctor')} ({data.get('specialty')}), Date & Time: {data.get('time')}. "
                f"Patient: {first_name} {last_name} (DOB: {patient_dob}), Phone: {phone}, Insurance: {insurance_payer} ({insurance_member_id})."
            )
        return f"Could not complete booking: {res.text}"

@llm.function_tool(description="Escala la llamada a un enfermero o recepcionista humano en caso de emergencia.")
async def escalate_to_human(reason: str) -> str:
    return f"Routing your call immediately to our head clinic nurse due to: {reason}. Please stay on the line."

async def entrypoint(ctx: JobContext):
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    vad_instance = ctx.proc.userdata.get("vad")
    if not vad_instance:
        vad_instance = silero.VAD.load()

    # Definir el agente con sus instrucciones clínicas y herramientas
    clara_agent = Agent(
        instructions=(
            "You are Clara, a friendly and professional virtual receptionist at MetroHealth Clinic in the US. "
            "Speak clearly, concisely, and empathetically. Keep every spoken response under 2 sentences.\n\n"
            "MANDATORY PATIENT INTAKE PROTOCOL:\n"
            "Before you confirm and book any appointment, you MUST collect and verify ALL of the following details:\n"
            "1. First Name (Nombre)\n"
            "2. Last Name (Apellidos)\n"
            "3. Date of Birth / Birth Date (Fecha de nacimiento, e.g. 'April 12, 1985' or '1985-04-12')\n"
            "4. Phone Number (Teléfono)\n"
            "5. Health Insurance Provider & Member ID (Seguro médico - always verify with verify_insurance)\n\n"
            "STRICT RULES:\n"
            "- If the caller gives only their first name (e.g., 'Juan'), ask: 'Thank you Juan, what is your last name and date of birth?'\n"
            "- If birth date, phone number, or insurance are missing, ask for them politely before booking.\n"
            "- Always verify the insurance using verify_insurance before booking.\n"
            "- NEVER call book_appointment until you have confirmed ALL details (First Name, Last Name, Birth Date, Phone, Insurance).\n"
            "- When confirming the booking, clearly state: Doctor, Specialty, Appointment Date & Time, Patient Full Name, Birth Date, and Phone Number.\n\n"
            "If the caller mentions acute chest pain, shortness of breath, or emergency symptoms, "
            "instruct them to call 911 and invoke escalate_to_human."
        ),
        tools=[check_availability, verify_insurance, book_appointment, escalate_to_human],
    )

    # Sesión del agente orquestando VAD, STT, LLM y TTS
    session = AgentSession(
        vad=vad_instance,
        stt=deepgram.STT(model="nova-2", language="en-US"),
        llm=openai.LLM(model="gpt-4o-mini", temperature=0.2),
        tts=cartesia.TTS(),
        turn_handling=TurnHandlingOptions(
            allow_interruptions=True,
            min_interruption_duration=0.35,
        ),
    )

    await session.start(agent=clara_agent, room=ctx.room)
    await session.say(
        "Thank you for calling MetroHealth Clinic. My name is Clara, how can I help you today?",
        allow_interruptions=True
    )

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm, agent_name="clara"))