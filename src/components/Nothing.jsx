import cls from '../components/nothing.module.scss'

export const Nothing = () => {
    return (
        <>
            <div className={cls.wrapper}>
                <div className={cls.nothing}>
                    <h1>В процессе </h1>
                    <div className={`${cls.loader} ${cls.first}`}></div>
                    <div className={`${cls.loader} ${cls.second}`}></div>
                    <div className={`${cls.loader} ${cls.third}`}></div>
                </div>
            </div>
        </>
    )
}