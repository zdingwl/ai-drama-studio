export interface ProjectSelectOption {
  value: string
  label: string
  englishName: string
}

const LANGUAGE_CODES = [
  'af', 'sq', 'am', 'ar', 'hy', 'az', 'eu', 'be', 'bn', 'bs', 'bg', 'my', 'ca', 'zh',
  'hr', 'cs', 'da', 'nl', 'en', 'et', 'fi', 'fil', 'fr', 'gl', 'ka', 'de', 'el', 'gu',
  'he', 'hi', 'hu', 'is', 'id', 'ga', 'it', 'ja', 'kn', 'kk', 'km', 'ko', 'lo', 'lv',
  'lt', 'mk', 'ms', 'ml', 'mr', 'mn', 'ne', 'no', 'fa', 'pl', 'pt', 'pa', 'ro', 'ru',
  'sr', 'sk', 'sl', 'es', 'sw', 'sv', 'ta', 'te', 'th', 'tr', 'uk', 'ur', 'uz', 'vi',
] as const

// ISO 3166-1 sovereign-country/commonly used international region codes.
const REGION_CODES = [
  'AF', 'AL', 'DZ', 'AD', 'AO', 'AG', 'AR', 'AM', 'AU', 'AT', 'AZ', 'BS', 'BH', 'BD',
  'BB', 'BY', 'BE', 'BZ', 'BJ', 'BT', 'BO', 'BA', 'BW', 'BR', 'BN', 'BG', 'BF', 'BI',
  'CV', 'KH', 'CM', 'CA', 'CF', 'TD', 'CL', 'CN', 'CO', 'KM', 'CG', 'CD', 'CR', 'CI',
  'HR', 'CU', 'CY', 'CZ', 'DK', 'DJ', 'DM', 'DO', 'EC', 'EG', 'SV', 'GQ', 'ER', 'EE',
  'SZ', 'ET', 'FJ', 'FI', 'FR', 'GA', 'GM', 'GE', 'DE', 'GH', 'GR', 'GD', 'GT', 'GN',
  'GW', 'GY', 'HT', 'HN', 'HU', 'IS', 'IN', 'ID', 'IR', 'IQ', 'IE', 'IL', 'IT', 'JM',
  'JP', 'JO', 'KZ', 'KE', 'KI', 'KP', 'KR', 'KW', 'KG', 'LA', 'LV', 'LB', 'LS', 'LR',
  'LY', 'LI', 'LT', 'LU', 'MG', 'MW', 'MY', 'MV', 'ML', 'MT', 'MH', 'MR', 'MU', 'MX',
  'FM', 'MD', 'MC', 'MN', 'ME', 'MA', 'MZ', 'MM', 'NA', 'NR', 'NP', 'NL', 'NZ', 'NI',
  'NE', 'NG', 'MK', 'NO', 'OM', 'PK', 'PW', 'PA', 'PG', 'PY', 'PE', 'PH', 'PL', 'PT',
  'QA', 'RO', 'RU', 'RW', 'KN', 'LC', 'VC', 'WS', 'SM', 'ST', 'SA', 'SN', 'RS', 'SC',
  'SL', 'SG', 'SK', 'SI', 'SB', 'SO', 'ZA', 'SS', 'ES', 'LK', 'SD', 'SR', 'SE', 'CH',
  'SY', 'TW', 'TJ', 'TZ', 'TH', 'TL', 'TG', 'TO', 'TT', 'TN', 'TR', 'TM', 'TV', 'UG',
  'UA', 'AE', 'GB', 'US', 'UY', 'UZ', 'VU', 'VA', 'VE', 'VN', 'YE', 'ZM', 'ZW',
] as const

// 第一项是该语言的默认目标地区；展示时仍然按国家英文名 A-Z 排序。
// 这里按“该语言是官方语言或主流商业使用语言”的目标市场维护。
const REGION_CODES_BY_LANGUAGE: Record<(typeof LANGUAGE_CODES)[number], readonly string[]> = {
  af: ['ZA', 'NA'],
  sq: ['AL'],
  am: ['ET'],
  ar: ['SA', 'AE', 'EG', 'DZ', 'BH', 'TD', 'KM', 'DJ', 'ER', 'IQ', 'JO', 'KW', 'LB', 'LY', 'MR', 'MA', 'OM', 'QA', 'SO', 'SD', 'SY', 'TN', 'YE'],
  hy: ['AM'],
  az: ['AZ'],
  eu: ['ES'],
  be: ['BY'],
  bn: ['BD', 'IN'],
  bs: ['BA'],
  bg: ['BG'],
  my: ['MM'],
  ca: ['ES', 'AD'],
  zh: ['CN', 'SG', 'TW'],
  hr: ['HR', 'BA'],
  cs: ['CZ'],
  da: ['DK'],
  nl: ['NL', 'BE', 'SR'],
  en: ['US', 'GB', 'CA', 'AU', 'NZ', 'IE', 'SG', 'IN', 'PH', 'ZA', 'AG', 'BS', 'BB', 'BZ', 'BW', 'CM', 'DM', 'FJ', 'GM', 'GH', 'GD', 'GY', 'JM', 'KE', 'KI', 'LS', 'LR', 'MW', 'MT', 'MH', 'MU', 'FM', 'NA', 'NR', 'NG', 'PW', 'PG', 'RW', 'KN', 'LC', 'VC', 'WS', 'SC', 'SL', 'SB', 'SS', 'SZ', 'TZ', 'TO', 'TT', 'TV', 'UG', 'VU', 'ZM', 'ZW'],
  et: ['EE'],
  fi: ['FI'],
  fil: ['PH'],
  fr: ['FR', 'BE', 'CA', 'CH', 'LU', 'MC', 'BJ', 'BF', 'BI', 'CM', 'CF', 'TD', 'KM', 'CG', 'CD', 'CI', 'DJ', 'GQ', 'GA', 'GN', 'HT', 'MG', 'ML', 'NE', 'RW', 'SN', 'SC', 'TG', 'VU'],
  gl: ['ES'],
  ka: ['GE'],
  de: ['DE', 'AT', 'CH', 'LI', 'LU', 'BE'],
  el: ['GR', 'CY'],
  gu: ['IN'],
  he: ['IL'],
  hi: ['IN'],
  hu: ['HU'],
  is: ['IS'],
  id: ['ID'],
  ga: ['IE'],
  it: ['IT', 'CH', 'SM', 'VA'],
  ja: ['JP'],
  kn: ['IN'],
  kk: ['KZ'],
  km: ['KH'],
  ko: ['KR', 'KP'],
  lo: ['LA'],
  lv: ['LV'],
  lt: ['LT'],
  mk: ['MK'],
  ms: ['MY', 'BN', 'SG'],
  ml: ['IN'],
  mr: ['IN'],
  mn: ['MN'],
  ne: ['NP', 'IN'],
  no: ['NO'],
  fa: ['IR', 'AF'],
  pl: ['PL'],
  pt: ['BR', 'PT', 'AO', 'CV', 'GW', 'MZ', 'ST', 'TL'],
  pa: ['IN', 'PK'],
  ro: ['RO', 'MD'],
  ru: ['RU', 'BY', 'KZ', 'KG'],
  sr: ['RS', 'BA', 'ME'],
  sk: ['SK'],
  sl: ['SI'],
  es: ['ES', 'MX', 'AR', 'BO', 'CL', 'CO', 'CR', 'CU', 'DO', 'EC', 'SV', 'GQ', 'GT', 'HN', 'NI', 'PA', 'PY', 'PE', 'UY', 'VE'],
  sw: ['TZ', 'KE', 'UG', 'RW', 'CD'],
  sv: ['SE', 'FI'],
  ta: ['IN', 'LK', 'SG', 'MY'],
  te: ['IN'],
  th: ['TH'],
  tr: ['TR', 'CY'],
  uk: ['UA'],
  ur: ['PK', 'IN'],
  uz: ['UZ'],
  vi: ['VN'],
}

const zhLanguageNames = new Intl.DisplayNames(['zh-CN'], { type: 'language' })
const enLanguageNames = new Intl.DisplayNames(['en'], { type: 'language' })
const zhRegionNames = new Intl.DisplayNames(['zh-CN'], { type: 'region' })
const enRegionNames = new Intl.DisplayNames(['en'], { type: 'region' })

function buildOptions(
  codes: readonly string[],
  zhNames: Intl.DisplayNames,
  enNames: Intl.DisplayNames,
): ProjectSelectOption[] {
  return codes
    .map((value) => {
      const englishName = enNames.of(value) || value
      const chineseName = zhNames.of(value) || value
      return {
        value,
        englishName,
        label: `${chineseName}（${englishName}）`,
      }
    })
    .sort((left, right) => left.englishName.localeCompare(right.englishName, 'en'))
}

export const PROJECT_LANGUAGE_OPTIONS = buildOptions(
  LANGUAGE_CODES,
  zhLanguageNames,
  enLanguageNames,
)

export const PROJECT_REGION_OPTIONS = buildOptions(
  REGION_CODES,
  zhRegionNames,
  enRegionNames,
)

export function normalizeProjectLanguage(value: string): string {
  const base = String(value || '').trim().split(/[-_]/)[0]?.toLowerCase() || ''
  return PROJECT_LANGUAGE_OPTIONS.some((option) => option.value === base) ? base : 'zh'
}

export function normalizeProjectTargetLanguage(value: string): string {
  const base = String(value || '').trim().split(/[-_]/)[0]?.toLowerCase() || ''
  return PROJECT_LANGUAGE_OPTIONS.some((option) => option.value === base) ? base : 'en'
}

export function normalizeProjectRegion(value: string): string {
  const normalized = String(value || '').trim().toUpperCase()
  return PROJECT_REGION_OPTIONS.some((option) => option.value === normalized) ? normalized : 'US'
}

export function getProjectRegionOptionsForLanguage(language: string): ProjectSelectOption[] {
  const normalizedLanguage = normalizeProjectTargetLanguage(language) as (typeof LANGUAGE_CODES)[number]
  const allowedRegions = new Set(REGION_CODES_BY_LANGUAGE[normalizedLanguage])
  return PROJECT_REGION_OPTIONS.filter((option) => allowedRegions.has(option.value))
}

export function normalizeProjectRegionForLanguage(language: string, region: string): string {
  const normalizedLanguage = normalizeProjectTargetLanguage(language) as (typeof LANGUAGE_CODES)[number]
  const normalizedRegion = normalizeProjectRegion(region)
  const regionCodes = REGION_CODES_BY_LANGUAGE[normalizedLanguage]
  return regionCodes.includes(normalizedRegion) ? normalizedRegion : (regionCodes[0] || 'US')
}

export function projectLanguageLabel(value: string): string {
  const base = String(value || '').trim().split(/[-_]/)[0]?.toLowerCase() || ''
  return PROJECT_LANGUAGE_OPTIONS.find((option) => option.value === base)?.label || value || '—'
}

export function projectRegionLabel(value: string): string {
  const normalized = String(value || '').trim().toUpperCase()
  return PROJECT_REGION_OPTIONS.find((option) => option.value === normalized)?.label || value || '—'
}
