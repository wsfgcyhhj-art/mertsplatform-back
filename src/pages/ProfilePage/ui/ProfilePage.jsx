import { useState, useEffect, useCallback } from "react";
import cls from "../styles/profile.module.scss";
import { useFindUser } from "../../../store/userStore.js";
import { MdEdit, MdLockReset, MdRefresh, MdLinkOff } from "react-icons/md";
import { Modal, Input, message, Row, Col, Spin } from 'antd';
import { toast } from "react-toastify";
import { FaUser, FaTrophy } from "react-icons/fa";
import { RiTelegram2Line } from "react-icons/ri";
import { FaPeopleGroup } from "react-icons/fa6";
import { ProfileBanner } from "./ProfileBanner.jsx";
import { api, API_BASE_URL, extractAuthToken } from "../../../api/client.js";
import { useNavigate } from "react-router-dom";
import { AchievementIcon } from "../../../components/AchievementToast.jsx";

export const ProfilePage = () => {
    const { userInfo, addUser } = useFindUser();
    const navigate = useNavigate();

    const [stats, setStats] = useState({ totalScore: 0, tasksAcceptedCount: 0 });
    const [achievements, setAchievements] = useState([]);
    const [loading, setLoading] = useState(true);

    // Модалка редактирования профиля
    const [editModalOpen, setEditModalOpen] = useState(false);
    const [name, setName] = useState(userInfo?.name || '');
    const [telegram, setTelegram] = useState(userInfo?.telegram || '');
    const [savingProfile, setSavingProfile] = useState(false);

    // Модалка смены пароля
    const [passwordModalOpen, setPasswordModalOpen] = useState(false);
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [changingPassword, setChangingPassword] = useState(false);

    // Модалка просмотра детали ачивки
    const [achDetailModal, setAchDetailModal] = useState(false);
    const [selectedAch, setSelectedAch] = useState(null);
    const [loadingDetail, setLoadingDetail] = useState(false);

    // Состояние привязки Telegram-бота
    const [isTelegramConnected, setIsTelegramConnected] = useState(Boolean(userInfo?.isTelegramConnected));
    const [telegramUsername, setTelegramUsername] = useState(userInfo?.telegramUsername || null);
    const [tgConnecting, setTgConnecting] = useState(false);
    const [tgDisconnecting, setTgDisconnecting] = useState(false);
    const [tgPolling, setTgPolling] = useState(false);
    const [refreshingTgStatus, setRefreshingTgStatus] = useState(false);

    const getAuthToken = useCallback(() => {
        return (
            localStorage.getItem('accessToken') ||
            localStorage.getItem('token') ||
            sessionStorage.getItem('accessToken') ||
            extractAuthToken()
        );
    }, []);

    const loadProfileData = useCallback(async () => {
        try {
            setLoading(true);
            const token = getAuthToken();
            const authHeaders = token
                ? {
                      'Content-Type': 'application/json',
                      'Authorization': `Bearer ${token}`,
                  }
                : undefined;

            const [meRes, achRes] = await Promise.all([
                api.get('/me', { headers: authHeaders }),
                api.get('/me/achievements', { headers: authHeaders }),
            ]);

            if (meRes.data?.user) {
                addUser(meRes.data.user, token);
                setName(meRes.data.user.name || '');
                setTelegram(meRes.data.user.telegram || '');
            }
            const connected = Boolean(meRes.data?.isTelegramConnected ?? meRes.data?.user?.isTelegramConnected);
            const tgUser = meRes.data?.telegramUsername ?? meRes.data?.user?.telegramUsername ?? null;
            setIsTelegramConnected(connected);
            setTelegramUsername(tgUser);
            if (connected) {
                setTgPolling(false);
            }
            if (meRes.data?.stats) {
                setStats(meRes.data.stats);
            }
            if (achRes.data?.achievements) {
                setAchievements(achRes.data.achievements);
            }
        } catch (err) {
            console.error('Failed to load profile data', err);
        } finally {
            setLoading(false);
        }
    }, [addUser, getAuthToken]);

    useEffect(() => {
        loadProfileData();
        const onRefresh = () => loadProfileData();
        window.addEventListener('merts:refresh-achievements', onRefresh);
        return () => window.removeEventListener('merts:refresh-achievements', onRefresh);
    }, [loadProfileData]);

    // Поллинг статуса привязки Telegram после перехода в бота
    useEffect(() => {
        if (!tgPolling || isTelegramConnected) return undefined;

        let attempts = 0;
        const intervalId = setInterval(async () => {
            attempts += 1;
            const token =
                localStorage.getItem('accessToken') ||
                localStorage.getItem('token') ||
                sessionStorage.getItem('accessToken') ||
                extractAuthToken();

            if (!token) {
                setTgPolling(false);
                return;
            }

            try {
                const response = await fetch(`${API_BASE_URL}/me`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`,
                    },
                    credentials: 'include',
                });

                if (response.status === 401) {
                    setTgPolling(false);
                    return;
                }

                if (response.ok) {
                    const data = await response.json();
                    const connected = Boolean(data?.isTelegramConnected ?? data?.user?.isTelegramConnected);
                    const tgUser = data?.telegramUsername ?? data?.user?.telegramUsername ?? null;
                    if (connected) {
                        setIsTelegramConnected(true);
                        setTelegramUsername(tgUser);
                        setTgPolling(false);
                        if (data?.user) addUser(data.user, token);
                        message.success('Telegram успешно подключен!');
                    }
                }
            } catch {
                // Игнорируем сетевые ошибки при фоновом поллинге
            }
            if (attempts >= 30) {
                setTgPolling(false);
            }
        }, 4000);

        return () => clearInterval(intervalId);
    }, [tgPolling, isTelegramConnected, addUser]);

    const handleConnectTelegram = async () => {
        const token =
            localStorage.getItem('accessToken') ||
            localStorage.getItem('token') ||
            sessionStorage.getItem('accessToken') ||
            extractAuthToken();

        if (!token) {
            toast.error('Сессия истекла, пожалуйста, войдите снова');
            message.error('Сессия истекла, пожалуйста, войдите снова');
            navigate('/login');
            return;
        }

        try {
            setTgConnecting(true);
            const response = await fetch(`${API_BASE_URL}/me/telegram/connect`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                credentials: 'include',
            });

            if (response.status === 401) {
                toast.error('Необходима повторная авторизация');
                message.error('Необходима повторная авторизация');
                return;
            }

            const data = await response.json();
            if (!response.ok) {
                throw new Error(data?.message || data?.error || 'Не удалось сгенерировать ссылку для Telegram');
            }

            if (data?.link) {
                window.open(data.link, '_blank', 'noopener,noreferrer');
                setTgPolling(true);
                message.info('Перейдите в открывшийся Telegram-бот и нажмите «Запустить» (/start)');
            }
        } catch (err) {
            message.error(err.message || 'Не удалось сгенерировать ссылку для Telegram');
        } finally {
            setTgConnecting(false);
        }
    };

    const handleDisconnectTelegram = async () => {
        const token =
            localStorage.getItem('accessToken') ||
            localStorage.getItem('token') ||
            sessionStorage.getItem('accessToken') ||
            extractAuthToken();

        if (!token) {
            toast.error('Сессия истекла, пожалуйста, войдите снова');
            message.error('Сессия истекла, пожалуйста, войдите снова');
            navigate('/login');
            return;
        }

        try {
            setTgDisconnecting(true);
            const response = await fetch(`${API_BASE_URL}/me/telegram/disconnect`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                credentials: 'include',
            });

            if (response.status === 401) {
                toast.error('Необходима повторная авторизация');
                message.error('Необходима повторная авторизация');
                return;
            }

            const data = await response.json();
            if (!response.ok) {
                throw new Error(data?.message || data?.error || 'Не удалось отвязать Telegram');
            }

            setIsTelegramConnected(false);
            setTelegramUsername(null);
            setTgPolling(false);
            if (userInfo) {
                addUser({ ...userInfo, isTelegramConnected: false, telegramUsername: null }, token);
            }
            message.success('Telegram-уведомления отключены');
        } catch (err) {
            message.error(err.message || 'Не удалось отвязать Telegram');
        } finally {
            setTgDisconnecting(false);
        }
    };

    const handleCheckTelegramStatus = async () => {
        const token =
            localStorage.getItem('accessToken') ||
            localStorage.getItem('token') ||
            sessionStorage.getItem('accessToken') ||
            extractAuthToken();

        if (!token) {
            toast.error('Сессия истекла, пожалуйста, войдите снова');
            message.error('Сессия истекла, пожалуйста, войдите снова');
            navigate('/login');
            return;
        }

        try {
            setRefreshingTgStatus(true);
            const response = await fetch(`${API_BASE_URL}/me`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                credentials: 'include',
            });

            if (response.status === 401) {
                toast.error('Необходима повторная авторизация');
                message.error('Необходима повторная авторизация');
                return;
            }

            const data = await response.json();
            if (!response.ok) {
                throw new Error(data?.message || data?.error || 'Не удалось проверить статус подключения');
            }

            const connected = Boolean(data?.isTelegramConnected ?? data?.user?.isTelegramConnected);
            const tgUser = data?.telegramUsername ?? data?.user?.telegramUsername ?? null;
            setIsTelegramConnected(connected);
            setTelegramUsername(tgUser);
            if (data?.user) {
                addUser(data.user, token);
            }
            if (connected) {
                setTgPolling(false);
                message.success('Telegram подключен!');
            } else {
                message.info('Привязка пока не завершена. Нажмите /start в боте и проверьте снова.');
            }
        } catch (err) {
            message.error(err.message || 'Не удалось проверить статус подключения');
        } finally {
            setRefreshingTgStatus(false);
        }
    };

    const handleSaveProfile = async () => {
        try {
            setSavingProfile(true);
            const token = getAuthToken();
            const res = await api.patch('/users/me/profile', {
                name: name.trim() || undefined,
                telegram: telegram.trim() || undefined,
            });

            if (res.data?.user) {
                addUser(res.data.user, token);
                message.success('Профиль успешно обновлен!');
                setEditModalOpen(false);
            }
        } catch (err) {
            message.error(err.response?.data?.message || 'Не удалось сохранить профиль');
        } finally {
            setSavingProfile(false);
        }
    };

    const handleAvatarUpload = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = async () => {
            const base64 = reader.result;
            try {
                const token = getAuthToken();
                const res = await api.patch('/users/me/avatar', { avatarUrl: base64 });
                if (res.data?.user) {
                    addUser(res.data.user, token);
                    message.success('Аватар обновлен!');
                }
            } catch {
                message.error('Не удалось загрузить аватар');
            }
        };
        reader.readAsDataURL(file);
    };

    const handleChangePassword = async () => {
        if (!currentPassword || !newPassword) {
            message.warning('Введите старый и новый пароли');
            return;
        }
        if (newPassword.length < 4) {
            message.warning('Новый пароль должен содержать минимум 4 символа');
            return;
        }

        try {
            setChangingPassword(true);
            await api.post('/me/change-password', {
                currentPassword,
                newPassword,
            });
            message.success('Пароль успешно изменен!');
            setPasswordModalOpen(false);
            setCurrentPassword('');
            setNewPassword('');
        } catch (err) {
            message.error(err.response?.data?.message || 'Ошибка смены пароля');
        } finally {
            setChangingPassword(false);
        }
    };

    const openAchievementDetail = async (ach) => {
        setAchDetailModal(true);
        setLoadingDetail(true);
        try {
            const res = await api.get(`/achievements/${ach.id}`);
            setSelectedAch(res.data?.achievement || ach);
        } catch {
            setSelectedAch(ach);
        } finally {
            setLoadingDetail(false);
        }
    };

    return (
        <>
            {/* 1. Обложка сверху */}
            <ProfileBanner />

            <div className={cls.profile}>
                {/* 2. Шапка (Hero) профиля: Аватар + Имя + Никнейм + Роль слева, кнопки справа */}
                <div className={cls.profile_info}>
                    <div className={cls.profile_infos} data-aos="fade-up">
                        <div className={cls.profile_hero_left}>
                            <div
                                className={cls.profile_avatar}
                                style={{
                                    backgroundImage: userInfo?.avatarUrl ? `url(${userInfo.avatarUrl})` : 'none',
                                    backgroundSize: 'cover',
                                    backgroundPosition: 'center',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                }}
                            >
                                {!userInfo?.avatarUrl && <FaUser style={{ fontSize: '46px', color: '#71717a' }} />}
                                <label className={cls.profiel_change}>
                                    изменить фото
                                    <input
                                        type="file"
                                        accept="image/*"
                                        onChange={handleAvatarUpload}
                                        className={cls.file}
                                    />
                                </label>
                            </div>

                            <div className={cls.profile_statistic_info}>
                                <div className={cls.profile_student}>
                                    {userInfo?.role === 'ADMIN' ? 'Администратор' : 'Студент'}
                                </div>
                                <h1>{userInfo?.name || userInfo?.login || 'Merts'}</h1>
                                <div style={{ fontSize: '15px', color: '#a1a1aa', fontWeight: 500 }}>
                                    @{userInfo?.login || 'ular'}
                                </div>

                                <div className={cls.custom_info} style={{ marginTop: '8px' }}>
                                    <div className={cls.custom_info_content}>
                                        <FaPeopleGroup style={{ color: '#fbbf24' }} />
                                        Группа {userInfo?.groupNumber || '—'} (М{userInfo?.currentMonth || 1})
                                    </div>
                                    <div
                                        className={cls.custom_info_content}
                                        title="Дней подряд в платформе"
                                        style={{
                                            border: '1px solid rgba(245, 158, 11, 0.35)',
                                            background: 'rgba(245, 158, 11, 0.1)',
                                            color: '#fbbf24',
                                        }}
                                    >
                                        <span>🔥</span>
                                        Стрик: {userInfo?.streakCount || 0} дн.
                                    </div>
                                    {userInfo?.telegram && (
                                        <div className={cls.custom_info_content}>
                                            <RiTelegram2Line style={{ color: '#34d399' }} />
                                            {userInfo.telegram}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div className={cls.profile_custom}>
                            <div className={cls.profile_custom_infos}>
                                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                                    <button
                                        type="button"
                                        onClick={() => setEditModalOpen(true)}
                                        style={{
                                            background: '#f59e0b',
                                            color: '#09090b',
                                            borderColor: '#f59e0b',
                                            fontWeight: 700,
                                        }}
                                    >
                                        <MdEdit /> Редактировать
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => setPasswordModalOpen(true)}
                                        style={{ background: '#27272a', color: '#f4f4f5' }}
                                    >
                                        <MdLockReset /> Сменить пароль
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* 3. Сетка статистики (4 плашки в один ряд) */}
                <div className={cls.stats_grid}>
                    <div style={{ background: '#18181b', border: '1px solid #27272a', borderRadius: '16px', padding: '20px 24px' }}>
                        <div style={{ color: '#a1a1aa', fontSize: '13px' }}>Всего баллов</div>
                        <div style={{ fontSize: '28px', fontWeight: 800, color: '#fbbf24', marginTop: '4px' }}>
                            {stats.totalScore}
                        </div>
                    </div>

                    <div style={{ background: '#18181b', border: '1px solid #27272a', borderRadius: '16px', padding: '20px 24px' }}>
                        <div style={{ color: '#a1a1aa', fontSize: '13px' }}>Принятых заданий</div>
                        <div style={{ fontSize: '28px', fontWeight: 800, color: '#34d399', marginTop: '4px' }}>
                            {stats.tasksAcceptedCount}
                        </div>
                    </div>

                    <div style={{ background: '#18181b', border: '1px solid #27272a', borderRadius: '16px', padding: '20px 24px' }}>
                        <div style={{ color: '#a1a1aa', fontSize: '13px' }}>Получено ачивок</div>
                        <div style={{ fontSize: '28px', fontWeight: 800, color: '#fbbf24', marginTop: '4px' }}>
                            {achievements.length}
                        </div>
                    </div>

                    <div style={{ background: '#18181b', border: '1px solid #27272a', borderRadius: '16px', padding: '20px 24px' }}>
                        <div style={{ color: '#a1a1aa', fontSize: '13px' }}>Текущий месяц</div>
                        <div style={{ fontSize: '28px', fontWeight: 800, color: '#f4f4f5', marginTop: '4px' }}>
                            {userInfo?.currentMonth || 1}
                        </div>
                    </div>
                </div>

                {/* 4. Двухколоночный грид: слева (1 кол.) — Уведомления в Telegram, справа (2 кол.) — Мои достижения */}
                <div className={`${cls.main_grid} grid grid-cols-1 lg:grid-cols-3 gap-6`}>
                    {/* Левая колонка: Уведомления в Telegram */}
                    <div className={`${cls.col_left} lg:col-span-1`}>
                        <div
                            className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6"
                            style={{
                                background: '#18181b',
                                border: isTelegramConnected
                                    ? '1px solid rgba(16, 185, 129, 0.35)'
                                    : '1px solid #27272a',
                                borderRadius: '16px',
                                padding: '24px',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '18px',
                            }}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                                <div
                                    style={{
                                        width: '48px',
                                        height: '48px',
                                        minWidth: '48px',
                                        borderRadius: '14px',
                                        background: isTelegramConnected
                                            ? 'rgba(16, 185, 129, 0.12)'
                                            : 'rgba(245, 158, 11, 0.12)',
                                        border: isTelegramConnected
                                            ? '1px solid rgba(16, 185, 129, 0.35)'
                                            : '1px solid rgba(245, 158, 11, 0.35)',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        color: isTelegramConnected ? '#34d399' : '#fbbf24',
                                        fontSize: '24px',
                                    }}
                                >
                                    <RiTelegram2Line />
                                </div>
                                <div>
                                    <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#f4f4f5' }}>
                                        Уведомления в Telegram
                                    </h3>
                                    {isTelegramConnected && (
                                        <span
                                            style={{
                                                display: 'inline-flex',
                                                alignItems: 'center',
                                                gap: '6px',
                                                marginTop: '6px',
                                                padding: '3px 10px',
                                                borderRadius: '999px',
                                                fontSize: '12px',
                                                fontWeight: 700,
                                                color: '#34d399',
                                                background: 'rgba(16, 185, 129, 0.12)',
                                                border: '1px solid rgba(16, 185, 129, 0.35)',
                                            }}
                                        >
                                            ● Подключен ({telegramUsername ? `@${telegramUsername.replace(/^@/, '')}` : 'активен'})
                                        </span>
                                    )}
                                </div>
                            </div>

                            <p style={{ margin: 0, fontSize: '14px', color: '#a1a1aa', lineHeight: 1.55 }}>
                                Получайте мгновенные уведомления о проверке ДЗ и новых ачивках
                            </p>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                {!isTelegramConnected ? (
                                    <>
                                        <button
                                            type="button"
                                            onClick={handleConnectTelegram}
                                            disabled={tgConnecting}
                                            style={{
                                                width: '100%',
                                                display: 'inline-flex',
                                                alignItems: 'center',
                                                justifyContent: 'center',
                                                gap: '8px',
                                                background: '#f59e0b',
                                                color: '#09090b',
                                                border: 'none',
                                                borderRadius: '12px',
                                                padding: '12px 18px',
                                                fontSize: '14px',
                                                fontWeight: 700,
                                                cursor: tgConnecting ? 'not-allowed' : 'pointer',
                                                opacity: tgConnecting ? 0.7 : 1,
                                            }}
                                        >
                                            <RiTelegram2Line style={{ fontSize: '18px' }} />
                                            {tgConnecting ? 'Генерация ссылки...' : 'Подключить Telegram'}
                                        </button>
                                        <button
                                            type="button"
                                            onClick={handleCheckTelegramStatus}
                                            disabled={refreshingTgStatus}
                                            style={{
                                                width: '100%',
                                                display: 'inline-flex',
                                                alignItems: 'center',
                                                justifyContent: 'center',
                                                gap: '6px',
                                                background: '#27272a',
                                                color: '#e4e4e7',
                                                border: '1px solid #3f3f46',
                                                borderRadius: '12px',
                                                padding: '10px 14px',
                                                fontSize: '13px',
                                                fontWeight: 600,
                                                cursor: refreshingTgStatus ? 'not-allowed' : 'pointer',
                                            }}
                                        >
                                            <MdRefresh style={{ fontSize: '16px' }} />
                                            {refreshingTgStatus
                                                ? 'Проверка...'
                                                : tgPolling
                                                ? 'Ожидание бота... (Обновить)'
                                                : 'Обновить статус'}
                                        </button>
                                    </>
                                ) : (
                                    <button
                                        type="button"
                                        onClick={handleDisconnectTelegram}
                                        disabled={tgDisconnecting}
                                        style={{
                                            width: '100%',
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            gap: '8px',
                                            background: '#27272a',
                                            color: '#f4f4f5',
                                            border: '1px solid #3f3f46',
                                            borderRadius: '12px',
                                            padding: '11px 16px',
                                            fontSize: '14px',
                                            fontWeight: 600,
                                            cursor: tgDisconnecting ? 'not-allowed' : 'pointer',
                                            opacity: tgDisconnecting ? 0.7 : 1,
                                        }}
                                    >
                                        <MdLinkOff style={{ fontSize: '16px', color: '#fbbf24' }} />
                                        {tgDisconnecting ? 'Отвязка...' : 'Отвязать'}
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Правая колонка: Мои достижения */}
                    <div className={`${cls.col_right} lg:col-span-2`}>
                        <div
                            className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6"
                            style={{
                                background: '#18181b',
                                border: '1px solid #27272a',
                                borderRadius: '16px',
                                padding: '24px',
                            }}
                        >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginBottom: '20px' }}>
                                <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '10px', color: '#f4f4f5' }}>
                                    <FaTrophy style={{ color: '#fbbf24' }} /> Мои достижения ({achievements.length})
                                </h2>
                                <button
                                    type="button"
                                    onClick={() => navigate('/achievements')}
                                    style={{
                                        background: '#09090b',
                                        border: '1px solid rgba(245, 158, 11, 0.35)',
                                        color: '#fbbf24',
                                        padding: '8px 16px',
                                        borderRadius: '12px',
                                        fontSize: '13px',
                                        fontWeight: 600,
                                        cursor: 'pointer',
                                    }}
                                >
                                    Все достижения каталога →
                                </button>
                            </div>

                            {loading ? (
                                <div style={{ textAlign: 'center', padding: '40px 0' }}><Spin /></div>
                            ) : achievements.length === 0 ? (
                                <div style={{ background: '#09090b', padding: '36px 20px', borderRadius: '14px', textAlign: 'center', border: '1px solid #27272a' }}>
                                    <p style={{ color: '#a1a1aa', fontSize: '15px', margin: 0 }}>
                                        Вы пока не получили достижений. Сдавайте домашние задания вовремя, чтобы открыть первые награды!
                                    </p>
                                </div>
                            ) : (
                                <Row gutter={[16, 16]}>
                                    {achievements.map((ach) => (
                                        <Col xs={24} sm={12} key={ach.id}>
                                            <div
                                                onClick={() => openAchievementDetail(ach)}
                                                style={{
                                                    background: '#09090b',
                                                    border: '1px solid rgba(245, 158, 11, 0.3)',
                                                    borderRadius: '14px',
                                                    padding: '16px',
                                                    cursor: 'pointer',
                                                    transition: 'transform 0.2s ease, border-color 0.2s ease',
                                                    height: '100%',
                                                }}
                                            >
                                                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '14px' }}>
                                                    <div
                                                        style={{
                                                            width: 44,
                                                            height: 44,
                                                            minWidth: 44,
                                                            borderRadius: 12,
                                                            background: 'rgba(245, 158, 11, 0.1)',
                                                            border: '1px solid rgba(245, 158, 11, 0.3)',
                                                            display: 'flex',
                                                            alignItems: 'center',
                                                            justifyContent: 'center',
                                                        }}
                                                    >
                                                        <AchievementIcon name={ach.iconUrl} size={20} />
                                                    </div>
                                                    <div>
                                                        <div style={{ fontWeight: 700, fontSize: '15px', color: '#f4f4f5' }}>{ach.title}</div>
                                                        <div style={{ fontSize: '13px', color: '#a1a1aa', marginTop: 4 }}>{ach.description}</div>
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: '10px' }}>
                                                            <span style={{ fontSize: '11px', fontWeight: 700, color: '#fbbf24', background: 'rgba(245, 158, 11, 0.1)', padding: '2px 8px', borderRadius: 6 }}>
                                                                +{ach.points || 10} pts
                                                            </span>
                                                            <span style={{ fontSize: '11px', color: '#34d399' }}>
                                                                ✓ {new Date(ach.awardedAt).toLocaleDateString('ru-RU')}
                                                            </span>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </Col>
                                    ))}
                                </Row>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* Модалка редактирования профиля */}
            <Modal
                title="Редактирование профиля"
                open={editModalOpen}
                onCancel={() => setEditModalOpen(false)}
                onOk={handleSaveProfile}
                confirmLoading={savingProfile}
                okText="Сохранить"
                cancelText="Отмена"
            >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '14px' }}>
                    <div>
                        <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', fontWeight: 600 }}>
                            Имя и Фамилия
                        </label>
                        <Input
                            placeholder="Ваше имя"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                        />
                    </div>
                    <div>
                        <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', fontWeight: 600 }}>
                            Telegram (@username)
                        </label>
                        <Input
                            placeholder="@username"
                            value={telegram}
                            onChange={(e) => setTelegram(e.target.value)}
                        />
                    </div>
                </div>
            </Modal>

            {/* Модалка смены пароля */}
            <Modal
                title="Смена пароля"
                open={passwordModalOpen}
                onCancel={() => setPasswordModalOpen(false)}
                onOk={handleChangePassword}
                confirmLoading={changingPassword}
                okText="Изменить пароль"
                cancelText="Отмена"
            >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '14px' }}>
                    <div>
                        <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', fontWeight: 600 }}>
                            Текущий пароль *
                        </label>
                        <Input.Password
                            placeholder="Старый пароль"
                            value={currentPassword}
                            onChange={(e) => setCurrentPassword(e.target.value)}
                        />
                    </div>
                    <div>
                        <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', fontWeight: 600 }}>
                            Новый пароль *
                        </label>
                        <Input.Password
                            placeholder="Новый пароль (минимум 4 символа)"
                            value={newPassword}
                            onChange={(e) => setNewPassword(e.target.value)}
                        />
                    </div>
                </div>
            </Modal>

            {/* Модалка деталки ачивки */}
            <Modal
                open={achDetailModal}
                onCancel={() => setAchDetailModal(false)}
                footer={null}
                centered
            >
                {loadingDetail || !selectedAch ? (
                    <div style={{ textAlign: 'center', padding: '40px 0' }}><Spin /></div>
                ) : (
                    <div style={{ textAlign: 'center', padding: '10px 0' }}>
                        <div
                            style={{
                                width: 64,
                                height: 64,
                                margin: '0 auto 14px auto',
                                borderRadius: 16,
                                background: 'rgba(245, 158, 11, 0.12)',
                                border: '1px solid rgba(245, 158, 11, 0.35)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                            }}
                        >
                            <AchievementIcon name={selectedAch.iconUrl} size={30} />
                        </div>
                        <h2 style={{ fontSize: '20px', fontWeight: 700 }}>{selectedAch.title}</h2>
                        <p style={{ color: '#a1a1aa', marginTop: '6px' }}>{selectedAch.description}</p>
                        <div style={{ background: '#18181b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', textAlign: 'left', marginTop: '14px' }}>
                            <div style={{ fontSize: '12px', color: '#71717a' }}>Критерий:</div>
                            <div style={{ fontSize: '13px', color: '#e4e4e7', marginTop: '2px' }}>
                                {selectedAch.criteria || selectedAch.description}
                            </div>
                        </div>
                    </div>
                )}
            </Modal>
        </>
    );
};
