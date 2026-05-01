// TODO: Build-Factory integration - port Onlook hover tooltip in a later phase.
import type { ReactNode } from 'react';

type Props = {
    children: ReactNode;
    content?: ReactNode;
    side?: string;
    sideOffset?: number;
    disabled?: boolean;
    className?: string;
    hideArrow?: boolean;
};

export const HoverOnlyTooltip = ({ children }: Props) => <>{children}</>;
