import { useState, useEffect } from 'react';
import {
  Table,
  Button,
  Tag,
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Popconfirm,
  message,
  Typography,
  Avatar,
  Checkbox,
  Card,
} from 'antd';
import {
  TrophyOutlined,
  PlusCircleOutlined,
  HistoryOutlined,
  InboxOutlined,
  ReloadOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { api } from '../../../api/client.js';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

export const StudentsTab = () => {
  const [students, setStudents] = useState([]);
  const [achievements, setAchievements] = useState([]);
  const [loading, setLoading] = useState(false);
  const [monthFilter, setMonthFilter] = useState(1);
  const [groupFilter, setGroupFilter] = useState('');

  // Модалка начисления баллов
  const [scoreModalUser, setScoreModalUser] = useState(null);
  const [scoreForm] = Form.useForm();
  const [submittingScore, setSubmittingScore] = useState(false);

  // Модалка выдачи ачивки
  const [achModalUser, setAchModalUser] = useState(null);
  const [achForm] = Form.useForm();
  const [submittingAch, setSubmittingAch] = useState(false);

  // Модалка истории баллов
  const [historyUser, setHistoryUser] = useState(null);
  const [historyList, setHistoryList] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Модалка архивации месяца
  const [isArchiveModalOpen, setIsArchiveModalOpen] = useState(false);
  const [archiveForm] = Form.useForm();
  const [archiving, setArchiving] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const params = {};
      if (monthFilter) params.month = monthFilter;
      if (groupFilter.trim()) params.groupNumber = groupFilter.trim();

      const [leadRes, achRes] = await Promise.all([
        api.get('/leaderboard', { params }),
        api.get('/achievements'),
      ]);

      setStudents(leadRes.data || []);
      setAchievements(achRes.data?.achievements || []);
    } catch (err) {
      console.error(err);
      message.error('Не удалось загрузить данные');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [monthFilter, groupFilter]);

  // Начисление баллов
  const openScoreModal = (user) => {
    setScoreModalUser(user);
    scoreForm.resetFields();
    scoreForm.setFieldsValue({
      amount: 10,
      month: user.currentMonth || monthFilter || 1,
    });
  };

  const handleScoreSubmit = async () => {
    try {
      const values = await scoreForm.validateFields();
      setSubmittingScore(true);

      await api.post(`/admin/users/${scoreModalUser.id}/score-adjust`, {
        amount: Number(values.amount),
        reason: values.reason.trim(),
        month: Number(values.month),
      });

      message.success('Баллы успешно скорректированы');
      setScoreModalUser(null);
      fetchData();
    } catch (err) {
      console.error(err);
      message.error(err.response?.data?.message || 'Ошибка при начислении баллов');
    } finally {
      setSubmittingScore(false);
    }
  };

  // Выдача ачивки
  const openAchModal = (user) => {
    setAchModalUser(user);
    achForm.resetFields();
  };

  const handleAchSubmit = async () => {
    try {
      const values = await achForm.validateFields();
      setSubmittingAch(true);

      await api.post(`/admin/users/${achModalUser.id}/achievements`, {
        achievementCode: values.achievementCode,
      });

      message.success('Достижение успешно присвоено студенту');
      setAchModalUser(null);
      fetchData();
    } catch (err) {
      console.error(err);
      message.error(err.response?.data?.message || 'Ошибка при выдаче ачивки');
    } finally {
      setSubmittingAch(false);
    }
  };

  // Просмотр истории
  const openHistoryModal = async (user) => {
    setHistoryUser(user);
    setLoadingHistory(true);
    try {
      const res = await api.get(`/admin/users/${user.id}/score-history`);
      setHistoryList(res.data?.adjustments || []);
    } catch (err) {
      console.error(err);
      message.error('Не удалось загрузить историю');
    } finally {
      setLoadingHistory(false);
    }
  };

  // Архивация месяца
  const handleArchiveMonth = async () => {
    try {
      const values = await archiveForm.validateFields();
      setArchiving(true);

      const res = await api.post('/admin/leaderboard/archive-and-reset', {
        month: Number(values.month),
        incrementMonth: Boolean(values.incrementMonth),
      });

      message.success(res.data?.message || 'Месяц успешно заархивирован');
      setIsArchiveModalOpen(false);
      fetchData();
    } catch (err) {
      console.error(err);
      message.error(err.response?.data?.message || 'Ошибка архивации месяца');
    } finally {
      setArchiving(false);
    }
  };

  const columns = [
    {
      title: 'Ранг',
      dataIndex: 'rank',
      key: 'rank',
      width: 70,
      render: (r) => {
        if (r === 1) return <Tag color="gold">🥇 1</Tag>;
        if (r === 2) return <Tag color="silver">🥈 2</Tag>;
        if (r === 3) return <Tag color="bronze">🥉 3</Tag>;
        return <Text strong>{r}</Text>;
      },
    },
    {
      title: 'Студент',
      key: 'student',
      render: (_, r) => (
        <Space>
          <Avatar src={r.avatarUrl} icon={!r.avatarUrl && <UserOutlined />} />
          <div>
            <Text strong>{r.name || r.login}</Text>
            <br />
            <Text type="secondary" style={{ fontSize: 12 }}>
              @{r.login}
            </Text>
          </div>
        </Space>
      ),
    },
    {
      title: 'Группа',
      dataIndex: 'groupNumber',
      key: 'groupNumber',
      render: (g) => <Tag color="blue">{g || '—'}</Tag>,
    },
    {
      title: 'Месяц',
      dataIndex: 'currentMonth',
      key: 'currentMonth',
      render: (m) => `Месяц ${m}`,
    },
    {
      title: 'Баллы',
      dataIndex: 'totalScore',
      key: 'totalScore',
      render: (score) => (
        <Text strong style={{ color: '#16a34a', fontSize: 15 }}>
          {score} б.
        </Text>
      ),
    },
    {
      title: 'Отправлено / Принято',
      key: 'tasksStats',
      render: (_, r) => (
        <span>
          <Tag color="cyan">{r.tasksSentCount} отпр.</Tag> /{' '}
          <Tag color="green">{r.tasksAcceptedCount} прин.</Tag>
        </span>
      ),
    },
    {
      title: 'Действия',
      key: 'actions',
      width: 280,
      render: (_, r) => (
        <Space size="small">
          <Button
            icon={<PlusCircleOutlined />}
            onClick={() => openScoreModal(r)}
          >
            Баллы
          </Button>
          <Button
            icon={<TrophyOutlined />}
            onClick={() => openAchModal(r)}
          >
            Ачивка
          </Button>
          <Button
            icon={<HistoryOutlined />}
            onClick={() => openHistoryModal(r)}
          />
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
        <Space>
          <Select
            style={{ width: 140 }}
            value={monthFilter}
            onChange={setMonthFilter}
            options={[
              { label: 'Все месяцы', value: undefined },
              { label: '1 месяц', value: 1 },
              { label: '2 месяц', value: 2 },
              { label: '3 месяц', value: 3 },
              { label: '4 месяц', value: 4 },
              { label: '5 месяц', value: 5 },
            ]}
          />
          <Input
            style={{ width: 160 }}
            placeholder="Фильтр по группе"
            value={groupFilter}
            onChange={(e) => setGroupFilter(e.target.value)}
            allowClear
          />
          <Button icon={<ReloadOutlined />} onClick={fetchData}>
            Обновить
          </Button>
        </Space>

        <Button
          danger
          type="primary"
          icon={<InboxOutlined />}
          onClick={() => {
            archiveForm.resetFields();
            archiveForm.setFieldsValue({
              month: monthFilter || 1,
              incrementMonth: false,
            });
            setIsArchiveModalOpen(true);
          }}
        >
          Зафиксировать и сбросить месяц
        </Button>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={students}
        loading={loading}
        pagination={{ pageSize: 15 }}
      />

      {/* Модалка начисления баллов */}
      <Modal
        title={`Корректировка баллов: ${scoreModalUser?.name || scoreModalUser?.login || ''}`}
        open={Boolean(scoreModalUser)}
        onOk={handleScoreSubmit}
        onCancel={() => setScoreModalUser(null)}
        confirmLoading={submittingScore}
        okText="Применить"
        cancelText="Отмена"
      >
        <Form form={scoreForm} layout="vertical">
          <Form.Item
            label="Количество баллов (положительное — бонус, отрицательное — штраф)"
            name="amount"
            rules={[{ required: true, message: 'Укажите количество баллов' }]}
          >
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            label="Причина начисления / списания"
            name="reason"
            rules={[{ required: true, message: 'Укажите причину' }]}
          >
            <Input placeholder="Например: Бонус за активность на вебинаре" />
          </Form.Item>

          <Form.Item
            label="Месяц"
            name="month"
            rules={[{ required: true, message: 'Укажите месяц' }]}
          >
            <InputNumber min={1} style={{ width: 140 }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Модалка ручной выдачи ачивки */}
      <Modal
        title={`Присвоение достижения: ${achModalUser?.name || achModalUser?.login || ''}`}
        open={Boolean(achModalUser)}
        onOk={handleAchSubmit}
        onCancel={() => setAchModalUser(null)}
        confirmLoading={submittingAch}
        okText="Выдать ачивку"
        cancelText="Отмена"
      >
        <Form form={achForm} layout="vertical">
          <Form.Item
            label="Выберите ачивку из каталога"
            name="achievementCode"
            rules={[{ required: true, message: 'Выберите ачивку' }]}
          >
            <Select
              placeholder="Каталог достижений"
              options={achievements.map((a) => ({
                label: `${a.title} (+${a.points || 10} б.) — ${a.description}`,
                value: a.code,
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Модалка истории баллов студента */}
      <Modal
        title={`История баллов: ${historyUser?.name || historyUser?.login || ''}`}
        open={Boolean(historyUser)}
        onCancel={() => setHistoryUser(null)}
        footer={null}
        width={600}
      >
        {loadingHistory ? (
          <p>Загрузка...</p>
        ) : historyList.length === 0 ? (
          <p>У студента пока нет ручных корректировок баллов.</p>
        ) : (
          <div>
            {historyList.map((h) => (
              <Card size="small" key={h.id} style={{ marginBottom: 8, background: 'rgba(255,255,255,0.04)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <Text strong style={{ color: h.amount >= 0 ? '#16a34a' : '#dc2626', fontSize: 16 }}>
                      {h.amount >= 0 ? `+${h.amount}` : h.amount} баллов
                    </Text>
                    <Paragraph style={{ margin: '4px 0 0 0', color: '#475569' }}>
                      {h.reason}
                    </Paragraph>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <Tag>Месяц {h.month}</Tag>
                    <br />
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {new Date(h.createdAt).toLocaleDateString()}
                    </Text>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </Modal>

      {/* Модалка фиксации и архивации месяца */}
      <Modal
        title="Архивация месяца и фиксация рейтинга"
        open={isArchiveModalOpen}
        onOk={handleArchiveMonth}
        onCancel={() => setIsArchiveModalOpen(false)}
        confirmLoading={archiving}
        okText="Зафиксировать и сохранить в архив"
        okButtonProps={{ danger: true }}
        cancelText="Отмена"
      >
        <Paragraph>
          При архивации итоговые баллы всех студентов за выбранный месяц фиксируются в таблице{' '}
          <Text code>MonthlyScoreArchive</Text> с присвоением финального ранга.
        </Paragraph>
        <Form form={archiveForm} layout="vertical">
          <Form.Item
            label="Какой месяц архивировать?"
            name="month"
            rules={[{ required: true, message: 'Укажите месяц' }]}
          >
            <InputNumber min={1} style={{ width: 140 }} />
          </Form.Item>

          <Form.Item
            name="incrementMonth"
            valuePropName="checked"
          >
            <Checkbox>
              Автоматически перевести студентов этого месяца на следующий (currentMonth + 1)
            </Checkbox>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};
