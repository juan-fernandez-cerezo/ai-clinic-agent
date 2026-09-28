import { AccessToken, AgentDispatchClient } from 'livekit-server-sdk';
import { NextRequest, NextResponse } from 'next/server';

export async function GET(req: NextRequest) {
  const room = req.nextUrl.searchParams.get('room') || 'demo-clinic-room';
  const username = req.nextUrl.searchParams.get('username') || `patient-${Math.floor(Math.random() * 1000)}`;

  const apiKey = process.env.LIVEKIT_API_KEY;
  const apiSecret = process.env.LIVEKIT_API_SECRET;
  const wsUrl = process.env.LIVEKIT_URL;

  if (!apiKey || !apiSecret || !wsUrl) {
    return NextResponse.json({ error: 'Faltan variables de LiveKit en el backend' }, { status: 500 });
  }

  // 1. Despachar explícitamente al agente de Python (Clara) a la sala de LiveKit
  try {
    const dispatchClient = new AgentDispatchClient(wsUrl, apiKey, apiSecret);
    await dispatchClient.createDispatch(room, 'clara');
  } catch (dispatchErr) {
    // Si ya existe un dispatch activo para esta sala, continuar normalmente
    console.warn('Dispatch info / ya activo:', dispatchErr);
  }

  // 2. Generar token de acceso para el navegador (con permisos de audio)
  const at = new AccessToken(apiKey, apiSecret, { identity: username });
  at.addGrant({
    room,
    roomJoin: true,
    canPublish: true,
    canSubscribe: true,
    canPublishData: true,
  });

  return NextResponse.json({
    token: await at.toJwt(),
    wsUrl,
    room,
    identity: username,
  });
}