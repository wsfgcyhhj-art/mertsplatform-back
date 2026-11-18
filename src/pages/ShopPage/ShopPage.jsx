import { useCallback, useEffect, useRef, useState } from 'react';
import { FaBoxOpen, FaShoppingBag } from 'react-icons/fa';
import { Modal } from 'antd';
import { api } from '../../api/client.js';
import { useFindUser } from '../../store/userStore.js';
import { safeUrl } from '../../utils/safeUrl.js';
import styles from './shop.module.scss';

const orderStatuses = {
    PENDING: 'Ожидает выдачи',
    COMPLETED: 'Выдан',
    CANCELLED: 'Отменён',
};
const number = new Intl.NumberFormat('ru-RU');

export function ShopPage() {
    const { userInfo } = useFindUser();
    const [catalog, setCatalog] = useState(null);
    const [orders, setOrders] = useState(null);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [selection, setSelection] = useState(null);
    const [busy, setBusy] = useState(false);
    const purchaseInProgress = useRef(false);

    const load = useCallback(async (signal) => {
        setError('');
        try {
            const [products, history] = await Promise.all([
                api.get('/shop/products', { signal }),
                api.get('/shop/orders/my', { signal }),
            ]);
            setCatalog(products.data);
            setOrders(history.data);
        } catch (err) {
            if (!signal?.aborted) {
                setError(err.response?.data?.detail || 'Не удалось загрузить магазин. Попробуйте ещё раз.');
            }
        }
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        load(controller.signal);
        return () => controller.abort();
    }, [load]);

    async function buy() {
        if (!selection || purchaseInProgress.current) return;
        purchaseInProgress.current = true;
        setBusy(true);
        setError('');
        setNotice('');
        const key = `merts:shop:${userInfo.id}:${selection.id}`;
        try {
            const requestId = sessionStorage.getItem(key) || crypto.randomUUID();
            sessionStorage.setItem(key, requestId);
            const { data } = await api.post('/shop/orders', {
                productId: selection.id, requestId, expectedPriceCoins: selection.priceCoins,
            });
            sessionStorage.removeItem(key);
            setCatalog(current => ({ ...current, availableCoins: data.availableCoins,
                totalEarnedPoints: data.totalEarnedPoints, spentPoints: data.spentPoints }));
            setOrders(current => [data.order, ...(current || []).filter(order => order.id !== data.order.id)]);
            setSelection(null);
            setNotice('Заказ оформлен. Статус доступен в истории покупок.');
            await load();
        } catch (err) {
            const status = err.response?.status;
            if ([400, 403, 404, 409].includes(status)) {
                sessionStorage.removeItem(key);
                setSelection(null);
            }
            setError(err.response?.data?.detail || 'Не удалось подтвердить заказ. Повторите запрос с тем же товаром.');
        } finally {
            purchaseInProgress.current = false;
            setBusy(false);
        }
    }

    return (
        <main className={styles.shop}>
            <header className={styles.header}>
                <h1><FaShoppingBag aria-hidden="true" /> Merts Shop</h1>
                {catalog && <dl className={styles.balance}>
                    <div><dt>Доступно</dt><dd>{number.format(catalog.availableCoins)} баллов</dd></div>
                    <div><dt>Заработано</dt><dd>{number.format(catalog.totalEarnedPoints)}</dd></div>
                    <div><dt>Потрачено</dt><dd>{number.format(catalog.spentPoints)}</dd></div>
                </dl>}
            </header>

            {notice && <p className={styles.notice} role="status">{notice}</p>}
            {error && !selection && <p className={styles.error} role="alert">
                {error} <button type="button" onClick={() => load()}>Обновить</button>
            </p>}
            {!catalog && !error && <p role="status">Загрузка магазина…</p>}

            {catalog && <>
                <section aria-labelledby="shop-catalog">
                    <h2 id="shop-catalog">Товары</h2>
                    {catalog.products.length === 0 && <p>Товаров пока нет.</p>}
                    <ul className={styles.grid}>
                        {catalog.products.map(product => {
                            const canBuy = product.stock > 0 && catalog.availableCoins >= product.priceCoins;
                            return <li className={styles.product} key={product.id}>
                                <div className={styles.image}>
                                    {product.imageUrl
                                        ? <img src={safeUrl(product.imageUrl)} alt="" loading="lazy" />
                                        : <FaBoxOpen aria-hidden="true" />}
                                </div>
                                <div className={styles.details}>
                                    <h3>{product.title}</h3>
                                    <p>{product.description}</p>
                                    <div className={styles.prices}>
                                        <strong>{number.format(product.priceCoins)} баллов</strong>
                                        <span>{number.format(product.priceSom)} сом</span>
                                    </div>
                                    <button type="button" disabled={!canBuy || busy} onClick={() => { setError(''); setSelection(product); }}>
                                        {!product.stock ? 'Нет в наличии' : canBuy ? 'Купить за баллы' : 'Недостаточно баллов'}
                                    </button>
                                </div>
                            </li>;
                        })}
                    </ul>
                </section>
                <section aria-labelledby="shop-history">
                    <h2 id="shop-history">Мои заказы</h2>
                    {orders?.length ? <ul className={styles.history}>
                        {orders.map(order => <li key={order.id}>
                            <div><strong>{order.productTitle}</strong>
                                <time dateTime={order.createdAt}>{new Date(order.createdAt).toLocaleDateString('ru-RU')}</time>
                            </div>
                            <span>{number.format(order.priceCoins)} баллов</span>
                            <span className={styles.status} data-status={order.status}>{orderStatuses[order.status]}</span>
                        </li>)}
                    </ul> : <p>Заказов пока нет.</p>}
                </section>
            </>}

            <Modal title="Подтвердить покупку" open={Boolean(selection)} onOk={buy}
                onCancel={() => { if (!busy) setSelection(null); }} okText="Купить" cancelText="Назад"
                confirmLoading={busy} cancelButtonProps={{ disabled: busy }} closable={!busy} maskClosable={!busy}>
                {selection && <p>{selection.title} · <strong>{number.format(selection.priceCoins)} баллов</strong></p>}
                {error && selection && <p role="alert">{error}</p>}
            </Modal>
        </main>
    );
}
