"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, X, UserPlus, UserMinus, Edit2, Users, AlertTriangle, BellIcon, BotIcon, UserIcon, BookOpenIcon, ChevronRightIcon } from "lucide-react";
import { ChatPanel } from "@/components/chat/ChatPanel";

const API = "http://localhost:8001";

type Employee = {
  id: number;
  employee_name: string;
  display_name: string;
  category: string;
  role_level: "secretary" | "leader" | "member";
  parent_id: number | null;
  persona_name: string | null;
  personality: string | null;
  tone_style: string | null;
  catchphrase: string | null;
  avatar_emoji: string | null;
  specialty: string | null;
  handles: string | null;
  primary_skill: string;
  retired_at: string | null;
};

type Orgchart = {
  secretary: (Employee & { knowledge_count: number; children: Employee[] }) | null;
  leaders: Array<Employee & { knowledge_count: number; dept_knowledge_count: number; children: Employee[] }>;
  common_knowledge_count: number;
  warnings: Array<{ employee_id: number; persona_name: string; count: number; message: string }>;
  totals: { headcount: number; leaders: number; members: number };
};

const ROLE_LABEL: Record<string, string> = {
  secretary: "秘書",
  leader: "リーダー",
  member: "メンバー",
};

const colorOf = (cat: string) => {
  const m: Record<string, string> = {
    "総括": "#7E3AED", "01_営業": "#0369A1", "02_経理": "#16A34A",
    "03_マーケティング": "#D97706", "04_CS": "#DC2626"
  };
  return m[cat] || "#6B7280";
};

type SecretaryFlow =
  | { kind: "hire" }
  | { kind: "edit"; emp: Employee }
  | { kind: "retire"; emp: Employee };

export default function AIEmployeesPage() {
  const qc = useQueryClient();
  const [chatEmployee, setChatEmployee] = useState<Employee | null>(null);
  const [secretaryFlow, setSecretaryFlow] = useState<SecretaryFlow | null>(null);

  const { data: org } = useQuery<Orgchart>({
    queryKey: ["staff-orgchart"],
    queryFn: () => fetch(`${API}/api/staff/orgchart`).then(r => r.json()),
    refetchInterval: 15000,
  });

  const refresh = () => qc.invalidateQueries({ queryKey: ["staff-orgchart"] });

  if (!org) return <div className="p-8">読み込み中...</div>;

  return (
    <div className="flex h-screen overflow-hidden">
      <div className="flex-1 overflow-y-auto p-8">
        <div className="flex items-start justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>AI社員（組織図）</h1>
            <p className="text-sm mt-1 inline-flex items-center gap-1 flex-wrap" style={{ color: "var(--eb-neutral)" }}>
              秘書<ChevronRightIcon className="w-3 h-3" aria-hidden />リーダー<ChevronRightIcon className="w-3 h-3" aria-hidden />メンバー の階層構造。クリックで個性確認・チャット・編集・退職処理。
            </p>
          </div>
          <button onClick={() => { setSecretaryFlow({ kind: "hire" }); setChatEmployee(null); }}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm text-white font-semibold"
            style={{ background: "var(--eb-primary)" }}>
            <UserPlus className="w-4 h-4" />採用（秘書とチャットで進める）
          </button>
        </div>

        {/* 統計 */}
        <div className="grid grid-cols-4 gap-3 mb-6 text-xs">
          <div className="rounded-lg p-3 bg-white border" style={{ borderColor: "var(--eb-border)" }}>
            <div className="font-bold opacity-60">在籍</div>
            <div className="text-xl font-bold mt-1">{org.totals.headcount}名</div>
          </div>
          <div className="rounded-lg p-3 bg-white border" style={{ borderColor: "var(--eb-border)" }}>
            <div className="font-bold opacity-60">リーダー</div>
            <div className="text-xl font-bold mt-1">{org.totals.leaders}名</div>
          </div>
          <div className="rounded-lg p-3 bg-white border" style={{ borderColor: "var(--eb-border)" }}>
            <div className="font-bold opacity-60">メンバー</div>
            <div className="text-xl font-bold mt-1">{org.totals.members}名</div>
          </div>
          <div className="rounded-lg p-3 bg-white border" style={{ borderColor: "var(--eb-border)" }}>
            <div className="font-bold opacity-60">共通ナレッジ</div>
            <div className="text-xl font-bold mt-1">{org.common_knowledge_count}件</div>
          </div>
        </div>

        {/* 警告 */}
        {org.warnings.length > 0 && (
          <div className="mb-6 rounded-lg p-3 flex items-start gap-2"
            style={{ background: "#FEF3C7", border: "1px solid #FCD34D" }}>
            <AlertTriangle className="w-4 h-4 mt-0.5" style={{ color: "#92400E" }} />
            <div className="text-xs" style={{ color: "#92400E" }}>
              {org.warnings.map(w => <div key={w.employee_id} className="inline-flex items-center gap-1"><BellIcon className="w-3 h-3" aria-label="bell" /> {w.message}</div>)}
            </div>
          </div>
        )}

        {/* 秘書カード */}
        {org.secretary && (
          <EmployeeCard
            emp={org.secretary as Employee}
            knowledgeCount={(org.secretary as any).knowledge_count}
            onChat={() => { setChatEmployee(org.secretary as Employee); setSecretaryFlow(null); }}
            onEdit={() => { setSecretaryFlow({ kind: "edit", emp: org.secretary as Employee }); setChatEmployee(null); }}
            onRetire={null}
          />
        )}

        {/* リーダーごとのカラム */}
        <div className="mt-6 space-y-6">
          {org.leaders.map(leader => (
            <div key={leader.id} className="rounded-xl p-4 bg-white" style={{ border: "1px solid var(--eb-border)" }}>
              <EmployeeCard
                emp={leader}
                knowledgeCount={leader.dept_knowledge_count}
                isLeader
                onChat={() => { setChatEmployee(leader); setSecretaryFlow(null); }}
                onEdit={() => { setSecretaryFlow({ kind: "edit", emp: leader }); setChatEmployee(null); }}
                onRetire={() => { setSecretaryFlow({ kind: "retire", emp: leader }); setChatEmployee(null); }}
              />
              {leader.children?.length > 0 && (
                <div className="ml-12 mt-4 space-y-2 border-l-2 pl-4"
                  style={{ borderColor: colorOf(leader.category) + "44" }}>
                  <p className="text-[11px] font-bold uppercase tracking-wide opacity-60 flex items-center gap-1">
                    <Users className="w-3 h-3" />
                    メンバー（{leader.children.length}名）
                  </p>
                  {leader.children.map(member => (
                    <EmployeeCard
                      key={member.id}
                      emp={member}
                      knowledgeCount={(member as any).knowledge_count || 0}
                      compact
                      onChat={() => { setChatEmployee(member); setSecretaryFlow(null); }}
                      onEdit={() => { setSecretaryFlow({ kind: "edit", emp: member }); setChatEmployee(null); }}
                      onRetire={() => { setSecretaryFlow({ kind: "retire", emp: member }); setChatEmployee(null); }}
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* チャット右パネル */}
      {chatEmployee && (
        <div className="w-[640px] shrink-0 flex flex-col"
          style={{ borderLeft: "1px solid var(--eb-border)", boxShadow: "-4px 0 12px rgba(0,0,0,0.05)" }}>
          <ChatPanel
            mode="employee"
            employeeId={chatEmployee.id}
            employeeName={chatEmployee.persona_name || chatEmployee.display_name}
            employeeColor={colorOf(chatEmployee.category)}
            avatarEmoji={chatEmployee.avatar_emoji || undefined}
            showThreadList={true}
            headerExtra={
              <div className="px-3 py-2.5 bg-white flex items-center justify-between"
                style={{ borderBottom: "1px solid var(--eb-border)" }}>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center text-lg"
                    style={{ background: colorOf(chatEmployee.category) + "22" }}>
                    {chatEmployee.avatar_emoji || <BotIcon className="w-4 h-4" aria-label="bot" />}
                  </div>
                  <div>
                    <p className="text-xs font-bold" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
                      {chatEmployee.persona_name || chatEmployee.display_name}
                    </p>
                    <p className="text-[10px]" style={{ color: "var(--eb-neutral)" }}>
                      {ROLE_LABEL[chatEmployee.role_level]}・{chatEmployee.specialty || chatEmployee.category}
                    </p>
                  </div>
                </div>
                <button onClick={() => setChatEmployee(null)} className="p-1 rounded hover:bg-gray-100">
                  <X className="w-4 h-4" style={{ color: "var(--eb-neutral)" }} />
                </button>
              </div>
            }
          />
        </div>
      )}

      {/* 人事AI（高橋結衣）とのチャットで採用・編集・退職を進める */}
      {secretaryFlow && (() => {
        // 人事リーダーを org から見つける
        const hr = org.leaders.find(l => l.category === "05_人事");
        if (!hr) {
          return (
            <div className="w-[480px] p-6 bg-white border-l">
              <p className="text-sm font-bold mb-2">人事AIが見つかりません</p>
              <p className="text-xs opacity-70">DB に hr_05 (高橋 結衣) が登録されているか確認してください。</p>
              <button onClick={() => setSecretaryFlow(null)} className="mt-3 px-3 py-1 rounded border text-xs">閉じる</button>
            </div>
          );
        }
        return (
          <div className="w-[720px] shrink-0 flex flex-col"
            style={{ borderLeft: "1px solid var(--eb-border)", boxShadow: "-4px 0 12px rgba(0,0,0,0.05)" }}>
            <ChatPanel
              mode="employee"
              employeeId={hr.id}
              employeeName={hr.persona_name || "人事AI"}
              employeeColor="#0F766E"
              avatarEmoji={hr.avatar_emoji || undefined}
              defaultProvider="openai"
              defaultModel="gpt-4o-mini"
              showThreadList={false}
              autoSendOnce={buildHRPrompt(secretaryFlow)}
              headerExtra={
                <div className="px-3 py-2.5 bg-white flex items-center justify-between"
                  style={{ borderBottom: "1px solid var(--eb-border)" }}>
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-full flex items-center justify-center text-lg"
                      style={{ background: "#0F766E22" }}>{hr.avatar_emoji || <UserIcon className="w-4 h-4" aria-label="user" />}</div>
                    <div>
                      <p className="text-xs font-bold" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
                        人事 {hr.persona_name}
                      </p>
                      <p className="text-[10px]" style={{ color: "var(--eb-neutral)" }}>
                        {flowLabel(secretaryFlow)}
                      </p>
                    </div>
                  </div>
                  <button onClick={() => { setSecretaryFlow(null); refresh(); }} className="p-1 rounded hover:bg-gray-100">
                    <X className="w-4 h-4" style={{ color: "var(--eb-neutral)" }} />
                  </button>
                </div>
              }
            />
          </div>
        );
      })()}
    </div>
  );
}

// ── 人事AIチャット起動用プロンプト構築 ──────────────
function buildHRPrompt(flow: SecretaryFlow): string {
  if (flow.kind === "hire") {
    return (
      "新しいAI社員を採用したいです。staff-management スキルの HIRE フローで進めてください。\n"
      + "リーダーかメンバーかから一緒に決めて、個性・担当領域・ナレッジ引継までヒアリングしてください。\n"
      + "最終的に確認カードを出して私の承認を取ってから staff_hire を実行してください。"
    );
  }
  if (flow.kind === "edit") {
    return (
      `${flow.emp.persona_name}（ID: ${flow.emp.id}, ${flow.emp.role_level}）の編集をしたいです。\n`
      + "staff-management スキルの EDIT フローで、何を変えたいか聞いてから提案 → 確認 → staff_update で実行してください。\n"
      + `現状: 名前=${flow.emp.persona_name} / 性格=${flow.emp.personality} / 口調=${flow.emp.tone_style} / 口癖=${flow.emp.catchphrase}`
    );
  }
  // retire
  return (
    `${flow.emp.persona_name}（ID: ${flow.emp.id}）を退職処理したいです。\n`
    + "staff-management スキルの RETIRE フローで、ナレッジ引継先（A:リーダーへ集約 / B:共通昇格 / C:細分配）を提案してから、\n"
    + "私の承認を取って staff_retire を実行してください。"
  );
}

function flowLabel(flow: SecretaryFlow): string {
  if (flow.kind === "hire") return "採用フロー";
  if (flow.kind === "edit") return `編集フロー: ${flow.emp.persona_name}`;
  return `退職フロー: ${flow.emp.persona_name}`;
}

// ── 社員カード ────────────────────────────────
function EmployeeCard({ emp, knowledgeCount, isLeader, compact, onChat, onEdit, onRetire }: {
  emp: Employee;
  knowledgeCount: number;
  isLeader?: boolean;
  compact?: boolean;
  onChat: () => void;
  onEdit: () => void;
  onRetire: (() => void) | null;
}) {
  const color = colorOf(emp.category);
  const role = ROLE_LABEL[emp.role_level] || "メンバー";

  return (
    <div className="flex items-start gap-3" style={{ padding: compact ? "8px 0" : "0" }}>
      <div className={compact ? "w-9 h-9 text-xl" : "w-12 h-12 text-2xl"}
        style={{
          background: color + "22", color, borderRadius: 8,
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0,
        }}>
        {emp.avatar_emoji || <BotIcon className={compact ? "w-4 h-4" : "w-5 h-5"} aria-label="bot" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-bold" style={{
            fontFamily: "var(--font-noto-sans-jp)",
            fontSize: compact ? 13 : 16,
          }}>
            {emp.persona_name || emp.display_name}
          </span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold"
            style={{ background: color + "22", color }}>
            {role}
          </span>
          {emp.specialty && (
            <span className="text-[11px] opacity-70">／ {emp.specialty}</span>
          )}
          <span className="text-[11px] opacity-60 inline-flex items-center gap-1"><BookOpenIcon className="w-3 h-3" aria-label="knowledge" /> {knowledgeCount}件</span>
        </div>
        {!compact && emp.handles && (
          <p className="text-xs mt-1" style={{ color: "var(--eb-neutral)" }}>{emp.handles}</p>
        )}
        {!compact && (emp.personality || emp.tone_style) && (
          <div className="text-[11px] mt-1.5 flex gap-3" style={{ color: "var(--eb-neutral)" }}>
            {emp.personality && <span>性格: {emp.personality}</span>}
            {emp.catchphrase && <span>口癖: 「{emp.catchphrase}」</span>}
          </div>
        )}
      </div>
      <div className="flex items-center gap-1.5 flex-shrink-0">
        <button onClick={onChat} title="チャット"
          className="flex items-center gap-1 px-2.5 py-1.5 rounded text-xs font-semibold text-white"
          style={{ background: color }}>
          <MessageSquare className="w-3.5 h-3.5" />チャット
        </button>
        <button onClick={onEdit} title="編集"
          className="p-1.5 rounded hover:bg-gray-100">
          <Edit2 className="w-3.5 h-3.5" style={{ color: "var(--eb-neutral)" }} />
        </button>
        {onRetire && (
          <button onClick={onRetire} title="退職処理"
            className="p-1.5 rounded hover:bg-red-50">
            <UserMinus className="w-3.5 h-3.5" style={{ color: "#dc2626" }} />
          </button>
        )}
      </div>
    </div>
  );
}


