import { useState, useEffect, useCallback } from "react";
import cls from "../styles/profile.module.scss";
import { useFindUser } from "../../../store/userStore.js";
import { MdEdit, MdLockReset } from "react-icons/md";
import { Modal, Input, message, Row, Col, Spin } from 'antd';
import { FaUser, FaTrophy } from "react-icons/fa";
import { RiTelegram2Line } from "react-icons/ri";
import { FaPeopleGroup } from "react-icons/fa6";
import { ProfileBanner } from "./ProfileBanner.jsx";
import { api } from "../../../api/client.js";
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

    const loadProfileData = useCallback(async () => {
        try {
            setLoading(true);
            const [meRes, achRes] = await Promise.all([
                api.get('/me'),
                api.get('/me/achievements'),
            ]);

            if (meRes.data?.user) {
                addUser(meRes.data.user);
                setName(meRes.data.user.name || '');
                setTelegram(meRes.data.user.telegram || '');
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
    }, [addUser]);

    useEffect(() => {
        loadProfileData();
        const onRefresh = () => loadProfileData();
        window.addEventListener('merts:refresh-achievements', onRefresh);
        return () => window.removeEventListener('merts:refresh-achievements', onRefresh);
    }, [loadProfileData]);

    const handleSaveProfile = async () => {
        try {
            setSavingProfile(true);
            const res = await api.patch('/me', {
                name: name.trim() || undefined,
                telegram: telegram.trim() || undefined,
            });

            if (res.data?.user) {
                addUser(res.data.user);
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
                const res = await api.patch('/me', { avatarUrl: base64 });
                if (res.data?.user) {
                    addUser(res.data.user);
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
            <ProfileBanner />
            <div className={cls.profile}>
                <div className={cls.profile_info}>
                    <div className={cls.profile_infos} data-aos="fade-up">
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
                            {!userInfo?.avatarUrl && <FaUser style={{ fontSize: '48px', color: '#71717a' }} />}
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
                            <h1>{userInfo?.name || userInfo?.login}</h1>
                            <div style={{ fontSize: '14px', color: '#a1a1aa', marginTop: '4px' }}>
                                @{userInfo?.login}
                            </div>
                        </div>

                        <div className={cls.profile_custom}>
                            <div className={cls.profile_custom_infos}>
                                <div style={{ display: 'flex', gap: '8px' }}>
                                    <button onClick={() => setEditModalOpen(true)}>
                                        <MdEdit /> Редактировать
                                    </button>
                                    <button
                                        onClick={() => setPasswordModalOpen(true)}
                                        style={{ background: '#27272a' }}
                                    >
                                        <MdLockReset /> Сменить пароль
                                    </button>
                                </div>

                                <div className={cls.custom_info}>
                                    <div className={cls.custom_info_content}>
                                        <FaUser />
                                        {userInfo?.name || 'Имя не указано'}
                                    </div>
                                    <div className={cls.custom_info_content}>
                                        <RiTelegram2Line />
                                        {userInfo?.telegram || 'Не указан'}
                                    </div>
                                    <div className={cls.custom_info_content}>
                                        <FaPeopleGroup />
                                        Группа {userInfo?.groupNumber || '—'} (М{userInfo?.currentMonth || 1})
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Блок статистики и баллов (Цинк / Янтарь / Изумруд) */}
                <div style={{ maxWidth: '1420px', margin: '30px auto', padding: '0 20px' }}>
                    <Row gutter={[20, 20]}>
                        <Col xs={24} sm={12} md={6}>
                            <div style={{ background: '#18181b', border: '1px solid #27272a', borderRadius: '16px', padding: '20px 24px' }}>
                                <div style={{ color: '#a1a1aa', fontSize: '13px' }}>Всего баллов</div>
                                <div style={{ fontSize: '28px', fontWeight: 800, color: '#fbbf24', marginTop: '4px' }}>
                                    {stats.totalScore}
                                </div>
                            </div>
                        </Col>
                        <Col xs={24} sm={12} md={6}>
                            <div style={{ background: '#18181b', border: '1px solid #27272a', borderRadius: '16px', padding: '20px 24px' }}>
                                <div style={{ color: '#a1a1aa', fontSize: '13px' }}>Принятых заданий</div>
                                <div style={{ fontSize: '28px', fontWeight: 800, color: '#34d399', marginTop: '4px' }}>
                                    {stats.tasksAcceptedCount}
                                </div>
                            </div>
                        </Col>
                        <Col xs={24} sm={12} md={6}>
                            <div style={{ background: '#18181b', border: '1px solid #27272a', borderRadius: '16px', padding: '20px 24px' }}>
                                <div style={{ color: '#a1a1aa', fontSize: '13px' }}>Получено ачивок</div>
                                <div style={{ fontSize: '28px', fontWeight: 800, color: '#fbbf24', marginTop: '4px' }}>
                                    {achievements.length}
                                </div>
                            </div>
                        </Col>
                        <Col xs={24} sm={12} md={6}>
                            <div style={{ background: '#18181b', border: '1px solid #27272a', borderRadius: '16px', padding: '20px 24px' }}>
                                <div style={{ color: '#a1a1aa', fontSize: '13px' }}>Текущий месяц</div>
                                <div style={{ fontSize: '28px', fontWeight: 800, color: '#f4f4f5', marginTop: '4px' }}>
                                    {userInfo?.currentMonth || 1}
                                </div>
                            </div>
                        </Col>
                    </Row>
                </div>

                {/* Блок достижений студента (Строго Zinc + Amber + Emerald) */}
                <div style={{ maxWidth: '1420px', margin: '20px auto 60px auto', padding: '0 20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
                        <h2 style={{ fontSize: '22px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '10px', color: '#f4f4f5' }}>
                            <FaTrophy style={{ color: '#fbbf24' }} /> Мои достижения ({achievements.length})
                        </h2>
                        <button
                            type="button"
                            onClick={() => navigate('/achievements')}
                            style={{
                                background: '#18181b',
                                border: '1px solid rgba(245, 158, 11, 0.35)',
                                color: '#fbbf24',
                                padding: '8px 16px',
                                borderRadius: '12px',
                                fontSize: '14px',
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
                        <div style={{ background: '#18181b', padding: '40px 20px', borderRadius: '16px', textAlign: 'center', border: '1px solid #27272a' }}>
                            <p style={{ color: '#a1a1aa', fontSize: '16px', margin: 0 }}>
                                Вы пока не получили достижений. Сдавайте домашние задания вовремя, чтобы открыть первые награды!
                            </p>
                        </div>
                    ) : (
                        <Row gutter={[16, 16]}>
                            {achievements.map((ach) => (
                                <Col xs={24} sm={12} md={8} lg={6} key={ach.id}>
                                    <div
                                        onClick={() => openAchievementDetail(ach)}
                                        style={{
                                            background: '#18181b',
                                            border: '1px solid rgba(245, 158, 11, 0.3)',
                                            borderRadius: '16px',
                                            padding: '18px',
                                            cursor: 'pointer',
                                            transition: 'transform 0.2s ease, border-color 0.2s ease',
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
