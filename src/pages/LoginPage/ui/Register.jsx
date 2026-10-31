import cls from '../loginStyles/login.module.scss';
import { useNavigate, Link } from 'react-router-dom';
import { useState } from 'react';
import { toast, ToastContainer } from 'react-toastify';
import { useFindUser } from '../../../store/userStore.js';
import { IoEyeSharp } from 'react-icons/io5';
import { FaEyeSlash } from 'react-icons/fa';
import { api } from '../../../api/client.js';

export const Register = () => {
    const navigate = useNavigate();
    const { addUser } = useFindUser();

    const [form, setForm] = useState({
        login: '',
        password: '',
        name: '',
        telegram: '',
        groupNumber: '',
        groupId: 'standard',
        currentMonth: 1,
    });
    const [togglePassword, setTogglePassword] = useState(false);
    const [loading, setLoading] = useState(false);

    const handleChange = (e) => {
        const { name, value } = e.target;
        setForm((prev) => ({
            ...prev,
            [name]: name === 'currentMonth' ? Number(value) || 1 : value,
        }));
    };

    const handleRegister = async (e) => {
        if (e) e.preventDefault();

        const cleanLogin = form.login.trim();
        const cleanPassword = form.password.trim();
        const cleanName = form.name.trim();
        const cleanTelegram = form.telegram.trim();
        const cleanGroupNumber = form.groupNumber.trim();
        const cleanGroupId = form.groupId.trim() || 'standard';

        if (!cleanLogin || !cleanPassword || !cleanName || !cleanTelegram || !cleanGroupNumber) {
            toast.warning('Заполните все обязательные поля!');
            return;
        }

        if (cleanLogin.length < 3) {
            toast.warning('Логин должен быть не менее 3 символов');
            return;
        }

        if (cleanPassword.length < 4) {
            toast.warning('Пароль должен быть не менее 4 символов');
            return;
        }

        setLoading(true);

        try {
            const res = await api.post('/auth/register', {
                login: cleanLogin,
                password: cleanPassword,
                name: cleanName,
                telegram: cleanTelegram,
                groupNumber: cleanGroupNumber,
                groupId: cleanGroupId,
                currentMonth: form.currentMonth || 1,
            });

            if (res.data?.user && res.data?.accessToken) {
                addUser(res.data.user, res.data.accessToken);
                toast.success('Регистрация успешна! Добро пожаловать!');
                setTimeout(() => {
                    navigate('/lessons');
                }, 800);
            }
        } catch (err) {
            setLoading(false);
            const msg = err.response?.data?.message || 'Ошибка при регистрации. Проверьте данные.';
            toast.error(msg);
        }
    };

    return (
        <>
            <ToastContainer theme="dark" />
            <div className={cls.wrapper} data-aos="zoom-in" data-aos-duration="600" style={{ minHeight: '100vh', padding: '30px 0' }}>
                <div className={cls.login_items} style={{ maxHeight: 'none', height: 'auto', width: '520px' }}>
                    <h1>Регистрация 🚀</h1>
                    <p>Создайте аккаунт студента MertsPlatform</p>
                    <form onSubmit={handleRegister} className={cls.login_item}>
                        <input
                            type="text"
                            name="login"
                            placeholder="Логин *"
                            value={form.login}
                            onChange={handleChange}
                            required
                        />

                        <div className={cls.pass_input}>
                            <input
                                type={togglePassword ? 'text' : 'password'}
                                name="password"
                                placeholder="Пароль *"
                                value={form.password}
                                onChange={handleChange}
                                required
                            />
                            <div className={cls.pass_toggle} onClick={() => setTogglePassword(prev => !prev)}>
                                {togglePassword ? <FaEyeSlash /> : <IoEyeSharp />}
                            </div>
                        </div>

                        <input
                            type="text"
                            name="name"
                            placeholder="Ваше имя и фамилия *"
                            value={form.name}
                            onChange={handleChange}
                            required
                        />

                        <input
                            type="text"
                            name="telegram"
                            placeholder="Telegram (@username) *"
                            value={form.telegram}
                            onChange={handleChange}
                            required
                        />

                        <div style={{ display: 'flex', gap: '10px' }}>
                            <input
                                type="text"
                                name="groupNumber"
                                placeholder="Номер группы (напр. 38) *"
                                value={form.groupNumber}
                                onChange={handleChange}
                                required
                                style={{ flex: 1 }}
                            />
                            <input
                                type="text"
                                name="groupId"
                                placeholder="ID группы (напр. standard)"
                                value={form.groupId}
                                onChange={handleChange}
                                style={{ flex: 1 }}
                            />
                        </div>

                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                            <label style={{ fontSize: '13px', color: 'rgba(249, 250, 251, 0.7)' }}>Текущий месяц обучения:</label>
                            <input
                                type="number"
                                name="currentMonth"
                                min="1"
                                max="12"
                                value={form.currentMonth}
                                onChange={handleChange}
                            />
                        </div>

                        <button type="submit" disabled={loading}>
                            {loading ? 'Регистрация...' : 'Зарегистрироваться'}
                        </button>

                        <div style={{ textAlign: 'center', marginTop: '10px', fontSize: '14px', color: 'rgba(249,250,251,0.7)' }}>
                            Уже есть аккаунт?{' '}
                            <Link to="/auth" style={{ color: 'var(--primary, #a855f7)', fontWeight: 600, textDecoration: 'none' }}>
                                Войти
                            </Link>
                        </div>
                    </form>
                </div>
            </div>
        </>
    );
};
