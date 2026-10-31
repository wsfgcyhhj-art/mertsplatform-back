import { Request, Response, NextFunction } from 'express';

export function notFoundHandler(req: Request, res: Response): void {
  res.status(404).json({
    statusCode: 404,
    error: 'Not Found',
    message: `Route ${req.method} ${req.originalUrl} not found`,
  });
}

export function errorHandler(
  err: any,
  _req: Request,
  res: Response,
  _next: NextFunction
): void {
  const statusCode = err.status || err.statusCode || 500;
  const message = err.message || 'Internal Server Error';

  let errorName = 'Internal Server Error';
  if (statusCode === 400) errorName = 'Bad Request';
  else if (statusCode === 401) errorName = 'Unauthorized';
  else if (statusCode === 403) errorName = 'Forbidden';
  else if (statusCode === 404) errorName = 'Not Found';
  else if (statusCode === 409) errorName = 'Conflict';

  console.error(`[Error] ${statusCode} - ${message}`, err.stack || err);

  res.status(statusCode).json({
    statusCode,
    error: errorName,
    message,
  });
}
