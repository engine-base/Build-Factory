"use client";

// T-006-04: タスク分解 UI (POST /api/task-decomposition/decompose 呼出 + EARS AC 表示).
//
// 設計 (AC-1 UBIQUITOUS):
//   - shadcn/ui Button / Card / Input / Textarea / Badge (no @heroicons / no emoji)
//   - Lucide icons (CLAUDE.md §5.1 / lucide-react)
//   - cn() from @/lib/utils
//
// AC-2 EVENT-DRIVEN: 送信時 loading state / response の config.backend_used 表示
// AC-3 STATE-DRIVEN: subtask_count を [1, 20] (min/max) で client validate /
//                    submit 中は button disabled / local state のみ
// AC-4 UNWANTED: 空 / 2000 chars 超 → client-side validation で API 呼ばない /
//                backend 4xx は detail.code + message を verbatim 表示

import * as React from "react";
import { Loader2, Sparkles, AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import {
  decomposeTask,
  TaskDecompositionError,
  type AcType,
  type DecomposeResponse,
} from "@/lib/api/task-decomposition";

// Mirrors backend/services/task_decomposition.py constants.
export const MIN_BRIEF_CHARS = 5;
export const MAX_BRIEF_CHARS = 2000;
export const MIN_SUBTASK_COUNT = 1;
export const MAX_SUBTASK_COUNT = 20;
export const DEFAULT_SUBTASK_COUNT = 5;

interface FormState {
  parent_brief: string;
  subtask_count: number;
  use_backend: boolean;
}

interface UiError {
  code: string;
  message: string;
}

const AC_TYPE_VARIANT: Record<AcType, "default" | "secondary" | "outline"> = {
  UBIQUITOUS: "default",
  "EVENT-DRIVEN": "secondary",
  "STATE-DRIVEN": "secondary",
  OPTIONAL: "outline",
  UNWANTED: "default",
};

export interface TaskDecomposeFormProps {
  className?: string;
  apiBase?: string;
  defaultBrief?: string;
}

export function TaskDecomposeForm({
  className,
  apiBase,
  defaultBrief = "",
}: TaskDecomposeFormProps) {
  const [form, setForm] = React.useState<FormState>({
    parent_brief: defaultBrief,
    subtask_count: DEFAULT_SUBTASK_COUNT,
    use_backend: true,
  });
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<UiError | null>(null);
  const [result, setResult] = React.useState<DecomposeResponse | null>(null);

  function validate(brief: string): UiError | null {
    const trimmed = brief.trim();
    if (trimmed.length < MIN_BRIEF_CHARS) {
      return {
        code: "task_decomposition.invalid_input",
        message: `parent_brief must be >= ${MIN_BRIEF_CHARS} chars`,
      };
    }
    if (trimmed.length > MAX_BRIEF_CHARS) {
      return {
        code: "task_decomposition.invalid_input",
        message: `parent_brief must be <= ${MAX_BRIEF_CHARS} chars`,
      };
    }
    return null;
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setResult(null);
    const validationError = validate(form.parent_brief);
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const resp = await decomposeTask(
        {
          parent_brief: form.parent_brief.trim(),
          subtask_count: form.subtask_count,
          use_backend: form.use_backend,
        },
        { apiBase },
      );
      setResult(resp);
    } catch (e) {
      if (e instanceof TaskDecompositionError) {
        setError({ code: e.code, message: e.message });
      } else {
        setError({
          code: "task_decomposition.network_error",
          message:
            e instanceof Error
              ? e.message
              : "unexpected error contacting the API",
        });
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={cn("flex flex-col gap-6", className)}>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="size-4" aria-hidden="true" />
            タスク分解 (Task Decomposition)
          </CardTitle>
          <CardDescription>
            親 brief を sub-task 群に分解し、各 sub-task に EARS 形式の
            受入基準 (AC) を付与します。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-4"
            onSubmit={handleSubmit}
            aria-label="task decompose form"
          >
            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">親 brief</span>
              <Textarea
                value={form.parent_brief}
                onChange={(e) =>
                  setForm((f) => ({ ...f, parent_brief: e.target.value }))
                }
                placeholder="例: ユーザー認証機能を実装"
                minLength={MIN_BRIEF_CHARS}
                maxLength={MAX_BRIEF_CHARS}
                required
                rows={3}
                aria-describedby="brief-help"
              />
              <span id="brief-help" className="text-xs text-muted-foreground">
                {MIN_BRIEF_CHARS} 〜 {MAX_BRIEF_CHARS} 文字
              </span>
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">sub-task 数</span>
              <Input
                type="number"
                min={MIN_SUBTASK_COUNT}
                max={MAX_SUBTASK_COUNT}
                value={form.subtask_count}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    subtask_count: Math.max(
                      MIN_SUBTASK_COUNT,
                      Math.min(MAX_SUBTASK_COUNT, Number(e.target.value) || 1),
                    ),
                  }))
                }
                required
              />
            </label>

            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.use_backend}
                onChange={(e) =>
                  setForm((f) => ({ ...f, use_backend: e.target.checked }))
                }
              />
              <span className="text-sm">AI backend (登録時) を使う</span>
            </label>

            <div>
              <Button type="submit" disabled={loading}>
                {loading ? (
                  <>
                    <Loader2
                      className="size-4 animate-spin"
                      aria-hidden="true"
                    />
                    分解中…
                  </>
                ) : (
                  "分解する"
                )}
              </Button>
            </div>
          </form>

          {error && (
            <div
              role="alert"
              className="mt-4 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
            >
              <AlertTriangle
                className="size-4 mt-0.5"
                aria-hidden="true"
              />
              <div>
                <div className="font-mono text-xs">{error.code}</div>
                <div>{error.message}</div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {result && (
        <Card aria-label="decompose result">
          <CardHeader>
            <CardTitle className="text-sm">
              結果: {result.config.count_returned} sub-task
            </CardTitle>
            <CardDescription>
              backend_used: {result.config.backend_used ? "true" : "false"} /
              count_requested: {result.config.count_requested}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-4">
              {result.subtasks.map((s, i) => (
                <li key={i} className="rounded-md border p-3">
                  <div className="text-sm font-semibold">
                    {i + 1}. {s.title}
                  </div>
                  <ul className="mt-2 flex flex-col gap-2">
                    {s.acceptance_criteria.map((ac, j) => (
                      <li key={j} className="text-xs">
                        <Badge
                          variant={AC_TYPE_VARIANT[ac.type] ?? "outline"}
                          className="mr-2"
                        >
                          {ac.type}
                        </Badge>
                        <span>{ac.text}</span>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
