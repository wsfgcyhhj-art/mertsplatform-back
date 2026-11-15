import type { Request } from 'express';

export function getPublicOrigin(req?: Request): string {
  const envUrl = (process.env.PUBLIC_API_URL || process.env.RENDER_EXTERNAL_URL || '').trim();
  if (envUrl) {
    return envUrl.replace(/\/api\/v1\/?$/i, '').replace(/\/+$/, '');
  }

  if (req) {
    const forwardedProto = req.headers['x-forwarded-proto'];
    const protoRaw = Array.isArray(forwardedProto) ? forwardedProto[0] : forwardedProto;
    const proto = (protoRaw?.split(',')[0]?.trim() || req.protocol || 'http').replace(/:$/, '');

    const forwardedHost = req.headers['x-forwarded-host'];
    const hostRaw = Array.isArray(forwardedHost) ? forwardedHost[0] : forwardedHost;
    const host = hostRaw?.split(',')[0]?.trim() || req.get('host') || `localhost:${process.env.PORT || 5000}`;

    return `${proto}://${host}`;
  }

  return `http://localhost:${process.env.PORT || 5000}`;
}

export function toPublicUrl(req: Request | undefined, rawUrl: string | null | undefined): string | null {
  if (rawUrl === null || rawUrl === undefined) return null;
  const trimmed = String(rawUrl).trim();
  if (!trimmed) return null;

  if (
    trimmed.startsWith('data:') ||
    trimmed.startsWith('http://') ||
    trimmed.startsWith('https://')
  ) {
    return trimmed;
  }

  const origin = getPublicOrigin(req);

  if (trimmed.startsWith('/api/v1/')) {
    return `${origin}${trimmed}`;
  }

  if (trimmed.startsWith('/')) {
    return `${origin}/api/v1${trimmed}`;
  }

  return `${origin}/api/v1/achievements/icons/${encodeURIComponent(trimmed.replace(/\.svg$/i, ''))}.svg`;
}

export function normalizeStoredMediaUrl(rawUrl: string | null | undefined): string | null {
  if (rawUrl === null || rawUrl === undefined) return null;
  const trimmed = String(rawUrl).trim();
  if (!trimmed) return null;

  const apiIdx = trimmed.indexOf('/api/v1/');
  if (apiIdx !== -1 && (trimmed.startsWith('http://') || trimmed.startsWith('https://'))) {
    return trimmed.slice(apiIdx);
  }
  return trimmed;
}

export function formatUserMedia<T extends { avatarUrl?: string | null; bannerUrl?: string | null }>(
  req: Request | undefined,
  user: T
): T {
  return {
    ...user,
    ...(user.avatarUrl !== undefined ? { avatarUrl: toPublicUrl(req, user.avatarUrl) } : {}),
    ...(user.bannerUrl !== undefined ? { bannerUrl: toPublicUrl(req, user.bannerUrl) } : {}),
  };
}
