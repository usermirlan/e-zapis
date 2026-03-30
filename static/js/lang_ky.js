/**
 * Client-Side i18n implementation for Kyrgyz language
 * Enables instant language switching without page reloads.
 */

const translations = {
    // Навбар
    "Главная": "Башкы бет",
    "Услуги": "Кызматтар",
    "Врачи": "Дарыгерлер",
    "Мои записи": "Менин жазууларым",
    "Профиль": "Профиль",
    "Кабинет врача": "Дарыгердин кабинети",
    "Панель сотрудника": "Кызматкердин панели",
    "Админ-панель": "Админ-панель",
    "Выйти": "Чыгуу",
    "Войти": "Кирүү",
    "Регистрация": "Каттоо",
    "Я — врач": "Мен — дарыгермин",
    
    // Главная страница - Hero
    "Ваше здоровье — наша главная ценность": "Сиздин ден соолугуңуз — биздин башкы баалуулугубуз",
    "Запишитесь к лучшим специалистам онлайн, без очередей и ожидания. Ваша поликлиника теперь в вашем смартфоне.": "Мыкты адистерге кезексиз жана күтүүсүз онлайн жазылыңыз. Сиздин бейтапкана эми смартфонуңузда.",
    "Записаться к врачу": "Дарыгерге жазылуу",
    "Как это работает?": "Бул кантип иштейт?",
    "Выберите специалиста": "Адисти тандаңыз",
    "Найдите нужного врача в списке": "Тизмеден керектүү дарыгерди табыңыз",
    "Выберите время": "Убакытты тандаңыз",
    "Удобная дата и слот в календаре": "Календардан ыңгайлуу датаны жана убакытты тандаңыз",
    "Подтвердите запись": "Жазууну ырастаңыз",
    "Получите электронный талон": "Электрондук талонду алыңыз",
    
    // Вход / Регистрация
    "Вход в систему": "Системага кирүү",
    "Войдите для записи к врачу": "Дарыгерге жазылуу үчүн кириңиз",
    "Зарегистрируйтесь для записи к врачу онлайн": "Онлайн жазылуу үчүн катталыңыз",
    "Или войти через": "Же муну менен кириңиз:",
    "Или через": "Же муну менен:",
    "Зарегистрироваться через Google": "Google аркылуу каттоо",
    "Создать аккаунт": "Аккаунт түзүү",
    "Зарегистрироваться": "Каттоо",
    "Нет аккаунта?": "Аккаунтуңуз жокпу?",
    "Уже есть аккаунт?": "Аккаунтуңуз барбы?",
    "Забыли пароль?": "Сырсөздү унуттуңузбу?",
    
    // Подвал
    "О Проекте": "Долбоор жөнүндө",
    "Современная система онлайн-записи. Экономим ваше время и заботимся о здоровье.": "Заманбап онлайн-жазылуу системасы. Убактыңызды үнөмдөп, ден соолугуңузга кам көрөбүз.",
    "Пациентам": "Бейтаптарга",
    "Все врачи": "Бардык дарыгерлер",
    "Контакты": "Байланыштар",
    "Помощь": "Жардам",
    "Техподдержка": "Техникалык колдоо",
    "Частые вопросы": "Көп берилүүчү суроолор"
};

class LanguageManager {
    constructor() {
        this.currentLang = localStorage.getItem('language') || 'ru';
        this.cache = new Map(); // Stores original Russian text
        this.init();
    }

    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.bindElements();
            this.applyLanguage();
            this.updateButtonUI();
        });
    }

    // Collect all elements with data-i18n attribute OR just text content to translate
    bindElements() {
        // Find explicitly marked elements
        const elements = document.querySelectorAll('[data-i18n]');
        elements.forEach(el => {
            if (!this.cache.has(el)) {
                this.cache.set(el, el.textContent.trim());
            }
        });
        
        // Also auto-bind some common selectors if they don't have data-i18n
        const autoSelectors = ['.nav-link', '.btn', 'h1', 'h2', 'h3', 'p', '.footer-link'];
        autoSelectors.forEach(selector => {
            document.querySelectorAll(selector).forEach(el => {
                // Ignore elements with children (except icons) to avoid breaking HTML structure
                if (el.children.length === 0 || (el.children.length === 1 && el.children[0].tagName === 'I')) {
                    const textNode = this.getTextNode(el);
                    if (textNode && textNode.nodeValue.trim().length > 0) {
                        el.setAttribute('data-i18n', 'auto');
                        this.cache.set(textNode, textNode.nodeValue.trim());
                    }
                }
            });
        });
    }

    getTextNode(element) {
        let textNode = null;
        for (let i = 0; i < element.childNodes.length; i++) {
            if (element.childNodes[i].nodeType === Node.TEXT_NODE && element.childNodes[i].nodeValue.trim() !== '') {
                textNode = element.childNodes[i];
                break;
            }
        }
        return textNode;
    }

    toggle() {
        this.currentLang = this.currentLang === 'ru' ? 'ky' : 'ru';
        localStorage.setItem('language', this.currentLang);
        this.applyLanguage();
        this.updateButtonUI();
    }

    applyLanguage() {
        if (this.currentLang === 'ru') {
            // Restore original text
            for (let [node, originalText] of this.cache.entries()) {
                if (node.nodeType === Node.TEXT_NODE) {
                    node.nodeValue = ` ${originalText} `;
                } else {
                    // Update text content while preserving child icons
                    this.updateRichElement(node, originalText);
                }
            }
        } else {
            // Translate to Kyrgyz
            for (let [node, originalText] of this.cache.entries()) {
                const translated = translations[originalText];
                if (translated) {
                    if (node.nodeType === Node.TEXT_NODE) {
                        node.nodeValue = ` ${translated} `;
                    } else {
                        this.updateRichElement(node, translated);
                    }
                }
            }
        }
    }

    updateRichElement(element, newText) {
        // If element has an icon, preserve it
        const icon = element.querySelector('i.bi');
        if (icon) {
            element.innerHTML = '';
            element.appendChild(icon);
            element.appendChild(document.createTextNode(` ${newText}`));
        } else {
            element.textContent = newText;
        }
    }

    updateButtonUI() {
        const btnCurrent = document.getElementById('langCurrent');
        const btnOther = document.getElementById('langOther');
        
        if (!btnCurrent || !btnOther) return;

        if (this.currentLang === 'ru') {
            btnCurrent.textContent = 'RU';
            btnCurrent.className = 'text-white fw-bold';
            btnOther.textContent = 'КЫ';
            btnOther.className = 'text-white-50';
        } else {
            btnCurrent.textContent = 'КЫ';
            btnCurrent.className = 'text-white fw-bold';
            btnOther.textContent = 'RU';
            btnOther.className = 'text-white-50';
        }
    }
}

// Instantiate globally
window.langManager = new LanguageManager();
