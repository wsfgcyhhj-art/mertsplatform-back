import { Request, Response, NextFunction } from 'express';

function snakeToCamel(key: string): string {
  return key.replace(/_([a-zA-Z0-9])/g, (_, char: string) => char.toUpperCase());
}

function camelToSnake(key: string): string {
  return key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
}

export function normalizeObjectKeys<T>(input: T): T {
  if (Array.isArray(input)) {
    return input.map((item) => normalizeObjectKeys(item)) as unknown as T;
  }

  if (
    input !== null &&
    typeof input === 'object' &&
    !(input instanceof Date) &&
    !Buffer.isBuffer(input)
  ) {
    const record = input as Record<string, unknown>;
    const normalized: Record<string, unknown> = {};

    for (const [key, rawValue] of Object.entries(record)) {
      const value = normalizeObjectKeys(rawValue);
      normalized[key] = value;

      const camelKey = snakeToCamel(key);
      if (camelKey !== key && !(camelKey in record)) {
        normalized[camelKey] = value;
      }

      const snakeKey = camelToSnake(key);
      if (snakeKey !== key && !(snakeKey in record)) {
        normalized[snakeKey] = value;
      }
    }

    return normalized as T;
  }

  return input;
}

/**
 * Глобальный middleware толерантности запросов:
 * Автоматически зеркалирует snake_case <-> camelCase в req.body и req.query,
 * позволяя любому внешнему фронтенду отправлять поля в любом стиле именования.
 */
export function normalizeRequestMiddleware(req: Request, _res: Response, next: NextFunction): void {
  if (req.body && typeof req.body === 'object' && !Buffer.isBuffer(req.body)) {
    req.body = normalizeObjectKeys(req.body);
  }

  if (req.query && typeof req.query === 'object') {
    const normalizedQuery = normalizeObjectKeys({ ...req.query });
    for (const [k, v] of Object.entries(normalizedQuery)) {
      if (!(k in req.query)) {
        try {
          (req.query as Record<string, unknown>)[k] = v;
        } catch {
          // В случае read-only геттера игнорируем
        }
      }
    }
  }

  next();
}
