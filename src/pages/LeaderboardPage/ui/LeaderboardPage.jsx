import { useState, useEffect } from "react";
import { Table, Tag, Avatar, Card, Row, Col, Select, Input, Spin, Badge } from "antd";
import { TrophyOutlined, UserOutlined, CrownOutlined, CheckCircleOutlined, FireOutlined } from "@ant-design/icons";
import { api } from "../../../api/client.js";
import { useFindUser } from "../../../store/userStore.js";

export const LeaderboardPage = () => {
    const { userInfo } = useFindUser();
    const [leaderboard, setLeaderboard] = useState([]);
    const [loading, setLoading] = useState(true);
    const [month, setMonth] = useState(userInfo?.currentMonth || 1);
    const [groupFilter, setGroupFilter] = useState('');

    const fetchLeaderboard = async () => {
        try {
            setLoading(true);
            const params = {};
            if (month) params.month = month;
            if (groupFilter.trim()) params.groupNumber = groupFilter.trim();

            const res = await api.get('/leaderboard', { params });
            // res.data — плоский массив студентов
            setLeaderboard(Array.isArray(res.data) ? res.data : []);
        } catch (err) {
            console.error('Failed to load leaderboard', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchLeaderboard();
    }, [month, groupFilter]);

    const top5 = leaderboard.slice(0, 5);

    const getRankColor = (rank) => {
        if (rank === 1) return '#f59e0b'; // Gold
        if (rank === 2) return '#94a3b8'; // Silver
        if (rank === 3) return '#b45309'; // Bronze
        return '#6b7280';
    };

    const columns = [
        {
            title: 'Место',
            dataIndex: 'rank',
            key: 'rank',
            width: 90,
            align: 'center',
            render: (rank) => {
                if (rank === 1) {
                    return <Tag color="gold" style={{ fontSize: '14px', fontWeight: 'bold' }}>🥇 1</Tag>;
                }
                if (rank === 2) {
                    return <Tag color="default" style={{ fontSize: '14px', fontWeight: 'bold' }}>🥈 2</Tag>;
                }
                if (rank === 3) {
                    return <Tag color="warning" style={{ fontSize: '14px', fontWeight: 'bold' }}>🥉 3</Tag>;
                }
                return <span style={{ fontWeight: 600, color: '#9ca3af' }}>#{rank}</span>;
            },
        },
        {
            title: 'Студент',
            key: 'student',
            render: (_, record) => {
                const isMe = record.id === userInfo?.id;
                return (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <Avatar
                            size={40}
                            src={record.avatarUrl}
                            icon={<UserOutlined />}
                            style={{
                                border: record.rank <= 3 ? `2px solid ${getRankColor(record.rank)}` : '1px solid rgba(255,255,255,0.1)'
                            }}
                        />
                        <div>
                            <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <span>{record.name || record.login}</span>
                                {isMe && <Tag color="purple">Вы</Tag>}
                            </div>
                            <div style={{ fontSize: '12px', color: '#9ca3af' }}>@{record.login}</div>
                        </div>
                    </div>
                );
            },
        },
        {
            title: 'Группа',
            dataIndex: 'groupNumber',
            key: 'groupNumber',
            align: 'center',
            render: (grp) => <Tag color="blue">{grp || '—'}</Tag>,
        },
        {
            title: 'Месяц',
            dataIndex: 'currentMonth',
            key: 'currentMonth',
            align: 'center',
            render: (m) => `М${m}`,
        },
        {
            title: 'Принято ДЗ',
            dataIndex: 'tasksAcceptedCount',
            key: 'tasksAcceptedCount',
            align: 'center',
            render: (val, record) => (
                <span style={{ color: '#10b981', fontWeight: 600 }}>
                    <CheckCircleOutlined style={{ marginRight: '4px' }} />
                    {val} <span style={{ fontSize: '11px', color: '#6b7280' }}>/ {record.tasksSentCount} сдано</span>
                </span>
            ),
        },
        {
            title: 'Всего баллов',
            dataIndex: 'totalScore',
            key: 'totalScore',
            align: 'right',
            sorter: (a, b) => b.totalScore - a.totalScore,
            defaultSortOrder: 'ascend',
            render: (score) => (
                <span style={{ fontSize: '16px', fontWeight: 700, color: 'var(--primary, #a855f7)' }}>
                    {score} <span style={{ fontSize: '12px' }}>pts</span>
                </span>
            ),
        },
    ];

    return (
        <div style={{ maxWidth: '1420px', margin: '20px auto', padding: '0 20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px', marginBottom: '24px' }}>
                <div>
                    <h1 style={{ fontSize: '30px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '12px', margin: 0 }}>
                        <TrophyOutlined style={{ color: '#f59e0b' }} /> Рейтинг студентов
                    </h1>
                    <p style={{ color: '#9ca3af', margin: '6px 0 0 0' }}>
                        Лидерборд участников по набранным баллам и принятым заданиям
                    </p>
                </div>

                <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <Select
                        value={month}
                        onChange={setMonth}
                        style={{ width: 140 }}
                        options={[
                            { value: 1, label: 'Месяц 1' },
                            { value: 2, label: 'Месяц 2' },
                            { value: 3, label: 'Месяц 3' },
                            { value: 4, label: 'Месяц 4' },
                            { value: 5, label: 'Месяц 5' },
                            { value: 6, label: 'Месяц 6' },
                        ]}
                    />

                    <Input
                        placeholder="Фильтр по группе"
                        value={groupFilter}
                        onChange={(e) => setGroupFilter(e.target.value)}
                        allowClear
                        style={{ width: 180 }}
                    />
                </div>
            </div>

            {/* Виджет Топ-5 лидеров */}
            {top5.length > 0 && (
                <div style={{ marginBottom: '32px' }}>
                    <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <CrownOutlined style={{ color: '#f59e0b' }} /> Топ-5 лидеров месяца
                    </h3>
                    <Row gutter={[16, 16]}>
                        {top5.map((student, idx) => (
                            <Col xs={24} sm={12} md={8} lg={4} key={student.id} style={{ flex: '1 0 180px' }}>
                                <Card
                                    style={{
                                        background: idx === 0 ? 'linear-gradient(135deg, rgba(245, 158, 11, 0.15), rgba(168, 85, 247, 0.1))' : 'var(--card, #131935)',
                                        border: idx === 0 ? '1px solid #f59e0b' : '1px solid rgba(255,255,255,0.08)',
                                        borderRadius: '14px',
                                        textAlign: 'center',
                                        padding: '12px 6px',
                                    }}
                                    bodyStyle={{ padding: '8px' }}
                                >
                                    <Badge
                                        count={idx === 0 ? '👑 1' : `#${idx + 1}`}
                                        style={{ backgroundColor: getRankColor(idx + 1), fontWeight: 'bold' }}
                                    >
                                        <Avatar
                                            size={64}
                                            src={student.avatarUrl}
                                            icon={<UserOutlined />}
                                            style={{
                                                border: `3px solid ${getRankColor(idx + 1)}`,
                                                boxShadow: idx === 0 ? '0 0 15px rgba(245, 158, 11, 0.4)' : 'none',
                                            }}
                                        />
                                    </Badge>
                                    <div style={{ fontWeight: 600, fontSize: '15px', marginTop: '10px' }}>
                                        {student.name || student.login}
                                    </div>
                                    <div style={{ fontSize: '12px', color: '#9ca3af' }}>Группа: {student.groupNumber || '—'}</div>
                                    <div style={{ marginTop: '8px', fontSize: '18px', fontWeight: 700, color: 'var(--primary, #a855f7)' }}>
                                        {student.totalScore} <span style={{ fontSize: '11px', color: '#9ca3af' }}>баллов</span>
                                    </div>
                                    <div style={{ fontSize: '12px', color: '#10b981', marginTop: '4px' }}>
                                        ✓ {student.tasksAcceptedCount} задач
                                    </div>
                                </Card>
                            </Col>
                        ))}
                    </Row>
                </div>
            )}

            {/* Таблица лидерборда */}
            <Card
                style={{ background: 'var(--card, #131935)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '16px' }}
                bodyStyle={{ padding: 0 }}
            >
                <Table
                    columns={columns}
                    dataSource={leaderboard}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 20, showTotal: (total) => `Всего студентов: ${total}` }}
                />
            </Card>
        </div>
    );
};
