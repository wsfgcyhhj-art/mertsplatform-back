import { useState, useEffect } from 'react';
import { Tag, ConfigProvider, theme, Button, Space, Spin } from 'antd';
import {
  FileTextOutlined,
  VideoCameraOutlined,
  CheckSquareOutlined,
  TeamOutlined,
  DatabaseOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  TrophyOutlined,
  ExportOutlined,
} from '@ant-design/icons';
import { useFindUser } from '../../../store/userStore.js';
import { api, API_BASE_URL } from '../../../api/client.js';
import styles from '../styles/admin.module.scss';

export const AdminDashboard = () => {
  const { userInfo } = useFindUser();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({
    totalStudents: 0,
    totalSubmissions: 0,
    pendingSubmissions: 0,
    acceptedSubmissions: 0,
  });

  const adminBaseUrl = new URL('/admin/', new URL(API_BASE_URL, window.location.origin)).href;
  const adminSections = [
    { key: 'submission', label: 'Проверка ДЗ', icon: <CheckSquareOutlined />, path: 'admin_panel/submission/' },
    { key: 'lesson', label: 'Видеоуроки', icon: <VideoCameraOutlined />, path: 'admin_panel/lesson/' },
    { key: 'task', label: 'Учебные задания', icon: <FileTextOutlined />, path: 'admin_panel/task/' },
    { key: 'user', label: 'Студенты и Баллы', icon: <TeamOutlined />, path: 'admin_panel/user/' },
    { key: 'achievement', label: 'Каталог ачивок', icon: <TrophyOutlined />, path: 'admin_panel/achievement/' },
  ];

  useEffect(() => {
    let active = true;
    const loadSummary = async () => {
      try {
        const res = await api.get('/admin/stats');
        if (active && res.data) {
          setStats({
            totalStudents: res.data.totalStudents || 0,
            totalSubmissions: res.data.totalSubmissions || 0,
            pendingSubmissions: res.data.pendingSubmissions || 0,
            acceptedSubmissions: res.data.acceptedSubmissions || 0,
          });
        }
      } catch (err) {
        console.error('KPI load error', err);
      } finally {
        if (active) setLoading(false);
      }
    };
    loadSummary();
    return () => {
      active = false;
    };
  }, []);

  return (
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#f59e0b',
          colorBgContainer: '#18181b',
          colorBgElevated: '#27272a',
          borderRadius: 12,
          fontSize: 16,
          controlHeight: 44,
        },
      }}
    >
      <div className={styles.adminContainer}>
        <div className={styles.adminHeader}>
          <div style={{ minWidth: 0, maxWidth: '100%' }}>
            <h1>Панель управления MertsPlatform</h1>
            <p>Сводка платформы и быстрый переход в Django Unfold Admin для управления учебным процессом</p>
          </div>
          <Space size="middle" wrap style={{ maxWidth: '100%' }}>
            <Button
              type="primary"
              size="large"
              icon={<DatabaseOutlined />}
              href={adminBaseUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                background: '#f59e0b',
                color: '#09090b',
                border: 'none',
                fontWeight: 700,
                minHeight: 48,
                height: 'auto',
                padding: '10px 16px',
                whiteSpace: 'normal',
                maxWidth: '100%',
              }}
            >
              Открыть Django Unfold Admin ↗
            </Button>
            <Tag
              color="gold"
              style={{
                fontSize: 15,
                padding: '10px 18px',
                borderRadius: 12,
                fontWeight: 600,
                maxWidth: '100%',
                whiteSpace: 'normal',
                wordBreak: 'break-word',
              }}
            >
              👑 {userInfo?.name || userInfo?.login} (ADMIN)
            </Tag>
          </Space>
        </div>

        {/* Крупные карточки статистики */}
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px 0' }}>
            <Spin size="large" />
          </div>
        ) : (
          <div className={styles.statsGrid}>
            <div className={styles.statCard}>
              <div>
                <div className={styles.statTitle}>Ожидают проверки</div>
                <div className={styles.statValue} style={{ color: '#f59e0b' }}>
                  {stats.pendingSubmissions}
                </div>
              </div>
              <div className={styles.statIcon} style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b' }}>
                <ClockCircleOutlined />
              </div>
            </div>

            <div className={styles.statCard}>
              <div>
                <div className={styles.statTitle}>Активных студентов</div>
                <div className={styles.statValue} style={{ color: '#10b981' }}>
                  {stats.totalStudents}
                </div>
              </div>
              <div className={styles.statIcon} style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#10b981' }}>
                <TeamOutlined />
              </div>
            </div>

            <div className={styles.statCard}>
              <div>
                <div className={styles.statTitle}>Всего сдач ДЗ</div>
                <div className={styles.statValue} style={{ color: '#3b82f6' }}>
                  {stats.totalSubmissions}
                </div>
              </div>
              <div className={styles.statIcon} style={{ background: 'rgba(59, 130, 246, 0.15)', color: '#3b82f6' }}>
                <FileTextOutlined />
              </div>
            </div>

            <div className={styles.statCard}>
              <div>
                <div className={styles.statTitle}>Принятых работ</div>
                <div className={styles.statValue} style={{ color: '#22c55e' }}>
                  {stats.acceptedSubmissions}
                </div>
              </div>
              <div className={styles.statIcon} style={{ background: 'rgba(34, 197, 94, 0.15)', color: '#22c55e' }}>
                <CheckCircleOutlined />
              </div>
            </div>
          </div>
        )}

        <div className={styles.mainWorkspace} style={{ minHeight: 'auto' }}>
          <h2 style={{ fontSize: 22, fontWeight: 700, marginBottom: 10, color: '#f4f4f5' }}>
            Управление разделами перенесено в Django Unfold Admin
          </h2>
          <p style={{ color: '#a1a1aa', marginBottom: 24, fontSize: 15 }}>
            Проверка домашних работ, видеоуроки, задания, студенты, баллы и каталог достижений теперь управляются централизованно на бэкенде.
          </p>
          <Space size="middle" wrap style={{ maxWidth: '100%' }}>
            {adminSections.map((section) => (
              <Button
                key={section.key}
                size="large"
                icon={section.icon}
                href={`${adminBaseUrl}${section.path}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  maxWidth: '100%',
                  height: 'auto',
                  minHeight: 44,
                  whiteSpace: 'normal',
                }}
              >
                {section.label} <ExportOutlined />
              </Button>
            ))}
          </Space>
        </div>
      </div>
    </ConfigProvider>
  );
};
