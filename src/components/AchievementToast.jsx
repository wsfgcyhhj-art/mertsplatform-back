import { useState, useEffect } from 'react';
import {
  FaCheckCircle,
  FaFire,
  FaBolt,
  FaTerminal,
  FaCrown,
  FaTrophy,
  FaShieldAlt,
  FaBullseye,
  FaBug,
  FaRocket,
  FaAward,
  FaLock,
  FaTimes,
} from 'react-icons/fa';
import { IoSparkles } from 'react-icons/io5';

export const CATEGORY_LABELS = {
  ALL: 'Все',
  START: 'Старт',
  TASKS: 'Домашки',
  SCORES: 'Баллы',
  SECRET: 'Секретные',
  SPECIAL: 'Особые',
};

export const AchievementIcon = ({ name, locked = false, size = 24 }) => {
  if (locked) {
    return <FaLock style={{ fontSize: size, color: '#52525b' }} />;
  }

  const iconStyle = { fontSize: size, color: '#fbbf24' };
  const key = String(name || '').trim();

  switch (key) {
    case 'Sparkles':
      return <IoSparkles style={iconStyle} />;
    case 'CheckCircle':
      return <FaCheckCircle style={{ fontSize: size, color: '#34d399' }} />;
    case 'Flame':
      return <FaFire style={iconStyle} />;
    case 'Zap':
      return <FaBolt style={iconStyle} />;
    case 'Terminal':
      return <FaTerminal style={{ fontSize: size, color: '#34d399' }} />;
    case 'Crown':
      return <FaCrown style={iconStyle} />;
    case 'Trophy':
      return <FaTrophy style={iconStyle} />;
    case 'Shield':
      return <FaShieldAlt style={iconStyle} />;
    case 'Target':
      return <FaBullseye style={iconStyle} />;
    case 'Bug':
      return <FaBug style={iconStyle} />;
    case 'Rocket':
      return <FaRocket style={iconStyle} />;
    case 'Award':
      return <FaAward style={iconStyle} />;
    default:
      return <FaTrophy style={iconStyle} />;
  }
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
            <AchievementIcon name={t.iconUrl || 'Trophy'} size={22} />
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
