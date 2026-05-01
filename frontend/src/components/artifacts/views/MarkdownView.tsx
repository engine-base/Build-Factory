"use client";

interface Props {
  data: Record<string, unknown>;
}

export function MarkdownView({ data }: Props) {
  const text = typeof data.text === "string" ? data.text : JSON.stringify(data, null, 2);
  return (
    <div className="prose prose-sm max-w-none whitespace-pre-wrap leading-relaxed">
      {text}
    </div>
  );
}
