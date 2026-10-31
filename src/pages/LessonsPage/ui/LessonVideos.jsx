import { useState, useEffect } from "react";
import cls from "../styles/lessons.module.scss";
import { FaArrowLeft, FaArrowRight, FaVideo } from "react-icons/fa";
import { api } from "../../../api/client.js";
import { Spin } from "antd";

export const LessonVideos = () => {
    const [lessons, setLessons] = useState([]);
    const [month, setMonth] = useState(1);
    const [index, setIndex] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        let isMounted = true;
        const fetchLessons = async () => {
            try {
                setLoading(true);
                const res = await api.get('/lessons');
                if (isMounted) {
                    const fetchedLessons = res.data?.lessons || [];
                    setLessons(fetchedLessons);
                    setMonth(res.data?.month || 1);
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
    }, []);

    if (loading) {
        return (
            <div style={{ padding: '80px 0', textAlign: 'center' }}>
                <Spin size="large" />
                <p style={{ marginTop: '16px', color: 'rgba(255,255,255,0.7)' }}>Загрузка видеоуроков...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div style={{ padding: '60px 20px', textAlign: 'center', background: 'var(--card)', borderRadius: '16px' }}>
                <p style={{ color: '#ef4444', fontSize: '18px' }}>{error}</p>
            </div>
        );
    }

    if (lessons.length === 0) {
        return (
            <div style={{ padding: '80px 20px', textAlign: 'center', background: 'var(--card)', borderRadius: '16px', marginTop: '30px' }}>
                <FaVideo style={{ fontSize: '48px', color: 'var(--primary)', marginBottom: '16px' }} />
                <h2>Уроки для {month}-го месяца пока готовятся</h2>
                <p style={{ color: 'rgba(255,255,255,0.6)', marginTop: '8px' }}>
                    Преподаватель скоро опубликует новые материалы. Следите за обновлениями!
                </p>
            </div>
        );
    }

    const currentLesson = lessons[index] || lessons[0];

    return (
        <div className={cls.videos}>
            <div className={cls.title}>
                <div className={cls.less_title}>
                    <h1>{currentLesson?.title}</h1>
                    <div className={cls.lesson_of_lesson}>
                        Урок {index + 1} из {lessons.length}
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
