import { useState, useEffect, useCallback } from 'react';
import { FaTrophy, FaCheckCircle, FaLock, FaTimes, FaUser } from 'react-icons/fa';
import { api } from '../../../api/client.js';
import { AchievementIcon, CATEGORY_LABELS } from '../../../components/AchievementToast.jsx';

const FILTER_TABS = [
  { key: 'ALL', label: 'Все' },
  { key: 'START', label: 'Старт' },
  { key: 'TASKS', label: 'Домашки' },
  { key: 'SCORES', label: 'Баллы' },
  { key: 'SECRET', label: 'Секретные' },
  { key: 'SPECIAL', label: 'Особые' },
];

export const AchievementsPage = () => {
  const [achievements, setAchievements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeCategory, setActiveCategory] = useState('ALL');

  // Модальное окно детальной карточки
  const [selectedAch, setSelectedAch] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const fetchAchievements = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get('/achievements');
      setAchievements(res.data?.achievements || []);
    } catch (err) {
      console.error('Failed to load achievements', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAchievements();
    const onRefresh = () => fetchAchievements();
    window.addEventListener('merts:refresh-achievements', onRefresh);
    return () => window.removeEventListener('merts:refresh-achievements', onRefresh);
  }, [fetchAchievements]);

  const openDetail = async (ach) => {
    setSelectedAch(ach);
    setDetailLoading(true);
    try {
      const res = await api.get(`/achievements/${ach.id}`);
      if (res.data?.achievement) {
        setSelectedAch(res.data.achievement);
      }
    } catch {
      // Оставляем данные карточки
    } finally {
      setDetailLoading(false);
    }
  };

  const unlockedList = achievements.filter((a) => a.isUnlockedByMe);
  const unlockedCount = unlockedList.length;
  const earnedBonusPoints = unlockedList.reduce((sum, a) => sum + (a.points || 0), 0);
  const totalPossiblePoints = achievements.reduce((sum, a) => sum + (a.points || 0), 0);

  const filteredAchievements =
    activeCategory === 'ALL'
      ? achievements
      : achievements.filter(
          (a) => String(a.category || '').toUpperCase() === activeCategory
        );

  return (
    <div
      style={{
        minHeight: '100vh',
        background: '#09090b', // bg-zinc-950
        color: '#f4f4f5', // text-zinc-100
        padding: '36px 32px 64px 32px',
        boxSizing: 'border-box',
      }}
    >
      <style>
        {`
          .merts-ach-card {
            background: rgba(24, 24, 27, 0.9); /* bg-zinc-900/90 */
            border: 1px solid #27272a; /* border-zinc-800 */
            border-radius: 16px; /* rounded-2xl */
            padding: 24px;
            cursor: pointer;
            transition: transform 0.2s ease, border-color 0.2s ease, background-color 0.2s ease;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-height: 220px;
          }
          .merts-ach-card:hover {
            transform: translateY(-4px);
            border-color: #3f3f46; /* hover:border-zinc-700 */
          }
          .merts-ach-card.unlocked {
            border-color: rgba(245, 158, 11, 0.3); /* border-amber-500/30 */
          }
          .merts-ach-card.unlocked:hover {
            border-color: rgba(245, 158, 11, 0.55);
          }
          .merts-ach-card.locked {
            background: rgba(24, 24, 27, 0.55);
            border-color: #27272a;
          }
        `}
      </style>

      <div style={{ maxWidth: 1440, margin: '0 auto' }}>
        {/* Верхняя панель со сводкой */}
        <div
          style={{
            background: '#18181b', // bg-zinc-900
            border: '1px solid #27272a', // border-zinc-800
            borderRadius: 16,
            padding: '28px 32px',
            marginBottom: 28,
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 24,
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  background: 'rgba(245, 158, 11, 0.1)',
                  border: '1px solid rgba(245, 158, 11, 0.3)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#fbbf24',
                }}
              >
                <FaTrophy size={20} />
              </div>
              <div>
                <h1 style={{ fontSize: 28, fontWeight: 800, margin: 0, color: '#f4f4f5' }}>
                  Каталог достижений
                </h1>
                <p style={{ fontSize: 14, color: '#a1a1aa', margin: '4px 0 0 0' }}>
                  Выполняйте учебные задания, набирайте баллы и открывайте редкие награды
                </p>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            {/* Сводка: открыто ачивок */}
            <div
              style={{
                background: '#09090b',
                border: '1px solid #27272a',
                borderRadius: 14,
                padding: '14px 22px',
                minWidth: 170,
              }}
            >
              <div style={{ fontSize: 12, color: '#a1a1aa', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Открыто наград
              </div>
              <div style={{ fontSize: 24, fontWeight: 800, color: '#34d399', marginTop: 4 }}>
                {unlockedCount}{' '}
                <span style={{ fontSize: 15, fontWeight: 500, color: '#71717a' }}>
                  / {achievements.length}
                </span>
              </div>
            </div>

            {/* Сводка: заработанные бонусные очки в янтарном оформлении */}
            <div
              style={{
                background: 'rgba(245, 158, 11, 0.08)',
                border: '1px solid rgba(245, 158, 11, 0.3)',
                borderRadius: 14,
                padding: '14px 22px',
                minWidth: 190,
              }}
            >
              <div style={{ fontSize: 12, color: '#fbbf24', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Бонусные очки
              </div>
              <div style={{ fontSize: 24, fontWeight: 800, color: '#fbbf24', marginTop: 4 }}>
                +{earnedBonusPoints}{' '}
                <span style={{ fontSize: 14, fontWeight: 500, color: '#a1a1aa' }}>
                  из {totalPossiblePoints} pts
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Фильтры по категориям */}
        <div
          style={{
            display: 'flex',
            gap: 10,
            flexWrap: 'wrap',
            marginBottom: 28,
          }}
        >
          {FILTER_TABS.map((tab) => {
            const isActive = activeCategory === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveCategory(tab.key)}
                style={{
                  padding: '10px 18px',
                  borderRadius: 12,
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  background: isActive ? 'rgba(245, 158, 11, 0.14)' : '#18181b',
                  border: isActive
                    ? '1px solid rgba(245, 158, 11, 0.45)'
                    : '1px solid #27272a',
                  color: isActive ? '#fbbf24' : '#a1a1aa',
                }}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Сетка карточек */}
        {loading ? (
          <div
            style={{
              padding: '80px 0',
              textAlign: 'center',
              color: '#a1a1aa',
              fontSize: 16,
            }}
          >
            Загрузка каталога достижений...
          </div>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(310px, 1fr))',
              gap: 20,
            }}
          >
            {filteredAchievements.map((ach) => {
              const isUnlocked = Boolean(ach.isUnlockedByMe);
              const catKey = String(ach.category || 'SPECIAL').toUpperCase();
              const catLabel = CATEGORY_LABELS[catKey] || catKey;

              return (
                <div
                  key={ach.id}
                  onClick={() => openDetail(ach)}
                  className={`merts-ach-card ${isUnlocked ? 'unlocked' : 'locked'}`}
                >
                  <div>
                    {/* Верхняя строка: иконка и бейдж статуса */}
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        marginBottom: 18,
                      }}
                    >
                      <div
                        style={{
                          width: 52,
                          height: 52,
                          borderRadius: 14,
                          background: isUnlocked
                            ? 'rgba(245, 158, 11, 0.1)'
                            : '#27272a',
                          border: isUnlocked
                            ? '1px solid rgba(245, 158, 11, 0.3)'
                            : '1px solid #3f3f46',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          filter: isUnlocked ? 'none' : 'grayscale(100%)',
                        }}
                      >
                        <AchievementIcon
                          name={ach.iconUrl}
                          locked={!isUnlocked}
                          size={24}
                        />
                      </div>

                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <span
                          style={{
                            fontSize: 11,
                            fontWeight: 600,
                            padding: '4px 10px',
                            borderRadius: 8,
                            background: '#27272a',
                            color: '#a1a1aa',
                          }}
                        >
                          {catLabel}
                        </span>

                        {isUnlocked ? (
                          <span
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 5,
                              fontSize: 12,
                              fontWeight: 600,
                              padding: '4px 10px',
                              borderRadius: 8,
                              background: 'rgba(16, 185, 129, 0.1)',
                              border: '1px solid rgba(16, 185, 129, 0.3)',
                              color: '#34d399',
                            }}
                          >
                            <FaCheckCircle size={12} /> Получено
                          </span>
                        ) : (
                          <span
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 5,
                              fontSize: 12,
                              fontWeight: 500,
                              padding: '4px 10px',
                              borderRadius: 8,
                              background: '#18181b',
                              border: '1px solid #27272a',
                              color: '#71717a',
                            }}
                          >
                            <FaLock size={11} /> Закрыто
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Заголовок и описание */}
                    <h3
                      style={{
                        fontSize: 18,
                        fontWeight: 700,
                        margin: '0 0 8px 0',
                        color: isUnlocked ? '#f4f4f5' : '#a1a1aa',
                      }}
                    >
                      {ach.title}
                    </h3>

                    <p
                      style={{
                        fontSize: 14,
                        color: isUnlocked ? '#a1a1aa' : '#71717a',
                        margin: 0,
                        lineHeight: 1.5,
                      }}
                    >
                      {ach.description}
                    </p>

                    {!isUnlocked && ach.criteria && (
                      <div
                        style={{
                          marginTop: 12,
                          padding: '8px 12px',
                          borderRadius: 10,
                          background: '#09090b',
                          border: '1px solid #27272a',
                          fontSize: 12,
                          color: '#71717a',
                        }}
                      >
                        Условие: {ach.criteria}
                      </div>
                    )}
                  </div>

                  {/* Нижняя строка: очки и счетчик студентов */}
                  <div
                    style={{
                      marginTop: 20,
                      paddingTop: 14,
                      borderTop: '1px solid #27272a',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <span
                      style={{
                        fontSize: 13,
                        fontWeight: 700,
                        padding: '4px 12px',
                        borderRadius: 8,
                        background: isUnlocked
                          ? 'rgba(245, 158, 11, 0.1)'
                          : '#27272a',
                        border: isUnlocked
                          ? '1px solid rgba(245, 158, 11, 0.3)'
                          : '1px solid transparent',
                        color: isUnlocked ? '#fbbf24' : '#a1a1aa',
                      }}
                    >
                      +{ach.points || 10} очков
                    </span>

                    <span style={{ fontSize: 12, color: '#71717a' }}>
                      Открыли: {ach.unlockedCount || 0} чел.
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Модальное окно детальной информации об ачивке */}
      {selectedAch && (
        <div
          onClick={() => setSelectedAch(null)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(9, 9, 11, 0.8)',
            backdropFilter: 'blur(4px)',
            zIndex: 2000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 20,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: '#18181b',
              border: '1px solid #27272a',
              borderRadius: 20,
              maxWidth: 520,
              width: '100%',
              padding: 28,
              color: '#f4f4f5',
              position: 'relative',
              boxShadow: '0 24px 60px rgba(0, 0, 0, 0.7)',
            }}
          >
            <button
              type="button"
              onClick={() => setSelectedAch(null)}
              style={{
                position: 'absolute',
                top: 20,
                right: 20,
                background: '#27272a',
                border: '1px solid #3f3f46',
                borderRadius: 10,
                width: 34,
                height: 34,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#a1a1aa',
                cursor: 'pointer',
              }}
            >
              <FaTimes size={14} />
            </button>

            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
              <div
                style={{
                  width: 64,
                  height: 64,
                  borderRadius: 16,
                  background: selectedAch.isUnlockedByMe
                    ? 'rgba(245, 158, 11, 0.12)'
                    : '#27272a',
                  border: selectedAch.isUnlockedByMe
                    ? '1px solid rgba(245, 158, 11, 0.35)'
                    : '1px solid #3f3f46',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <AchievementIcon
                  name={selectedAch.iconUrl}
                  locked={!selectedAch.isUnlockedByMe}
                  size={30}
                />
              </div>

              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 700,
                      padding: '3px 10px',
                      borderRadius: 8,
                      background: 'rgba(245, 158, 11, 0.12)',
                      border: '1px solid rgba(245, 158, 11, 0.3)',
                      color: '#fbbf24',
                    }}
                  >
                    +{selectedAch.points || 10} очков
                  </span>
                  {selectedAch.isUnlockedByMe ? (
                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        padding: '3px 10px',
                        borderRadius: 8,
                        background: 'rgba(16, 185, 129, 0.12)',
                        color: '#34d399',
                      }}
                    >
                      ✓ Разблокировано
                    </span>
                  ) : (
                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        padding: '3px 10px',
                        borderRadius: 8,
                        background: '#27272a',
                        color: '#a1a1aa',
                      }}
                    >
                      Не получено
                    </span>
                  )}
                </div>
                <h2 style={{ fontSize: 22, fontWeight: 800, margin: 0, color: '#f4f4f5' }}>
                  {selectedAch.title}
                </h2>
              </div>
            </div>

            <p style={{ fontSize: 15, color: '#a1a1aa', lineHeight: 1.55, margin: '0 0 18px 0' }}>
              {selectedAch.description}
            </p>

            <div
              style={{
                background: '#09090b',
                border: '1px solid #27272a',
                borderRadius: 14,
                padding: '14px 16px',
                marginBottom: 20,
              }}
            >
              <div style={{ fontSize: 12, color: '#71717a', marginBottom: 4 }}>
                Условие получения:
              </div>
              <div style={{ fontSize: 14, color: '#e4e4e7', fontWeight: 500 }}>
                {selectedAch.criteria || selectedAch.description}
              </div>
            </div>

            {detailLoading ? (
              <div style={{ fontSize: 13, color: '#71717a', padding: '8px 0' }}>
                Загрузка списка обладателей...
              </div>
            ) : (
              selectedAch.recentAchievers &&
              selectedAch.recentAchievers.length > 0 && (
                <div>
                  <div style={{ fontSize: 13, color: '#a1a1aa', fontWeight: 600, marginBottom: 10 }}>
                    Последние получившие студенты ({selectedAch.unlockedCount || selectedAch.recentAchievers.length}):
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {selectedAch.recentAchievers.map((u) => (
                      <div
                        key={u.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          padding: '6px 12px',
                          borderRadius: 999,
                          background: '#09090b',
                          border: '1px solid #27272a',
                          fontSize: 13,
                          color: '#e4e4e7',
                        }}
                      >
                        {u.avatarUrl ? (
                          <img
                            src={u.avatarUrl}
                            alt={u.name || u.login}
                            style={{ width: 20, height: 20, borderRadius: '50%', objectFit: 'cover' }}
                          />
                        ) : (
                          <FaUser size={12} style={{ color: '#a1a1aa' }} />
                        )}
                        <span>{u.name || u.login}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )
            )}
          </div>
        </div>
      )}
    </div>
  );
};
