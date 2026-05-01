// TODO: Build-Factory integration - replace with @assistant-ui equivalents.
// Minimal stubs so canvas frame view compiles.
import type { ReactNode, IframeHTMLAttributes, HTMLAttributes } from 'react';

export const WebPreview = ({ children, ...rest }: HTMLAttributes<HTMLDivElement> & { children?: ReactNode }) => (
  <div {...rest}>{children}</div>
);

export const WebPreviewBody = ({ children, ...rest }: IframeHTMLAttributes<HTMLIFrameElement> & { children?: ReactNode }) => (
  <iframe {...rest}>{children}</iframe>
);
