import { CheckCircle, CircleDashed, CircleNotch, WarningCircle, XCircle } from '@phosphor-icons/react'

const ICONS = {
  success: CheckCircle,
  warning: WarningCircle,
  danger: XCircle,
  processing: CircleNotch,
  queued: CircleDashed,
}

const CLASSES = {
  success: 'bg-success-soft text-success',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-danger-soft text-danger',
  processing: 'bg-accent-soft text-accent',
  queued: 'bg-border-soft text-ink-faint',
}

export default function StatusPill({ tone, label }) {
  const Icon = ICONS[tone]
  return (
    <span
      className={`inline-flex w-fit items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${CLASSES[tone]}`}
    >
      <Icon size={13} weight="bold" className={tone === 'processing' ? 'animate-spin' : undefined} />
      {label}
    </span>
  )
}
