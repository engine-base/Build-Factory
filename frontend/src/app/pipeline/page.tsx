"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchPipeline } from "@/lib/api";
import { PipelineTable } from "@/components/dashboard/PipelineTable";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function PipelinePage() {
  const { data = [], isLoading } = useQuery({
    queryKey: ["pipeline-full"],
    queryFn: () => fetchPipeline(100),
  });

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold tracking-tight">パイプライン</h1>
        <p className="text-sm text-muted-foreground">アクティブ案件一覧</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">全案件 ({data.length}件)</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <p className="p-4 text-sm text-muted-foreground">読み込み中...</p>
          ) : (
            <PipelineTable data={data} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
