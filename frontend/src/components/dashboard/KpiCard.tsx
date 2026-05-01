"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface KpiCardProps {
  title: string;
  value: string | number;
  sub?: string;
  icon: LucideIcon;
  trend?: "up" | "down" | "neutral";
  className?: string;
}

export function KpiCard({ title, value, sub, icon: Icon, trend, className }: KpiCardProps) {
  return (
    <Card className={cn("hover:shadow-md transition-shadow", className)}>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        <div className="p-2 rounded-lg bg-primary/10">
          <Icon className="w-4 h-4 text-primary" />
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-bold tracking-tight">{value}</p>
        {sub && (
          <p className={cn(
            "text-xs mt-1",
            trend === "up" && "text-emerald-600",
            trend === "down" && "text-red-500",
            trend === "neutral" && "text-muted-foreground",
            !trend && "text-muted-foreground"
          )}>
            {sub}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
