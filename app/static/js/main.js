/**
 * MTProxy Manager - Main JavaScript
 */

document.addEventListener('DOMContentLoaded', function() {
    // Инициализация компонентов
    initSidebar();
    initAlerts();
    initCopyButtons();
    initConfirmForms();
    initMtgStatusWidget();
});

/**
 * Sidebar toggle для мобильных устройств
 */
function initSidebar() {
    const toggle = document.getElementById('sidebar-toggle');
    const sidebar = document.querySelector('.sidebar');
    
    if (toggle && sidebar) {
        toggle.addEventListener('click', function() {
            sidebar.classList.toggle('open');
        });
        
        // Закрытие при клике вне sidebar
        document.addEventListener('click', function(e) {
            if (sidebar.classList.contains('open') && 
                !sidebar.contains(e.target) && 
                !toggle.contains(e.target)) {
                sidebar.classList.remove('open');
            }
        });
    }
}

/**
 * Автозакрытие alert сообщений
 */
function initAlerts() {
    const alerts = document.querySelectorAll('.alert');
    
    alerts.forEach(function(alert) {
        // Кнопка закрытия
        const closeBtn = alert.querySelector('.alert-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() {
                fadeOut(alert);
            });
        }
        
        // Автозакрытие через 5 секунд для success сообщений
        if (alert.classList.contains('alert-success')) {
            setTimeout(function() {
                fadeOut(alert);
            }, 5000);
        }
    });
}

/**
 * Плавное скрытие элемента
 */
function fadeOut(element) {
    element.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
    element.style.opacity = '0';
    element.style.transform = 'translateY(-10px)';
    
    setTimeout(function() {
        element.remove();
    }, 300);
}

/**
 * Универсальные кнопки копирования
 */
function initCopyButtons() {
    document.querySelectorAll('[data-copy]').forEach(function(btn) {
        btn.addEventListener('click', function() {
            const text = this.dataset.copy;
            copyToClipboard(text, this);
        });
    });
    
    document.querySelectorAll('[data-copy-target]').forEach(function(btn) {
        btn.addEventListener('click', function() {
            const targetId = this.dataset.copyTarget;
            const target = document.getElementById(targetId);
            if (target) {
                copyToClipboard(target.value || target.textContent, this);
            }
        });
    });
}

/**
 * Копирование текста в буфер обмена
 */
function copyToClipboard(text, button) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function() {
            showCopySuccess(button);
        }).catch(function(err) {
            console.error('Ошибка копирования:', err);
            fallbackCopy(text, button);
        });
    } else {
        fallbackCopy(text, button);
    }
}

/**
 * Fallback копирование для старых браузеров
 */
function fallbackCopy(text, button) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    textarea.select();
    
    try {
        document.execCommand('copy');
        showCopySuccess(button);
    } catch (err) {
        console.error('Fallback копирование не удалось:', err);
        alert('Не удалось скопировать. Пожалуйста, скопируйте вручную.');
    }
    
    document.body.removeChild(textarea);
}

/**
 * Показать успешное копирование на кнопке
 */
function showCopySuccess(button) {
    const originalContent = button.innerHTML;
    const originalClass = button.className;
    
    button.innerHTML = '✓';
    button.classList.add('btn-success');
    
    setTimeout(function() {
        button.innerHTML = originalContent;
        button.className = originalClass;
    }, 1500);
}

/**
 * Подтверждение для форм с data-confirm
 */
function initConfirmForms() {
    document.querySelectorAll('form[data-confirm]').forEach(function(form) {
        form.addEventListener('submit', function(e) {
            const message = this.dataset.confirm || 'Вы уверены?';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
}

/**
 * Виджет статуса MTG в sidebar
 */
function initMtgStatusWidget() {
    const widget = document.getElementById('mtg-status-widget');
    if (!widget) return;
    
    // Обновляем статус каждые 30 секунд
    updateMtgStatus();
    setInterval(updateMtgStatus, 30000);
}

/**
 * Обновление статуса MTG
 */
function updateMtgStatus() {
    const widget = document.getElementById('mtg-status-widget');
    if (!widget) return;
    
    const indicator = widget.querySelector('.status-indicator');
    if (!indicator) return;
    
    // Получаем URL API из data-атрибута или используем дефолтный
    const apiUrl = widget.dataset.apiUrl || '/admin/api/system-stats';
    
    fetch(apiUrl)
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(data => {
            if (data.mtg) {
                if (data.mtg.running) {
                    indicator.textContent = 'Работает';
                    indicator.className = 'status-indicator running';
                } else {
                    indicator.textContent = 'Остановлен';
                    indicator.className = 'status-indicator stopped';
                }
            }
        })
        .catch(error => {
            console.debug('MTG status update failed:', error);
            indicator.textContent = '—';
            indicator.className = 'status-indicator';
        });
}

/**
 * Форматирование байтов в читаемый формат
 */
function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Б';
    
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ', 'ПБ'];
    
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

/**
 * Форматирование даты
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * Debounce функция для оптимизации
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * AJAX запрос с CSRF токеном
 */
function fetchWithCsrf(url, options = {}) {
    const csrfToken = document.querySelector('meta[name="csrf-token"]');
    
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken ? csrfToken.content : ''
        }
    };
    
    return fetch(url, { ...defaultOptions, ...options });
}

/**
 * Показать уведомление
 */
function showNotification(message, type = 'info') {
    const container = document.querySelector('.flash-messages') || createNotificationContainer();
    
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = `
        <span class="alert-message">${message}</span>
        <button type="button" class="alert-close" aria-label="Закрыть">&times;</button>
    `;
    
    container.appendChild(alert);
    
    // Инициализируем закрытие
    alert.querySelector('.alert-close').addEventListener('click', function() {
        fadeOut(alert);
    });
    
    // Автозакрытие
    if (type === 'success') {
        setTimeout(function() {
            fadeOut(alert);
        }, 5000);
    }
}

/**
 * Создать контейнер для уведомлений
 */
function createNotificationContainer() {
    const container = document.createElement('div');
    container.className = 'flash-messages';
    
    const content = document.querySelector('.content');
    if (content) {
        content.insertBefore(container, content.firstChild);
    } else {
        document.body.insertBefore(container, document.body.firstChild);
    }
    
    return container;
}

/**
 * Автообновление данных на странице dashboard
 */
function initDashboardAutoRefresh() {
    const dashboard = document.querySelector('.dashboard');
    if (!dashboard) return;
    
    setInterval(function() {
        fetch('/admin/api/system-stats')
            .then(response => response.json())
            .then(data => {
                // Обновление CPU
                const cpuEl = document.getElementById('cpu-percent');
                if (cpuEl && data.system && data.system.cpu) {
                    cpuEl.textContent = data.system.cpu.percent + '%';
                    updateProgressBar('cpu', data.system.cpu.percent);
                }
                
                // Обновление памяти
                const memoryEl = document.getElementById('memory-percent');
                if (memoryEl && data.system && data.system.memory) {
                    memoryEl.textContent = data.system.memory.percent + '%';
                    updateProgressBar('memory', data.system.memory.percent);
                }
                
                // Обновление диска
                const diskEl = document.getElementById('disk-percent');
                if (diskEl && data.system && data.system.disk) {
                    diskEl.textContent = data.system.disk.percent + '%';
                    updateProgressBar('disk', data.system.disk.percent);
                }
            })
            .catch(error => console.debug('Dashboard update failed:', error));
    }, 30000);
}

/**
 * Обновление progress bar
 */
function updateProgressBar(name, percent) {
    const bar = document.querySelector(`#${name}-bar .stat-bar-fill`);
    if (bar) {
        bar.style.width = percent + '%';
        
        // Обновление класса цвета
        bar.classList.remove('warning', 'danger');
        if (percent > 90) {
            bar.classList.add('danger');
        } else if (percent > 70) {
            bar.classList.add('warning');
        }
    }
}

/**
 * Валидация формы
 */
function validateForm(form) {
    const inputs = form.querySelectorAll('input[required], select[required], textarea[required]');
    let isValid = true;
    
    inputs.forEach(function(input) {
        if (!input.value.trim()) {
            input.classList.add('is-invalid');
            isValid = false;
        } else {
            input.classList.remove('is-invalid');
        }
    });
    
    return isValid;
}

/**
 * Проверка совпадения паролей
 */
function initPasswordMatch() {
    const password = document.getElementById('password') || document.getElementById('new_password');
    const password2 = document.getElementById('password2') || document.getElementById('new_password2');
    
    if (password && password2) {
        function checkMatch() {
            if (password2.value && password.value !== password2.value) {
                password2.setCustomValidity('Пароли не совпадают');
                password2.classList.add('is-invalid');
            } else {
                password2.setCustomValidity('');
                password2.classList.remove('is-invalid');
            }
        }
        
        password.addEventListener('input', checkMatch);
        password2.addEventListener('input', checkMatch);
    }
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    initPasswordMatch();
    initDashboardAutoRefresh();
});