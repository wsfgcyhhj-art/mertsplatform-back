import { useState, useEffect } from 'react';
import { Tabs, Tag, ConfigProvider, theme, Button, Space } from 'antd';
import {
  FileTextOutlined,
  VideoCameraOutlined,
  CheckSquareOutlined,
  TeamOutlined,
  DatabaseOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import { SubmissionsTab } from './SubmissionsTab.jsx';
import { LessonsTab } from './LessonsTab.jsx';
import { TasksTab } from './TasksTab.jsx';
import { StudentsTab } from './StudentsTab.jsx';
import { useFindUser } from '../../../store/userStore.js';
import { api } from '../../../api/client.js';
import styles from '../styles/admin.module.scss';

export const AdminDashboard = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { userInfo } = useFindUser();

  const [kpi, setKpi] = useState({
    pendingSubmissions: 0,
    totalStudents: 0,
    totalLessons: 0,
    totalTasks: 0,
  });

  const getTabFromPath = () => {
    const path = location.pathname;
    if (path.includes('/admin/lessons')) return 'lessons';
    if (path.includes('/admin/tasks')) return 'tasks';
    if (path.includes('/admin/students')) return 'students';
    return 'submissions';
  };

  const [activeKey, setActiveKey] = useState(getTabFromPath());

  useEffect(() => {
    setActiveKey(getTabFromPath());
  }, [location.pathname]);

  useEffect(() => {
    const loadSummary = async () => {
      try {
        const [subsRes, leadRes, lessonsRes, tasksRes] = await Promise.all([
          api.get('/admin/submissions', { params: { status: 'SENT' } }),
          api.get('/leaderboard'),
          api.get('/admin/lessons'),
          api.get('/admin/tasks'),
        ]);
        setKpi({
          pendingSubmissions: subsRes.data?.submissions?.length || 0,
          totalStudents: Array.isArray(leadRes.data) ? leadRes.data.length : 0,
          totalLessons: lessonsRes.data?.lessons?.length || 0,
          totalTasks: tasksRes.data?.tasks?.length || 0,
        });
      } catch (err) {
        console.error('KPI load error', err);
      }
    };
    loadSummary();
  }, [activeKey]);

  const handleTabChange = (key) => {
    setActiveKey(key);
    navigate(`/admin/${key}`);
  };

  const tabItems = [
    {
      key: 'submissions',
      label: (
        <span>
          <FileTextOutlined /> Проверка ДЗ ({kpi.pendingSubmissions})
        </span>
      ),
      children: <SubmissionsTab />,
    },
    {
      key: 'lessons',
      label: (
        <span>
          <VideoCameraOutlined /> Видеоуроки ({kpi.totalLessons})
        </span>
      ),
      children: <LessonsTab />,
    },
    {
      key: 'tasks',
      label: (
        <span>
          <CheckSquareOutlined /> Задания ({kpi.totalTasks})
        </span>
      ),
      children: <TasksTab />,
    },
    {
      key: 'students',
      label: (
        <span>
          <TeamOutlined /> Студенты и Баллы ({kpi.totalStudents})
        </span>
      ),
      children: <StudentsTab />,
    },
  ];

  return (
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#a855f7',
          colorBgContainer: '#182042',
          colorBgElevated: '#1e274f',
          borderRadius: 12,
          fontSize: 16,
          controlHeight: 44,
        },
      }}
    >
      <div className={styles.adminContainer}>
        <div className={styles.adminHeader}>
          <div>
            <h1>Панель управления MertsPlatform</h1>
            <p>Полноэкранный центр проверки домашних работ, управления уроками, заданиями и рейтингом</p>
          </div>
          <Space size="middle" wrap>
            <Button
              type="primary"
              size="large"
              icon={<DatabaseOutlined />}
              href="http://localhost:8000/admin"
              target="_blank"
              style={{
                background: 'linear-gradient(135deg, #a855f7 0%, #6366f1 100%)',
                border: 'none',
                fontWeight: 600,
                height: 48,
                padding: '0 24px',
              }}
            >
              Открыть СУБД (Django Admin) ↗
            </Button>
            <Tag
              color="purple"
              style={{
                fontSize: 15,
                padding: '10px 18px',
                borderRadius: 12,
                fontWeight: 600,
              }}
            >
              👑 {userInfo?.name || userInfo?.login} (ADMIN)
            </Tag>
          </Space>
        </div>

        {/* Крупные карточки статистики */}
        <div className={styles.statsGrid}>
          <div className={styles.statCard} onClick={() => handleTabChange('submissions')} style={{ cursor: 'pointer' }}>
            <div>
              <div className={styles.statTitle}>Ожидают проверки</div>
              <div className={styles.statValue} style={{ color: '#f59e0b' }}>
                {kpi.pendingSubmissions}
              </div>
            </div>
            <div className={styles.statIcon} style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b' }}>
              <ClockCircleOutlined />
            </div>
          </div>

          <div className={styles.statCard} onClick={() => handleTabChange('students')} style={{ cursor: 'pointer' }}>
            <div>
              <div className={styles.statTitle}>Активных студентов</div>
              <div className={styles.statValue} style={{ color: '#10b981' }}>
                {kpi.totalStudents}
              </div>
            </div>
            <div className={styles.statIcon} style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#10b981' }}>
              <TeamOutlined />
            </div>
          </div>

          <div className={styles.statCard} onClick={() => handleTabChange('lessons')} style={{ cursor: 'pointer' }}>
            <div>
              <div className={styles.statTitle}>Видеоуроков в базе</div>
              <div className={styles.statValue} style={{ color: '#3b82f6' }}>
                {kpi.totalLessons}
              </div>
            </div>
            <div className={styles.statIcon} style={{ background: 'rgba(59, 130, 246, 0.15)', color: '#3b82f6' }}>
              <VideoCameraOutlined />
            </div>
          </div>

          <div className={styles.statCard} onClick={() => handleTabChange('tasks')} style={{ cursor: 'pointer' }}>
            <div>
              <div className={styles.statTitle}>Учебных заданий</div>
              <div className={styles.statValue} style={{ color: '#a855f7' }}>
                {kpi.totalTasks}
              </div>
            </div>
            <div className={styles.statIcon} style={{ background: 'rgba(168, 85, 247, 0.15)', color: '#a855f7' }}>
              <CheckSquareOutlined />
            </div>
          </div>
        </div>

        {/* Основная рабочая область во весь экран */}
        <div className={styles.mainWorkspace}>
          <Tabs
            activeKey={activeKey}
            onChange={handleTabChange}
            items={tabItems}
            size="large"
          />
        </div>
      </div>
    </ConfigProvider>
  );
};
