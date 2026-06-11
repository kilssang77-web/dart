import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList } from 'recharts'

export interface StrategyEntry {
  name: string
  winProb: number
  rate: number
  isSelected: boolean
}

interface StrategyCompareChartProps {
  strategies: StrategyEntry[]
}

export default function StrategyCompareChart({ strategies }: StrategyCompareChartProps) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart
        layout="vertical"
        data={strategies}
        margin={{ top: 4, right: 60, bottom: 4, left: 60 }}
        barSize={26}
      >
        <XAxis
          type="number"
          domain={[0, 100]}
          unit="%"
          tick={{ fontSize: 12 }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          type="category"
          dataKey="name"
          tick={{ fontSize: 12 }}
          width={64}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          formatter={(v: number) => [`${v.toFixed(1)}%`, '낙찰 확률']}
          cursor={{ fill: '#f1f5f9' }}
        />
        <Bar dataKey="winProb" name="낙찰확률" radius={[0, 4, 4, 0]}>
          {strategies.map((s, i) => (
            <Cell key={i} fill={s.isSelected ? '#2563eb' : s.winProb === 0 ? '#e2e8f0' : '#93c5fd'} />
          ))}
          <LabelList
            dataKey="rate"
            position="right"
            formatter={(v: number) => `${(v * 100).toFixed(2)}%`}
            style={{ fontSize: 12, fill: '#64748b' }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
