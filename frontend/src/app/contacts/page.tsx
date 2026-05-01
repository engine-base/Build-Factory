"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchContacts } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { User } from "lucide-react";

export default function ContactsPage() {
  const { data = [], isLoading } = useQuery({
    queryKey: ["contacts"],
    queryFn: () => fetchContacts(100),
  });

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold tracking-tight">コンタクト</h1>
        <p className="text-sm text-muted-foreground">{data.length}件</p>
      </div>
      <Card>
        <CardContent className="p-0">
          <ScrollArea className="h-[calc(100vh-180px)]">
            <div className="divide-y">
              {isLoading && <p className="p-4 text-sm text-muted-foreground">読み込み中...</p>}
              {data.map((c: Record<string, string>) => (
                <div key={c.id} className="flex items-start gap-3 p-4 hover:bg-muted/30">
                  <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <User className="w-4 h-4 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm">{c.name}</p>
                    <p className="text-xs text-muted-foreground">{c.company}</p>
                    {c.email && <p className="text-xs text-muted-foreground">{c.email}</p>}
                  </div>
                  {c.status && (
                    <Badge variant="secondary" className="text-[10px]">{c.status}</Badge>
                  )}
                </div>
              ))}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
