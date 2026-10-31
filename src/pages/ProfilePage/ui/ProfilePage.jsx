import { useState, useEffect } from "react";
import cls from "../styles/profile.module.scss";
import { useFindUser } from "../../../store/userStore.js";
import { MdEdit, MdLockReset } from "react-icons/md";
import { Button, Modal, Input, message, Avatar, Row, Col, Card, Tag, Spin } from 'antd';
import { FaTelegram, FaUser, FaCheckCircle, FaTrophy } from "react-icons/fa";
import { RiTelegram2Line } from "react-icons/ri";
import { FaPeopleGroup } from "react-icons/fa6";
import { ProfileBanner } from "./ProfileBanner.jsx";
import { api } from "../../../api/client.js";
import { useNavigate } from "react-router-dom";

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

    const loadProfileData = async () => {
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
    };

    useEffect(() => {
        loadProfileData();
    }, []);

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
            } catch (err) {
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
        } catch (err) {
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
                            {!userInfo?.avatarUrl && <FaUser style={{ fontSize: '48px', color: '#666' }} />}
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
                            <div style={{ fontSize: '14px', color: '#9ca3af', marginTop: '4px' }}>
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
                                        style={{ background: 'rgba(255,255,255,0.08)' }}
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

                {/* Блок статистики и баллов */}
                <div style={{ maxWidth: '1420px', margin: '30px auto', padding: '0 20px' }}>
                    <Row gutter={[20, 20]}>
                        <Col xs={24} sm={12} md={6}>
                            <Card style={{ background: 'var(--card, #131935)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '14px' }}>
                                <div style={{ color: '#9ca3af', fontSize: '13px' }}>Всего баллов</div>
                                <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--primary, #a855f7)', marginTop: '4px' }}>
                                    {stats.totalScore}
                                </div>
                            </Card>
                        </Col>
                        <Col xs={24} sm={12} md={6}>
                            <Card style={{ background: 'var(--card, #131935)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '14px' }}>
                                <div style={{ color: '#9ca3af', fontSize: '13px' }}>Принятых заданий</div>
                                <div style={{ fontSize: '28px', fontWeight: 700, color: '#10b981', marginTop: '4px' }}>
                                    {stats.tasksAcceptedCount}
                                </div>
                            </Card>
                        </Col>
                        <Col xs={24} sm={12} md={6}>
                            <Card style={{ background: 'var(--card, #131935)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '14px' }}>
                                <div style={{ color: '#9ca3af', fontSize: '13px' }}>Получено ачивок</div>
                                <div style={{ fontSize: '28px', fontWeight: 700, color: '#f59e0b', marginTop: '4px' }}>
                                    {achievements.length}
                                </div>
                            </Card>
                        </Col>
                        <Col xs={24} sm={12} md={6}>
                            <Card style={{ background: 'var(--card, #131935)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '14px' }}>
                                <div style={{ color: '#9ca3af', fontSize: '13px' }}>Текущий месяц</div>
                                <div style={{ fontSize: '28px', fontWeight: 700, color: '#3b82f6', marginTop: '4px' }}>
                                    {userInfo?.currentMonth || 1}
                                </div>
                            </Card>
                        </Col>
                    </Row>
                </div>

                {/* Блок достижений студента */}
                <div style={{ maxWidth: '1420px', margin: '20px auto 60px auto', padding: '0 20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
                        <h2 style={{ fontSize: '22px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <FaTrophy style={{ color: '#f59e0b' }} /> Мои достижения ({achievements.length})
                        </h2>
                        <Button
                            type="link"
                            onClick={() => navigate('/achievements')}
                            style={{ color: 'var(--primary, #a855f7)' }}
                        >
                            Все достижения каталога →
                        </Button>
                    </div>

                    {loading ? (
                        <div style={{ textAlign: 'center', padding: '40px 0' }}><Spin /></div>
                    ) : achievements.length === 0 ? (
                        <div style={{ background: 'var(--card, #131935)', padding: '40px 20px', borderRadius: '14px', textAlign: 'center', border: '1px solid rgba(255,255,255,0.08)' }}>
                            <p style={{ color: '#9ca3af', fontSize: '16px', margin: 0 }}>
                                Вы пока не получили достижений. Сдавайте домашние задания вовремя, чтобы открыть первые награды!
                            </p>
                        </div>
                    ) : (
                        <Row gutter={[16, 16]}>
                            {achievements.map((ach) => (
                                <Col xs={24} sm={12} md={8} lg={6} key={ach.id}>
                                    <Card
                                        hoverable
                                        onClick={() => openAchievementDetail(ach)}
                                        style={{
                                            background: 'var(--card, #131935)',
                                            border: '1px solid rgba(168, 85, 247, 0.4)',
                                            borderRadius: '14px',
                                        }}
                                    >
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                            <div style={{ fontSize: '32px' }}>{ach.iconUrl || '🏆'}</div>
                                            <div>
                                                <div style={{ fontWeight: 600, fontSize: '15px' }}>{ach.title}</div>
                                                <div style={{ fontSize: '12px', color: '#9ca3af' }}>{ach.description}</div>
                                                <div style={{ fontSize: '11px', color: '#10b981', marginTop: '4px' }}>
                                                    ✓ {new Date(ach.awardedAt).toLocaleDateString('ru-RU')}
                                                </div>
                                            </div>
                                        </div>
                                    </Card>
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
                        <div style={{ fontSize: '50px', marginBottom: '10px' }}>{selectedAch.iconUrl || '🏆'}</div>
                        <h2 style={{ fontSize: '20px', fontWeight: 700 }}>{selectedAch.title}</h2>
                        <p style={{ color: '#9ca3af', marginTop: '6px' }}>{selectedAch.description}</p>
                        <div style={{ background: 'rgba(255,255,255,0.04)', padding: '12px', borderRadius: '10px', textAlign: 'left', marginTop: '14px' }}>
                            <div style={{ fontSize: '12px', color: '#9ca3af' }}>Критерий:</div>
                            <div style={{ fontSize: '13px', color: '#fff', marginTop: '2px' }}>
                                {selectedAch.criteria || selectedAch.description}
                            </div>
                        </div>
                    </div>
                )}
            </Modal>
        </>
    );
};
