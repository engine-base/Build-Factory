"use client";

import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import { memo } from "react";
import remarkGfm from "remark-gfm";

export const MarkdownText = memo(function MarkdownText() {
  return (
    <MarkdownTextPrimitive
      remarkPlugins={[remarkGfm]}
      className="aui-md prose prose-sm max-w-none dark:prose-invert leading-relaxed"
    />
  );
});
