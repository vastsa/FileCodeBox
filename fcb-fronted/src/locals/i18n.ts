import { createI18n } from 'vue-i18n' //引入vue-i18n组件
import messages from './index'
let language = (
  navigator.language || 'zh_cn'
).toLowerCase().replace(/-/, '_');
if (['zh','zh_cn','en','es','zh_tw'].indexOf(language) === -1) {
  language = 'zh_cn'
}
const lang = (localStorage.getItem('language') || language);
const i18n = createI18n({
  silentTranslationWarn: true,
  globalInjection: true,
  legacy: false,
  locale: lang,
  messages,
});

export default i18n
