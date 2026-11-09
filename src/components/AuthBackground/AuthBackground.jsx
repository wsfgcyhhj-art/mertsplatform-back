import React, { useEffect, useRef } from 'react';
import cls from './authBackground.module.scss';

/**
 * AuthBackground — Интерактивный живой фон в стиле Linear / Geeks Online
 * с монограммой «M» MertsPlatform, параллаксом мыши, виньеткой и дыханием градиентов.
 */
export const AuthBackground = ({ children }) => {
  const containerRef = useRef(null);

  useEffect(() => {
    // Проверяем, поддерживает ли устройство точный курсор (мышь/трекпад)
    const isFinePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (!isFinePointer || prefersReducedMotion) {
      return;
    }

    const container = containerRef.current;
    if (!container) return;

    let rafId = null;
    let targetX = 0;
    let targetY = 0;
    let currentX = 0;
    let currentY = 0;

    const PARALLAX_STRENGTH = 24; // максимальный сдвиг в пикселях

    const onMouseMove = (e) => {
      const { innerWidth, innerHeight } = window;
      // Нормализуем координаты от -1 до 1 относительно центра
      const normX = (e.clientX / innerWidth - 0.5) * 2;
      const normY = (e.clientY / innerHeight - 0.5) * 2;

      targetX = normX * PARALLAX_STRENGTH;
      targetY = normY * PARALLAX_STRENGTH;

      if (!rafId) {
        rafId = requestAnimationFrame(updateParallax);
      }
    };

    const updateParallax = () => {
      // Плавная интерполяция (LERP) для мягкого следования
      currentX += (targetX - currentX) * 0.08;
      currentY += (targetY - currentY) * 0.08;

      if (container) {
        container.style.setProperty('--mouse-x', `${currentX.toFixed(2)}px`);
        container.style.setProperty('--mouse-y', `${currentY.toFixed(2)}px`);
      }

      // Если разница еще заметна, продолжаем кадр
      if (Math.abs(targetX - currentX) > 0.05 || Math.abs(targetY - currentY) > 0.05) {
        rafId = requestAnimationFrame(updateParallax);
      } else {
        rafId = null;
      }
    };

    window.addEventListener('mousemove', onMouseMove, { passive: true });

    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      if (rafId) {
        cancelAnimationFrame(rafId);
      }
    };
  }, []);

  return (
    <div className={cls.authContainer} ref={containerRef}>
      <div className={cls.backgroundBase} />
      <div className={cls.ambientGlow} />
      <div className={cls.patternLayer} />
      <div className={cls.vignetteOverlay} />
      <div className={cls.contentLayer}>
        {children}
      </div>
    </div>
  );
};

export default AuthBackground;
