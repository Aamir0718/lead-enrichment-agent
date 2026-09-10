import { motion, useReducedMotion } from 'motion/react'
import {
  ArrowSquareOut,
  EnvelopeSimple,
  Lightning,
  LinkedinLogo,
  WarningCircle,
} from '@phosphor-icons/react'
import PendingCard from './PendingCard'
import StatusPill from './StatusPill'
import { bareUrl, initials, statusMeta } from '../lib/format'

function FieldLabel({ children }) {
  return <span className="text-[11.5px] font-semibold tracking-wide text-ink-faint uppercase">{children}</span>
}

function Field({ label, children }) {
  return (
    <div className="flex flex-col gap-2">
      <FieldLabel>{label}</FieldLabel>
      {children}
    </div>
  )
}

function EmptyNote({ children }) {
  return <span className="text-[13.5px] text-ink-faint">{children}</span>
}

export default function ResultCard({ record, index }) {
  const reduceMotion = useReducedMotion()

  if (record.pending) {
    return <PendingCard record={record} index={index} reduceMotion={reduceMotion} />
  }

  const meta = statusMeta(record.status)
  const confidence = typeof record.confidence_score === 'number' ? record.confidence_score.toFixed(2) : '-'

  return (
    <motion.article
      className="rounded-[var(--radius-lg)] border border-border bg-surface p-7"
      initial={reduceMotion ? false : { opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.15 }}
      transition={{ duration: 0.5, delay: index * 0.06, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="mb-5 flex items-start justify-between gap-4">
        <div className="flex flex-col gap-2">
          <StatusPill tone={meta.tone} label={meta.label} />
          <h2 className="font-mono text-[19px] font-semibold tracking-tight text-ink">{record.domain}</h2>
        </div>
        {record.status !== 'failed' && (
          <div className="flex-shrink-0 text-right">
            <span className="block font-mono text-2xl font-semibold text-ink">{confidence}</span>
            <span className="text-xs text-ink-faint">confidence</span>
          </div>
        )}
      </div>

      {record.status === 'failed' ? (
        <p className="flex items-center gap-2 text-sm text-danger">
          <WarningCircle size={16} />
          {record.error || 'No data could be extracted for this domain.'}
        </p>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-8 md:grid-cols-[1.4fr_1fr]">
            <div className="flex flex-col gap-5">
              <p className="text-[15.5px] leading-relaxed text-ink">
                {record.company_overview || 'No overview extracted.'}
              </p>

              <Field label="Target audience">
                <p className="text-sm leading-relaxed text-ink-muted">
                  {record.target_audience || 'Not identified.'}
                </p>
              </Field>

              <Field label="Contact emails">
                {record.contact_emails?.length ? (
                  <div className="flex flex-wrap gap-2">
                    {record.contact_emails.map((email) => (
                      <a
                        key={email}
                        href={`mailto:${email}`}
                        className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-3 py-1.5 text-[13px] font-medium text-accent transition hover:-translate-y-px"
                      >
                        <EnvelopeSimple size={14} />
                        {email}
                      </a>
                    ))}
                  </div>
                ) : (
                  <EmptyNote>None found on public pages</EmptyNote>
                )}
              </Field>
            </div>

            <div className="flex flex-col gap-5 border-t border-border-soft pt-5 md:border-t-0 md:border-l md:pt-0 md:pl-7">
              <Field label="Leadership">
                {record.leadership?.length ? (
                  <ul className="flex flex-col gap-3">
                    {record.leadership.map((person) => (
                      <li key={person.name} className="flex items-center gap-2.5">
                        <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-accent-soft font-mono text-xs font-semibold text-accent">
                          {initials(person.name)}
                        </span>
                        <span className="min-w-0 flex-1 leading-tight">
                          <span className="block text-sm font-medium text-ink">{person.name}</span>
                          {person.role && <span className="block text-xs text-ink-faint">{person.role}</span>}
                        </span>
                        {person.linkedin_url && (
                          <a
                            href={person.linkedin_url}
                            target="_blank"
                            rel="noopener"
                            className="flex-shrink-0 text-ink-faint transition hover:text-accent"
                          >
                            <LinkedinLogo size={16} />
                          </a>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyNote>None identified from scraped pages</EmptyNote>
                )}
              </Field>

              <Field label="Pages scraped">
                <div className="flex flex-col gap-1.5">
                  {record.pages_scraped?.map((url) => (
                    <a
                      key={url}
                      href={url}
                      target="_blank"
                      rel="noopener"
                      className="flex items-center gap-1.5 truncate text-[13px] text-ink-muted transition hover:text-accent"
                    >
                      <ArrowSquareOut size={13} className="flex-shrink-0 text-ink-faint" />
                      <span className="truncate">{bareUrl(url)}</span>
                    </a>
                  ))}
                </div>
              </Field>

              <div className="flex items-center gap-1.5 text-[13px] text-ink-faint">
                <Lightning size={14} />
                {record.llm_calls_used ?? 0} LLM call{record.llm_calls_used === 1 ? '' : 's'}
              </div>
            </div>
          </div>

          {record.critique_notes?.length > 0 && (
            <div className="mt-5 border-t border-border-soft pt-5">
              <FieldLabel>Critique notes</FieldLabel>
              <ul className="mt-2 flex flex-col gap-1.5">
                {record.critique_notes.map((note) => (
                  <li
                    key={note}
                    className="relative pl-4 text-[13.5px] text-ink-muted before:absolute before:left-0 before:text-ink-faint before:content-['-']"
                  >
                    {note}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </motion.article>
  )
}
