import sharp from 'sharp';
import { prisma } from '../prisma.js';
import { PRESET_ACHIEVEMENT_ICONS } from './achievementIcons.js';

export interface MediaPresetItem {
  slug: string;
  title: string;
  url: string;
  dataUri: string;
  svg: string;
}

function toDataUri(svg: string): string {
  return `data:image/svg+xml;base64,${Buffer.from(svg.trim(), 'utf8').toString('base64')}`;
}

const RAW_BANNERS: Array<{ slug: string; title: string; svg: string }> = [
  {
    slug: 'linear-graphite',
    title: 'Linear Graphite (Фирменный темный)',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 400"><defs><linearGradient id="bg1" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#09090b"/><stop offset="50%" stop-color="#18181b"/><stop offset="100%" stop-color="#09090b"/></linearGradient><radialGradient id="glow1" cx="75%" cy="30%" r="55%"><stop offset="0%" stop-color="#f59e0b" stop-opacity="0.24"/><stop offset="100%" stop-color="#09090b" stop-opacity="0"/></radialGradient></defs><rect width="1600" height="400" fill="url(#bg1)"/><rect width="1600" height="400" fill="url(#glow1)"/><g stroke="#27272a" stroke-width="1" opacity="0.45"><line x1="0" y1="80" x2="1600" y2="80"/><line x1="0" y1="160" x2="1600" y2="160"/><line x1="0" y1="240" x2="1600" y2="240"/><line x1="0" y1="320" x2="1600" y2="320"/><line x1="320" y1="0" x2="320" y2="400"/><line x1="640" y1="0" x2="640" y2="400"/><line x1="960" y1="0" x2="960" y2="400"/><line x1="1280" y1="0" x2="1280" y2="400"/></g></svg>`,
  },
  {
    slug: 'amber-horizon',
    title: 'Amber Horizon (Янтарный горизонт)',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 400"><defs><linearGradient id="bg2" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#09090b"/><stop offset="50%" stop-color="#271a07"/><stop offset="100%" stop-color="#09090b"/></linearGradient><radialGradient id="glow2" cx="50%" cy="100%" r="65%"><stop offset="0%" stop-color="#fbbf24" stop-opacity="0.32"/><stop offset="100%" stop-color="#09090b" stop-opacity="0"/></radialGradient></defs><rect width="1600" height="400" fill="url(#bg2)"/><rect width="1600" height="400" fill="url(#glow2)"/><path d="M0 320 Q 400 220 800 300 T 1600 260 L 1600 400 L 0 400 Z" fill="#f59e0b" fill-opacity="0.08"/></svg>`,
  },
  {
    slug: 'emerald-matrix',
    title: 'Emerald Matrix (Изумрудный код)',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 400"><defs><linearGradient id="bg3" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#06120e"/><stop offset="50%" stop-color="#09090b"/><stop offset="100%" stop-color="#071f18"/></linearGradient><radialGradient id="glow3" cx="25%" cy="50%" r="55%"><stop offset="0%" stop-color="#10b981" stop-opacity="0.25"/><stop offset="100%" stop-color="#09090b" stop-opacity="0"/></radialGradient></defs><rect width="1600" height="400" fill="url(#bg3)"/><rect width="1600" height="400" fill="url(#glow3)"/><circle cx="1300" cy="180" r="240" fill="none" stroke="#34d399" stroke-opacity="0.12" stroke-width="2"/><circle cx="1300" cy="180" r="160" fill="none" stroke="#34d399" stroke-opacity="0.18" stroke-width="1.5"/></svg>`,
  },
  {
    slug: 'cyber-nebula',
    title: 'Cyber Nebula (Неоновая туманность)',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 400"><defs><linearGradient id="bg4" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#0c0a1d"/><stop offset="50%" stop-color="#14112f"/><stop offset="100%" stop-color="#09090b"/></linearGradient><radialGradient id="glow4" cx="65%" cy="40%" r="50%"><stop offset="0%" stop-color="#8b5cf6" stop-opacity="0.28"/><stop offset="60%" stop-color="#f59e0b" stop-opacity="0.08"/><stop offset="100%" stop-color="#09090b" stop-opacity="0"/></radialGradient></defs><rect width="1600" height="400" fill="url(#bg4)"/><rect width="1600" height="400" fill="url(#glow4)"/></svg>`,
  },
  {
    slug: 'minimal-obsidian',
    title: 'Minimal Obsidian (Строгий обсидиан)',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 400"><rect width="1600" height="400" fill="#09090b"/><path d="M0 398 L1600 398" stroke="#27272a" stroke-width="4"/><circle cx="800" cy="-120" r="420" fill="#fbbf24" fill-opacity="0.06"/></svg>`,
  },
  {
    slug: 'gold-circuit',
    title: 'Gold Circuit (Золотой контур)',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 400"><rect width="1600" height="400" fill="#0b0b0e"/><g stroke="#f59e0b" stroke-opacity="0.18" stroke-width="2" fill="none"><path d="M100 350 L300 350 L380 270 L700 270"/><path d="M900 130 L1220 130 L1300 210 L1520 210"/><circle cx="700" cy="270" r="6" fill="#fbbf24"/><circle cx="900" cy="130" r="6" fill="#fbbf24"/></g></svg>`,
  },
];

const RAW_AVATARS: Array<{ slug: string; title: string; svg: string }> = [
  {
    slug: 'amber-coder',
    title: 'Amber Coder',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect width="256" height="256" rx="128" fill="#18181b"/><circle cx="128" cy="96" r="44" fill="#fbbf24"/><path d="M48 224c12-44 46-68 80-68s68 24 80 68" fill="#f59e0b"/></svg>`,
  },
  {
    slug: 'emerald-hacker',
    title: 'Emerald Hacker',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect width="256" height="256" rx="128" fill="#091914"/><circle cx="128" cy="96" r="44" fill="#34d399"/><path d="M48 224c12-44 46-68 80-68s68 24 80 68" fill="#10b981"/></svg>`,
  },
  {
    slug: 'violet-architect',
    title: 'Violet Architect',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect width="256" height="256" rx="128" fill="#131127"/><circle cx="128" cy="96" r="44" fill="#a78bfa"/><path d="M48 224c12-44 46-68 80-68s68 24 80 68" fill="#8b5cf6"/></svg>`,
  },
  {
    slug: 'zinc-minimal',
    title: 'Zinc Minimal',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect width="256" height="256" rx="128" fill="#18181b"/><circle cx="128" cy="96" r="44" fill="#e4e4e7"/><path d="M48 224c12-44 46-68 80-68s68 24 80 68" fill="#a1a1aa"/></svg>`,
  },
  {
    slug: 'crimson-blaze',
    title: 'Crimson Blaze',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect width="256" height="256" rx="128" fill="#1f0d12"/><circle cx="128" cy="96" r="44" fill="#fb7185"/><path d="M48 224c12-44 46-68 80-68s68 24 80 68" fill="#f43f5e"/></svg>`,
  },
  {
    slug: 'cyan-runner',
    title: 'Cyan Runner',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect width="256" height="256" rx="128" fill="#081c24"/><circle cx="128" cy="96" r="44" fill="#38bdf8"/><path d="M48 224c12-44 46-68 80-68s68 24 80 68" fill="#0284c7"/></svg>`,
  },
];

export const PRESET_BANNERS: MediaPresetItem[] = RAW_BANNERS.map((b) => ({
  ...b,
  url: `/api/v1/media/presets/banners/${b.slug}.svg`,
  dataUri: toDataUri(b.svg),
}));

export const PRESET_AVATARS: MediaPresetItem[] = RAW_AVATARS.map((a) => ({
  ...a,
  url: `/api/v1/media/presets/avatars/${a.slug}.svg`,
  dataUri: toDataUri(a.svg),
}));

export function findPresetBanner(slug: string): MediaPresetItem | undefined {
  const clean = String(slug || '').trim().replace(/\.svg$/i, '').toLowerCase();
  return PRESET_BANNERS.find((b) => b.slug === clean);
}

export function findPresetAvatar(slug: string): MediaPresetItem | undefined {
  const clean = String(slug || '').trim().replace(/\.svg$/i, '').toLowerCase();
  if (clean === 'avatar-amber-wolf') {
    return PRESET_AVATARS[0];
  }
  return PRESET_AVATARS.find((a) => a.slug === clean || `avatar-${a.slug}` === clean);
}

export const ALLOWED_IMAGE_MIMES = new Set([
  'image/jpeg',
  'image/jpg',
  'image/png',
  'image/webp',
  'image/gif',
  'image/svg+xml',
]);

/**
 * Оптимизирует загруженное изображение через sharp и сохраняет в таблицу MediaAsset в БД Neon.
 * Удаляет предыдущий MediaAsset того же владельца и типа, чтобы не накапливать мусор.
 */
export async function saveOptimizedMediaAsset(params: {
  buffer: Buffer;
  mimeType: string;
  kind: 'AVATAR' | 'BANNER' | 'ACHIEVEMENT_ICON';
  ownerId?: string;
}): Promise<{ id: string; url: string; mimeType: string; sizeBytes: number }> {
  const { buffer, mimeType, kind, ownerId } = params;
  const normalizedMime = mimeType.toLowerCase().trim();

  if (!ALLOWED_IMAGE_MIMES.has(normalizedMime)) {
    throw new Error('Неподдерживаемый формат изображения. Разрешены: JPEG, PNG, WebP, GIF, SVG');
  }

  let outputBuffer: Buffer;
  let outputMime: string;

  if (normalizedMime === 'image/svg+xml') {
    const head = buffer.subarray(0, 512).toString('utf8').toLowerCase();
    if (!head.includes('<svg')) {
      throw new Error('Некорректный SVG-файл: отсутствует тег <svg>');
    }
    outputBuffer = buffer;
    outputMime = 'image/svg+xml';
  } else {
    const pipeline = sharp(buffer, { animated: normalizedMime === 'image/gif' });
    if (kind === 'AVATAR') {
      outputBuffer = await pipeline
        .resize(256, 256, { fit: 'cover', position: 'center' })
        .webp({ quality: 85 })
        .toBuffer();
    } else if (kind === 'BANNER') {
      outputBuffer = await pipeline
        .resize(1600, 400, { fit: 'cover', position: 'center' })
        .webp({ quality: 85 })
        .toBuffer();
    } else {
      outputBuffer = await pipeline
        .resize(128, 128, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
        .webp({ quality: 90 })
        .toBuffer();
    }
    outputMime = 'image/webp';
  }

  if (ownerId && (kind === 'AVATAR' || kind === 'BANNER')) {
    await prisma.mediaAsset.deleteMany({
      where: { ownerId, kind },
    }).catch(() => {});
  }

  const asset = await prisma.mediaAsset.create({
    data: {
      kind,
      mimeType: outputMime,
      data: new Uint8Array(outputBuffer),
      sizeBytes: outputBuffer.byteLength,
      ownerId: ownerId || null,
    },
    select: {
      id: true,
      mimeType: true,
      sizeBytes: true,
    },
  });

  return {
    id: asset.id,
    url: `/api/v1/media/${asset.id}`,
    mimeType: asset.mimeType,
    sizeBytes: asset.sizeBytes,
  };
}

export function getAllMediaPresetsCatalog() {
  return {
    banners: PRESET_BANNERS.map(({ slug, title, url, dataUri }) => ({
      slug,
      title,
      url,
      dataUri,
    })),
    avatars: PRESET_AVATARS.map(({ slug, title, url, dataUri }) => ({
      slug,
      title,
      url,
      dataUri,
    })),
    achievementIcons: PRESET_ACHIEVEMENT_ICONS.map(({ slug, legacyKey, code, label, color, url, dataUri }) => ({
      slug,
      legacyKey,
      code,
      label,
      color,
      url,
      dataUri,
    })),
  };
}
