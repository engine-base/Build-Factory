// TODO: Build-Factory integration - replace with shadcn dropdown-menu when added.
// Minimal passthrough stubs so canvas top-bar compiles.
import type { ReactNode } from 'react';

type AnyProps = Record<string, unknown> & { children?: ReactNode };

const passthrough = ({ children }: AnyProps) => <>{children}</>;

export const DropdownMenu = passthrough;
export const DropdownMenuTrigger = passthrough;
export const DropdownMenuContent = passthrough;
export const DropdownMenuItem = passthrough;
export const DropdownMenuLabel = passthrough;
export const DropdownMenuSeparator = passthrough;
export const DropdownMenuGroup = passthrough;
export const DropdownMenuPortal = passthrough;
export const DropdownMenuSub = passthrough;
export const DropdownMenuSubTrigger = passthrough;
export const DropdownMenuSubContent = passthrough;
export const DropdownMenuRadioGroup = passthrough;
export const DropdownMenuRadioItem = passthrough;
export const DropdownMenuCheckboxItem = passthrough;
export const DropdownMenuShortcut = passthrough;
