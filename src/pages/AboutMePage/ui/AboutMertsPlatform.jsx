import {MdOutlinePeopleAlt, MdOutlineRocketLaunch, MdOutlineSchool} from "react-icons/md";
import cls  from '../styles/about.module.scss'

export const AboutMertsPlatform = () => {
    const AboutCards = [
            {
                id: 1,
                title: "Удобное обучение",
                description:
                    "Все уроки, задания и материалы собраны в одном месте, чтобы обучение было максимально комфортным.",
                icon: MdOutlineSchool,
            },
            {
                id: 2,
                title: "Постоянное развитие",
                description:
                    "MertsPlatform регулярно получает новые функции, улучшения и становится удобнее с каждым обновлением.",
                icon: MdOutlineRocketLaunch,
            },
            {
                id: 3,
                title: "Для студентов",
                description: "Удобно практиковаться, закреплять материал и совершенствовать навыки программирования.",                icon: MdOutlinePeopleAlt,
            }
        ]
    return (
        <>

            <div className={cls.merts_platform} data-aos="fade-up" data-aos-duration="1500">
                <div className={cls.merts_title}>
                    <h3>О MertsPlatform</h3>
                </div>
                <div className={cls.merts_platform_items}>
                    {
                        AboutCards?.map((c) => (
                            <div  key={c?.id} className={cls.merts_platform_item}>
                                <div className={cls.merts_icon}>
                                    <div className={cls.imgs}>
                                        <c.icon/>
                                    </div>
                                    <span>{c?.title}</span>
                                </div>
                                <div className={cls.card_info}>
                                        <p>{c?.description}</p>
                                </div>
                            </div>
                        ))
                    }
                </div>
            </div>

        </>
    )
}