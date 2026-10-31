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
  message,
  Typography,
  Card,
  Divider,
} from 'antd';
import {
  CheckOutlined,
  CloseOutlined,
  ClockCircleOutlined,
  GithubOutlined,
  EyeOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { api } from '../../../api/client.js';

const { Text, Paragraph, Link } = Typography;
const { TextArea } = Input;

export const SubmissionsTab = () => {
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('SENT');
  const [monthFilter, setMonthFilter] = useState(undefined);
  const [groupFilter, setGroupFilter] = useState('');

  // Модалка проверки
  const [selectedSub, setSelectedSub] = useState(null);
  const [fullHistory, setFullHistory] = useState([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [submittingReview, setSubmittingReview] = useState(false);
  const [form] = Form.useForm();

  const fetchSubmissions = async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter && statusFilter !== 'ALL') params.status = statusFilter;
      if (monthFilter) params.month = monthFilter;
      if (groupFilter.trim()) params.groupNumber = groupFilter.trim();

      const res = await api.get('/admin/submissions', { params });
      setSubmissions(res.data?.submissions || []);
    } catch (err) {
      console.error(err);
      message.error('Не удалось загрузить список сдач');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSubmissions();
  }, [statusFilter, monthFilter, groupFilter]);

  const openReviewModal = async (record) => {
    setSelectedSub(record);
    setIsModalOpen(true);
    form.resetFields();
    form.setFieldsValue({
      score: record.task?.hasScore ? record.task?.maxScore || 100 : undefined,
    });

    try {
      const res = await api.get(`/admin/submissions/${record.id}`);
      setFullHistory(res.data?.history || []);
    } catch (err) {
      console.error(err);
    }
  };

  const handleReview = async (status) => {
    try {
      const values = await form.validateFields();
      if (status === 'REVISION' && (!values.reviewerComment || !values.reviewerComment.trim())) {
        message.warning('Для отправки на доработку обязательно укажите замечания');
        return;
      }

      setSubmittingReview(true);
      const payload = {
        status,
        score: selectedSub.task?.hasScore ? Number(values.score) : null,
        reviewerComment: values.reviewerComment ? values.reviewerComment.trim() : null,
      };

      const res = await api.patch(`/admin/submissions/${selectedSub.id}/review`, payload);

      if (res.data?.awardedAchievements?.length > 0) {
        message.success(
          `Решение проверено! Студенту начислены ачивки: ${res.data.awardedAchievements.join(', ')}`
        );
      } else {
        message.success('Вердикт успешно сохранен');
      }

      setIsModalOpen(false);
      fetchSubmissions();
    } catch (err) {
      console.error(err);
      message.error(err.response?.data?.message || 'Ошибка при сохранении вердикта');
    } finally {
      setSubmittingReview(false);
    }
  };

  const statusTags = {
    SENT: <Tag color="blue">Ожидает проверки</Tag>,
    IN_REVIEW: <Tag color="orange">На проверке</Tag>,
    REVISION: <Tag color="volcano">На доработке</Tag>,
    ACCEPTED: <Tag color="green">Принято</Tag>,
  };

  const columns = [
    {
      title: 'Студент',
      key: 'student',
      render: (_, r) => (
        <div>
          <Text strong>{r.user?.name || r.user?.login}</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 12 }}>
            @{r.user?.login} | Группа: {r.user?.groupNumber || '—'}
          </Text>
        </div>
      ),
    },
    {
      title: 'Задание',
      key: 'task',
      render: (_, r) => (
        <div>
          <Text>{r.task?.title}</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 12 }}>
            Месяц {r.task?.month} • {r.task?.topic}
            {r.task?.isBonus && <Tag color="gold" style={{ marginLeft: 6 }}>Бонус</Tag>}
          </Text>
        </div>
      ),
    },
    {
      title: 'Попытка',
      dataIndex: 'version',
      key: 'version',
      render: (v) => <Tag color="purple">v{v}</Tag>,
    },
    {
      title: 'Решение (GitHub)',
      dataIndex: 'solutionLink',
      key: 'solutionLink',
      render: (link) => (
        <Link href={link} target="_blank" rel="noopener noreferrer">
          <GithubOutlined style={{ marginRight: 6 }} />
          Открыть репозиторий
        </Link>
      ),
    },
    {
      title: 'Статус',
      dataIndex: 'status',
      key: 'status',
      render: (status) => statusTags[status] || status,
    },
    {
      title: 'Балл',
      key: 'score',
      render: (_, r) => (r.score !== null ? `${r.score} б.` : '—'),
    },
    {
      title: 'Действие',
      key: 'action',
      render: (_, r) => (
        <Button
          type="primary"
          icon={<EyeOutlined />}
          onClick={() => openReviewModal(r)}
        >
          Проверить
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <Select
          style={{ width: 180 }}
          value={statusFilter}
          onChange={setStatusFilter}
          options={[
            { label: 'Ожидают (SENT)', value: 'SENT' },
            { label: 'На проверке (IN_REVIEW)', value: 'IN_REVIEW' },
            { label: 'На доработке (REVISION)', value: 'REVISION' },
            { label: 'Принятые (ACCEPTED)', value: 'ACCEPTED' },
            { label: 'Все статусы', value: 'ALL' },
          ]}
        />
        <Select
          style={{ width: 140 }}
          placeholder="Все месяцы"
          allowClear
          value={monthFilter}
          onChange={setMonthFilter}
          options={[
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
        <Button icon={<ReloadOutlined />} onClick={fetchSubmissions}>
          Обновить
        </Button>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={submissions}
        loading={loading}
        pagination={{ pageSize: 10 }}
      />

      {/* Модалка проверки решения */}
      <Modal
        title={`Проверка работы: ${selectedSub?.task?.title || ''}`}
        open={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        footer={null}
        width={720}
      >
        {selectedSub && (
          <div>
            <Card size="small" style={{ marginBottom: 16, background: 'rgba(255,255,255,0.04)' }}>
              <Paragraph>
                <Text strong>Студент: </Text>
                {selectedSub.user?.name || selectedSub.user?.login} (группа: {selectedSub.user?.groupNumber || '—'})
              </Paragraph>
              <Paragraph>
                <Text strong>Ссылка на решение: </Text>
                <Link href={selectedSub.solutionLink} target="_blank" rel="noopener noreferrer">
                  <GithubOutlined /> {selectedSub.solutionLink}
                </Link>
              </Paragraph>
              {selectedSub.comment && (
                <Paragraph>
                  <Text strong>Комментарий студента: </Text>
                  <span>{selectedSub.comment}</span>
                </Paragraph>
              )}
            </Card>

            {fullHistory.length > 1 && (
              <div style={{ marginBottom: 16 }}>
                <Text strong style={{ display: 'block', marginBottom: 8 }}>
                  Предыдущие попытки ({fullHistory.length}):
                </Text>
                <div style={{ maxHeight: 150, overflowY: 'auto', background: 'rgba(255,255,255,0.04)', padding: 12, borderRadius: 8 }}>
                  {fullHistory.map((h) => (
                    <div key={h.id} style={{ fontSize: 14, marginBottom: 8, borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: 6 }}>
                      <Text strong>v{h.version}</Text> — {statusTags[h.status]} {h.score !== null ? `(${h.score} б.)` : ''}
                      {h.reviewerComment && <div style={{ color: '#94a3b8' }}>Замечание: {h.reviewerComment}</div>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <Divider />

            <Form form={form} layout="vertical">
              {selectedSub.task?.hasScore && (
                <Form.Item
                  label={`Баллы (Максимум: ${selectedSub.task?.maxScore || 100})`}
                  name="score"
                  rules={[{ required: true, message: 'Укажите балл' }]}
                >
                  <InputNumber
                    min={0}
                    max={selectedSub.task?.maxScore || 100}
                    style={{ width: '100%' }}
                  />
                </Form.Item>
              )}

              <Form.Item
                label="Замечания / Комментарий ментора"
                name="reviewerComment"
                extra="Обязательно при отправке на доработку"
              >
                <TextArea rows={4} placeholder="Опишите, что сделано отлично или что требуется исправить..." />
              </Form.Item>

              <Space style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 20 }}>
                <Button
                  icon={<ClockCircleOutlined />}
                  onClick={() => handleReview('IN_REVIEW')}
                  loading={submittingReview}
                >
                  Взять на проверку
                </Button>
                <Button
                  danger
                  icon={<CloseOutlined />}
                  onClick={() => handleReview('REVISION')}
                  loading={submittingReview}
                >
                  На доработку
                </Button>
                <Button
                  type="primary"
                  style={{ background: '#16a34a' }}
                  icon={<CheckOutlined />}
                  onClick={() => handleReview('ACCEPTED')}
                  loading={submittingReview}
                >
                  Принять решение
                </Button>
              </Space>
            </Form>
          </div>
        )}
      </Modal>
    </div>
  );
};
