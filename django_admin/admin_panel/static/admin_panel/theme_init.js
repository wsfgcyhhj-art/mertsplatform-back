// Default to dark theme on first visit while keeping Unfold's Light/Dark/System switcher active
(function () {
  try {
    if (!localStorage.getItem('_x_adminTheme')) {
      localStorage.setItem('_x_adminTheme', JSON.stringify('dark'));
      document.documentElement.classList.add('dark');
    }
  } catch (e) {}

  document.addEventListener('DOMContentLoaded', function () {
    // Inject a visible quick theme toggle button right into the top header bar
    const headerRight = document.querySelector('#header .ms-auto');
    if (headerRight && !document.getElementById('merts-theme-toggle')) {
      const btn = document.createElement('button');
      btn.id = 'merts-theme-toggle';
      btn.type = 'button';
      btn.className = 'merts-quick-theme-btn';

      const updateLabel = () => {
        const isDark = document.documentElement.classList.contains('dark');
        btn.innerHTML = isDark
          ? '<span class="material-symbols-outlined" style="font-size:18px;">light_mode</span><span>Светлая тема</span>'
          : '<span class="material-symbols-outlined" style="font-size:18px;">dark_mode</span><span>Темная тема</span>';
      };

      updateLabel();

      btn.addEventListener('click', function () {
        const isDark = document.documentElement.classList.contains('dark');
        const nextTheme = isDark ? 'light' : 'dark';
        localStorage.setItem('_x_adminTheme', JSON.stringify(nextTheme));
        if (nextTheme === 'dark') {
          document.documentElement.classList.add('dark');
          document.documentElement.classList.remove('light');
        } else {
          document.documentElement.classList.remove('dark');
          document.documentElement.classList.add('light');
        }
        updateLabel();
      });

      headerRight.prepend(btn);
    }
  });
})();
