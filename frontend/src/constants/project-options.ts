/**
 * F01 新建项目允许选择的固定语言/地区选项。
 *
 * 业务作用：所有创建项目页面都从这里读取标准值，避免组件各自维护一套代码，
 * 也避免用户自由输入 `English`、`美国`、`usa` 等无法稳定用于后续流程的数据。
 *
 * 注意：这里的 value 是数据库和 project.json 真正保存的稳定代码；label 只用于界面展示。
 */
export interface ProjectOption {
  value: string
  label: string
}

export const SOURCE_LANGUAGE_OPTIONS: ProjectOption[] = [
  { value: '', label: '自动识别（暂不指定）' },
  { value: 'zh', label: '中文（zh）' },
  { value: 'en', label: '英语（en）' },
  { value: 'ja', label: '日语（ja）' },
  { value: 'ko', label: '韩语（ko）' },
  { value: 'es', label: '西班牙语（es）' },
  { value: 'pt', label: '葡萄牙语（pt）' },
  { value: 'fr', label: '法语（fr）' },
  { value: 'de', label: '德语（de）' },
  { value: 'id', label: '印尼语（id）' },
  { value: 'th', label: '泰语（th）' },
  { value: 'vi', label: '越南语（vi）' },
]

export const TARGET_LANGUAGE_OPTIONS: ProjectOption[] = SOURCE_LANGUAGE_OPTIONS.filter(
  (item) => item.value !== '',
)

export const TARGET_REGION_OPTIONS: ProjectOption[] = [
  { value: 'US', label: '美国（US）' },
  { value: 'GB', label: '英国（GB）' },
  { value: 'JP', label: '日本（JP）' },
  { value: 'KR', label: '韩国（KR）' },
  { value: 'ES', label: '西班牙（ES）' },
  { value: 'BR', label: '巴西（BR）' },
  { value: 'FR', label: '法国（FR）' },
  { value: 'DE', label: '德国（DE）' },
  { value: 'ID', label: '印度尼西亚（ID）' },
  { value: 'TH', label: '泰国（TH）' },
  { value: 'VN', label: '越南（VN）' },
  { value: 'TW', label: '中国台湾（TW）' },
  { value: 'SG', label: '新加坡（SG）' },
]
