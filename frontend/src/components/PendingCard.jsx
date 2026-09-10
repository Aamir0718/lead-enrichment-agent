import { motion } from 'motion/react'
import StatusPill from './StatusPill'

export default function PendingCard({ record, index, reduceMotion }) {
  return (
    <motion.article
      className="rounded-[var(--radius-lg)] border border-border bg-surface p-7"
      initial={reduceMotion ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.05, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="mb-6 flex items-center gap-3">
        <StatusPill tone={record.tone} label={record.label} />
        <h2 className="font-mono text-[19px] font-semibold tracking-tight text-ink-faint">{record.domain}</h2>
      </div>
      <div className="flex flex-col gap-3">
        <div className="h-4 w-4/5 animate-pulse rounded bg-border-soft" />
        <div className="h-4 w-3/5 animate-pulse rounded bg-border-soft" />
        <div className="h-4 w-2/5 animate-pulse rounded bg-border-soft" />
      </div>
    </motion.article>
  )
}
