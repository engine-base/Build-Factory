import { RecordsPanel } from "@/components/records/RecordsPanel";

export default function RecordsPage() {
  return (
    <div className="flex flex-col h-screen">
      <div className="px-6 py-4 border-b">
        <h1 className="text-xl font-bold tracking-tight">スキル出力</h1>
        <p className="text-sm text-muted-foreground">
          90スキルが生成したMarkdownファイルを閲覧・検索できます
        </p>
      </div>
      <div className="flex-1 overflow-hidden">
        <RecordsPanel />
      </div>
    </div>
  );
}
