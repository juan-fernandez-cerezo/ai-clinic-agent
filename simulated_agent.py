# simulated_agent.py
import sys
import httpx

# Asegurar codificación utf-8 en terminales Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_URL = "http://127.0.0.1:8000"

def verify_server_online():
    """Comprueba que el backend FastAPI esté ejecutándose antes de iniciar."""
    try:
        res = httpx.get(f"{BASE_URL}/", timeout=2.0)
        return res.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False

def run_inbound_call_simulation():
    print("\n" + "="*65)
    print(" [1] SIMULACION DE LLAMADA ENTRANTE (Paciente solicitando cita)")
    print("="*65)
    
    # 1. El paciente pide cita con Primary Care
    print("\n[PACIENTE]: 'Hi, I need an appointment for a general checkup this week.'")
    res = httpx.get(f"{BASE_URL}/slots/available", params={"specialty": "primary care"})
    if res.status_code != 200:
        print(f"[ERROR] Error al consultar slots ({res.status_code}): {res.text}")
        return

    data = res.json()
    available_slots = data.get("slots", [])
    if not available_slots:
        print("[AGENTE CLARA]: 'I'm sorry, I couldn't find an available primary care appointment this week.'")
        return

    chosen_slot = available_slots[0]
    print(f"[AGENTE CLARA]: 'I found an opening with {chosen_slot['doctor']} on {chosen_slot['time']}. Does that work?'")
    
    # 2. Validación de seguro médico y recogida de datos
    print("\n[PACIENTE]: 'Yes, that works! My name is Juan Perez, phone is +1 (555) 234-5678, and I have Aetna insurance, ID is AET12348.'")
    ins_res = httpx.post(f"{BASE_URL}/insurance/verify", json={
        "payer": "Aetna",
        "member_id": "AET12348",
        "patient_dob": "1985-04-12"
    })
    
    if ins_res.status_code == 200:
        ins_data = ins_res.json()
        if ins_data.get("eligible"):
            print(f"[AGENTE CLARA]: 'Great! Your {ins_data['payer']} coverage is verified. Your copay is ${ins_data['copay_usd']:.2f}.'")
        else:
            print(f"[AGENTE CLARA]: 'We could not verify your policy automatically ({ins_data.get('reason')}). Transferring to reception...'")
            return
    else:
        print(f"[ERROR] Error validando seguro: {ins_res.text}")
        return
    
    # 3. Reserva del horario con los 4 campos validados
    print("\n[PACIENTE]: 'Perfect, please confirm the appointment.'")
    book_res = httpx.post(f"{BASE_URL}/slots/book", json={
        "slot_id": chosen_slot["id"],
        "first_name": "Juan",
        "last_name": "Perez",
        "phone": "+1 (555) 234-5678",
        "insurance_payer": "Aetna",
        "insurance_member_id": "AET12348",
        "patient_dob": "1985-04-12"
    })
    
    if book_res.status_code == 200:
        book_data = book_res.json()
        print(f"[AGENTE CLARA]: 'You are all set, Juan Perez! Your confirmation code is {book_data['confirmation']}.'")
        print(f"   [CITA CONFIRMADA]: 🩺 {book_data['doctor']} ({book_data.get('specialty')}) | 📅 {book_data['time']}")
        print(f"   [DATOS PACIENTE]: 👤 {book_data.get('patient')} | 🎂 DOB: {book_data.get('patient_dob')} | 📞 Tel: {book_data.get('phone')} | 🛡️ Seguro: {book_data.get('insurance')}")
    else:
        print(f"[ERROR] Error al reservar slot: {book_res.status_code} - {book_res.text}")

def run_proactive_cancellation_demo():
    print("\n" + "="*65)
    print(" [2] SIMULACION DE RECUPERACION PROACTIVA (No-Show / Cancelacion)")
    print("="*65)
    print("[INFO] Simulando que el paciente anterior cancela slot-01...")
    
    res = httpx.post(f"{BASE_URL}/cancellations/trigger-recovery", params={"slot_id": "slot-01"})
    if res.status_code != 200:
        print(f"[ERROR] Error en trigger de cancelacion: {res.status_code} - {res.text}")
        return

    data = res.json()
    target = data.get("target_patient_for_call")
    slot = data.get("reopened_slot")
    
    if target and slot:
        print(f"\n[EVENTO DISPARADO] Hueco reabierto: {slot['id']} con {slot['doctor']} ({slot['time']})")
        print(f"[WORKFLOW PROACTIVO] Disparando llamada saliente inmediata a paciente en lista de espera:")
        print(f"   - Paciente: {target.get('full_name')} ({target.get('phone')})")
        print(f"[AGENTE CLARA SALIENTE]: 'Hi {target.get('full_name')}, a spot just opened up with {slot['doctor']} for {slot['time']}. As you were on our priority waitlist, would you like to take it?'")
    else:
        print("[INFO] No hay pacientes en espera en este momento.")

def show_live_telemetry():
    print("\n" + "="*65)
    print(" [3] TELEMETRIA EN TIEMPO REAL (Metricas registradas)")
    print("="*65)
    res = httpx.get(f"{BASE_URL}/telemetry/live-calls")
    if res.status_code == 200:
        data = res.json()
        calls = data.get("calls", [])
        source = data.get("source", "desconocido")
        print(f"Origen de datos: {source.upper()} (Total registradas: {len(calls)})")
        for i, call in enumerate(calls[:3], 1):
            direction = call.get("direction", "N/A")
            outcome = call.get("outcome", "N/A")
            dur = call.get("duration_seconds", 0)
            latency = call.get("avg_latency_ms", 0)
            cost = call.get("cost_usd", 0.0)
            print(f"  {i}. [{direction.upper()}] Resultado: {outcome} | Duracion: {dur}s | Latencia: {latency}ms | Coste: ${cost:.4f}")
    else:
        print(f"[ERROR] Error al consultar telemetria: {res.status_code}")

if __name__ == "__main__":
    if not verify_server_online():
        print("\n[ERROR] El servidor de la clinica no esta en ejecucion en http://127.0.0.1:8000")
        print("[INFO] Por favor, inicia el servidor en una terminal con:")
        print("   .\\venv\\Scripts\\uvicorn.exe ehr_api:app --reload")
        print("   o ejecuta el script start_server.bat")
        sys.exit(1)
        
    run_inbound_call_simulation()
    run_proactive_cancellation_demo()
    show_live_telemetry()