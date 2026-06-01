import { PieChart, Pie, Cell } from 'recharts'

interface WinProbGaugeProps {
  winProb: number
  label?: string
}

export default function WinProbGauge({ winProb, label }: WinProbGaugeProps) {
  const pct = winProb * 100
  const color = pct >= 70 ? '#16a34a' : pct >= 40 ? '#d97706' : '#dc2626'
  const data = [{ value: pct }, { value: 100 - pct }]

  return (
    <div className="relative flex flex-col items-center">
      <PieChart width={200} height={115}>
        <Pie
          data={data}
          cx={100}
          cy={105}
          startAngle={180}
          endAngle={0}
          innerRadius={55}
          outerRadius={90}
          dataKey="value"
          strokeWidth={0}
        >
          <Cell fill={color} />
          <Cell fill="#e2e8f0" />
        </Pie>
      </PieChart>
      <div className="absolute bottom-0 text-center">
        <div className="text-3xl font-bold font-mono" style={{ color }}>
          {pct.toFixed(1)}%
        </div>
        {label && <div className="text-xs text-muted-foreground mt-0.5">{label}</div>}
      </div>
    </div>
  )
}
