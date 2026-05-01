// TODO: Build-Factory integration - replace with lucide-react icons
// Proxy: any Icons.X access returns a passthrough lucide-style icon component.
import * as LucideIcons from 'lucide-react';
import type { ComponentType, SVGProps } from 'react';

type IconComponent = ComponentType<SVGProps<SVGSVGElement> & { className?: string }>;

const FallbackIcon: IconComponent = (props) => {
  // eslint-disable-next-line jsx-a11y/alt-text
  return <span {...(props as object)} />;
};

// Map of common Onlook icon names to lucide names where straightforward.
const aliasMap: Record<string, keyof typeof LucideIcons> = {
  ZoomIn: 'ZoomIn',
  ZoomOut: 'ZoomOut',
  Reset: 'RotateCcw',
  Plus: 'Plus',
  Minus: 'Minus',
  ChevronDown: 'ChevronDown',
  ChevronRight: 'ChevronRight',
  ChevronLeft: 'ChevronLeft',
  ChevronUp: 'ChevronUp',
  Cross2: 'X',
  Check: 'Check',
  Pencil: 'Pencil',
  Trash: 'Trash',
  Copy: 'Copy',
  Code: 'Code',
  ChatBubble: 'MessageSquare',
  Frame: 'Square',
  CrumpledPaper: 'FileX',
  Globe: 'Globe',
  ExternalLink: 'ExternalLink',
};

export const Icons = new Proxy({} as Record<string, IconComponent>, {
  get(_target, prop: string) {
    const aliased = aliasMap[prop];
    if (aliased && (LucideIcons as Record<string, unknown>)[aliased]) {
      return (LucideIcons as unknown as Record<string, IconComponent>)[aliased];
    }
    if ((LucideIcons as Record<string, unknown>)[prop]) {
      return (LucideIcons as unknown as Record<string, IconComponent>)[prop];
    }
    return FallbackIcon;
  },
});
