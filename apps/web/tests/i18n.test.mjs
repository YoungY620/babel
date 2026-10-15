import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import i18next from 'i18next';

const en = JSON.parse(await readFile(new URL('../src/i18n/dict/en.json', import.meta.url), 'utf8'));
const zh = JSON.parse(await readFile(new URL('../src/i18n/dict/zh-CN.json', import.meta.url), 'utf8'));

test('both dictionaries cover the same UI messages and interpolate plural forms', async () => {
  const baseKeys = dictionary => [...new Set(Object.keys(dictionary).map(key => key.replace(/_(one|other)$/, '')))].sort();
  assert.deepEqual(baseKeys(en), baseKeys(zh));
  for (const dictionary of [en, zh]) assert.ok(Object.values(dictionary).every(value => typeof value === 'string' && value.trim()));
  const i18n = i18next.createInstance();
  await i18n.init({ lng: 'en', fallbackLng: false, keySeparator: false,
    resources: { en: { translation: en }, 'zh-CN': { translation: zh } }, interpolation: { escapeValue: false } });
  assert.equal(i18n.t('count.episodes', { count: 1 }), '1 episode');
  assert.equal(i18n.t('count.episodes', { count: 2 }), '2 episodes');
  await i18n.changeLanguage('zh-CN');
  assert.equal(i18n.t('count.episodes', { count: 2 }), '2 集');
  assert.equal(i18n.t('episode.play', { title: '从一个故事开始' }), '播放《从一个故事开始》');
});
