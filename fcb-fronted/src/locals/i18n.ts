import { createI18n } from 'vue-i18n' //引入vue-i18n组件
import messages from './index'
const language = (
  navigator.language  || 'zh'
).toLowerCase();

const lang = localStorage.getItem('language') || language

const i18n = createI18n({
  silentTranslationWarn: true,
  globalInjection: true,
  legacy: false,
  locale: lang,
  messages,
});

export default i18n
