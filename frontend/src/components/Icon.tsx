import type { CSSProperties, ReactNode } from 'react'

// Ícones SVG portados 1:1 do design DocWatch (Opção B). viewBox 0 0 24 24.
export type IconName =
  | 'logo' | 'doc' | 'docMini' | 'grid' | 'bolt' | 'sliders' | 'search'
  | 'sun' | 'moon' | 'bell' | 'eye' | 'download' | 'dots' | 'plus'
  | 'filter' | 'refresh' | 'folder' | 'arrowRight' | 'check' | 'checkSmall'
  | 'tableMini' | 'alert'

interface IconDef { body: ReactNode; sw?: number; fill?: boolean }

const ICONS: Record<IconName, IconDef> = {
  logo: { sw: 1.9, body: <><path d="M4 4h11l5 5v11a0 0 0 0 1 0 0H4z" /><path d="M14 4v5h5" /><path d="M8 13h8M8 17h5" /></> },
  doc: { sw: 1.7, body: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6M8 13h8M8 17h6" /></> },
  docMini: { sw: 1.6, body: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6" /></> },
  grid: { sw: 1.7, body: <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M9 21V9" /></> },
  bolt: { sw: 1.7, body: <path d="M13 2 4 14h7l-1 8 9-12h-7z" /> },
  sliders: { sw: 1.7, body: <><path d="M4 6h11M4 12h16M4 18h9" /><circle cx="18" cy="6" r="2" /><circle cx="9" cy="12" r="2" /><circle cx="16" cy="18" r="2" /></> },
  search: { sw: 1.8, body: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></> },
  sun: { sw: 1.8, body: <><circle cx="12" cy="12" r="4.2" /><path d="M12 2v2.5M12 19.5V22M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2 12h2.5M19.5 12H22M4.2 19.8 6 18M18 6l1.8-1.8" /></> },
  moon: { sw: 1.8, body: <path d="M20 14.5A8 8 0 0 1 9.5 4a7 7 0 1 0 10.5 10.5z" /> },
  bell: { sw: 1.8, body: <><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></> },
  eye: { sw: 1.7, body: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" /><circle cx="12" cy="12" r="3" /></> },
  download: { sw: 1.7, body: <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 21h16" /> },
  dots: { fill: true, body: <><circle cx="12" cy="5" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="12" cy="19" r="1.6" /></> },
  plus: { sw: 2, body: <path d="M12 5v14M5 12h14" /> },
  filter: { sw: 1.8, body: <path d="M3 5h18M6 12h12M10 19h4" /> },
  refresh: { sw: 2, body: <path d="M21 12a9 9 0 1 1-2.6-6.4M21 4v5h-5" /> },
  folder: { sw: 1.7, body: <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /> },
  arrowRight: { sw: 1.8, body: <path d="M5 12h14M13 6l6 6-6 6" /> },
  check: { sw: 3.2, body: <path d="M20 6 9 17l-5-5" /> },
  checkSmall: { sw: 1.8, body: <path d="m4 12 5 5L20 6" /> },
  tableMini: { sw: 1.8, body: <><path d="M4 4h16v16H4z" /><path d="M4 9h16" /></> },
  alert: { sw: 1.8, body: <><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></> },
}

interface IconProps {
  name: IconName
  size?: number
  sw?: number
  stroke?: string
  className?: string
  style?: CSSProperties
}

export function Icon({ name, size = 18, sw, stroke = 'currentColor', className, style }: IconProps) {
  const def = ICONS[name]
  const isFill = !!def.fill
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      className={className}
      style={style}
      fill={isFill ? 'currentColor' : 'none'}
      stroke={isFill ? 'none' : stroke}
      strokeWidth={sw ?? def.sw}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {def.body}
    </svg>
  )
}
