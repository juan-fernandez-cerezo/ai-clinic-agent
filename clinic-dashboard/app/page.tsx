'use client';

import { useState, useEffect } from 'react';
import '@livekit/components-styles';
import {
  LiveKitRoom,
  RoomAudioRenderer,
  VoiceAssistantControlBar,
  useVoiceAssistant,
} from '@livekit/components-react';

interface CallRecord {
  id: string;
  direction: string;
  outcome: string;
  duration_seconds: number;
  avg_latency_ms: number;
  cost_usd: number;
  started_at: string;
  patient_info?: {
    full_name: string;
    phone: string;
    dob?: string;
    insurance: string;
  };
  patients?: {
    full_name: string;
    phone: string;
    dob?: string;
    insurance_payer: string;
    insurance_member_id: string;
  } | null;
  appointment?: {
    doctor: string;
    specialty: string;
    appointment_time: string;
    slot_id?: string;
    patient_dob?: string;
  };
}

function ActiveVoiceSession({ onHangUp }: { onHangUp: () => void }) {
  const { state, agent } = useVoiceAssistant();

  const stateColors: Record<string, string> = {
    speaking: 'bg-emerald-400 animate-pulse',
    listening: 'bg-sky-400 animate-pulse',
    thinking: 'bg-amber-400 animate-pulse',
    connecting: 'bg-yellow-400 animate-ping',
    disconnected: 'bg-rose-500',
  };

  const stateLabels: Record<string, string> = {
    speaking: '🗣️ Clara está hablando...',
    listening: '👂 Clara te escucha (habla por el micrófono)...',
    thinking: '⏳ Clara está consultando los datos...',
    connecting: '🟡 Conectando con Clara...',
    disconnected: 'Desconectado',
  };

  return (
    <div className="flex flex-col sm:flex-row items-center gap-4 bg-slate-900 border border-slate-700/80 px-4 py-3 rounded-xl shadow-lg">
      <div className="flex items-center gap-3">
        <span className={`h-3 w-3 rounded-full ${stateColors[state] || 'bg-emerald-400'}`} />
        <div>
          <p className="text-sm font-semibold text-white">
            {stateLabels[state] || '🟢 En llamada con Clara'}
          </p>
          <p className="text-xs text-slate-400">
            {agent ? 'Agente de voz activo: Clara (LiveKit AI)' : 'Conectando con el agente Clara en LiveKit Cloud...'}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <VoiceAssistantControlBar controls={{ leave: false }} />
        <button
          onClick={onHangUp}
          className="bg-rose-600 hover:bg-rose-500 text-white font-medium text-xs px-3.5 py-2 rounded-lg transition shadow flex items-center gap-1.5 cursor-pointer"
        >
          🛑 Colgar
        </button>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [token, setToken] = useState<string>('');
  const [url, setUrl] = useState<string>('');
  const [inCall, setInCall] = useState<boolean>(false);
  const [connecting, setConnecting] = useState<boolean>(false);
  const [callError, setCallError] = useState<string | null>(null);
  const [calls, setCalls] = useState<CallRecord[]>([]);

  useEffect(() => {
    let isMounted = true;

    const fetchTelemetry = async () => {
      try {
        const candidateUrls = [
          `/api/ehr/telemetry/live-calls?_t=${Date.now()}`,
          `http://localhost:8000/telemetry/live-calls?_t=${Date.now()}`,
          `http://127.0.0.1:8000/telemetry/live-calls?_t=${Date.now()}`,
        ];

        for (const targetUrl of candidateUrls) {
          try {
            const res = await fetch(targetUrl, { cache: 'no-store' });
            if (res.ok) {
              const data = await res.json();
              if (isMounted) {
                setCalls(data.calls || []);
              }
              return;
            }
          } catch {
            // probar siguiente endpoint
          }
        }
      } catch {
        // Backend apagado o desconectado
      }
    };

    void fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 3000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Iniciar llamada de prueba por el navegador
  const startCall = async () => {
    setCallError(null);
    setConnecting(true);
    try {
      const roomName = `clinic-call-${Date.now()}`;
      const res = await fetch(`/api/token?room=${roomName}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setToken(data.token);
      setUrl(data.wsUrl);
      setInCall(true);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Error desconocido';
      console.error('Error al generar token:', e);
      setCallError(`Error al iniciar llamada: ${message}`);
    } finally {
      setConnecting(false);
    }
  };

  const endCall = () => {
    setInCall(false);
    setToken('');
    setUrl('');
  };

  const triggerCancellation = async () => {
    const candidateUrls = [
      `/api/ehr/cancellations/trigger-recovery?slot_id=slot-01&_t=${Date.now()}`,
      `http://localhost:8000/cancellations/trigger-recovery?slot_id=slot-01&_t=${Date.now()}`,
      `http://127.0.0.1:8000/cancellations/trigger-recovery?slot_id=slot-01&_t=${Date.now()}`,
    ];

    for (const targetUrl of candidateUrls) {
      try {
        const res = await fetch(targetUrl, { method: 'POST' });
        if (res.ok) {
          alert('¡Cancelación procesada! El hueco ha quedado libre y se ha registrado la llamada de recuperación.');
          return;
        }
      } catch {
        // intentar siguiente
      }
    }
  };

  const totalCost = calls.reduce((acc, c) => acc + Number(c.cost_usd), 0);
  const avgLatency = calls.length
    ? Math.round(calls.reduce((acc, c) => acc + c.avg_latency_ms, 0) / calls.length)
    : 720;

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 p-8 font-sans">
      <div className="max-w-6xl mx-auto space-y-8">
        
        {/* Encabezado */}
        <header className="flex justify-between items-center border-b border-slate-800 pb-5">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">ProsperAI • Clinic Voice Ops</h1>
            <p className="text-sm text-slate-400">Autonomous Patient Navigation & Real-Time Telemetry</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="flex h-3 w-3 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
            </span>
            <span className="text-xs uppercase tracking-wider font-semibold text-emerald-400">Clara Online (Voice Agent)</span>
          </div>
        </header>

        {/* Sección de Prueba de Voz WebRTC (Gratis / Sin Twilio) */}
        <section className="bg-slate-800/80 border border-slate-700 p-6 rounded-xl flex flex-col md:flex-row items-center justify-between gap-6 shadow-lg">
          <div>
            <h2 className="text-lg font-semibold text-white">Test Patient Phone Call (In-Browser WebRTC)</h2>
            <p className="text-sm text-slate-400 mt-1 max-w-xl">
              Prueba hablar en tiempo real con Clara usando tu micrófono. Pídele cita para medicina primaria, dale tu seguro Aetna (ID: AET12348) y verifica cómo gestiona la reserva.
            </p>
            {callError && (
              <p className="text-xs text-rose-400 mt-2 bg-rose-500/10 border border-rose-500/20 px-3 py-1.5 rounded-lg inline-block">
                ⚠️ {callError}
              </p>
            )}
          </div>
          <div>
            {!inCall ? (
              <button
                onClick={startCall}
                disabled={connecting}
                className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium px-5 py-2.5 rounded-lg shadow transition flex items-center gap-2 cursor-pointer"
              >
                {connecting ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                    <span>Conectando...</span>
                  </>
                ) : (
                  <span>📞 Start Test Call</span>
                )}
              </button>
            ) : (
              <LiveKitRoom
                serverUrl={url}
                token={token}
                connect={true}
                video={false}
                audio={true}
                onDisconnected={endCall}
                onError={(err) => setCallError(`Error en conexión WebRTC: ${err.message}`)}
                data-lk-theme="default"
                className="flex items-center justify-end"
              >
                <RoomAudioRenderer />
                <ActiveVoiceSession onHangUp={endCall} />
              </LiveKitRoom>
            )}
          </div>
        </section>

        {/* Tarjetas de Métricas de Negocio */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-slate-800/50 border border-slate-700/60 p-5 rounded-lg">
            <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Total Handled Calls</p>
            <p className="text-3xl font-bold mt-2 text-white">{calls.length}</p>
            <p className="text-xs text-emerald-400 mt-1">100% First-Call Resolution</p>
          </div>
          <div className="bg-slate-800/50 border border-slate-700/60 p-5 rounded-lg">
            <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Voice Latency</p>
            <p className="text-3xl font-bold mt-2 text-sky-400">{avgLatency} ms</p>
            <p className="text-xs text-slate-400 mt-1">Target &lt;800ms (Barge-in ready)</p>
          </div>
          <div className="bg-slate-800/50 border border-slate-700/60 p-5 rounded-lg">
            <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold">AI Operating Cost</p>
            <p className="text-3xl font-bold mt-2 text-emerald-400">${totalCost.toFixed(4)}</p>
            <p className="text-xs text-slate-400 mt-1">~$0.28 / call average</p>
          </div>
          <div className="bg-slate-800/50 border border-slate-700/60 p-5 rounded-lg">
            <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Clinic Savings</p>
            <p className="text-3xl font-bold mt-2 text-purple-400">
              ${Math.max(0, calls.length * 2.25 - totalCost).toFixed(2)}
            </p>
            <p className="text-xs text-slate-400 mt-1">Vs. human reception ($2.25/call)</p>
          </div>
        </div>

        {/* Feed de Llamadas y Botón de Cancelación Proactiva */}
        <section className="bg-slate-800/50 border border-slate-700/60 rounded-xl overflow-hidden shadow-sm">
          <div className="p-4 border-b border-slate-700 flex flex-wrap gap-4 justify-between items-center bg-slate-800/70">
            <div>
              <h2 className="font-semibold text-white">Live Call Telemetry & Audit Log</h2>
              <p className="text-xs text-slate-400">Auditoría en tiempo real para recepcionistas y supervisores</p>
            </div>
            <button
              onClick={triggerCancellation}
              className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs px-3.5 py-2 rounded-md font-medium transition shadow"
            >
              ⚡ Simulate Cancellation (Triggers Rebooking)
            </button>
          </div>

          <table className="w-full text-left text-sm">
            <thead className="bg-slate-800/90 text-slate-400 uppercase text-xs border-b border-slate-700">
              <tr>
                <th className="py-3 px-4">Direction</th>
                <th className="py-3 px-4">Patient & DOB</th>
                <th className="py-3 px-4">Doctor & Specialty</th>
                <th className="py-3 px-4">Appointment Time</th>
                <th className="py-3 px-4">Insurance</th>
                <th className="py-3 px-4">Outcome</th>
                <th className="py-3 px-4">Latency / Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {calls.map((c) => (
                <tr key={c.id} className="hover:bg-slate-800/30 transition">
                  <td className="py-3 px-4 font-mono text-xs uppercase text-slate-300">
                    <span className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                      c.direction === 'inbound' ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20' : 'bg-purple-500/10 text-purple-400 border border-purple-500/20'
                    }`}>
                      {c.direction}
                    </span>
                    <p className="text-[11px] text-slate-500 mt-1">
                      {new Date(c.started_at).toLocaleTimeString()}
                    </p>
                  </td>
                  <td className="py-3 px-4">
                    <div>
                      <p className="font-semibold text-white text-xs">
                        {c.patients?.full_name || c.patient_info?.full_name || 'Anonymous Patient'}
                      </p>
                      <p className="text-slate-400 text-xs mt-0.5">
                        🎂 DOB: <span className="text-slate-200">{c.patients?.dob || c.patient_info?.dob || c.appointment?.patient_dob || 'N/A'}</span>
                      </p>
                      <p className="text-slate-400 text-xs">
                        📞 {c.patients?.phone || c.patient_info?.phone || 'N/A'}
                      </p>
                    </div>
                  </td>
                  <td className="py-3 px-4">
                    <div>
                      <p className="font-medium text-emerald-400 text-xs">
                        🩺 {c.appointment?.doctor || 'Dr. Sarah Adams'}
                      </p>
                      <p className="text-slate-300 text-xs capitalize">
                        🏷️ {c.appointment?.specialty || 'Primary Care'}
                      </p>
                    </div>
                  </td>
                  <td className="py-3 px-4">
                    <div className="text-xs">
                      <p className="text-white font-medium">
                        📅 {c.appointment?.appointment_time || '2026-09-25 10:00 AM'}
                      </p>
                      <p className="text-[11px] text-slate-400 mt-0.5">Duration: {c.duration_seconds}s</p>
                    </div>
                  </td>
                  <td className="py-3 px-4">
                    {c.patients?.insurance_payer ? (
                      <div className="text-xs">
                        <p className="text-sky-400 font-medium">🛡️ {c.patients.insurance_payer}</p>
                        <p className="text-slate-400 font-mono text-[11px]">ID: {c.patients.insurance_member_id}</p>
                      </div>
                    ) : c.patient_info?.insurance ? (
                      <p className="text-sky-400 text-xs">🛡️ {c.patient_info.insurance}</p>
                    ) : (
                      <span className="text-slate-500 text-xs italic">Self-Pay / N/A</span>
                    )}
                  </td>
                  <td className="py-3 px-4">
                    <span className="px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      {c.outcome}
                    </span>
                  </td>
                  <td className="py-3 px-4 font-mono text-xs">
                    <p className="text-sky-400">{c.avg_latency_ms} ms</p>
                    <p className="text-emerald-400">${Number(c.cost_usd).toFixed(4)}</p>
                  </td>
                </tr>
              ))}
              {calls.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500">
                    No calls recorded yet. Click &quot;Start Test Call&quot; or execute the simulation script.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </section>

      </div>
    </div>
  );
}