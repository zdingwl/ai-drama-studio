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

export function projectLanguageLabel(value: string): string {
  const base = String(value || '').trim().split(/[-_]/)[0]?.toLowerCase() || ''
  return PROJECT_LANGUAGE_OPTIONS.find((option) => option.value === base)?.label || value || '—'
}

export function projectRegionLabel(value: string): string {
  const normalized = String(value || '').trim().toUpperCase()
  return PROJECT_REGION_OPTIONS.find((option) => option.value === normalized)?.label || value || '—'
}
