import cls from '../../../../src/pages/LoginPage/loginStyles/login.module.scss';
import { useNavigate, Link } from "react-router-dom";
import { useState } from "react";
import { toast, ToastContainer } from "react-toastify";
import { useFindUser } from "../../../store/userStore.js";
import { IoEyeSharp } from "react-icons/io5";
import { FaEyeSlash } from "react-icons/fa";
import { api } from "../../../api/client.js";

export const Login = () => {
    const navigate = useNavigate();
    const { addUser } = useFindUser();
    const [login, setLogin] = useState('');
    const [passwords, setPasswords] = useState('');
    const [togglePassword, setTogglePassword] = useState(false);
    const [loading, setLoading] = useState(false);

    const verifyClick = async (e) => {
        if (e) e.preventDefault();
        const cleanLogin = login.trim();
        const cleanPassword = passwords.trim();

        if (cleanLogin === '' || cleanPassword === '') {
            toast.warning('Заполните все поля!');
            return;
        }

        setLoading(true);

        try {
            const res = await api.post('/auth/login', {
                login: cleanLogin,
                password: cleanPassword
            });

            if (res.data?.user && res.data?.accessToken) {
                addUser(res.data.user, res.data.accessToken);
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
        <>
            <ToastContainer theme="dark" />
            <div className={cls.wrapper} data-aos="zoom-in" data-aos-duration="600">
                <div className={cls.login_items}>
                    <h1>Добро пожаловать 👋</h1>
                    <p>Войдите в свой аккаунт MertsPlatform</p>
                    <form onSubmit={verifyClick} className={cls.login_item}>
                        <input
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
                        <button type="submit" disabled={loading}>
                            {loading ? 'Вход...' : 'Войти'}
                        </button>

                        <div style={{ textAlign: 'center', marginTop: '10px', fontSize: '14px', color: 'rgba(249,250,251,0.7)' }}>
                            Еще нет аккаунта?{' '}
                            <Link to="/register" style={{ color: 'var(--primary, #a855f7)', fontWeight: 600, textDecoration: 'none' }}>
                                Зарегистрироваться
                            </Link>
                        </div>
                    </form>
                </div>
            </div>
        </>
    );
};
