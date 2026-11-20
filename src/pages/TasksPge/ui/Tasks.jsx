import { safeUrl } from '../../../utils/safeUrl.js';
import { useState, useEffect, useCallback } from "react";
import cls from "../styles/task.module.scss";
import { IoCheckmarkDoneCircleOutline, IoEyeSharp } from "react-icons/io5";
import { FaGithub, FaHtml5, FaClock, FaExclamationTriangle, FaMicrophone } from "react-icons/fa";
import { IoLogoCss3, IoLogoJavascript } from "react-icons/io";
import { Modal, Input, Button, Tag, Spin, message, Alert } from "antd";
import { api, resolveMediaUrl } from "../../../api/client.js";
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

    const applyTasksResponse = useCallback((data, requestedMonth) => {
        setTasks(data?.tasks || []);
        setMonth(data?.month || Number(requestedMonth) || userInfo?.currentMonth || 1);
    }, [userInfo?.currentMonth]);

    const fetchTasks = useCallback(async () => {
        try {
            const requestedMonth = new URLSearchParams(window.location.search).get('month');
            const params = /^[1-9]\d*$/.test(requestedMonth || '') ? { month: requestedMonth } : {};
            const res = await api.get('/tasks', { params });
            applyTasksResponse(res.data, params.month);
        } catch (err) {
            console.error('Failed to load tasks', err);
            message.error('Не удалось загрузить задания');
        } finally {
            setLoading(false);
        }
    }, [applyTasksResponse]);

    useEffect(() => {
        let active = true;
        const load = async () => {
            try {
                const requestedMonth = new URLSearchParams(window.location.search).get('month');
                const params = /^[1-9]\d*$/.test(requestedMonth || '') ? { month: requestedMonth } : {};
                const res = await api.get('/tasks', { params });
                if (active) applyTasksResponse(res.data, params.month);
            } catch (err) {
                console.error('Failed to load tasks', err);
                if (active) message.error('Не удалось загрузить задания');
            } finally {
                if (active) setLoading(false);
            }
        };
        load();
        return () => { active = false; };
    }, [applyTasksResponse]);

    useEffect(() => {
        const task = tasks.find(({ id }) => window.location.hash === `#task-${encodeURIComponent(id)}`);
        if (!loading && task) {
            document.getElementById(`task-${task.id}`)?.scrollIntoView({ block: 'start' });
        }
    }, [loading, tasks]);

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
            const res = await api.post('/submissions', {
                taskId: selectedTask.id,
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
            const [taskRes, subsRes] = await Promise.all([
                api.get(`/tasks/${task.id}`),
                api.get('/submissions', { params: { taskId: task.id } }),
            ]);
            const taskObj = taskRes.data?.task || taskRes.data || task;
            const submissions = subsRes.data?.submissions || taskObj.submissions || [];
            setTaskHistory({ ...taskObj, submissions });
        } catch {
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
                        const sub = t.mySubmission ?? t.latestSubmission;
                        const isAccepted = sub?.status === 'ACCEPTED';
                        const isRevision = sub?.status === 'REVISION';
                        const canSubmit = !sub || isRevision;

                        return (
                            <div
                                key={t.id}
                                id={`task-${t.id}`}
                                className={`${cls.task_item} ${isAccepted ? cls.done : ''}`}
                                data-aos="fade-up"
                                style={{ minHeight: 'auto', height: 'auto', paddingBottom: '30px' }}
                            >
                                <div className={cls.task_left}>
                                    <div className={cls.img} style={{ marginRight: "10px" }}>
                                        {renderTopicIcon(t.topic)}
                                    </div>

                                    <div className={cls.info} style={{ flex: '1 1 320px', minWidth: 0, width: '100%' }}>
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
                                                    onClick={() => window.open(safeUrl(t.exampleLink), "_blank", "noopener,noreferrer")}
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

                                <div className={cls.task_right} style={{ position: 'static', flex: '1 1 320px', minWidth: 0, width: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
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
                                                    href={safeUrl(sub.solutionLink)}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    style={{ color: 'var(--primary, #f59e0b)' }}
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
                                                style={{ background: 'var(--primary, #f59e0b)', borderColor: 'var(--primary, #f59e0b)' }}
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
                        style={{ background: 'var(--primary, #f59e0b)', borderColor: 'var(--primary, #f59e0b)' }}
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
                                            <a href={safeUrl(subItem.solutionLink)} target="_blank" rel="noreferrer" style={{ color: 'var(--primary)' }}>
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
                                                    background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.12), rgba(239, 68, 68, 0.08))',
                                                    border: '1px solid rgba(245, 158, 11, 0.3)',
                                                    borderRadius: '10px',
                                                    display: 'flex',
                                                    flexDirection: 'column',
                                                    gap: '8px',
                                                }}
                                            >
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#e9d5ff', fontSize: '13px', fontWeight: 600 }}>
                                                    <FaMicrophone style={{ color: '#fbbf24' }} />
                                                    <span>Голосовой фидбек ментора</span>
                                                </div>
                                                <audio
                                                    controls
                                                    preload="none"
                                                    style={{ width: '100%', height: '36px', outline: 'none' }}
                                                    src={resolveMediaUrl(subItem.voiceFeedbackUrl)}
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
