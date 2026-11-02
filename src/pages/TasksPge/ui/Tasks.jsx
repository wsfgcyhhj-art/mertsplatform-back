import { useState, useEffect } from "react";
import cls from "../styles/task.module.scss";
import { IoCheckmarkDoneCircleOutline, IoEyeSharp } from "react-icons/io5";
import { FaGithub, FaHtml5, FaClock, FaExclamationTriangle, FaMicrophone } from "react-icons/fa";
import { IoLogoCss3, IoLogoJavascript } from "react-icons/io";
import { Modal, Input, Button, Tag, Spin, message, Alert } from "antd";
import { api, API_BASE_URL, extractAuthToken } from "../../../api/client.js";
import { useFindUser } from "../../../store/userStore.js";

export const TaskS = () => {
    const { userInfo, addUser } = useFindUser();
    const [tasks, setTasks] = useState([]);
    const [month, setMonth] = useState(1);
    const [loading, setLoading] = useState(true);

    // Модалка отправки решения
    const [submitModalOpen, setSubmitModalOpen] = useState(false);
    const [selectedTask, setSelectedTask] = useState(null);
    const [solutionLink, setSolutionLink] = useState('');
    const [comment, setComment] = useState('');
    const [submitting, setSubmitting] = useState(false);

    // Модалка просмотра истории сдачи
    const [historyModalOpen, setHistoryModalOpen] = useState(false);
    const [taskHistory, setTaskHistory] = useState(null);
    const [loadingHistory, setLoadingHistory] = useState(false);

    const fetchTasks = async () => {
        try {
            setLoading(true);
            const res = await api.get('/tasks');
            setTasks(res.data?.tasks || []);
            setMonth(res.data?.month || 1);
        } catch (err) {
            console.error('Failed to load tasks', err);
            message.error('Не удалось загрузить задания');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchTasks();
    }, []);

    const openSubmitModal = (task) => {
        setSelectedTask(task);
        setSolutionLink('');
        setComment('');
        setSubmitModalOpen(true);
    };

    const handleSendSubmission = async () => {
        const trimmedLink = solutionLink.trim();
        if (!trimmedLink) {
            message.warning('Укажите ссылку на GitHub репозиторий');
            return;
        }

        // Валидация github ссылки
        const githubRegex = /^https?:\/\/(www\.)?github\.com\/[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+(\/.*)?$/;
        if (!githubRegex.test(trimmedLink)) {
            message.warning('Ссылка должна быть в формате https://github.com/пользователь/репозиторий');
            return;
        }

        try {
            setSubmitting(true);
            const res = await api.post(`/tasks/${selectedTask.id}/submissions`, {
                solutionLink: trimmedLink,
                comment: comment.trim() || undefined,
            });
            if (res.data?.streakCount !== undefined && userInfo) {
                addUser({ ...userInfo, streakCount: res.data.streakCount });
            }
            message.success('Решение успешно отправлено на проверку!');
            setSubmitModalOpen(false);
            fetchTasks();
        } catch (err) {
            const errText = err.response?.data?.message || 'Ошибка отправки решения';
            message.error(errText);
        } finally {
            setSubmitting(false);
        }
    };

    const openTaskHistory = async (task) => {
        setSelectedTask(task);
        setHistoryModalOpen(true);
        setLoadingHistory(true);
        try {
            const res = await api.get(`/tasks/${task.id}`);
            setTaskHistory(res.data?.task || null);
        } catch (err) {
            message.error('Не удалось загрузить историю сдачи');
        } finally {
            setLoadingHistory(false);
        }
    };

    const renderTopicIcon = (topic) => {
        const t = (topic || '').toUpperCase();
        if (t.includes('HTML')) return <FaHtml5 style={{ color: '#e34f26' }} />;
        if (t.includes('CSS')) return <IoLogoCss3 style={{ color: '#1572b6' }} />;
        return <IoLogoJavascript style={{ color: '#f7df1e' }} />;
    };

    const renderStatusBadge = (submission) => {
        if (!submission) {
            return <Tag color="default">Не сдано</Tag>;
        }
        if (submission.status === 'SENT') {
            return (
                <Tag color="processing" icon={<FaClock />}>
                    На проверке (Попытка #{submission.version})
                </Tag>
            );
        }
        if (submission.status === 'ACCEPTED') {
            return (
                <Tag color="success" icon={<IoCheckmarkDoneCircleOutline />}>
                    Принято ({submission.score || 0} баллов)
                </Tag>
            );
        }
        if (submission.status === 'REVISION') {
            return (
                <Tag color="warning" icon={<FaExclamationTriangle />}>
                    Требуется доработка
                </Tag>
            );
        }
        return <Tag>{submission.status}</Tag>;
    };

    if (loading) {
        return (
            <div style={{ textAlign: 'center', padding: '100px 0' }}>
                <Spin size="large" />
                <p style={{ marginTop: '16px', color: 'rgba(255,255,255,0.7)' }}>Загрузка заданий...</p>
            </div>
        );
    }

    return (
        <div className={cls.TaskS}>
            <div className={cls.title}>
                <h1>Задания месяца {month}</h1>
            </div>

            <div className={cls.search}>
                <button className={cls.active_btn} style={{ background: 'var(--primary)', color: '#fff' }}>
                    Все задания ({tasks.length})
                </button>
            </div>

            <div className={cls.task_items}>
                {tasks.length === 0 ? (
                    <div style={{ padding: '60px 20px', textAlign: 'center', background: '#0e1225', borderRadius: '12px', width: '100%' }}>
                        <h3>Заданий для этого месяца пока нет</h3>
                        <p style={{ color: '#888', marginTop: '8px' }}>Задания появятся по мере прохождения учебной программы</p>
                    </div>
                ) : (
                    tasks.map((t) => {
                        const sub = t.latestSubmission;
                        const isAccepted = sub?.status === 'ACCEPTED';
                        const isSent = sub?.status === 'SENT';
                        const isRevision = sub?.status === 'REVISION';
                        const canSubmit = !sub || isRevision;

                        return (
                            <div
                                key={t.id}
                                className={`${cls.task_item} ${isAccepted ? cls.done : ''}`}
                                data-aos="fade-up"
                                style={{ minHeight: 'auto', height: 'auto', paddingBottom: '30px' }}
                            >
                                <div className={cls.task_left}>
                                    <div className={cls.img} style={{ marginRight: "10px" }}>
                                        {renderTopicIcon(t.topic)}
                                    </div>

                                    <div className={cls.info} style={{ width: '480px' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                            <h3>{t.title}</h3>
                                            {t.isBonus && <Tag color="gold">БОНУС</Tag>}
                                            {t.hasScore && <Tag color="purple">до {t.maxScore} баллов</Tag>}
                                        </div>

                                        <p>{t.description || 'Описание задания отсутствует'}</p>

                                        <div className={cls.buttons}>
                                            <span className={cls.s}>{t.topic || 'Web'}</span>

                                            {t.exampleLink && (
                                                <button
                                                    className={cls.button_primer}
                                                    onClick={() => window.open(t.exampleLink, "_blank")}
                                                >
                                                    <IoEyeSharp />
                                                    Пример
                                                </button>
                                            )}

                                            <button
                                                style={{ width: '150px' }}
                                                onClick={() => openTaskHistory(t)}
                                            >
                                                История сдач
                                            </button>
                                        </div>
                                    </div>
                                </div>

                                <div className={cls.hr} style={{ height: 'auto', alignSelf: 'stretch' }}></div>

                                <div className={cls.task_right} style={{ position: 'static', width: '480px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                                    <div className={cls.right_infos}>
                                        <div style={{ marginBottom: '12px' }}>
                                            {renderStatusBadge(sub)}
                                        </div>

                                        {isRevision && sub?.reviewerComment && (
                                            <Alert
                                                type="warning"
                                                showIcon
                                                message="Замечания ментора:"
                                                description={sub.reviewerComment}
                                                style={{ marginBottom: '12px' }}
                                            />
                                        )}

                                        {isAccepted && sub?.reviewerComment && (
                                            <Alert
                                                type="success"
                                                showIcon
                                                message="Отзыв ментора:"
                                                description={sub.reviewerComment}
                                                style={{ marginBottom: '12px' }}
                                            />
                                        )}

                                        {sub?.solutionLink && (
                                            <div style={{ fontSize: '13px', color: '#9ca3af', marginBottom: '8px' }}>
                                                Сданное решение:{' '}
                                                <a
                                                    href={sub.solutionLink}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    style={{ color: 'var(--primary, #a855f7)' }}
                                                >
                                                    {sub.solutionLink}
                                                </a>
                                            </div>
                                        )}
                                    </div>

                                    <div style={{ marginTop: '20px', display: 'flex', gap: '12px' }}>
                                        {canSubmit ? (
                                            <Button
                                                type="primary"
                                                icon={<FaGithub />}
                                                size="large"
                                                onClick={() => openSubmitModal(t)}
                                                style={{ background: 'var(--primary, #a855f7)', borderColor: 'var(--primary, #a855f7)' }}
                                            >
                                                {isRevision ? 'Сдать исправленную версию' : 'Сдать ДЗ (GitHub)'}
                                            </Button>
                                        ) : (
                                            <Button
                                                disabled
                                                size="large"
                                                style={{ background: isAccepted ? '#166534' : '#374151', color: '#fff' }}
                                            >
                                                {isAccepted ? '✓ Задание принято' : '⏳ Решение на проверке'}
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            </div>
                        );
                    })
                )}
            </div>

            {/* Модалка отправки решения */}
            <Modal
                title={`Сдача задания: ${selectedTask?.title || ''}`}
                open={submitModalOpen}
                onCancel={() => !submitting && setSubmitModalOpen(false)}
                footer={[
                    <Button key="cancel" onClick={() => setSubmitModalOpen(false)} disabled={submitting}>
                        Отмена
                    </Button>,
                    <Button
                        key="submit"
                        type="primary"
                        loading={submitting}
                        onClick={handleSendSubmission}
                        style={{ background: 'var(--primary, #a855f7)', borderColor: 'var(--primary, #a855f7)' }}
                    >
                        Отправить на проверку
                    </Button>,
                ]}
            >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
                    <div>
                        <label style={{ display: 'block', marginBottom: '6px', fontWeight: 600 }}>
                            Ссылка на репозиторий GitHub *
                        </label>
                        <Input
                            prefix={<FaGithub />}
                            placeholder="https://github.com/username/repository"
                            value={solutionLink}
                            onChange={(e) => setSolutionLink(e.target.value)}
                        />
                        <span style={{ fontSize: '12px', color: '#888', marginTop: '4px', display: 'block' }}>
                            Убедитесь, что репозиторий публичный и содержит выполненный код.
                        </span>
                    </div>

                    <div>
                        <label style={{ display: 'block', marginBottom: '6px', fontWeight: 600 }}>
                            Комментарий к решению (опционально)
                        </label>
                        <Input.TextArea
                            rows={3}
                            placeholder="На что обратить внимание ментору при проверке..."
                            value={comment}
                            onChange={(e) => setComment(e.target.value)}
                        />
                    </div>
                </div>
            </Modal>

            {/* Модалка истории сдачи */}
            <Modal
                title={`История попыток: ${selectedTask?.title || ''}`}
                open={historyModalOpen}
                onCancel={() => setHistoryModalOpen(false)}
                footer={[
                    <Button key="close" onClick={() => setHistoryModalOpen(false)}>
                        Закрыть
                    </Button>,
                ]}
                width={650}
            >
                {loadingHistory ? (
                    <div style={{ textAlign: 'center', padding: '40px 0' }}>
                        <Spin />
                    </div>
                ) : (
                    <div>
                        {(!taskHistory?.submissions || taskHistory.submissions.length === 0) ? (
                            <p style={{ color: '#888', textAlign: 'center', padding: '20px 0' }}>
                                По этому заданию еще не было сдач
                            </p>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '12px' }}>
                                {taskHistory.submissions.map((subItem) => (
                                    <div
                                        key={subItem.id}
                                        style={{
                                            border: '1px solid rgba(255,255,255,0.1)',
                                            borderRadius: '8px',
                                            padding: '12px',
                                            background: 'rgba(255,255,255,0.02)',
                                        }}
                                    >
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                            <span style={{ fontWeight: 600 }}>Попытка #{subItem.version}</span>
                                            {renderStatusBadge(subItem)}
                                        </div>

                                        <div style={{ marginTop: '8px', fontSize: '13px' }}>
                                            <a href={subItem.solutionLink} target="_blank" rel="noreferrer" style={{ color: 'var(--primary)' }}>
                                                {subItem.solutionLink}
                                            </a>
                                        </div>

                                        {subItem.comment && (
                                            <div style={{ marginTop: '6px', fontSize: '13px', color: '#ccc' }}>
                                                <em>Студент: {subItem.comment}</em>
                                            </div>
                                        )}

                                        {subItem.reviewerComment && (
                                            <div style={{ marginTop: '8px', padding: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '6px', fontSize: '13px' }}>
                                                <strong>Ментор:</strong> {subItem.reviewerComment}
                                            </div>
                                        )}

                                        {subItem.voiceFeedbackUrl && (
                                            <div
                                                style={{
                                                    marginTop: '10px',
                                                    padding: '10px 14px',
                                                    background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.12), rgba(239, 68, 68, 0.08))',
                                                    border: '1px solid rgba(168, 85, 247, 0.3)',
                                                    borderRadius: '10px',
                                                    display: 'flex',
                                                    flexDirection: 'column',
                                                    gap: '8px',
                                                }}
                                            >
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#e9d5ff', fontSize: '13px', fontWeight: 600 }}>
                                                    <FaMicrophone style={{ color: '#c084fc' }} />
                                                    <span>Голосовой фидбек ментора</span>
                                                </div>
                                                <audio
                                                    controls
                                                    preload="none"
                                                    style={{ width: '100%', height: '36px', outline: 'none' }}
                                                    src={`${API_BASE_URL}/submissions/${subItem.id}/voice?token=${extractAuthToken() || ''}`}
                                                >
                                                    Ваш браузер не поддерживает воспроизведение аудио.
                                                </audio>
                                            </div>
                                        )}

                                        <div style={{ marginTop: '6px', fontSize: '11px', color: '#777' }}>
                                            Дата: {new Date(subItem.createdAt).toLocaleString('ru-RU')}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </Modal>
        </div>
    );
};
