"use client";

/**
 * T-V3-C-14 / S-038: スキルマネージャ (Skill Manager) page.
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/ai/S-038-skill-manager.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-038
 * @feature-id F-002,F-003
 * @task-ids T-V3-C-14
 * @entities E-035
 * @phase Phase 1B
 *
 * 3-tier AC mapping:
 *   structural.AC-S1 (data-screen-id="S-038")               — root <main> element.
 *   structural.AC-S2 (h1 text "スキルマネージャ")          — <h1> in the header band.
 *   functional.AC-F1 (GET  /api/skills via typed client)    — listQuery in this file.
 *   functional.AC-F2 (POST /api/skills via typed client)    — createMutation in this file.
 *   functional.AC-F3 (POST /api/skills/{id}/test)           — testMutation in this file.
 *   functional.AC-F4 (POST /api/skills/{id}/archive)        — archiveMutation in this file.
 *   functional.AC-F5 (4xx/5xx → non-technical toast w/ endpoint, no stack) — error handlers.
 *   functional.AC-F6 (GET /api/skills?category=ai → non-archived rows)     — listQuery params.
 *   functional.AC-F7 (POST archive sets archived_at + excludes from AI list) — backend AC.
 *   functional.AC-F8 (non-owner POST → 403)                 — surface SkillsApiError(403).
 *   functional.AC-F9 (>10 test/min → 429)                   — surface SkillsApiError(429).
 */

import * as React from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Archive,
  Edit3,
  PlayCircle,
  Plus,
  Search,
  Sparkles,
  Wrench,
  X,
} from "lucide-react";

import {
  archiveSkill,
  createSkill,
  listSkills,
  SkillsApiError,
  testSkill,
  type Skill,
} from "@/api/skills";

// --------------------------------------------------------------------------
// Constants
// --------------------------------------------------------------------------

/** Filter chips shown in the S-038 mock (category dropdown + active/archive toggle). */
const CATEGORY_FILTERS: readonly { id: string; label: string }[] = [
  { id: "all", label: "全カテゴリ" },
  { id: "spec", label: "spec" },
  { id: "impl", label: "impl" },
  { id: "review", label: "review" },
  { id: "ops", label: "ops" },
  { id: "ai", label: "ai" },
];

const SKILLS_QUERY_KEY = ["skills", "list"] as const;

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

function reportSkillsError(err: unknown): void {
  if (err instanceof SkillsApiError) {
    toast.error(err.toUserMessage());
    return;
  }
  toast.error("通信に失敗しました。時間をおいて再試行してください");
}

function isArchived(skill: Skill): boolean {
  return Boolean(skill.archived_at);
}

function filterSkills(
  skills: readonly Skill[],
  category: string,
  showArchived: boolean,
  search: string,
): Skill[] {
  const q = search.trim().toLowerCase();
  return skills.filter((s) => {
    if (!showArchived && isArchived(s)) return false;
    if (showArchived && !isArchived(s)) return false;
    if (category !== "all" && s.category !== category) return false;
    if (q) {
      const hay = `${s.name} ${s.display_name ?? ""} ${s.description ?? ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export default function SkillManagerPage(): React.JSX.Element {
  const qc = useQueryClient();

  const [category, setCategory] = React.useState<string>("all");
  const [showArchived, setShowArchived] = React.useState<boolean>(false);
  const [search, setSearch] = React.useState<string>("");
  const [createOpen, setCreateOpen] = React.useState<boolean>(false);
  const [newSkill, setNewSkill] = React.useState({
    name: "",
    category: "spec",
    description: "",
    skill_md: "",
  });
  const [testTarget, setTestTarget] = React.useState<Skill | null>(null);
  const [testInput, setTestInput] = React.useState<string>("");
  const [testOutput, setTestOutput] = React.useState<string>("");

  // AC-F1 / AC-F6: GET /api/skills (category & archived passed through).
  const queryKey: QueryKey = React.useMemo(
    () => [...SKILLS_QUERY_KEY, { category, showArchived }],
    [category, showArchived],
  );
  const listQuery = useQuery({
    queryKey,
    queryFn: ({ signal }) =>
      listSkills(
        {
          ...(category !== "all" ? { category } : {}),
          archived: showArchived,
        },
        { signal },
      ),
    retry: false,
    staleTime: 30_000,
  });

  React.useEffect(() => {
    if (listQuery.error) reportSkillsError(listQuery.error);
  }, [listQuery.error]);

  const items: Skill[] = listQuery.data?.items ?? [];
  const filtered = React.useMemo(
    () => filterSkills(items, category, showArchived, search),
    [items, category, showArchived, search],
  );

  const activeCount = items.filter((s) => !isArchived(s)).length;
  const archivedCount = items.filter((s) => isArchived(s)).length;

  // AC-F2: POST /api/skills.
  const createMutation = useMutation({
    mutationFn: () => createSkill(newSkill),
    onSuccess: () => {
      toast.success("スキルを作成しました");
      setCreateOpen(false);
      setNewSkill({ name: "", category: "spec", description: "", skill_md: "" });
      void qc.invalidateQueries({ queryKey: SKILLS_QUERY_KEY });
    },
    onError: reportSkillsError,
  });

  // AC-F3: POST /api/skills/{id}/test.
  const testMutation = useMutation({
    mutationFn: (vars: { id: string | number; test_input: string }) =>
      testSkill(vars.id, { test_input: vars.test_input }),
    onSuccess: (data) => {
      setTestOutput(data.output);
      toast.success(`テスト実行完了 (${data.duration_ms}ms)`);
    },
    onError: reportSkillsError,
  });

  // AC-F4 / AC-F7: POST /api/skills/{id}/archive.
  const archiveMutation = useMutation({
    mutationFn: (id: string | number) => archiveSkill(id),
    onSuccess: () => {
      toast.success("スキルをアーカイブしました");
      void qc.invalidateQueries({ queryKey: SKILLS_QUERY_KEY });
    },
    onError: reportSkillsError,
  });

  const onSubmitNew = React.useCallback(
    (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (createMutation.isPending) return;
      if (!newSkill.name || !newSkill.description || !newSkill.skill_md) {
        toast.error("name / description / skill_md は必須です");
        return;
      }
      createMutation.mutate();
    },
    [createMutation, newSkill],
  );

  const onSubmitTest = React.useCallback(
    (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (!testTarget || testMutation.isPending) return;
      if (!testInput.trim()) {
        toast.error("テスト入力を指定してください");
        return;
      }
      testMutation.mutate({ id: testTarget.id, test_input: testInput });
    },
    [testTarget, testInput, testMutation],
  );

  return (
    <main
      data-screen-id="S-038"
      data-feature-id="F-002,F-003"
      data-task-ids="T-V3-C-14"
      data-entities="E-035"
      data-phase="Phase 1B"
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      <div className="max-w-[1200px] mx-auto px-6 py-6">
        {/* Header */}
        <div className="flex items-end justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Wrench className="w-6 h-6 text-eb-500" aria-hidden />
              スキルマネージャ
            </h1>
            <p className="text-sm text-slate-600 mt-1">
              既存 90+ スキル一覧 / archive 切替 / skill-creator で新規作成
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                const firstActive = filtered.find((s) => !isArchived(s));
                if (!firstActive) {
                  toast.error("テスト対象のスキルがありません");
                  return;
                }
                setTestTarget(firstActive);
                setTestInput("");
                setTestOutput("");
              }}
              className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-3 rounded-md flex items-center gap-2"
            >
              <PlayCircle className="w-4 h-4" aria-hidden />
              テスト実行
            </button>
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="bg-eb-500 hover:bg-eb-600 text-white text-sm h-9 px-4 rounded-md font-semibold flex items-center gap-2"
              data-testid="open-create-skill"
            >
              <Plus className="w-4 h-4" aria-hidden />
              新規スキル作成 (skill-creator)
            </button>
          </div>
        </div>

        {/* Filter bar */}
        <div
          className="bg-white border border-slate-200 rounded-lg p-3 mb-4 flex items-center gap-2"
          data-testid="filter-bar"
        >
          <div className="relative flex-1 max-w-[300px]">
            <Search
              className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-slate-400"
              aria-hidden
            />
            <input
              type="search"
              placeholder="スキル検索..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="border border-slate-200 text-xs h-8 pl-7 pr-2 rounded-md w-full"
              aria-label="スキル検索"
            />
          </div>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="border border-slate-200 text-xs h-8 px-2 rounded-md"
            aria-label="カテゴリ"
          >
            {CATEGORY_FILTERS.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => setShowArchived(false)}
            aria-pressed={!showArchived}
            className={
              !showArchived
                ? "text-xs bg-eb-50 text-eb-700 border border-eb-200 px-3 py-1 rounded-full font-medium"
                : "text-xs hover:bg-slate-100 text-slate-600 px-3 py-1 rounded-full"
            }
          >
            Active {activeCount}
          </button>
          <button
            type="button"
            onClick={() => setShowArchived(true)}
            aria-pressed={showArchived}
            className={
              showArchived
                ? "text-xs bg-eb-50 text-eb-700 border border-eb-200 px-3 py-1 rounded-full font-medium"
                : "text-xs hover:bg-slate-100 text-slate-600 px-3 py-1 rounded-full"
            }
          >
            Archive {archivedCount}
          </button>
          <span className="ml-auto text-xs text-slate-500 mono">
            Total {items.length} · Active {activeCount}
          </span>
        </div>

        {/* Loading / empty / error */}
        {listQuery.isLoading && (
          <p className="text-sm text-slate-500" role="status">
            読み込み中...
          </p>
        )}
        {!listQuery.isLoading && listQuery.isError && (
          <p className="text-sm text-red-600" role="alert">
            一覧の取得に失敗しました
          </p>
        )}

        {/* Skills grid */}
        <div className="grid grid-cols-3 gap-3" data-testid="skills-grid">
          {filtered.map((skill) => (
            <article
              key={String(skill.id)}
              data-testid={`skill-card-${skill.name}`}
              className={
                "bg-white border border-slate-200 rounded-lg p-4 hover:border-eb-500" +
                (isArchived(skill) ? " opacity-60" : "")
              }
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Wrench className="w-4 h-4 text-eb-500" aria-hidden />
                  <span className="text-sm font-bold mono">
                    {skill.display_name ?? skill.name}
                  </span>
                </div>
                <span className="text-[10px] bg-emerald-50 text-emerald-700 px-1.5 py-0.5 rounded-full">
                  {skill.version ?? "v 1.0"}
                </span>
              </div>
              <p className="text-xs text-slate-600 leading-relaxed mb-3">
                {skill.description ?? "(説明なし)"}
              </p>
              <div className="flex items-center gap-2 text-[10px] text-slate-500 mb-3">
                <span className="bg-slate-100 px-1.5 py-0.5 rounded mono">
                  {skill.category}
                </span>
                {typeof skill.usage_count === "number" && (
                  <span>{skill.usage_count} uses</span>
                )}
              </div>
              <div className="flex gap-1.5">
                <button
                  type="button"
                  className="text-xs text-eb-500 hover:text-eb-600 font-semibold flex items-center gap-1"
                  aria-label="編集"
                >
                  <Edit3 className="w-3 h-3" aria-hidden />
                  edit
                </button>
                <button
                  type="button"
                  data-testid={`test-${skill.name}`}
                  className="text-xs text-slate-500 hover:text-slate-900 ml-auto"
                  aria-label={`${skill.name} をテスト実行`}
                  onClick={() => {
                    setTestTarget(skill);
                    setTestInput("");
                    setTestOutput("");
                  }}
                >
                  <PlayCircle className="w-3 h-3" aria-hidden />
                </button>
                {!isArchived(skill) && (
                  <button
                    type="button"
                    data-testid={`archive-${skill.name}`}
                    className="text-xs text-slate-500 hover:text-slate-900"
                    aria-label={`${skill.name} をアーカイブ`}
                    onClick={() => archiveMutation.mutate(skill.id)}
                    disabled={archiveMutation.isPending}
                  >
                    <Archive className="w-3 h-3" aria-hidden />
                  </button>
                )}
              </div>
            </article>
          ))}

          {/* skill-creator CTA */}
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="border-2 border-dashed border-eb-300 hover:border-eb-500 bg-eb-50/30 rounded-lg p-4 text-center hover:bg-eb-50 flex flex-col items-center justify-center min-h-[150px]"
            data-testid="open-create-skill-cta"
          >
            <Sparkles className="w-6 h-6 text-eb-500 mb-2" aria-hidden />
            <span className="text-sm font-bold text-eb-700">skill-creator</span>
            <span className="text-xs text-slate-600 mt-1">
              対話で新規スキル作成
            </span>
          </button>
        </div>
      </div>

      {/* New skill modal */}
      {createOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-skill-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) setCreateOpen(false);
          }}
        >
          <form
            onSubmit={onSubmitNew}
            className="bg-white rounded-xl p-6 w-full max-w-2xl"
            data-testid="create-skill-form"
          >
            <div className="flex items-center justify-between mb-4">
              <h2 id="create-skill-title" className="font-bold text-base">
                新しいスキルを作成
              </h2>
              <button
                type="button"
                aria-label="閉じる"
                className="text-slate-500"
                onClick={() => setCreateOpen(false)}
              >
                <X className="w-4 h-4" aria-hidden />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-3">
              <div>
                <label className="block text-[10px] font-semibold mb-1 text-slate-500">
                  スキル名 (英数字・ハイフン)
                </label>
                <input
                  value={newSkill.name}
                  onChange={(e) =>
                    setNewSkill((s) => ({ ...s, name: e.target.value }))
                  }
                  placeholder="例: my-skill"
                  className="w-full px-2 py-1.5 rounded text-xs border border-slate-200"
                  required
                />
              </div>
              <div>
                <label className="block text-[10px] font-semibold mb-1 text-slate-500">
                  カテゴリ
                </label>
                <select
                  value={newSkill.category}
                  onChange={(e) =>
                    setNewSkill((s) => ({ ...s, category: e.target.value }))
                  }
                  className="w-full px-2 py-1.5 rounded text-xs border border-slate-200"
                >
                  {CATEGORY_FILTERS.filter((c) => c.id !== "all").map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-span-2">
                <label className="block text-[10px] font-semibold mb-1 text-slate-500">
                  説明
                </label>
                <input
                  value={newSkill.description}
                  onChange={(e) =>
                    setNewSkill((s) => ({ ...s, description: e.target.value }))
                  }
                  className="w-full px-2 py-1.5 rounded text-xs border border-slate-200"
                  required
                />
              </div>
            </div>

            <div className="mb-4">
              <label className="block text-[10px] font-semibold mb-1 text-slate-500">
                SKILL.md 本文
              </label>
              <textarea
                value={newSkill.skill_md}
                onChange={(e) =>
                  setNewSkill((s) => ({ ...s, skill_md: e.target.value }))
                }
                rows={8}
                placeholder={"# スキル名\n\n## ロール定義\n\nあなたは..."}
                className="w-full px-3 py-2 rounded text-xs border border-slate-200"
                required
              />
            </div>

            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => setCreateOpen(false)}
                className="px-4 py-2 rounded text-xs font-semibold bg-slate-100 text-slate-700"
              >
                キャンセル
              </button>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="px-4 py-2 rounded text-xs font-semibold text-white bg-eb-500 hover:bg-eb-600 disabled:opacity-50"
                data-testid="submit-create-skill"
              >
                {createMutation.isPending ? "作成中..." : "作成"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Test runner modal */}
      {testTarget && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="test-skill-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) setTestTarget(null);
          }}
        >
          <form
            onSubmit={onSubmitTest}
            className="bg-white rounded-xl p-6 w-full max-w-2xl"
            data-testid="test-skill-form"
          >
            <div className="flex items-center justify-between mb-4">
              <h2 id="test-skill-title" className="font-bold text-base">
                スキルテスト実行: {testTarget.display_name ?? testTarget.name}
              </h2>
              <button
                type="button"
                aria-label="閉じる"
                className="text-slate-500"
                onClick={() => setTestTarget(null)}
              >
                <X className="w-4 h-4" aria-hidden />
              </button>
            </div>

            <label className="block text-[10px] font-semibold mb-1 text-slate-500">
              テスト入力
            </label>
            <input
              value={testInput}
              onChange={(e) => setTestInput(e.target.value)}
              placeholder="スキルへの入力テキスト..."
              className="w-full px-3 py-2 rounded text-xs border border-slate-200 mb-3"
              autoFocus
            />

            {testOutput && (
              <pre
                data-testid="test-output"
                className="text-[11px] p-3 rounded overflow-auto max-h-40 whitespace-pre-wrap bg-slate-50 text-slate-700 mb-3"
              >
                {testOutput}
              </pre>
            )}

            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => setTestTarget(null)}
                className="px-4 py-2 rounded text-xs font-semibold bg-slate-100 text-slate-700"
              >
                閉じる
              </button>
              <button
                type="submit"
                disabled={testMutation.isPending || !testInput.trim()}
                className="px-4 py-2 rounded text-xs font-semibold text-white bg-eb-500 hover:bg-eb-600 disabled:opacity-50"
                data-testid="submit-test-skill"
              >
                {testMutation.isPending ? "実行中..." : "実行"}
              </button>
            </div>
          </form>
        </div>
      )}
    </main>
  );
}
