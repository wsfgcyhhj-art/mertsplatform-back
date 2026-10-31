import cls from '../../src/components/notfound.module.scss'
import {FaRocket} from "react-icons/fa";
import {useNavigate} from "react-router-dom";
import {toast, ToastContainer} from "react-toastify";

export const NotFound = () => {

    const navigate = useNavigate();

    const pasxolkoClick = () => {
        const noty = toast.success('ПАСХОЛКОООО')
        setTimeout(() => {
            window.location.href = 'https://help.reg.ru/support/hosting/sayt-ne-rabotayet/oshibka-404#:~:text=%D0%9E%D1%88%D0%B8%D0%B1%D0%BA%D0%B0%20404%20page%20not%20found,%D0%B1%D1%80%D0%B0%D1%83%D0%B7%D0%B5%D1%80%D1%83%20%D1%81%20%D0%BF%D0%BE%D0%BC%D0%BE%D1%89%D1%8C%D1%8E%20%D0%BA%D0%BE%D0%B4%D0%B0%20404.'
        },1000)
    }

    return (

        <div className={cls.notfound}>
            <ToastContainer theme="dark"/>
            <div className={cls.notfound_content} data-aos="fade-up" data-aos-duration="600">
                <h2> <span onClick={pasxolkoClick} style={{marginRight: '5px'}}>404</span>Страница не найдена</h2>
                <button onClick={() => navigate('/main')}>На главную страницу</button>

            </div>
            <div className={cls.notfound_content_2} data-aos="fade-up" data-aos-duration="600">
                <p><FaRocket style={{marginRight: '10px'}} />Ты попал в пустую орбиту интернета </p>
                <button onClick={() => navigate(-1)}>Вернутся назад</button>
            </div>

            <div className={cls.notfound_item} data-aos="zoom-in" data-aos-duration="1000" >

                <div className={cls.papa}>

                    <div className={cls.notfound_block}>
                        <span className={cls.number} >404</span>
                    </div>

                    <div className={cls.orbit1}>
                        <div className={cls.planet1}>UNKNOWN</div>
                    </div>

                    <div className={cls.orbit2}>
                        <div className={cls.planet2}>LOST</div>
                    </div>

                    <div className={cls.orbit3}>
                        <div className={cls.planet3}>LOST</div>
                    </div>
                    <div className={cls.orbit4}>
                        <div className={cls.planet4}>EXPLORE</div>
                    </div>
                    <div className={cls.orbit5}>
                        <div className={cls.planet5}>page</div>
                    </div>
                </div>
            </div>


        </div>
    )
}