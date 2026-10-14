import { NextRequest } from 'next/server';

export const dynamic = 'force-dynamic';
async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const origin = request.headers.get('origin');
  if (origin) {
    let source: URL;
    try { source = new URL(origin); } catch { return Response.json({ detail: 'Invalid origin' }, { status: 403 }); }
    if (source.host !== request.headers.get('host') || !['http:', 'https:'].includes(source.protocol))
      return Response.json({ detail: 'Cross-origin request rejected' }, { status: 403 });
  }
  const { path } = await context.params;
  const base = process.env.ASTER_API_URL || 'http://127.0.0.1:8000';
  const target = `${base}/${path.map(encodeURIComponent).join('/')}${request.nextUrl.search}`;
  try {
    const result = await fetch(target, {
      method: request.method, cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: request.method === 'GET' ? undefined : await request.text(),
      signal: AbortSignal.timeout(30_000),
    });
    return new Response(result.body, { status: result.status, headers: {
      'Content-Type': result.headers.get('Content-Type') || 'application/json',
      'Cache-Control': 'no-store',
      ...(result.headers.get('Content-Disposition') ? { 'Content-Disposition': result.headers.get('Content-Disposition')! } : {}),
    } });
  } catch {
    return Response.json({ detail: 'The campaign backend is unavailable. Start the Aster API and try again.' }, { status: 503 });
  }
}
export const GET = proxy;
export const POST = proxy;
