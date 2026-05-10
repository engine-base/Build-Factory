"use client";

import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const COLORS = ["#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd", "#ddd6fe"];
const STAGE_LABELS: Record<string, string> = {
  lead: "リード", contact: "接触", proposal: "提案", negotiation: "交渉",
};

const fmt = (v: number) =>
  v >= 1_000_000 ? `¥${(v / 1_000_000).toFixed(1)}M` :
  v >= 1_000 ? `¥${(v / 1_000).toFixed(0)}K` : `¥${v}`;

interface RevenueChartProps {
  data: Array<{ month: string; revenue: number }>;
}

export function RevenueChart({ data }: RevenueChartProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">売上推移（6ヶ月）</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={data}>
            <defs>
              <linearGradient id="revenue-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis dataKey="month" tick={{ fontSize: 11 }} />
            <YAxis tickFormatter={fmt} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => [fmt(Number(v)), "売上"]} />
            <Area type="monotone" dataKey="revenue" stroke="#6366f1" fill="url(#revenue-grad)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

interface PipelineChartProps {
  data: Array<{ stage: string; count: number; total: number }>;
}

export function PipelineChart({ data }: PipelineChartProps) {
  const labeled = data.map((d) => ({ ...d, name: STAGE_LABELS[d.stage] ?? d.stage }));
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">パイプライン分布</CardTitle>
      </CardHeader>
      <CardContent className="flex gap-4 items-center">
        <ResponsiveContainer width="55%" height={200}>
          <PieChart>
            <Pie data={labeled} dataKey="total" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name }) => name}>
              {labeled.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Pie>
            <Tooltip formatter={(v) => fmt(Number(v))} />
          </PieChart>
        </ResponsiveContainer>
        <div className="flex-1 space-y-2">
          {labeled.map((d, i) => (
            <div key={d.stage} className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: COLORS[i % COLORS.length] }} />
                {d.name}
              </span>
              <span className="font-medium">{fmt(d.total)}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

interface ExpensesChartProps {
  data: Array<{ category: string; total: number }>;
}

export function ExpensesChart({ data }: ExpensesChartProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">今月の経費（カテゴリ別）</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis type="number" tickFormatter={fmt} tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="category" tick={{ fontSize: 11 }} width={80} />
            <Tooltip formatter={(v) => [fmt(Number(v)), "金額"]} />
            <Bar dataKey="total" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
