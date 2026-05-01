"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchKpi, fetchRevenueTrend, fetchPipelineByStage,
  fetchPipeline, fetchExpenses,
} from "@/lib/api";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { RevenueChart, PipelineChart, ExpensesChart } from "@/components/dashboard/Charts";
import { PipelineTable } from "@/components/dashboard/PipelineTable";
import { SkillActivity } from "@/components/dashboard/SkillActivity";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { TrendingUp, Wallet, CheckSquare, Users, Trophy } from "lucide-react";

const fmt = (v: number) =>
  v >= 1_000_000 ? `¥${(v / 1_000_000).toFixed(1)}M` :
  v >= 1_000 ? `¥${(v / 1_000).toFixed(0)}K` : `¥${v}`;

export default function DashboardPage() {
  const { data: kpi } = useQuery({ queryKey: ["kpi"], queryFn: fetchKpi, refetchInterval: 60_000 });
  const { data: revenue = [] } = useQuery({ queryKey: ["revenue"], queryFn: fetchRevenueTrend });
  const { data: pipelineStage = [] } = useQuery({ queryKey: ["pipelineStage"], queryFn: fetchPipelineByStage });
  const { data: pipeline = [] } = useQuery({ queryKey: ["pipeline"], queryFn: () => fetchPipeline(20) });
  const { data: expenses = [] } = useQuery({ queryKey: ["expenses"], queryFn: fetchExpenses });

  const today = new Date().toLocaleDateString("ja-JP", { year: "numeric", month: "long", day: "numeric", weekday: "short" });

  return (
    <div className="p-6 space-y-6 max-w-[1400px]">
      <div>
        <h1 className="text-xl font-bold tracking-tight">ダッシュボード</h1>
        <p className="text-sm text-muted-foreground">{today}</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title="今月売上"
          value={kpi ? fmt(kpi.revenue_month) : "—"}
          sub={kpi ? `利益 ${fmt(kpi.profit_month)}` : ""}
          icon={Wallet}
          trend={kpi?.profit_month > 0 ? "up" : "neutral"}
        />
        <KpiCard
          title="パイプライン"
          value={kpi ? `${kpi.pipeline_count}件` : "—"}
          sub={kpi ? `加重 ${fmt(kpi.pipeline_weighted)}` : ""}
          icon={TrendingUp}
        />
        <KpiCard
          title="今月受注"
          value={kpi ? `${kpi.won_count}件` : "—"}
          sub={kpi ? fmt(kpi.won_amount) : ""}
          icon={Trophy}
          trend="up"
        />
        <KpiCard
          title="タスク / コンタクト"
          value={kpi ? `${kpi.active_tasks} / ${kpi.contacts}` : "—"}
          sub="未完了タスク / 総コンタクト数"
          icon={CheckSquare}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <RevenueChart data={revenue} />
        </div>
        <PipelineChart data={pipelineStage} />
      </div>

      {/* Pipeline table + Expenses */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-sm font-medium">アクティブ案件</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <PipelineTable data={pipeline} />
          </CardContent>
        </Card>
        <ExpensesChart data={expenses} />
      </div>

      <Separator />

      {/* Skill Activity — all 90 skills */}
      <div>
        <h2 className="text-base font-semibold mb-4">スキル出力 — 全カテゴリ</h2>
        <SkillActivity />
      </div>
    </div>
  );
}
