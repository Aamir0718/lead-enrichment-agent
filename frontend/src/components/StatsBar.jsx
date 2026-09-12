export default function StatsBar({ stats }) {
  return (
    <section
      aria-label="Run summary"
      className="mb-14 grid grid-cols-1 divide-y divide-border-soft border-y border-border-soft md:grid-cols-5 md:divide-x md:divide-y-0"
    >
      {stats.map((stat) => (
        <div key={stat.label} className="flex flex-col gap-1.5 py-5 first:md:pl-0 md:px-5 md:py-7">
          <span className="font-mono text-[28px] font-semibold tracking-tight text-ink">{stat.value}</span>
          <span className="text-[13px] text-ink-faint">{stat.label}</span>
        </div>
      ))}
    </section>
  )
}
