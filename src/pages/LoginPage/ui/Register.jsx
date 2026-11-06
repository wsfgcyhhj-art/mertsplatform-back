import cls from '../loginStyles/login.module.scss';
import { useNavigate, Link } from 'react-router-dom';
import { useState } from 'react';
import { toast, ToastContainer } from 'react-toastify';
import { useFindUser } from '../../../store/userStore.js';
import { IoEyeSharp } from 'react-icons/io5';
import { FaEyeSlash } from 'react-icons/fa';
import { api } from '../../../api/client.js';
import { showAchievementToast } from '../../../components/AchievementToast.jsx';
import { hashPasswordClient } from '../../../utils/crypto.js';

export const Register = () => {
    const navigate = useNavigate();
    const { addUser } = useFindUser();

    const [form, setForm] = useState({
        login: '',
        password: '',
        groupNumber: '',
    });
    const [togglePassword, setTogglePassword] = useState(false);
    const [loading, setLoading] = useState(false);

    const handleChange = (e) => {
        const { name, value } = e.target;
        setForm((prev) => ({
            ...prev,
            [name]: value,
        }));
    };

    const handleRegister = async (e) => {
        if (e) e.preventDefault();

        const cleanLogin = form.login.trim();
        const cleanPassword = form.password.trim();
        const cleanGroupNumber = form.groupNumber.trim();

        if (!cleanLogin || !cleanPassword || !cleanGroupNumber) {
            toast.warning('Заполните все обязательные поля!');
            return;
        }

        if (cleanLogin.length < 3) {
            toast.warning('Логин должен быть не менее 3 символов');
            return;
        }

        if (cleanPassword.length < 8) {
            toast.warning('Пароль должен быть не менее 8 символов');
            return;
        }

        setLoading(true);

        try {
            const hashedPassword = await hashPasswordClient(cleanPassword);

            const res = await api.post('/auth/register', {
                login: cleanLogin,
                password: hashedPassword,
                groupNumber: cleanGroupNumber,
            });

            if (res.data?.user && res.data?.accessToken) {
                localStorage.setItem('accessToken', res.data.accessToken);
                addUser(res.data.user, res.data.accessToken);
                toast.success('Регистрация успешна! Добро пожаловать!');
                setTimeout(() => {
                    navigate('/lessons');
                    if (res.data?.awardedAchievement) {
                        setTimeout(() => {
                            showAchievementToast({
                                title: res.data.awardedAchievement.title,
                                description: res.data.awardedAchievement.description,
                                points: res.data.awardedAchievement.points,
                                iconUrl: res.data.awardedAchievement.iconUrl,
                            });
                        }, 400);
                    }
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
                            name="groupNumber"
                            placeholder="Номер группы (напр. 38) *"
                            value={form.groupNumber}
                            onChange={handleChange}
                            required
                        />

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
