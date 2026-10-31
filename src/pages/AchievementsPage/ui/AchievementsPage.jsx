import { useState, useEffect } from "react";
import { Card, Row, Col, Tag, Modal, Avatar, Spin, Badge, message } from "antd";
import { TrophyOutlined, CheckCircleOutlined, LockOutlined, UserOutlined } from "@ant-design/icons";
import { api } from "../../../api/client.js";

export const AchievementsPage = () => {
    const [achievements, setAchievements] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedAchievement, setSelectedAchievement] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);

    const fetchAchievements = async () => {
        try {
            setLoading(true);
            const res = await api.get('/achievements');
            setAchievements(res.data?.achievements || []);
        } catch (err) {
            console.error('Failed to load achievements', err);
            message.error('Не удалось загрузить каталог достижений');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAchievements();
    }, []);

    const openDetail = async (ach) => {
        setModalOpen(true);
        setDetailLoading(true);
        try {
            const res = await api.get(`/achievements/${ach.id}`);
            setSelectedAchievement(res.data?.achievement || ach);
        } catch (err) {
            setSelectedAchievement(ach);
        } finally {
            setDetailLoading(false);
        }
    };

    if (loading) {
        return (
            <div style={{ textAlign: 'center', padding: '100px 0' }}>
                <Spin size="large" />
                <p style={{ marginTop: '16px', color: 'rgba(255,255,255,0.7)' }}>Загрузка достижений...</p>
            </div>
        );
    }

    const unlockedCount = achievements.filter((a) => a.isUnlockedByMe).length;

    return (
        <div style={{ maxWidth: '1420px', margin: '20px auto', padding: '0 20px' }}>
            <div style={{ marginBottom: '28px' }}>
                <h1 style={{ fontSize: '30px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <TrophyOutlined style={{ color: 'var(--primary, #a855f7)' }} /> Каталог достижений
                </h1>
                <p style={{ color: '#9ca3af' }}>
                    Получено вами: <strong style={{ color: '#10b981' }}>{unlockedCount}</strong> из {achievements.length}
                </p>
            </div>

            <Row gutter={[20, 20]}>
                {achievements.map((ach) => {
                    const isUnlocked = ach.isUnlockedByMe;

                    return (
                        <Col xs={24} sm={12} md={8} lg={6} key={ach.id}>
                            <Card
                                hoverable
                                onClick={() => openDetail(ach)}
                                style={{
                                    background: isUnlocked ? 'linear-gradient(145deg, rgba(168, 85, 247, 0.15), rgba(19, 25, 53, 0.9))' : 'var(--card, #131935)',
                                    border: isUnlocked ? '1px solid var(--primary, #a855f7)' : '1px solid rgba(255,255,255,0.06)',
                                    borderRadius: '16px',
                                    height: '100%',
                                    opacity: isUnlocked ? 1 : 0.75,
                                    transition: 'all 0.3s ease',
                                }}
                            >
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                                    <div style={{ fontSize: '36px' }}>
                                        {ach.iconUrl || '🏆'}
                                    </div>
                                    {isUnlocked ? (
                                        <Tag color="success" icon={<CheckCircleOutlined />}>
                                            Получено
                                        </Tag>
                                    ) : (
                                        <Tag icon={<LockOutlined />}>Заблокировано</Tag>
                                    )}
                                </div>

                                <h3 style={{ fontSize: '17px', fontWeight: 600, margin: '0 0 6px 0', color: '#fff' }}>
                                    {ach.title}
                                </h3>

                                <p style={{ fontSize: '13px', color: '#9ca3af', minHeight: '38px', margin: 0 }}>
                                    {ach.description}
                                </p>

                                <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', color: '#6b7280' }}>
                                    <Tag color="purple">+{ach.points || 10} pts</Tag>
                                    <span>Открыли: {ach.unlockedCount} чел.</span>
                                </div>
                            </Card>
                        </Col>
                    );
                })}
            </Row>

            {/* Модалка детальной информации об ачивке */}
            <Modal
                open={modalOpen}
                onCancel={() => setModalOpen(false)}
                footer={null}
                width={500}
                centered
            >
                {detailLoading || !selectedAchievement ? (
                    <div style={{ textAlign: 'center', padding: '40px 0' }}>
                        <Spin />
                    </div>
                ) : (
                    <div style={{ textAlign: 'center', padding: '10px 0' }}>
                        <div style={{ fontSize: '56px', marginBottom: '12px' }}>
                            {selectedAchievement.iconUrl || '🏆'}
                        </div>
                        <h2 style={{ fontSize: '22px', fontWeight: 700, margin: '0 0 8px 0' }}>
                            {selectedAchievement.title}
                        </h2>
                        <div style={{ marginBottom: '16px' }}>
                            {selectedAchievement.isUnlockedByMe ? (
                                <Tag color="success" style={{ fontSize: '13px', padding: '4px 10px' }}>
                                    ✓ Вы получили эту ачивку {selectedAchievement.unlockedAt ? new Date(selectedAchievement.unlockedAt).toLocaleDateString('ru-RU') : ''}
                                </Tag>
                            ) : (
                                <Tag color="default" style={{ fontSize: '13px', padding: '4px 10px' }}>
                                    🔒 Пока не получено
                                </Tag>
                            )}
                        </div>

                        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '14px', borderRadius: '12px', textAlign: 'left', marginBottom: '16px' }}>
                            <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '4px' }}>Критерий получения:</div>
                            <div style={{ fontSize: '14px', color: '#fff', fontWeight: 500 }}>
                                {selectedAchievement.criteria || selectedAchievement.description}
                            </div>
                            <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--primary)' }}>
                                Награда: +{selectedAchievement.points || 10} баллов к рейтингу
                            </div>
                        </div>

                        {selectedAchievement.recentAchievers && selectedAchievement.recentAchievers.length > 0 && (
                            <div style={{ textAlign: 'left' }}>
                                <div style={{ fontSize: '13px', color: '#9ca3af', marginBottom: '10px' }}>
                                    Недавно получили:
                                </div>
                                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                                    {selectedAchievement.recentAchievers.map((achiever) => (
                                        <div
                                            key={achiever.id}
                                            style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'rgba(255,255,255,0.05)', padding: '4px 8px', borderRadius: '20px' }}
                                        >
                                            <Avatar size={24} src={achiever.avatarUrl} icon={<UserOutlined />} />
                                            <span style={{ fontSize: '12px' }}>{achiever.name || achiever.login}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </Modal>
        </div>
    );
};
