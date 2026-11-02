import { useState, useEffect } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
  AutoComplete,
  Tag,
  Space,
  Popconfirm,
  message,
  Typography,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { api } from '../../../api/client.js';

const { Text, Link } = Typography;

export const LessonsTab = () => {
  const [lessons, setLessons] = useState([]);
  const [availableGroups, setAvailableGroups] = useState([]);
  const [loading, setLoading] = useState(false);
  const [monthFilter, setMonthFilter] = useState(undefined);
  const [groupFilter, setGroupFilter] = useState(undefined);

  // Модалка создания/редактирования
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingLesson, setEditingLesson] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  // Модалка предпросмотра YouTube видео
  const [previewYoutubeId, setPreviewYoutubeId] = useState(null);

  const fetchLessons = async () => {
    setLoading(true);
    try {
      const params = {};
      if (monthFilter) params.month = monthFilter;
      if (groupFilter) params.groupNumber = groupFilter;
      const res = await api.get('/admin/lessons', { params });
      setLessons(res.data?.lessons || []);
      if (Array.isArray(res.data?.availableGroups)) {
        setAvailableGroups(res.data.availableGroups);
      }
    } catch (err) {
      console.error(err);
      message.error('Не удалось загрузить уроки');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLessons();
  }, [monthFilter, groupFilter]);

  const openCreateModal = () => {
    setEditingLesson(null);
    form.resetFields();
    form.setFieldsValue({
      groupNumber: groupFilter || availableGroups[0] || '',
      month: monthFilter || 1,
      order: lessons.length + 1,
    });
    setIsModalOpen(true);
  };

  const openEditModal = (lesson) => {
    setEditingLesson(lesson);
    form.resetFields();
    form.setFieldsValue({
      title: lesson.title,
      videoLink: lesson.videoLink,
      groupNumber: lesson.groupNumber,
      month: lesson.month,
      order: lesson.order,
    });
    setIsModalOpen(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);

      if (editingLesson) {
        await api.patch(`/admin/lessons/${editingLesson.id}`, values);
        message.success('Урок успешно обновлен');
      } else {
        await api.post('/admin/lessons', values);
        message.success('Урок успешно добавлен');
      }

      setIsModalOpen(false);
      fetchLessons();
    } catch (err) {
      console.error(err);
      message.error(err.response?.data?.message || err.response?.data?.error || 'Ошибка при сохранении урока');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await api.delete(`/admin/lessons/${id}`);
      message.success('Урок успешно удален');
      fetchLessons();
    } catch (err) {
      console.error(err);
      message.error('Не удалось удалить урок');
    }
  };

  const columns = [
    {
      title: '№',
      dataIndex: 'order',
      key: 'order',
      width: 60,
    },
    {
      title: 'Группа',
      dataIndex: 'groupNumber',
      key: 'groupNumber',
      width: 110,
      render: (grp) => <Tag color="purple">Группа {grp || '—'}</Tag>,
    },
    {
      title: 'Месяц',
      dataIndex: 'month',
      key: 'month',
      width: 100,
      render: (m) => `Месяц ${m}`,
    },
    {
      title: 'Название урока',
      dataIndex: 'title',
      key: 'title',
      render: (text) => <Text strong>{text}</Text>,
    },
    {
      title: 'YouTube ID / Ссылка',
      key: 'videoLink',
      render: (_, r) => (
        <Space>
          <Text code>{r.youtubeId}</Text>
          <Button
            type="link"
            size="small"
            icon={<PlayCircleOutlined />}
            onClick={() => setPreviewYoutubeId(r.youtubeId)}
          >
            Смотреть
          </Button>
          <Link href={r.videoLink} target="_blank" rel="noopener noreferrer">
            Открыть ссылку
          </Link>
        </Space>
      ),
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
            title="Удалить урок?"
            description="Это действие нельзя отменить"
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

  const groupOptions = availableGroups.map((g) => ({
    label: `Группа ${g}`,
    value: g,
  }));

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
        <Space wrap>
          <Select
            style={{ width: 160 }}
            placeholder="Все группы"
            allowClear
            value={groupFilter}
            onChange={setGroupFilter}
            options={[
              { label: 'Все группы', value: undefined },
              ...groupOptions,
            ]}
          />
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
              { label: '6 месяц', value: 6 },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={fetchLessons}>
            Обновить
          </Button>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
          Добавить урок
        </Button>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={lessons}
        loading={loading}
        pagination={{ pageSize: 10 }}
      />

      {/* Модалка создания/редактирования */}
      <Modal
        title={editingLesson ? 'Редактирование урока' : 'Новый урок'}
        open={isModalOpen}
        onOk={handleSave}
        onCancel={() => setIsModalOpen(false)}
        confirmLoading={saving}
        okText="Сохранить"
        cancelText="Отмена"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="Название урока"
            name="title"
            rules={[{ required: true, message: 'Введите название урока' }]}
          >
            <Input placeholder="Например: Архитектура React и хуки состояния" />
          </Form.Item>

          <Form.Item
            label="Учебная группа (выберите из списка или введите новую)"
            name="groupNumber"
            rules={[{ required: true, message: 'Укажите номер группы (например: 15)' }]}
          >
            <AutoComplete
              options={availableGroups.map((g) => ({ value: g, label: `Группа ${g}` }))}
              placeholder="Выберите существующую группу или введите номер (напр. 15)"
              filterOption={(inputValue, option) =>
                String(option?.value ?? '')
                  .toLowerCase()
                  .includes(inputValue.toLowerCase())
              }
            />
          </Form.Item>

          <Form.Item
            label="Ссылка на YouTube"
            name="videoLink"
            rules={[{ required: true, message: 'Введите ссылку на YouTube' }]}
            extra="Поддерживаются любые форматы: youtube.com/watch?v=..., youtu.be/..., shorts/..."
          >
            <Input placeholder="https://www.youtube.com/watch?v=dQw4w9WgXcQ" />
          </Form.Item>

          <Space orientation="horizontal" style={{ width: '100%' }}>
            <Form.Item
              label="Месяц"
              name="month"
              rules={[{ required: true, message: 'Укажите месяц' }]}
            >
              <InputNumber min={1} style={{ width: 150 }} />
            </Form.Item>

            <Form.Item
              label="Порядковый номер (order)"
              name="order"
            >
              <InputNumber min={0} style={{ width: 150 }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      {/* Модалка предпросмотра YouTube */}
      <Modal
        title="Предпросмотр видео"
        open={Boolean(previewYoutubeId)}
        onCancel={() => setPreviewYoutubeId(null)}
        footer={null}
        width={700}
        destroyOnClose
      >
        {previewYoutubeId && (
          <iframe
            style={{ width: '100%', height: 380, border: 'none', borderRadius: 8 }}
            src={`https://www.youtube.com/embed/${previewYoutubeId}`}
            title="YouTube video"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        )}
      </Modal>
    </div>
  );
};
