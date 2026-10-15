import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import zh from "./dict/zh-CN.json";
import en from "./dict/en.json";
import type { Locale } from "@babel/catalog";

export function readPreference(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
export function savePreference(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* Private browsing still works. */
  }
}
const saved = readPreference("babel-language");
const language: Locale =
  saved === "en" || saved === "zh-CN"
    ? saved
    : navigator.language.startsWith("zh")
      ? "zh-CN"
      : "en";
void i18n.use(initReactI18next).init({
  lng: language,
  supportedLngs: ["zh-CN", "en"],
  fallbackLng: false,
  keySeparator: false,
  resources: { "zh-CN": { translation: zh }, en: { translation: en } },
  interpolation: { escapeValue: false },
});
export default i18n;
