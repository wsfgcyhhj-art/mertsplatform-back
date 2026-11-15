import { Request, Response, NextFunction } from 'express';

export interface ApiErrorPayload {
  statusCode: number;
  error: string;
  message: string;
  fields?: Record<string, string>;
}

export function sendApiError(
  res: Response,
  statusCode: number,
  message: string,
  fields?: Record<string, string>,
  customError?: string
): void {
  const errorMap: Record<number, string> = {
    400: 'Bad Request',
    401: 'Unauthorized',
    403: 'Forbidden',
    404: 'Not Found',
    409: 'Conflict',
    422: 'Unprocessable Entity',
    429: 'Too Many Requests',
    500: 'Internal Server Error',
    503: 'Service Unavailable',
  };

  const payload: ApiErrorPayload = {
    statusCode,
    error: customError || errorMap[statusCode] || 'Error',
    message,
  };

  if (fields && Object.keys(fields).length > 0) {
    payload.fields = fields;
  }

  res.status(statusCode).json(payload);
}

export function notFoundHandler(req: Request, res: Response): void {
  sendApiError(res, 404, `Route ${req.method} ${req.originalUrl} not found`, undefined, 'Not Found');
}

export function errorHandler(
  err: any,
  _req: Request,
  res: Response,
  _next: NextFunction
): void {
  if (err instanceof SyntaxError && 'body' in err) {
    sendApiError(res, 400, 'Invalid JSON payload in request body', { body: 'Malformed JSON' });
    return;
  }

  const statusCode = err.status || err.statusCode || 500;
  const message = err.message || 'Internal Server Error';

  console.error(`[Error] ${statusCode} - ${message}`, err.stack || err);

  sendApiError(res, statusCode, message, err.fields);
}
