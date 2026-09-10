import { DownloadSimple, GithubLogo } from '@phosphor-icons/react'

const REPO_URL = 'https://github.com/Aamir0718/lead-enrichment-agent'

export default function Header({ onDownload, downloadDisabled }) {
  return (
    <header className="border-b border-border-soft">
      <div className="mx-auto flex max-w-[1100px] flex-wrap items-center justify-between gap-4 px-6 py-5">
        <div className="flex items-center gap-3">
          <span className="flex h-[38px] w-[38px] items-center justify-center rounded-[10px] bg-accent font-mono text-[13px] font-semibold text-white">
            LE
          </span>
          <div className="flex flex-col leading-tight">
            <span className="text-[15px] font-semibold text-ink">Lead Enrichment Agent</span>
            <span className="text-[13px] text-ink-faint">Autonomous company intelligence pipeline</span>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={onDownload}
            disabled={downloadDisabled}
            className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-4 py-2.5 text-sm font-medium text-accent transition hover:border-accent active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-border"
          >
            <DownloadSimple size={16} />
            Download JSON
          </button>
          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener"
            className="inline-flex items-center gap-2 rounded-full bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-90 active:scale-[0.98]"
          >
            <GithubLogo size={16} />
            View repository
          </a>
        </div>
      </div>
    </header>
  )
}
