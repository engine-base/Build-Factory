"use client";

import { useState } from "react";
import { ChevronRightIcon, ChevronDownIcon } from "lucide-react";

interface Node {
  id: string;
  text: string;
  children?: Node[];
}

interface Props {
  data: Record<string, unknown>;
  onChange?: (data: Record<string, unknown>) => void;
}

export function MindmapView({ data, onChange }: Props) {
  const root = (data.root as Node) || (Array.isArray(data.nodes) ? (data.nodes as Node[])[0] : null);

  if (!root) {
    return <div className="text-sm text-gray-500">マインドマップが空です</div>;
  }

  const update = (newRoot: Node) => onChange?.({ ...data, root: newRoot });

  return (
    <div className="overflow-x-auto">
      <NodeView
        node={root}
        depth={0}
        onUpdate={update}
        path={[]}
        rootRef={root}
      />
    </div>
  );
}

function NodeView({
  node, depth, onUpdate, path, rootRef,
}: {
  node: Node;
  depth: number;
  onUpdate: (newRoot: Node) => void;
  path: number[];
  rootRef: Node;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const hasChildren = (node.children?.length || 0) > 0;
  const colorByDepth = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899"];
  const color = colorByDepth[depth % colorByDepth.length];

  const editText = (text: string) => {
    const next = JSON.parse(JSON.stringify(rootRef)) as Node;
    let cur: Node = next;
    for (const i of path) cur = cur.children![i];
    cur.text = text;
    onUpdate(next);
  };

  const addChild = () => {
    const text = prompt("新しいノードのテキスト");
    if (!text) return;
    const next = JSON.parse(JSON.stringify(rootRef)) as Node;
    let cur: Node = next;
    for (const i of path) cur = cur.children![i];
    cur.children = [...(cur.children || []), { id: `n-${Date.now()}`, text }];
    onUpdate(next);
  };

  const removeMe = () => {
    if (path.length === 0) return; // root は消さない
    const next = JSON.parse(JSON.stringify(rootRef)) as Node;
    let parent: Node = next;
    for (let i = 0; i < path.length - 1; i++) parent = parent.children![path[i]];
    parent.children!.splice(path[path.length - 1], 1);
    onUpdate(next);
  };

  return (
    <div className="ml-4">
      <div className="group flex items-center gap-1 py-0.5">
        {hasChildren && (
          <button
            onClick={() => setCollapsed((v) => !v)}
            className="text-xs text-gray-500 w-4"
            aria-label={collapsed ? "展開" : "折りたたむ"}
          >
            {collapsed ? <ChevronRightIcon className="w-3 h-3" /> : <ChevronDownIcon className="w-3 h-3" />}
          </button>
        )}
        {!hasChildren && <span className="w-4" />}
        <input
          value={node.text}
          onChange={(e) => editText(e.target.value)}
          className="rounded px-2 py-0.5 text-sm font-medium outline-none focus:bg-yellow-50"
          style={{ borderLeft: `3px solid ${color}` }}
        />
        <button
          onClick={addChild}
          className="invisible rounded px-1.5 text-xs text-gray-500 group-hover:visible hover:bg-gray-100"
          title="子追加"
        >+</button>
        {path.length > 0 && (
          <button
            onClick={removeMe}
            className="invisible rounded px-1.5 text-xs text-red-500 group-hover:visible hover:bg-red-50"
            title="削除"
          >×</button>
        )}
      </div>
      {!collapsed && hasChildren && (
        <div className="border-l border-dashed border-gray-300">
          {node.children!.map((c, i) => (
            <NodeView
              key={c.id || i}
              node={c}
              depth={depth + 1}
              onUpdate={onUpdate}
              path={[...path, i]}
              rootRef={rootRef}
            />
          ))}
        </div>
      )}
    </div>
  );
}
