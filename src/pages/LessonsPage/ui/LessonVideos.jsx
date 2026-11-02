import { useState, useEffect } from "react";
import cls from "../styles/lessons.module.scss";
import { FaArrowLeft, FaArrowRight, FaVideo } from "react-icons/fa";
import { api } from "../../../api/client.js";
import { useFindUser } from "../../../store/userStore.js";
import { Spin } from "antd";

export const LessonVideos = () => {
    const { userInfo } = useFindUser();
    const maxUserMonth = Math.max(1, Number(userInfo?.currentMonth) || 1);

    const [lessons, setLessons] = useState([]);
    const [selectedMonth, setSelectedMonth] = useState(maxUserMonth);
    const [currentMonthLimit, setCurrentMonthLimit] = useState(maxUserMonth);
    const [groupNumber, setGroupNumber] = useState(userInfo?.groupNumber || '');
    const [index, setIndex] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        let isMounted = true;
        const fetchLessons = async () => {
            try {
                setLoading(true);
                setError(null);
                const res = await api.get('/lessons', {
                    params: { month: selectedMonth },
                });
                if (isMounted) {
                    const fetchedLessons = res.data?.lessons || [];
                    setLessons(fetchedLessons);
                    if (res.data?.currentMonth) {
                        setCurrentMonthLimit(Math.max(1, Number(res.data.currentMonth)));
                    }
                    if (res.data?.groupNumber) {
                        setGroupNumber(res.data.groupNumber);
                    }
                    setIndex(0);
                }
            } catch (err) {
                if (isMounted) {
                    console.error('Failed to load lessons', err);
                    setError('Не удалось загрузить уроки. Проверьте соединение.');
                }
            } finally {
                if (isMounted) {
                    setLoading(false);
                }
            }
        };

        fetchLessons();
        return () => {
            isMounted = false;
        };
    }, [selectedMonth]);

    const availableMonths = Array.from({ length: currentMonthLimit }, (_, i) => i + 1);

    const renderMonthSwitcher = () => (
        <div
            style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '12px',
                marginBottom: '20px',
                padding: '14px 18px',
                background: 'var(--card, #18181b)',
                border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: '14px',
            }}
        >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '14px', color: 'rgba(255,255,255,0.7)', fontWeight: 600 }}>
                    Программа обучения:
                </span>
                {groupNumber && (
                    <span
                        style={{
                            padding: '4px 10px',
                            borderRadius: '8px',
                            background: 'rgba(168, 85, 247, 0.15)',
                            border: '1px solid rgba(168, 85, 247, 0.35)',
                            color: '#e9d5ff',
                            fontSize: '13px',
                            fontWeight: 700,
                        }}
                    >
                        Группа {groupNumber}
                    </span>
                )}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '13px', color: 'rgba(255,255,255,0.6)', marginRight: '4px' }}>
                    Месяц:
                </span>
                {availableMonths.map((m) => {
                    const isActive = selectedMonth === m;
                    return (
                        <button
                            key={m}
                            type="button"
                            onClick={() => setSelectedMonth(m)}
                            style={{
                                padding: '6px 14px',
                                borderRadius: '10px',
                                border: isActive
                                    ? '1px solid var(--primary, #a855f7)'
                                    : '1px solid rgba(255,255,255,0.12)',
                                background: isActive
                                    ? 'var(--primary, #a855f7)'
                                    : 'rgba(255,255,255,0.04)',
                                color: '#fff',
                                fontSize: '13px',
                                fontWeight: isActive ? 700 : 500,
                                cursor: 'pointer',
                                transition: 'all 0.2s ease',
                            }}
                        >
                            {m} месяц {m === currentMonthLimit ? '(текущий)' : ''}
                        </button>
                    );
                })}
                {currentMonthLimit > 1 && (
                    <button
                        type="button"
                        onClick={() => setSelectedMonth('all')}
                        style={{
                            padding: '6px 14px',
                            borderRadius: '10px',
                            border:
                                selectedMonth === 'all'
                                    ? '1px solid var(--primary, #a855f7)'
                                    : '1px solid rgba(255,255,255,0.12)',
                            background:
                                selectedMonth === 'all'
                                    ? 'var(--primary, #a855f7)'
                                    : 'rgba(255,255,255,0.04)',
                            color: '#fff',
                            fontSize: '13px',
                            fontWeight: selectedMonth === 'all' ? 700 : 500,
                            cursor: 'pointer',
                            transition: 'all 0.2s ease',
                        }}
                    >
                        Все пройденные
                    </button>
                )}
            </div>
        </div>
    );

    if (loading) {
        return (
            <div className={cls.videos}>
                {renderMonthSwitcher()}
                <div style={{ padding: '80px 0', textAlign: 'center' }}>
                    <Spin size="large" />
                    <p style={{ marginTop: '16px', color: 'rgba(255,255,255,0.7)' }}>Загрузка видеоуроков...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className={cls.videos}>
                {renderMonthSwitcher()}
                <div style={{ padding: '60px 20px', textAlign: 'center', background: 'var(--card)', borderRadius: '16px' }}>
                    <p style={{ color: '#ef4444', fontSize: '18px' }}>{error}</p>
                </div>
            </div>
        );
    }

    if (lessons.length === 0) {
        return (
            <div className={cls.videos}>
                {renderMonthSwitcher()}
                <div style={{ padding: '80px 20px', textAlign: 'center', background: 'var(--card)', borderRadius: '16px', marginTop: '10px' }}>
                    <FaVideo style={{ fontSize: '48px', color: 'var(--primary)', marginBottom: '16px' }} />
                    <h2>
                        {selectedMonth === 'all'
                            ? `Уроки для группы ${groupNumber || '—'} пока готовятся`
                            : `Уроки для ${selectedMonth}-го месяца (группа ${groupNumber || '—'}) пока готовятся`}
                    </h2>
                    <p style={{ color: 'rgba(255,255,255,0.6)', marginTop: '8px' }}>
                        Преподаватель скоро опубликует новые видеоматериалы для вашей группы. Следите за обновлениями!
                    </p>
                </div>
            </div>
        );
    }

    const currentLesson = lessons[index] || lessons[0];

    return (
        <div className={cls.videos}>
            {renderMonthSwitcher()}

            <div className={cls.title}>
                <div className={cls.less_title}>
                    <h1>{currentLesson?.title}</h1>
                    <div className={cls.lesson_of_lesson}>
                        Урок {index + 1} из {lessons.length}
                        {currentLesson?.month ? ` • Месяц ${currentLesson.month}` : ''}
                    </div>
                </div>
            </div>

            {currentLesson?.youtubeId ? (
                <iframe
                    data-aos="zoom-in"
                    className={cls.video}
                    src={`https://www.youtube.com/embed/${currentLesson.youtubeId}`}
                    title={currentLesson.title}
                    frameBorder="0"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                    referrerPolicy="strict-origin-when-cross-origin"
                    allowFullScreen
                />
            ) : (
                <div style={{
                    width: '100%',
                    height: '450px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: '#111',
                    borderRadius: '12px',
                    color: '#888'
                }}>
                    Видео недоступно или не прикреплена корректная ссылка
                </div>
            )}

            <div className={cls.video_paginasion}>
                <button
                    disabled={index === 0}
                    className={cls.paginasion_btn}
                    onClick={() => setIndex((prev) => Math.max(0, prev - 1))}
                >
                    <FaArrowLeft /> Предыдущий урок
                </button>
                <div className={cls.paginasion_info}>
                    {index + 1} урок
                </div>
                <button
                    className={cls.paginasion_btn}
                    disabled={index === lessons.length - 1}
                    onClick={() => setIndex((prev) => Math.min(lessons.length - 1, prev + 1))}
                >
                    Следующий урок <FaArrowRight />
                </button>
            </div>
        </div>
    );
};
