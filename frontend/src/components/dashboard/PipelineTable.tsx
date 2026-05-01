"use client";

import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

const STAGE_MAP: Record<string, { label: string; color: string }> = {
  lead: { label: "リード", color: "bg-slate-100 text-slate-700" },
  contact: { label: "接触", color: "bg-blue-100 text-blue-700" },
  proposal: { label: "提案", color: "bg-yellow-100 text-yellow-700" },
  negotiation: { label: "交渉", color: "bg-orange-100 text-orange-700" },
};

const fmt = (v: number) =>
  v >= 1_000_000 ? `¥${(v / 1_000_000).toFixed(1)}M` :
  v >= 1_000 ? `¥${(v / 1_000).toFixed(0)}K` : `¥${v}`;

interface Deal {
  id: number;
  client: string;
  project: string;
  stage: string;
  amount: number;
  probability: number;
  next_action: string;
  next_action_date: string;
}

export function PipelineTable({ data }: { data: Deal[] }) {
  return (
    <ScrollArea className="h-72">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-xs text-muted-foreground">
            <th className="text-left py-2 px-3 font-medium">クライアント</th>
            <th className="text-left py-2 px-3 font-medium">ステージ</th>
            <th className="text-right py-2 px-3 font-medium">金額</th>
            <th className="text-right py-2 px-3 font-medium">確度</th>
            <th className="text-left py-2 px-3 font-medium">次のアクション</th>
          </tr>
        </thead>
        <tbody>
          {data.map((d) => {
            const stage = STAGE_MAP[d.stage] ?? { label: d.stage, color: "bg-gray-100 text-gray-700" };
            return (
              <tr key={d.id} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                <td className="py-2 px-3">
                  <p className="font-medium">{d.client}</p>
                  <p className="text-[11px] text-muted-foreground truncate max-w-[160px]">{d.project}</p>
                </td>
                <td className="py-2 px-3">
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-[11px] font-medium ${stage.color}`}>
                    {stage.label}
                  </span>
                </td>
                <td className="py-2 px-3 text-right font-medium">{fmt(d.amount)}</td>
                <td className="py-2 px-3 text-right">
                  <span className={`text-[11px] font-medium ${d.probability >= 70 ? "text-emerald-600" : d.probability >= 40 ? "text-yellow-600" : "text-muted-foreground"}`}>
                    {d.probability}%
                  </span>
                </td>
                <td className="py-2 px-3">
                  <p className="text-[11px] truncate max-w-[180px]">{d.next_action}</p>
                  {d.next_action_date && (
                    <p className="text-[10px] text-muted-foreground">{d.next_action_date}</p>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </ScrollArea>
  );
}
