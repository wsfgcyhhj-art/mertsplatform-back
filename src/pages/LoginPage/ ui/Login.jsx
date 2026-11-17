import cls from '../../../../src/pages/LoginPage/loginStyles/login.module.scss';
import { useNavigate, Link } from "react-router-dom";
import { useState } from "react";
import { toast, ToastContainer } from "react-toastify";
import { useFindUser } from "../../../store/userStore.js";
import { IoEyeSharp } from "react-icons/io5";
import { FaEyeSlash } from "react-icons/fa";
import { api } from "../../../api/client.js";
import { AuthBackground } from "../../../components/AuthBackground/AuthBackground.jsx";

export const Login = () => {
    const navigate = useNavigate();
    const { addUser } = useFindUser();
    const [login, setLogin] = useState('');
    const [passwords, setPasswords] = useState('');
    const [togglePassword, setTogglePassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [changeRequired, setChangeRequired] = useState(false);
    const [newPassword, setNewPassword] = useState('');
    const resetToken = new URLSearchParams(window.location.search).get('reset');

    const verifyClick = async (e) => {
        if (e) e.preventDefault();
        if (resetToken || changeRequired) {
            if (newPassword.length < 12) { toast.warning('Минимум 12 символов'); return; }
            setLoading(true);
            try {
                const hashed = newPassword;
                if (resetToken) {
                    await api.post('/auth/reset-password', {token: resetToken, new_password: hashed});
                } else {
                    await api.put('/users/me/password', {currentPassword: passwords, newPassword: hashed});
                }
                window.location.assign('/login');
            } catch (err) { toast.error(err.response?.data?.message || 'Не удалось изменить пароль'); }
            finally { setLoading(false); }
            return;
        }
        const cleanLogin = login.trim();
        const cleanPassword = passwords;

        if (cleanLogin === '' || cleanPassword === '') {
            toast.warning('Заполните все поля!');
            return;
        }

        setLoading(true);

        try {
            const hashedPassword = cleanPassword;

            const res = await api.post('/auth/login', {
                login: cleanLogin,
                password: hashedPassword
            });

            if (res.data?.user && res.data?.accessToken) {
                addUser(res.data.user, res.data.accessToken);
                if (res.data.user.must_change_password) { setChangeRequired(true); setLoading(false); return; }
                toast.success('Успешный вход!');
                setTimeout(() => {
                    if (res.data.user.role === 'ADMIN') {
                        navigate('/admin');
                    } else {
                        navigate('/lessons');
                    }
                }, 600);
            }
        } catch (apiErr) {
            setLoading(false);
            const msg = apiErr.response?.data?.message || 'Неверный логин или пароль';
            toast.error(msg);
        }
    };

    return (
        <AuthBackground>
            <ToastContainer theme="dark" />
            <div className={cls.wrapper} data-aos="zoom-in" data-aos-duration="600">
                <div className={cls.login_items}>
                    <h1>Добро пожаловать 👋</h1>
                    <p>Войдите в свой аккаунт MertsPlatform</p>
                    <form onSubmit={verifyClick} className={cls.login_item}>
                        {!(resetToken || changeRequired) && <><input
                            type="text"
                            placeholder="Логин"
                            value={login}
                            onChange={(e) => setLogin(e.target.value)}
                            required
                        />
                        <div className={cls.pass_input}>
                            <input
                                type={togglePassword ? 'text' : 'password'}
                                placeholder="Пароль"
                                value={passwords}
                                onChange={(e) => setPasswords(e.target.value)}
                                required
                            />
                            <div className={cls.pass_toggle} onClick={() => setTogglePassword(prev => !prev)}>
                                {togglePassword ? <FaEyeSlash /> : <IoEyeSharp />}
                            </div>
                        </div>
                        </>}
                        {(resetToken || changeRequired) && <><p>Установите новый пароль</p><input type="password" minLength={12} value={newPassword} onChange={e => setNewPassword(e.target.value)} required autoComplete="new-password" /></>}
                        <button type="submit" disabled={loading}>
                            {loading ? 'Вход...' : 'Войти'}
                        </button>

                        <div style={{ textAlign: 'center', marginTop: '10px', fontSize: '14px', color: 'rgba(249,250,251,0.7)' }}>
                            Доступ выдаёт владелец через Telegram.{' '}
                            <Link to="/register" style={{ color: 'var(--primary, #f59e0b)', fontWeight: 600, textDecoration: 'none' }}>
                                Зарегистрироваться
                            </Link>
                        </div>
                    </form>
                </div>
            </div>
        </AuthBackground>
    );
};
