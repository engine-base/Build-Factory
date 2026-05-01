import { ChatPanel } from "@/components/chat/ChatPanel";

export default function ChatPage() {
  return (
    <div className="flex flex-col h-screen">
      <div className="px-6 py-4 border-b">
        <h1 className="text-xl font-bold tracking-tight">AIチャット</h1>
        <p className="text-sm text-muted-foreground">
          company.db・スキル出力ファイルを参照してデータドリブンに回答します
        </p>
      </div>
      <div className="flex-1 overflow-hidden">
        <ChatPanel mode="secretary" />
      </div>
    </div>
  );
}
