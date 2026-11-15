import { Router, Request, Response } from 'express';
import { prisma } from '../prisma.js';
import {
  findPresetAvatar,
  findPresetBanner,
  getAllMediaPresetsCatalog,
} from '../services/mediaPresets.js';
import { toPublicUrl } from '../utils/url.js';

export const mediaRouter = Router();

// GET /api/v1/media/presets — каталог готовых темных обоев, дефолтных аватаров и иконок ачивок
mediaRouter.get('/presets', (req: Request, res: Response): void => {
  const catalog = getAllMediaPresetsCatalog();
  res.json({
    banners: catalog.banners.map((item) => ({
      ...item,
      path: item.url,
      url: toPublicUrl(req, item.url) || item.url,
    })),
    avatars: catalog.avatars.map((item) => ({
      ...item,
      path: item.url,
      url: toPublicUrl(req, item.url) || item.url,
    })),
    achievementIcons: catalog.achievementIcons.map((item) => ({
      ...item,
      path: item.url,
      url: toPublicUrl(req, item.url) || item.url,
    })),
  });
});

// GET /api/v1/media/presets/banners/:slug — векторные обои профиля с бэкенда
mediaRouter.get('/presets/banners/:slug', (req: Request, res: Response): void => {
  const rawSlug = Array.isArray(req.params.slug) ? req.params.slug[0] : req.params.slug;
  const preset = findPresetBanner(rawSlug);

  if (!preset) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'Banner preset not found',
    });
    return;
  }

  res.setHeader('Content-Type', 'image/svg+xml; charset=utf-8');
  res.setHeader('Cache-Control', 'public, max-age=86400');
  res.setHeader('Cross-Origin-Resource-Policy', 'cross-origin');
  res.send(preset.svg);
});

// GET /api/v1/media/presets/avatars/:slug — векторные аватарки с бэкенда
mediaRouter.get('/presets/avatars/:slug', (req: Request, res: Response): void => {
  const rawSlug = Array.isArray(req.params.slug) ? req.params.slug[0] : req.params.slug;
  const preset = findPresetAvatar(rawSlug);

  if (!preset) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'Avatar preset not found',
    });
    return;
  }

  res.setHeader('Content-Type', 'image/svg+xml; charset=utf-8');
  res.setHeader('Cache-Control', 'public, max-age=86400');
  res.setHeader('Cross-Origin-Resource-Policy', 'cross-origin');
  res.send(preset.svg);
});

// GET /api/v1/media/:id — персистентная отдача загруженного медиафайла из таблицы MediaAsset (Neon PostgreSQL)
mediaRouter.get('/:id', async (req: Request, res: Response): Promise<void> => {
  const rawId = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
  const cleanId = String(rawId || '').trim().replace(/\.(webp|svg|png|jpg|jpeg|gif)$/i, '');

  if (!cleanId) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Media asset ID is required',
      fields: { id: 'Media asset ID is required' },
    });
    return;
  }

  const asset = await prisma.mediaAsset.findUnique({
    where: { id: cleanId },
  });

  if (!asset) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'Media asset not found',
    });
    return;
  }

  const body = Buffer.from(asset.data);
  res.setHeader('Content-Type', asset.mimeType);
  res.setHeader('Content-Length', String(body.byteLength));
  res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
  res.setHeader('Cross-Origin-Resource-Policy', 'cross-origin');
  res.send(body);
});
