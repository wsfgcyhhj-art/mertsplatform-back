import { useState, useEffect } from 'react';
import { FaLock, FaTimes } from 'react-icons/fa';
import { API_BASE_URL } from '../api/client.js';

export const CATEGORY_LABELS = {
  ALL: 'Все',
  START: 'Старт',
  TASKS: 'Домашки',
  SCORES: 'Баллы',
  SECRET: 'Секретные',
  SPECIAL: 'Особые',
};

const FALLBACK_TROPHY_SVG =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/></svg>'
  );

export function resolveBackendIconSrc(rawUrl) {
  const val = String(rawUrl || '').trim();
  if (!val) {
    return `${API_BASE_URL.replace(/\/$/, '')}/achievements/icons/trophy.svg`;
  }
  if (val.startsWith('data:image/') || val.startsWith('http://') || val.startsWith('https://')) {
    return val;
  }
  if (val.startsWith('/api/v1/')) {
    const serverOrigin = API_BASE_URL.replace(/\/api\/v1\/?$/, '');
    return `${serverOrigin}${val}`;
  }
  if (val.startsWith('/')) {
    return `${API_BASE_URL.replace(/\/$/, '')}${val}`;
  }
  return `${API_BASE_URL.replace(/\/$/, '')}/achievements/icons/${encodeURIComponent(val)}.svg`;
}

export const AchievementIcon = ({ iconUrl, name, locked = false, size = 24 }) => {
  const raw = iconUrl || name;
  const resolvedSrc = resolveBackendIconSrc(raw);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    setHasError(false);
  }, [resolvedSrc]);

  return (
    <div
      style={{
        position: 'relative',
        width: size,
        height: size,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <img
        src={hasError ? FALLBACK_TROPHY_SVG : resolvedSrc}
        alt=""
        onError={() => {
          if (!hasError) setHasError(true);
        }}
        style={{
          width: size,
          height: size,
          objectFit: 'contain',
          display: 'block',
          filter: locked ? 'grayscale(100%) opacity(0.45)' : 'none',
          transition: 'filter 0.2s ease',
        }}
      />
      {locked && (
        <span
          style={{
            position: 'absolute',
            right: -6,
            bottom: -6,
            width: Math.max(14, Math.round(size * 0.55)),
            height: Math.max(14, Math.round(size * 0.55)),
            borderRadius: '50%',
            background: '#18181b',
            border: '1px solid #3f3f46',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#a1a1aa',
          }}
        >
          <FaLock size={Math.max(8, Math.round(size * 0.3))} />
        </span>
      )}
    </div>
  );
};

// Глобальная шина событий для показа кастомного темного Toast
const TOAST_EVENT = 'merts:achievement-unlocked';

export function showAchievementToast(payload) {
  window.dispatchEvent(new CustomEvent(TOAST_EVENT, { detail: payload }));
}

export const AchievementToastHost = () => {
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    const handler = (e) => {
      const id = `${Date.now()}-${Math.random()}`;
      const newToast = { id, ...e.detail };
      setToasts((prev) => [...prev, newToast]);

      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 6500);
    };

    window.addEventListener(TOAST_EVENT, handler);
    return () => window.removeEventListener(TOAST_EVENT, handler);
  }, []);

  const dismiss = (id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  if (toasts.length === 0) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 24,
        right: 24,
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        maxWidth: 420,
        width: 'calc(100vw - 48px)',
      }}
    >
      <style>
        {`
          @keyframes mertsToastSlideIn {
            from {
              opacity: 0;
              transform: translateY(-12px) scale(0.97);
            }
            to {
              opacity: 1;
              transform: translateY(0) scale(1);
            }
          }
        `}
      </style>
      {toasts.map((t) => (
        <div
          key={t.id}
          style={{
            background: '#18181b', // zinc-900
            border: '1px solid rgba(245, 158, 11, 0.4)', // border-amber-500/40
            borderRadius: 16, // rounded-2xl
            padding: '16px 18px',
            boxShadow: '0 20px 45px rgba(0, 0, 0, 0.65)',
            display: 'flex',
            alignItems: 'flex-start',
            gap: 14,
            color: '#f4f4f5', // text-zinc-100
            animation: 'mertsToastSlideIn 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
          }}
        >
          <div
            style={{
              width: 44,
              height: 44,
              minWidth: 44,
              borderRadius: 12,
              background: 'rgba(245, 158, 11, 0.12)',
              border: '1px solid rgba(245, 158, 11, 0.3)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <AchievementIcon iconUrl={t.iconUrl} size={22} />
          </div>

          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginBottom: 4,
              }}
            >
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                  color: '#fbbf24', // amber-400
                }}
              >
                Новое достижение
              </span>
              {t.points && (
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    padding: '2px 8px',
                    borderRadius: 999,
                    background: 'rgba(245, 158, 11, 0.12)',
                    border: '1px solid rgba(245, 158, 11, 0.3)',
                    color: '#fbbf24',
                  }}
                >
                  +{t.points} очков
                </span>
              )}
            </div>

            <div
              style={{
                fontSize: 15,
                fontWeight: 700,
                color: '#f4f4f5',
                lineHeight: 1.35,
              }}
            >
              {t.customMessage || `Получена ачивка «${t.title}»`}
            </div>

            {t.description && (
              <div
                style={{
                  fontSize: 13,
                  color: '#a1a1aa', // text-zinc-400
                  marginTop: 4,
                  lineHeight: 1.4,
                }}
              >
                {t.description}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => dismiss(t.id)}
            aria-label="Закрыть уведомление"
            style={{
              background: 'transparent',
              border: 'none',
              color: '#71717a',
              cursor: 'pointer',
              padding: 4,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <FaTimes size={14} />
          </button>
        </div>
      ))}
    </div>
  );
};
