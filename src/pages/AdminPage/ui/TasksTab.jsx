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
  Switch,
  Space,
  Popconfirm,
  message,
  Typography,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  StarOutlined,
} from '@ant-design/icons';
import { api } from '../../../api/client.js';

const { Text, Link } = Typography;
const { TextArea } = Input;

export const TasksTab = () => {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [monthFilter, setMonthFilter] = useState(1);

  // Модалка
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState(null);
  const [saving, setSaving] = useState(false);
  const [hasScoreValue, setHasScoreValue] = useState(true);
  const [form] = Form.useForm();

  const fetchTasks = async () => {
    setLoading(true);
    try {
      const params = {};
      if (monthFilter) params.month = monthFilter;
      const res = await api.get('/admin/tasks', { params });
      setTasks(res.data?.tasks || []);
    } catch (err) {
      console.error(err);
      message.error('Не удалось загрузить список заданий');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
  }, [monthFilter]);

  const openCreateModal = () => {
    setEditingTask(null);
    form.resetFields();
    setHasScoreValue(true);
    form.setFieldsValue({
      month: monthFilter || 1,
      order: tasks.length,
      hasScore: true,
      maxScore: 100,
      isBonus: false,
    });
    setIsModalOpen(true);
  };

  const openEditModal = (task) => {
    setEditingTask(task);
    form.resetFields();
    setHasScoreValue(task.hasScore);
    form.setFieldsValue({
      title: task.title,
      description: task.description,
      topic: task.topic,
      month: task.month,
      order: task.order,
      exampleLink: task.exampleLink,
      attachmentLink: task.attachmentLink,
      hasScore: task.hasScore,
      maxScore: task.maxScore || 100,
      isBonus: task.isBonus,
    });
    setIsModalOpen(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);

      if (editingTask) {
        await api.patch(`/admin/tasks/${editingTask.id}`, values);
        message.success('Задание успешно обновлено');
      } else {
        await api.post('/admin/tasks', values);
        message.success('Задание успешно создано');
      }

      setIsModalOpen(false);
      fetchTasks();
    } catch (err) {
      console.error(err);
      message.error(err.response?.data?.message || 'Ошибка при сохранении задания');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await api.delete(`/admin/tasks/${id}`);
      message.success('Задание успешно удалено');
      fetchTasks();
    } catch (err) {
      console.error(err);
      message.error('Не удалось удалить задание');
    }
  };

  const columns = [
    {
      title: '№',
      dataIndex: 'order',
      key: 'order',
      width: 50,
    },
    {
      title: 'Месяц',
      dataIndex: 'month',
      key: 'month',
      width: 90,
      render: (m) => `Месяц ${m}`,
    },
    {
      title: 'Тема',
      dataIndex: 'topic',
      key: 'topic',
      render: (topic) => <Tag color="cyan">{topic}</Tag>,
    },
    {
      title: 'Название задания',
      key: 'title',
      render: (_, r) => (
        <div>
          <Text strong>{r.title}</Text>
          {r.isBonus && (
            <Tag color="gold" style={{ marginLeft: 8 }}>
              <StarOutlined /> Бонусное ДЗ
            </Tag>
          )}
        </div>
      ),
    },
    {
      title: 'Баллы',
      key: 'score',
      width: 110,
      render: (_, r) => (r.hasScore ? <Text type="success">{r.maxScore} б.</Text> : <Text type="secondary">Без баллов</Text>),
    },
    {
      title: 'Сдачи',
      key: 'submissionsCount',
      width: 90,
      render: (_, r) => <Tag color="blue">{r._count?.submissions || 0} шт.</Tag>,
    },
    {
      title: 'Действия',
      key: 'actions',
      width: 140,
      render: (_, r) => (
        <Space>
          <Button
            type="text"
            icon={<EditOutlined />}
            size="small"
            onClick={() => openEditModal(r)}
          />
          <Popconfirm
            title="Удалить задание?"
            description="Все сдачи студентов по этому заданию также будут удалены!"
            onConfirm={() => handleDelete(r.id)}
            okText="Да, удалить"
            cancelText="Отмена"
            okButtonProps={{ danger: true }}
          >
            <Button type="text" danger icon={<DeleteOutlined />} size="small" />
          </Popconfirm>
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
          <Button icon={<ReloadOutlined />} onClick={fetchTasks}>
            Обновить
          </Button>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
          Создать задание
        </Button>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={tasks}
        loading={loading}
        pagination={{ pageSize: 10 }}
      />

      {/* Модалка создания/редактирования */}
      <Modal
        title={editingTask ? 'Редактирование задания' : 'Новое задание'}
        open={isModalOpen}
        onOk={handleSave}
        onCancel={() => setIsModalOpen(false)}
        confirmLoading={saving}
        okText="Сохранить"
        cancelText="Отмена"
        width={680}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="Тема занятия / блока"
            name="topic"
            rules={[{ required: true, message: 'Укажите тему' }]}
          >
            <Input placeholder="Например: Архитектура Express & REST API" />
          </Form.Item>

          <Form.Item
            label="Название задания"
            name="title"
            rules={[{ required: true, message: 'Введите название задания' }]}
          >
            <Input placeholder="Например: Разработка сервиса авторизации JWT" />
          </Form.Item>

          <Form.Item
            label="Описание и критерии приемки"
            name="description"
            rules={[{ required: true, message: 'Введите описание задания' }]}
          >
            <TextArea rows={4} placeholder="Подробно опишите требования к решению задания..." />
          </Form.Item>

          <Space style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <Form.Item
              label="Месяц"
              name="month"
              rules={[{ required: true, message: 'Укажите месяц' }]}
            >
              <InputNumber min={1} style={{ width: 120 }} />
            </Form.Item>

            <Form.Item
              label="Порядковый номер"
              name="order"
            >
              <InputNumber min={0} style={{ width: 120 }} />
            </Form.Item>

            <Form.Item
              label="Оцениваемое задание?"
              name="hasScore"
              valuePropName="checked"
            >
              <Switch onChange={setHasScoreValue} />
            </Form.Item>

            {hasScoreValue && (
              <Form.Item
                label="Макс. балл"
                name="maxScore"
                rules={[{ required: true, message: 'Укажите макс. балл' }]}
              >
                <InputNumber min={1} style={{ width: 120 }} />
              </Form.Item>
            )}

            <Form.Item
              label="Бонусное задание?"
              name="isBonus"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>
          </Space>

          <Form.Item
            label="Ссылка на пример / дизайн (опционально)"
            name="exampleLink"
          >
            <Input placeholder="https://www.figma.com/..." />
          </Form.Item>

          <Form.Item
            label="Ссылка на материалы / репозиторий шаблона (опционально)"
            name="attachmentLink"
          >
            <Input placeholder="https://github.com/..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};
